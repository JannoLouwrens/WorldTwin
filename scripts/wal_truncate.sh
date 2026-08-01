#!/bin/bash
# Weekly WAL maintenance for WorldTwin History Store.
#
# In-process PRAGMA wal_checkpoint(TRUNCATE) cannot succeed under our 90
# concurrent plugin writers — they nearly always hold the SQLite write
# lock. The only clean path is: stop the aggregator briefly, run TRUNCATE
# from a one-off container, restart.
#
# Total downtime: ~1-5 minutes depending on WAL size. Reads from the live
# Caddy cache files (the static .json snapshots in /home/opc/worldtwin/cache)
# remain available throughout — only /api/* endpoints are interrupted.
#
# Schedule: Sunday 03:43 local time (off-peak, off the :00/:30 marks).
set -euo pipefail

LOG_TAG="[wt-wal-truncate]"
echo "$(date -Iseconds) $LOG_TAG starting"

# Snapshot WAL size before
BEFORE=$(stat -c '%s' /data/history/history.sqlite-wal 2>/dev/null || echo 0)
DB_BEFORE=$(stat -c '%s' /data/history/history.sqlite 2>/dev/null || echo 0)
echo "$(date -Iseconds) $LOG_TAG before: db=${DB_BEFORE} wal=${BEFORE}"

# Stop the aggregator
cd /home/opc/worldtwin
docker compose stop aggregator
echo "$(date -Iseconds) $LOG_TAG aggregator stopped"

# Run TRUNCATE in a one-off container
docker run --rm -v /data/history:/history python:3.12-slim python -c '
import sqlite3, time
t0 = time.time()
c = sqlite3.connect("/history/history.sqlite", timeout=600, isolation_level=None)
c.execute("PRAGMA busy_timeout=600000")
r = c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
print(f"checkpoint: busy={r[0]} log={r[1]} ckpt={r[2]} in {time.time()-t0:.1f}s")
c.close()
'

# Restart aggregator
docker compose start aggregator
echo "$(date -Iseconds) $LOG_TAG aggregator restarted"

# Snapshot WAL size after
AFTER=$(stat -c '%s' /data/history/history.sqlite-wal 2>/dev/null || echo 0)
DB_AFTER=$(stat -c '%s' /data/history/history.sqlite 2>/dev/null || echo 0)
echo "$(date -Iseconds) $LOG_TAG after:  db=${DB_AFTER} wal=${AFTER}"
echo "$(date -Iseconds) $LOG_TAG reclaimed: $((BEFORE - AFTER)) bytes"
