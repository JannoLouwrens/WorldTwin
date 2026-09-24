"""Background scheduler that runs each registered source on its refresh interval."""
from __future__ import annotations

import asyncio
import re
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from . import cache, registry, sanity
from .models import Envelope


# The old single _FETCH_SEM(8) throttled network and CPU together, so a slow
# upstream serialized everything behind it AND `elapsed` measured queue time
# (quakes reported 163 s for a 10 KB payload). Split (MASTER_PLAN §5):
#   NET_SEM  — held ONLY around the network fetch. I/O-bound; 16 in flight.
#   CPU_SEM  — the serialize/sanity/write tail. Two pipelines keeps boot RAM
#              flat inside the container's 3G limit (the original motivation
#              for the semaphore, measured 2026-06-11).
NET_SEM = asyncio.Semaphore(16)
CPU_SEM = asyncio.Semaphore(2)


async def _run_one(reg: registry.RegisteredLayer, client: httpx.AsyncClient) -> None:
    """Fetch a single layer once, normalize, and write cache."""
    meta = reg.meta
    t0 = time.time()
    try:
        async with NET_SEM:
            # t0 INSIDE the acquire: elapsed measures work, not queue time.
            t0 = time.time()
            result = await reg.fetch(client)
        # Convention: fetch returns either
        #   - None → keep previous cache (now marked, never silent: this was
        #     the path 72 of 92 plugins used to fail INVISIBLY — no status
        #     mark meant /api/health kept reporting the layer green forever)
        #   - data → use as both v1 normalized data AND legacy (same shape)
        #   - (v1_data, legacy_data) → use each independently
        if result is None:
            cache.mark_attempt_failed(
                meta.id, "fetch returned None — kept previous cache",
                time.time() - t0)
            return
        async with CPU_SEM:
            if isinstance(result, tuple) and len(result) == 2:
                v1_data, legacy_data = result
            else:
                v1_data = result
                legacy_data = result
            # sanity.sweep_and_tag runs ONCE here and feeds BOTH writers
            # (REVIVAL_V1 §6.5). It used to run only inside write_legacy, so
            # all 92 v1 envelopes shipped un-swept values to the new client.
            # In a thread: the copy-on-write walk over a bulk payload is CPU
            # work that must not stall the event loop.
            try:
                legacy_data = await asyncio.to_thread(
                    sanity.sweep_and_tag, legacy_data)
            except Exception as e:
                print(f"[{meta.id}] sanity sweep failed: {e}")
            if isinstance(result, tuple) and result[0] is not result[1]:
                try:
                    v1_data = await asyncio.to_thread(
                        sanity.sweep_and_tag, v1_data)
                except Exception as e:
                    print(f"[{meta.id}] sanity sweep failed (v1): {e}")
            else:
                v1_data = legacy_data  # the common single-return case
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
                    cache.mark_attempt_failed(
                        meta.id, "fetch returned empty — kept previous cache",
                        time.time() - t0)
                    return
            env_dict = env.to_dict()
            # Run cache + history writes off the event loop. history.snapshot()
            # holds the SQLite GIL for tens of milliseconds per call; enough
            # workers can starve uvicorn's accept loop and make every API
            # request time out under Caddy's 30s reverse-proxy budget.
            # Passing `meta` puts the manifest update + render slice inside
            # write_envelope's commit path (cache.py owns those call sites).
            await asyncio.to_thread(cache.write_envelope, meta.id, env_dict, meta)
            await asyncio.to_thread(cache.write_legacy, meta.id, legacy_data)
            elapsed = time.time() - t0
            cache.mark_ok(meta.id, env.count, elapsed)
            # Daily counts ledger — success only; a failed day gets no entry.
            await asyncio.to_thread(cache.update_counts, meta.id, env.count)
    except Exception as e:
        elapsed = time.time() - t0
        err = f"{type(e).__name__}: {e}"
        cache.mark_error(meta.id, err, elapsed)
        print(f"[{meta.id}] fetch failed: {err}")
        # Don't flood logs with full tracebacks for common network errors
        if not isinstance(e, (httpx.HTTPStatusError, httpx.ReadTimeout, httpx.ConnectError)):
            traceback.print_exc()


def _seed_status_from_disk(meta: Any, mtime: float) -> None:
    """Seed in-memory status from the on-disk cache so /api/health and
    /v1/health list a layer even when the restart-amnesia gate skips its
    first fetch. Without this, every restart blinded monitoring to ~50
    slow-refresh layers until their next real fetch (verified 2026-06-12:
    /api/health listed 40 of ~90 layers while Caddy was serving all their
    caches fine). cache.load_status() may have already restored a persisted
    status; the envelope on disk is fresher ground truth for this layer
    (the gate only runs when the cache file is within refresh_s)."""
    count: int | None = None
    fetched_at: str | None = None
    try:
        # Envelope JSON is compact and both "fetched_at" and "count" precede
        # "data" (models.Envelope.to_dict keeps data last), so the values sit
        # in the first few hundred bytes — no need to parse a potentially
        # huge payload at boot.
        with cache.envelope_path(meta.id).open("r", encoding="utf-8") as f:
            head = f.read(4096)
        m = re.search(r'"count":(\d+)', head)
        if m:
            count = int(m.group(1))
        m = re.search(r'"fetched_at":"([^"]+)"', head)
        if m:
            fetched_at = m.group(1)
    except OSError:
        pass
    cache.mark_ok(meta.id, count, 0.0)
    st = cache.get_status(meta.id)
    if st is not None:
        # get_status returns the live dict — annotate that this status was
        # rebuilt from disk, with the real fetch time (cache file mtime), and
        # seed the durable last_success_at from the envelope's OWN fetched_at
        # (never from "now" — computed health derives ok from this).
        st["last_fetch"] = datetime.fromtimestamp(mtime, timezone.utc).isoformat()
        st["from_cache"] = True
        st["last_success_at"] = fetched_at or st["last_fetch"]


async def _worker_loop(reg: registry.RegisteredLayer, client: httpx.AsyncClient) -> None:
    """Infinite loop for one layer — honors initial_delay_s and refresh_s.

    RESTART AMNESIA FIX: if the on-disk cache is still fresh, sleep out the
    remainder of refresh_s instead of refetching. The container restarts
    often (mem-watchdog); refetching all sources on every boot burned
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
            # The gate is about to sleep out the remainder without fetching —
            # register the layer as healthy from disk so it isn't invisible
            # in health endpoints until the next real fetch (days for weekly
            # layers).
            _seed_status_from_disk(meta, mtime)
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
