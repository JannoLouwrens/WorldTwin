#!/bin/bash
# Editorial probe — the newsroom's automated editor (VISION.md D9).
# Nightly: checks every cache for emptiness and staleness, writes a
# transparent report to /cache/_editor.json (served at /api/cache/_editor.json
# — the editor's report is itself public data, per the Charter).
set -uo pipefail

docker exec -i aggregator python - <<'PY'
import json, os, time
from pathlib import Path

CACHE = Path("/cache")
now = time.time()
problems, checked = [], 0

for f in sorted(CACHE.glob("*.json")):
    if f.name.startswith("_"):
        continue
    checked += 1
    size = f.stat().st_size
    age_h = (now - f.stat().st_mtime) / 3600
    issue = None
    if size < 100:
        issue = f"near-empty ({size} bytes)"
    elif age_h > 24 * 8:
        issue = f"stale ({age_h/24:.1f} days old)"
    else:
        # empty containers that still have bytes (e.g. {"count":0,...})
        try:
            head = f.open("r", encoding="utf-8").read(400)
            if '"count":0' in head.replace(" ", "") or head.strip() in ("[]", "{}"):
                issue = "zero-count payload"
        except Exception:
            issue = "unreadable"
    if issue:
        problems.append({"id": f.stem, "issue": issue, "size": size, "age_h": round(age_h, 1)})

report = {
    "source": "WorldTwin editorial probe",
    "fetched": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    "checked": checked,
    "count": len(problems),
    "problems": problems,
    "charter": "Gaps are shown, not hidden. This report is generated nightly and is itself public.",
}
tmp = CACHE / "_editor.json.tmp"
tmp.write_text(json.dumps(report, separators=(",", ":")))
tmp.replace(CACHE / "_editor.json")
print(f"[editor] {checked} caches checked, {len(problems)} problems")
for p in problems[:20]:
    print(f"[editor]   {p['id']}: {p['issue']}")
PY
