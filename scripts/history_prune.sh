#!/bin/bash
# Offline history-store cleanup for WorldTwin.
#
# WHY THIS IS A SCRIPT AND NOT THE IN-PROCESS LOOP
# ------------------------------------------------
# server.py's _history_compact_loop is gated behind HISTORY_RETENTION=1 and
# should stay that way. Run in-process it would:
#   * issue multi-GB DELETEs as single autocommit statements, ballooning the
#     WAL by roughly the volume of pages touched, and
#   * VACUUM a ~52 GB database, which rewrites the whole file into a temp
#     copy *alongside* the original (needs the resulting size free, on a
#     volume that had 45 GB spare), while
#   * holding the write lock far longer than the 60 s busy_timeout of the
#     ~89 plugin writers, which starves them, grows RSS, and trips
#     mem_watchdog.sh into killing the container mid-VACUUM.
#
# So: stop the aggregator, prune in bounded batches with a checkpoint after
# each one (keeps the WAL flat), VACUUM only if the disk can actually take
# it, restart. Same stop/one-off-container/start pattern as wal_truncate.sh.
#
# Downtime: minutes to tens of minutes depending on how much is deleted.
# The static /api/cache/*.json files keep serving throughout — only /api/*
# and /v1/* endpoints are interrupted.
#
# NOT scheduled by default. Run it by hand in a window you are watching:
#     /home/opc/worldtwin/scripts/history_prune.sh 2>&1 | tee -a /var/log/wt-history-prune.log
#
# Env overrides:
#   SNAPSHOT_KEEP_DAYS  (default 7)   snapshots newer than this are kept
#   EPHEMERAL_KEEP_DAYS (default 30)  per-entity observations kept this long
#   BATCH               (default 2000) rows per delete batch
#   SKIP_VACUUM         (default 0)   set 1 to reclaim nothing, just delete
set -euo pipefail

LOG_TAG="[wt-history-prune]"
SNAPSHOT_KEEP_DAYS="${SNAPSHOT_KEEP_DAYS:-7}"
EPHEMERAL_KEEP_DAYS="${EPHEMERAL_KEEP_DAYS:-30}"
BATCH="${BATCH:-2000}"
SKIP_VACUUM="${SKIP_VACUUM:-0}"

DB=/data/history/history.sqlite

echo "$(date -Iseconds) $LOG_TAG starting (snapshots>${SNAPSHOT_KEEP_DAYS}d, ephemeral obs>${EPHEMERAL_KEEP_DAYS}d, batch=${BATCH})"

DB_BEFORE=$(stat -c '%s' "$DB" 2>/dev/null || echo 0)
WAL_BEFORE=$(stat -c '%s' "${DB}-wal" 2>/dev/null || echo 0)
FREE_BEFORE=$(df -B1 --output=avail /data | tail -1 | tr -d ' ')
echo "$(date -Iseconds) $LOG_TAG before: db=${DB_BEFORE} wal=${WAL_BEFORE} free=${FREE_BEFORE}"

cd /home/opc/worldtwin

# TENANT-SAFE: only ever touches this one container, never the docker daemon.
docker compose stop aggregator
echo "$(date -Iseconds) $LOG_TAG aggregator stopped"

# Always bring the aggregator back, even if the prune dies partway.
restart_aggregator() {
  echo "$(date -Iseconds) $LOG_TAG restarting aggregator"
  cd /home/opc/worldtwin && docker compose start aggregator || true
}
trap restart_aggregator EXIT

docker run --rm \
  -e SNAPSHOT_KEEP_DAYS="$SNAPSHOT_KEEP_DAYS" \
  -e EPHEMERAL_KEEP_DAYS="$EPHEMERAL_KEEP_DAYS" \
  -e BATCH="$BATCH" \
  -e SKIP_VACUUM="$SKIP_VACUUM" \
  -v /data/history:/history \
  python:3.12-slim python -u -c '
import os, shutil, sqlite3, time
from datetime import datetime, timezone, timedelta

SNAP_DAYS = int(os.environ["SNAPSHOT_KEEP_DAYS"])
EPH_DAYS  = int(os.environ["EPHEMERAL_KEEP_DAYS"])
BATCH     = int(os.environ["BATCH"])
SKIP_VAC  = os.environ["SKIP_VACUUM"] == "1"
DB        = "/history/history.sqlite"

