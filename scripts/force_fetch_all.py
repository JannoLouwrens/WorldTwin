#!/usr/bin/env python3
"""Synchronously trigger a fetch for every enabled plugin RIGHT NOW.

Bypasses the scheduler's refresh_s + initial_delay_s. Useful after deploying
new history-decomposer rules — every plugin's NEXT snapshot is taken
immediately instead of waiting hours/days for its natural cycle.

Run inside the aggregator container:
    docker compose exec -T aggregator python3 /app/worldtwin/_force_fetch.py
"""
from __future__ import annotations
import asyncio
import sys
import time

sys.path.insert(0, '/app')

import httpx
from worldtwin import registry, scheduler


async def main() -> int:
    registry.autodiscover()
    layers = [r for r in registry.all_layers() if r.meta.enabled]
    print(f"force-fetch: {len(layers)} enabled plugins")

    # Reasonable concurrency — don't hammer all 80+ APIs simultaneously
    sem = asyncio.Semaphore(8)
    counts = {"ok": 0, "skip": 0, "err": 0}

    async def _run(reg):
        async with sem:
            t0 = time.time()
            try:
                async with httpx.AsyncClient(
                    timeout=180,
                    follow_redirects=True,
                    headers={"User-Agent": "WorldTwin/1.0"},
                ) as client:
                    await scheduler._run_one(reg, client)
                elapsed = time.time() - t0
                # Check whether the layer wrote a cache
                from worldtwin import cache as cmod
                p = cmod.legacy_path(reg.meta.id)
                if p.exists():
                    sz = p.stat().st_size
                    print(f"  ok    [{reg.meta.id:30}] {sz:>10,} bytes in {elapsed:5.1f}s")
                    counts["ok"] += 1
                else:
                    print(f"  skip  [{reg.meta.id:30}] (no cache file written)")
                    counts["skip"] += 1
            except Exception as e:
                print(f"  ERR   [{reg.meta.id:30}] {type(e).__name__}: {e}")
                counts["err"] += 1

    await asyncio.gather(*[_run(r) for r in layers])
    print()
    print(f"DONE — ok={counts['ok']}, skip={counts['skip']}, err={counts['err']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
