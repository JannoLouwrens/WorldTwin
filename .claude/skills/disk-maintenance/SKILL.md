---
name: disk-maintenance
description: Diagnose and fix WorldTwin disk pressure, SQLite WAL bloat, and aggregator OOM-restart loops on the Oracle server. Use when /data is filling up, history.sqlite or its WAL is huge, the aggregator is OOM-restarting, or disk/memory alerts fire.
disable-model-invocation: true
allowed-tools: Bash
---

# Disk / WAL / memory maintenance

Manual-only — dangerous ops where the wrong move cascades onto other tenants.
`KEY`/`H` from `CLAUDE.local.md`. Full background: `docs/operations.md` and
`docs/architecture/HISTORY_STORE.md`.

## First: triage

```bash
ssh -i "$KEY" $H "df -h / /data"
ssh -i "$KEY" $H "du -sh /data/* 2>/dev/null | sort -h | tail -10"
ssh -i "$KEY" $H "ls -lh /data/history/history.sqlite*"   # DB + -wal + -shm
ssh -i "$KEY" $H "docker stats --no-stream aggregator"
```

`history.sqlite` (+ its `-wal`) is almost always the consumer. It grows
~2.9 GB/day.

## WAL bloat → truncate

```bash
ssh -i "$KEY" $H "bash /home/opc/worldtwin/scripts/wal_truncate.sh"
```
This stops the aggregator, runs `PRAGMA wal_checkpoint(TRUNCATE)`, restarts, and
prints before/after sizes. (Also runs automatically Sundays via cron.)

**Hard ceilings — NEVER raise these** (raising them caused a 45 GB WAL →
`/data` 100 % full → OOM loop):
- `PRAGMA wal_autocheckpoint` ≤ 5000
- `PRAGMA mmap_size` ≤ 256 MB
- Don't remove the boot WAL-TRUNCATE from `server.py` lifespan.

## Disk genuinely full → prune

Last resort. `emergency_prune()` truncates raw **observations** while
**preserving daily snapshots** (the replay record — the product). Prefer pruning
observations to deleting snapshots. Check `history.py` / `docs/architecture/
HISTORY_STORE.md` for the current prune entrypoint before running.

## Aggregator OOM-restart loop → recover ONE container

`mem_watchdog.sh` (cron, every 2 min) already restarts only the aggregator at
~90 % memory. If it's looping:

```bash
ssh -i "$KEY" $H "docker kill aggregator; docker rm -f aggregator; cd /home/opc/worldtwin && docker compose up -d aggregator"
```

**NEVER `systemctl restart docker`** — it SIGKILLs Caddy and every company-*
tenant. Recovery is single-container only. Don't fix OOM by raising the 3 GiB
limit — there's no headroom on this free-tier box; find the leak instead.

## Expected non-incidents

- Boot health endpoint unresponsive 1–5 min while WAL-TRUNCATE runs → normal.
- Gemini `ai_narrative` returning 429 → expected, deterministic fallback kicks in.
