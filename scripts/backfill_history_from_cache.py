#!/usr/bin/env python3
"""One-time backfill: walk every existing /cache/*.json and load it into
the history store using each file's mtime as fetched_at.

This recovers what the lab already has — V-Dem 1789→2025, Maddison 1→2018,
HYDE -10000→2023, NOAA CO2 -800k→2025, paleo temp -9350→2025, World Bank
1960→2024, every event stream's current state, etc.

Idempotent: re-running is safe because INSERT OR IGNORE on the PRIMARY KEY
(source_id, observed_at, fetched_at) deduplicates.

Run from inside the aggregator container:
  docker compose exec aggregator python3 /app/worldtwin/../../scripts/backfill_history_from_cache.py
Or copy the script to /home/opc/worldtwin/aggregator/ and run via exec.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make the worldtwin package importable when this is run from /app or from a
# sibling directory.
sys.path.insert(0, '/app')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'aggregator'))

from worldtwin import history  # noqa: E402

CACHE_DIR = Path(os.environ.get('CACHE_DIR', '/cache'))


def main() -> int:
    files = sorted(CACHE_DIR.glob('*.json'))
    print(f'[backfill] {len(files)} cache files to load from {CACHE_DIR}')
    total_obs = 0
    total_snaps = 0
    errors = []
    t0 = time.time()
    for i, p in enumerate(files, 1):
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
            with p.open('r', encoding='utf-8') as f:
                payload = json.load(f)
            # Inject the file's mtime as fetched_at so the snapshot key
            # reflects when the file was written, not when this script ran.
            if isinstance(payload, dict) and not payload.get('fetched'):
                payload['fetched'] = mtime
            res = history.snapshot(p.stem, payload)
            total_obs += res.get('observation_rows', 0)
            total_snaps += 1 if res.get('snapshot_added') else 0
            if res.get('errors'):
                errors.append((p.name, res['errors']))
            print(f'  [{i:3}/{len(files)}] {p.name:35} '
                  f'obs={res.get("observation_rows", 0):>5} '
                  f'snap={"OK" if res.get("snapshot_added") else "FAIL"}')
        except Exception as e:
            errors.append((p.name, str(e)))
            print(f'  [{i:3}/{len(files)}] {p.name:35} ERROR: {e}')

    elapsed = time.time() - t0
    print()
    print(f'[backfill] DONE in {elapsed:.1f}s')
    print(f'[backfill] {total_snaps} snapshots loaded, {total_obs} observations rows added')
    if errors:
        print(f'[backfill] {len(errors)} errors:')
        for name, err in errors[:20]:
            print(f'    {name}: {str(err)[:200]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
