#!/usr/bin/env python3
"""WorldTwin · History Store coverage report.

Walks every plugin in aggregator/worldtwin/sources/, asks the history.sqlite
how many observation rows + snapshots it has for that plugin, and writes a
markdown report to docs/sources/HISTORY_COVERAGE.md.

Run from inside the container:
    docker compose exec -T aggregator python3 /app/worldtwin/_coverage.py
"""
from __future__ import annotations
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, '/app')

DB = Path(os.environ.get("HISTORY_DB", "/history/history.sqlite"))
SOURCES_DIR = Path("/app/worldtwin/sources")
OUT = Path("/cache/HISTORY_COVERAGE.md")


def get_layer_meta_from_file(p: Path) -> dict:
    """Naive extract of LayerMeta(id="xxx") from a plugin source."""
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return {}
    import re
    m = re.search(r'id\s*=\s*["\']([^"\']+)["\']', text)
    layer_id = m.group(1) if m else p.stem
    cm = re.search(r'category\s*=\s*["\']([^"\']+)["\']', text)
    category = cm.group(1) if cm else "?"
    em = re.search(r'enabled\s*=\s*(True|False|bool)', text)
    enabled = em.group(1) if em else "?"
    return {"id": layer_id, "category": category, "enabled": enabled, "file": p.name}


def main() -> int:
    if not DB.exists():
        print(f"history.sqlite not found at {DB}")
        return 1
    plugins = sorted([p for p in SOURCES_DIR.glob("*.py")
                      if not p.name.startswith("_") and p.name != "__init__.py"])
    metas = [get_layer_meta_from_file(p) for p in plugins]

    c = sqlite3.connect(str(DB))
    obs_total = c.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    snap_total = c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    db_size_mb = round(DB.stat().st_size / 1024 / 1024, 1)

    rows = []
    for meta in metas:
        layer_id = meta.get("id") or meta.get("file", "?")
        # observations row count
        obs = c.execute(
            "SELECT COUNT(*) FROM observations WHERE source_id LIKE ?",
            (layer_id + ".%",),
        ).fetchone()[0]
        snap = c.execute(
            "SELECT COUNT(*), MAX(fetched_at), SUM(payload_kb) FROM snapshots WHERE layer_id = ?",
            (layer_id,),
        ).fetchone()
        snap_count, snap_latest, snap_kb = snap
        # observed_at range
        rng = c.execute(
            "SELECT MIN(observed_at), MAX(observed_at) FROM observations WHERE source_id LIKE ?",
            (layer_id + ".%",),
        ).fetchone()
        obs_min, obs_max = rng
        rows.append({
            "id": layer_id,
            "file": meta.get("file"),
            "category": meta.get("category"),
            "obs_rows": obs,
            "snap_count": snap_count or 0,
            "snap_kb": round(snap_kb or 0, 1),
            "snap_latest": snap_latest,
            "observed_min": obs_min,
            "observed_max": obs_max,
        })

    # Sort by observation row count desc
    rows.sort(key=lambda r: -r["obs_rows"])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    out_lines = [
        "# WorldTwin History Store · Coverage Report",
        "",
        f"_Generated {today} UTC._",
        "",
        f"**Vision:** A lab where anyone — from the king of Rome to a sceptical citizen —",
        f"can read the world from raw, dated, cross-checked sources instead of someone",
        f"else's framing, and trace every claim back to the instrument that measured it.",
        "",
        "## Totals",
        "",
        f"- **Observations:** {obs_total:,} rows across {len(rows)} plugins",
        f"- **Snapshots:**    {snap_total:,} payloads, {db_size_mb} MB on disk",
        f"- **Database:**     `/data/history/history.sqlite`",
        f"- **Volume:**       100 GB on `/data` (Oracle block volume, free tier)",
        "",
        "## Per-plugin coverage (ranked by observation rows)",
        "",
        "| Rank | Plugin | Category | Obs rows | Snapshots | Snap KB | Observed range | Latest fetch |",
        "|------|--------|----------|---------:|----------:|--------:|----------------|--------------|",
    ]
    for i, r in enumerate(rows, 1):
        rng = f"{r['observed_min'][:10]} → {r['observed_max'][:10]}" if r['observed_min'] else "—"
        latest = (r['snap_latest'] or "")[:19].replace("T", " ")
        out_lines.append(
            f"| {i} | `{r['id']}` | {r['category']} | {r['obs_rows']:,} | "
            f"{r['snap_count']} | {r['snap_kb']} | {rng} | {latest} |"
        )
    out_lines.append("")
    out_lines.append("## Notes")
    out_lines.append("")
    out_lines.append("- Observation rows = decomposed time-series + event records.")
    out_lines.append("- Snapshot rows = complete payload, zlib-compressed, never decomposed.")
    out_lines.append("- A plugin showing 0 observations but >=1 snapshot means we have the receipt but the decomposer didn't recognise the payload shape — the snapshot can be re-decomposed later without re-fetching.")
    out_lines.append("- A plugin with 0 snapshots either has not yet fired since the History Store was deployed, or its fetch is failing upstream.")
    out_lines.append("- See `docs/architecture/HISTORY_STORE.md` for the design.")

    OUT.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"wrote {OUT} · {len(rows)} plugins · {obs_total:,} observations · {snap_total:,} snapshots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
