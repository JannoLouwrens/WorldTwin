#!/bin/bash
# Memory watchdog for aggregator — restarts container when MemUsage exceeds
# 90% of the limit, and starts it if it is not running at all. Runs every
# 2 minutes via cron. The aggregator has a slow memory leak (likely in
# plugin worker closures or httpx pools) that we haven't isolated yet;
# this is a pragmatic safety net until we do.
#
# Logs each check (silent on healthy, verbose on action).
set -euo pipefail

LOG_TAG="[wt-mem-watchdog]"
THRESHOLD_PCT=90   # restart when MemUsage% >= this (was 85 — too eager on a
                   # 3GB box; the boot WAL-truncate + round-2 fixes lowered
                   # steady-state RAM, so this should rarely fire now)

# DOWN-DETECTION (added 2026-08-01): `docker stats` on an *exited* container
# reports "0B / 0B 0.00%", which the threshold check below reads as healthy —
# that blind spot left the aggregator down for 6 days after the Jul 26 OOM
# storm (a wedged `docker kill` counts as a manual stop, so unless-stopped
# never re-fires). If the container isn't running, start it and exit.
RUNNING=$(docker inspect -f '{{.State.Running}}' aggregator 2>/dev/null || echo "missing")
if [ "$RUNNING" != "true" ]; then
  echo "$(date -Iseconds) $LOG_TAG aggregator not running (state: $RUNNING) — starting"
  cd /home/opc/worldtwin
  timeout 60 docker compose up -d aggregator 2>&1 | tail -2
  echo "$(date -Iseconds) $LOG_TAG start complete (aggregator-only)"
  exit 0
fi

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
  # TENANT-SAFE recovery — only ever touches the aggregator's own cgroup,
  # NEVER the docker daemon (the old tier-3 `systemctl restart docker`
  # bounced every container on the box: Caddy, OpenClaw, all of it).
  #
  # 1. docker kill — SIGKILL straight to the single container's cgroup.
  #    This is what actually works under memory pressure; `compose restart`
  #    sends SIGTERM and waits, which wedges ("did not receive an exit
  #    event") exactly when the process is too starved to handle SIGTERM.
  # 2. docker rm -f as backstop if kill left a dead container.
  # 3. compose up -d to bring it back. unless-stopped restart policy may
  #    already be doing this, so `up -d` is idempotent.
  timeout 25 docker kill aggregator 2>&1 || echo "$(date -Iseconds) $LOG_TAG kill returned non-zero (may already be down)"
  timeout 25 docker rm -f aggregator 2>&1 || true
  timeout 60 docker compose up -d aggregator 2>&1 | tail -2
  echo "$(date -Iseconds) $LOG_TAG restart complete (aggregator-only)"
fi
# Silent on healthy — keeps log readable
