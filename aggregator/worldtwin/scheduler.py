"""Background scheduler that runs each registered source on its refresh interval."""
from __future__ import annotations

import asyncio
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from . import cache, registry
from .models import Envelope


# Cap concurrent fetch pipelines. At boot all ~90 workers fired inside their
# initial_delay_s window; the combined fetch+serialize spikes blew past the
# container's 3G limit and the mem-watchdog killed it every ~6 minutes
# (measured 2026-06-11). Eight concurrent pipelines keeps boot RAM flat.
_FETCH_SEM = asyncio.Semaphore(8)


async def _run_one(reg: registry.RegisteredLayer, client: httpx.AsyncClient) -> None:
    """Fetch a single layer once, normalize, and write cache."""
    meta = reg.meta
    t0 = time.time()
    try:
      async with _FETCH_SEM:
        result = await reg.fetch(client)
        # Convention: fetch returns either
        #   - None → skip (keep previous cache)
        #   - data → use as both v1 normalized data AND legacy (same shape)
        #   - (v1_data, legacy_data) → use each independently
        if result is None:
            return
        if isinstance(result, tuple) and len(result) == 2:
            v1_data, legacy_data = result
        else:
            v1_data = result
            legacy_data = result
        # Bulk archive keys (_history_only_*) are meant ONLY for
        # history.snapshot via write_legacy. Without this strip, the 139MB
        # ucdp_ged archive was serialized into BOTH /cache/v1 files too.
        if isinstance(v1_data, dict):
            v1_data = {k: v for k, v in v1_data.items()
                       if not k.startswith("_history_only_")}
        now = datetime.now(timezone.utc)
        fetched_at = now.isoformat()
        expires_at = (now + timedelta(seconds=meta.refresh_s)).isoformat()
        env = Envelope.build(meta, v1_data, fetched_at, expires_at)
        # Empty-clobber guard: a degraded fetch that returns an empty
        # container must not overwrite a good cache (fires.json was
        # literally `[]` in production while FIRMS was failing).
        if (env.count or 0) == 0 and not getattr(meta, "allow_empty", False):
            prev = cache.legacy_path(meta.id)
            try:
                had_data = prev.exists() and prev.stat().st_size > 64
            except OSError:
                had_data = False
            if had_data:
                cache.mark_error(meta.id, "fetch returned empty — kept previous cache",
                                 time.time() - t0)
                return
        env_dict = env.to_dict()
        # Run cache + history writes off the event loop. history.snapshot()
        # holds the SQLite GIL for tens of milliseconds per call; with 90
        # workers that is enough to starve uvicorn's accept loop and make
        # every API request time out under Caddy's 30s reverse-proxy budget.
        await asyncio.to_thread(cache.write_envelope, meta.id, env_dict)
        await asyncio.to_thread(cache.write_legacy, meta.id, legacy_data)
        elapsed = time.time() - t0
        cache.mark_ok(meta.id, env.count, elapsed)
    except Exception as e:
        elapsed = time.time() - t0
        err = f"{type(e).__name__}: {e}"
        cache.mark_error(meta.id, err, elapsed)
        print(f"[{meta.id}] fetch failed: {err}")
        # Don't flood logs with full tracebacks for common network errors
        if not isinstance(e, (httpx.HTTPStatusError, httpx.ReadTimeout, httpx.ConnectError)):
            traceback.print_exc()


async def _worker_loop(reg: registry.RegisteredLayer, client: httpx.AsyncClient) -> None:
    """Infinite loop for one layer — honors initial_delay_s and refresh_s.

    RESTART AMNESIA FIX: if the on-disk cache is still fresh, sleep out the
    remainder of refresh_s instead of refetching. The container restarts
    often (mem-watchdog); refetching all ~90 sources on every boot burned
    upstream quotas (Open-Meteo, Space-Track suspension) and sustained the
    OOM-restart loop by re-running every heavy pipeline at once.
    """
    meta = reg.meta
    first_sleep = float(meta.initial_delay_s or 1)
    try:
        mtime = cache.legacy_path(meta.id).stat().st_mtime
        age = time.time() - mtime
        if age < meta.refresh_s:
            first_sleep = max(first_sleep, meta.refresh_s - age)
    except OSError:
        pass  # no cache yet — fetch after the normal stagger delay
    await asyncio.sleep(first_sleep)
    while True:
        t0 = time.time()
        await _run_one(reg, client)
        elapsed = time.time() - t0
        sleep_for = max(1.0, reg.meta.refresh_s - elapsed)
        await asyncio.sleep(sleep_for)


def start_all(client: httpx.AsyncClient) -> list[asyncio.Task]:
    """Kick off a background task per registered layer. Returns the task list."""
    tasks: list[asyncio.Task] = []
    for reg in registry.all_layers():
        if not reg.meta.enabled:
            continue
        tasks.append(asyncio.create_task(_worker_loop(reg, client), name=f"worker:{reg.meta.id}"))
    print(f"[scheduler] started {len(tasks)} workers")
    return tasks
