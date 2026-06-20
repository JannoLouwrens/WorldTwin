# Operations runbook — WorldTwin

Incident-derived rules for running WorldTwin on one free-tier ARM box shared with
other tenants. Every rule here exists because something broke. The
`.claude/skills/disk-maintenance` skill wraps the dangerous parts; this is the
reference behind it. Server facts are in `CLAUDE.local.md`.

## The three rules that protect other tenants

This box also runs Caddy, the OpenClaw company-* agents, jj-app, admin, and
searxng. A heavy hand on WorldTwin can take them all down.

1. **Recovery is single-container only.** Never `systemctl restart docker` or any
   daemon-wide restart — it SIGKILLs every tenant. To recover the aggregator:
   `docker kill aggregator && docker rm -f aggregator && docker compose up -d aggregator`.
2. **Stay inside the 3 GiB memory budget.** The aggregator has a hard 3 GiB limit
   by design; there is no headroom. Don't add background services, metric
   collectors, or raise the limit.
3. **`mem_watchdog.sh` (cron, every 2 min) restarts ONLY the aggregator** at ~90 %
   memory. Keep it tenant-safe — it must never escalate to the docker daemon.

## SQLite WAL / disk — the 45 GB incident

The history store (`/data/history/history.sqlite`, WAL mode) grows ~2.9 GB/day.
A WAL runaway once hit 45 GB on top of a 54 GB DB and filled `/data` to 100 %,
which OOM-killed the aggregator in a loop.

- **Hard ceilings — do not raise:** `PRAGMA wal_autocheckpoint = 5000`,
  `PRAGMA mmap_size = 256 MB`. Raising either caused the runaway.
- **Boot WAL-TRUNCATE must stay** in `server.py`'s lifespan, and must run
  **before** scheduler workers spawn (else it deadlocks on the exclusive lock).
- **Manual WAL truncate** (also runs Sundays via `scripts/wal_truncate.sh`):
  stop the aggregator, `PRAGMA wal_checkpoint(TRUNCATE)`, restart. The script
  prints before/after sizes.
- **Disk full triage:** `du -sh /data/* | sort -h` — `history.sqlite` is almost
  always the consumer. Last resort is `emergency_prune()` which truncates raw
  observations while **preserving daily snapshots** (the replay record). Prefer
  pruning observations over deleting snapshots — the snapshots are the product.

## Secrets

- API keys live **only** in `/home/opc/worldtwin/.env` (and the repo's
  git-ignored `.env`). Never hardcode a key anywhere else.
- All external APIs are called **server-side from plugins**. Never add a
  `/proxy/*` Caddy route — one such relay leaked the Windy key. The current
  Caddyfile has no `/proxy/*` route; keep it that way.
- Leaked-key procedure: `git filter-repo` to rewrite history (NOT `git rm`,
  which leaves the key in history), then **rotate the key** at the provider.

## Rate-limit kill-switches

- `SPACETRACK_DISABLED=1` in `.env` is a deliberate kill-switch. An eager query
  storm (a restart loop hammering the `gp` endpoint, ~2,496 restarts) got the
  Space-Track IP suspended for days. Don't flip it off without confirming the
  query cadence is rate-limit-safe.
- Gemini (the one LLM call, `ai_narrative.py`) returning 429 is **expected** and
  falls back deterministically — not an incident.

## The nightly editor (data correctness as a cron job)

- `scripts/nightly_audit.py` (06:17 UTC) walks every source for emptiness,
  staleness, and shape drift, and emails the report via Gmail OAuth. It must run
  with stdout redirected to a log under cron (`>> /var/log/wt-audit.log 2>&1`) —
  unredirected it floods the mailbot.
- `scripts/editor_probe.sh` (05:17) is the lighter freshness probe.

## Health checks

```bash
curl -s http://129.151.191.74/api/health
ssh ... "df -h /data; du -sh /data/history/* 2>/dev/null"
ssh ... "docker stats --no-stream aggregator"
ssh ... "docker compose -f /home/opc/worldtwin/docker-compose.yml logs --tail 50 aggregator"
```
