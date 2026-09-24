"""One-shot tombstone writer — run in-container as `python -m worldtwin.tombstones`.

For every registered layer with enabled=False, writes a tombstone envelope to
BOTH cache trees (legacy /cache/<id>.json and /cache/v1/<id>.json) via
cache._atomic_write, which also handles the gzip sidecars (small files get any
stale .gz sidecar dropped, so a tombstone can never be shadowed by an old
precompressed cache).

The two hard-404 ids (spacetrack_gp, webcams) are skipped entirely: nothing is
written for them — the orchestrator quarantines their files off the served
paths and Caddy returns a genuine 404.

After writing, both files' mtimes are backdated to a fixed old epoch so the
scheduler's restart-amnesia gate can never count a tombstone as fresh cache
(a future un-retire must not sleep out a full refresh_s on tombstone bytes).

Idempotent: re-running rewrites the same envelopes and re-backdates. It
refuses to touch any path belonging to an ENABLED layer.
"""
from __future__ import annotations

import os
import sys

from . import cache, registry

RETIRED_ON = "2026-09-24"

# Never write tombstones for these — they are hard 404s (legal removals),
# not visible refusals. The orchestrator quarantines their cache files.
HARD_404_IDS = {"spacetrack_gp", "webcams"}

# Fixed old epoch for backdating: 2000-01-01T00:00:00Z. Any staleness gate
# comparing mtime against refresh_s sees a tombstone as ancient, never fresh.
OLD_EPOCH = 946684800


def _tombstone(meta) -> dict:
    return {
        "id": meta.id,
        "name": meta.name,
        "category": meta.category,
        "kind": meta.kind,
        "state": "retired",
        "reason": (getattr(meta, "retired_reason", "") or "retired"),
        "retired_on": RETIRED_ON,
        "source": getattr(meta, "source", ""),
        "license": getattr(meta, "license", ""),
        "count": 0,
        "data": [],
    }


def _backdate(path) -> None:
    for p in (path, path.with_suffix(path.suffix + ".gz")):
        try:
            if p.exists():
                os.utime(p, (OLD_EPOCH, OLD_EPOCH))
        except OSError as e:
            print(f"[tombstones] WARN could not backdate {p}: {e}")


def main() -> int:
    registry.autodiscover()
    layers = registry.all_layers()
    enabled_ids = {r.meta.id for r in layers if r.meta.enabled}

    written = 0
    skipped_enabled = 0
    skipped_404 = 0
    for reg in sorted(layers, key=lambda r: r.meta.id):
        meta = reg.meta
        if meta.id in HARD_404_IDS:
            print(f"[tombstones] {meta.id}: hard-404 — writing NOTHING (orchestrator quarantines its files)")
            skipped_404 += 1
            continue
        if meta.enabled:
            skipped_enabled += 1
            continue
        # Belt and braces: never overwrite a cache belonging to an enabled layer.
        if meta.id in enabled_ids:
            print(f"[tombstones] REFUSED {meta.id}: layer is enabled")
            continue
        payload = _tombstone(meta)
        legacy = cache.legacy_path(meta.id)      # /cache/<id>.json
        v1 = cache.envelope_path(meta.id)        # /cache/v1/<id>.json
        cache._atomic_write(legacy, payload)
        cache._atomic_write(v1, payload)
        _backdate(legacy)
        _backdate(v1)
        written += 1
        print(f"[tombstones] {meta.id}: tombstoned (both trees, mtime backdated) — {payload['reason'][:80]}")

    print(
        f"[tombstones] done: {written} tombstoned, "
        f"{skipped_enabled} enabled layers untouched, "
        f"{skipped_404} hard-404 ids skipped, "
        f"{len(layers)} layers total"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
