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


async def _run_one(reg: registry.RegisteredLayer, client: httpx.AsyncClient) -> None:
    """Fetch a single layer once, normalize, and write cache."""
    meta = reg.meta
    t0 = time.time()
    try:
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
        now = datetime.now(timezone.utc)
        fetched_at = now.isoformat()
        expires_at = (now + timedelta(seconds=meta.refresh_s)).isoformat()
        env = Envelope.build(meta, v1_data, fetched_at, expires_at)
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
    """Infinite loop for one layer — honors initial_delay_s and refresh_s."""
    if reg.meta.initial_delay_s:
        await asyncio.sleep(reg.meta.initial_delay_s)
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