# Same list server.py treats as disposable: one source_id per aircraft/ship/
# video/webcam etc. Slow-moving economic, conflict and climate series are
# never touched — those are the rows that are actually worth keeping.
EPHEMERAL = ("flights.", "ships.", "webcams.", "youtube.", "radio.",
             "gaming.", "trends.", "news.", "iss.", "fires.")

now = datetime.now(timezone.utc)
snap_cut = (now - timedelta(days=SNAP_DAYS)).isoformat()
eph_cut  = (now - timedelta(days=EPH_DAYS)).isoformat()

c = sqlite3.connect(DB, timeout=600, isolation_level=None)
c.execute("PRAGMA busy_timeout=600000")
c.execute("PRAGMA journal_mode=WAL")
c.execute("PRAGMA synchronous=NORMAL")

def checkpoint():
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")

def batched(label, sql, params):
    """Delete in bounded chunks, truncating the WAL after each chunk so it
    never grows to the size of the whole deletion."""
    total, t0 = 0, time.time()
    while True:
        cur = c.execute(sql, params)
        n = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        total += n
        if n:
            checkpoint()
            print(f"  {label}: {total} rows deleted ({time.time()-t0:.0f}s)", flush=True)
        if n < BATCH:
            break
    return total

print(f"snapshot cutoff {snap_cut}", flush=True)
snaps = batched(
    "snapshots",
    "DELETE FROM snapshots WHERE ROWID IN ("
    "  SELECT ROWID FROM snapshots WHERE fetched_at < ? LIMIT ?)",
    (snap_cut, BATCH),
)

obs = 0
for prefix in EPHEMERAL:
    obs += batched(
        f"obs:{prefix}",
        "DELETE FROM observations WHERE ROWID IN ("
        "  SELECT ROWID FROM observations"
        "  WHERE source_id >= ? AND source_id < ? AND fetched_at < ? LIMIT ?)",
        (prefix, prefix + "~", eph_cut, BATCH),
    )

checkpoint()
page_size = c.execute("PRAGMA page_size").fetchone()[0]
freelist  = c.execute("PRAGMA freelist_count").fetchone()[0]
db_bytes  = os.path.getsize(DB)
reusable  = freelist * page_size
live      = db_bytes - reusable
print(f"deleted: snapshots={snaps} observations={obs}", flush=True)
print(f"db={db_bytes/1024**3:.1f} GiB, reusable free pages={reusable/1024**3:.1f} GiB, "
      f"live data={live/1024**3:.1f} GiB", flush=True)

if SKIP_VAC:
    print("VACUUM skipped (SKIP_VACUUM=1). Freed pages stay in the file and "
          "get reused by new writes, so the file will not grow.", flush=True)
else:
    # VACUUM writes a fresh copy of the live data next to the original, so it
    # needs at least that much free space. Refuse rather than fill the volume
    # (a full /data is what took this box down once already).
    free = shutil.disk_usage("/history").free
    need = int(live * 1.2) + 1024**3
    print(f"VACUUM needs ~{need/1024**3:.1f} GiB free; have {free/1024**3:.1f} GiB", flush=True)
    if free < need:
        print("REFUSING to VACUUM — not enough headroom. Deletions are still "
              "committed and the freed pages will be reused, so this is safe; "
              "re-run with more free space to shrink the file.", flush=True)
    else:
        t0 = time.time()
        c.execute("VACUUM")
        print(f"VACUUM done in {time.time()-t0:.0f}s", flush=True)

checkpoint()
c.close()
'

trap - EXIT
restart_aggregator

DB_AFTER=$(stat -c '%s' "$DB" 2>/dev/null || echo 0)
WAL_AFTER=$(stat -c '%s' "${DB}-wal" 2>/dev/null || echo 0)
FREE_AFTER=$(df -B1 --output=avail /data | tail -1 | tr -d ' ')
echo "$(date -Iseconds) $LOG_TAG after:  db=${DB_AFTER} wal=${WAL_AFTER} free=${FREE_AFTER}"
echo "$(date -Iseconds) $LOG_TAG db delta: $((DB_BEFORE - DB_AFTER)) bytes"
echo "$(date -Iseconds) $LOG_TAG done"
