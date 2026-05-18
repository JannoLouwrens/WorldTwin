#!/bin/bash
# Memory watchdog for aggregator — restarts container when MemUsage exceeds
# 85% of the limit. Runs every 5 minutes via cron. The aggregator has a
# slow memory leak (likely in plugin worker closures or httpx pools) that
# we haven't isolated yet; this is a pragmatic safety net until we do.
#
# Logs each check (silent on healthy, verbose on action).
set -euo pipefail

LOG_TAG="[wt-mem-watchdog]"
THRESHOLD_PCT=85   # restart when MemUsage% >= this

# Get current usage via docker stats (no streaming, just one snapshot)
LINE=$(docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.MemPerc}}' aggregator 2>/dev/null || true)
if [ -z "$LINE" ]; then
  echo "$(date -Iseconds) $LOG_TAG aggregator container not found"
  exit 0
fi

# Parse "aggregator 1.5GiB / 3GiB 50.00%"
PCT=$(echo "$LINE" | awk '{print $NF}' | tr -d '%')
PCT_INT=$(printf '%.0f' "$PCT" 2>/dev/null || echo 0)

if [ "$PCT_INT" -ge "$THRESHOLD_PCT" ]; then
  echo "$(date -Iseconds) $LOG_TAG MEM AT ${PCT}% — restarting (line: $LINE)"
  cd /home/opc/worldtwin
  # Three-tier recovery, escalating force:
  # 1. graceful `docker compose restart` (30s timeout)
  # 2. hard `docker rm -f` + `docker compose up -d`
  # 3. nuclear: `systemctl restart docker` + force-recreate
  # Reason: when memory is near 100%, kernel cgroup pauses processes and
  # SIGTERM/SIGKILL can't be delivered. Only restarting the docker daemon
  # frees the cgroup.
  if ! timeout 30 docker compose restart aggregator 2>&1; then
    echo "$(date -Iseconds) $LOG_TAG step 1 failed — hard recreating"
    if ! timeout 20 docker rm -f aggregator 2>&1; then
      echo "$(date -Iseconds) $LOG_TAG step 2 failed — restarting docker daemon"
      sudo systemctl restart docker
      sleep 5
    fi
    docker compose up -d --force-recreate aggregator 2>&1 | tail -3
  fi
  echo "$(date -Iseconds) $LOG_TAG restart complete"
fi
# Silent on healthy — keeps log readable
