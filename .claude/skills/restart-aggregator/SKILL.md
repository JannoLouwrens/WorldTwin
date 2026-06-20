---
name: restart-aggregator
description: Restart, rebuild, or force-fetch the WorldTwin FastAPI aggregator container on the Oracle server and tail logs to confirm health. Use when asked to restart/rebuild the aggregator, reload .env or API keys, force a data fetch, or debug a stale layer or a down backend.
disable-model-invocation: true
allowed-tools: Bash
---

# Restart / rebuild / force-fetch the aggregator

Manual-only (touches the live server). `KEY`/`H` from `CLAUDE.local.md`. Full
reference: `docs/deploy.md`. The container runs the **modular package**
(`python -m worldtwin`) — editing the legacy `aggregator.py` monolith does nothing.

## Pick the right action

```bash
KEY="<see CLAUDE.local.md>"; H="opc@129.151.191.74"

# Reload .env / API keys, or apply a sources/*.py change you already scp'd
ssh -i "$KEY" $H "cd /home/opc/worldtwin && docker compose restart aggregator"

# Rebuild — ONLY when requirements.txt or Dockerfile changed
ssh -i "$KEY" $H "cd /home/opc/worldtwin && docker compose build aggregator --no-cache && docker compose up -d"

# Force an immediate fetch (bypass per-plugin scheduler; semaphore-bounded)
ssh -i "$KEY" $H "cd /home/opc/worldtwin && docker compose exec -T aggregator python3 -m worldtwin._force_fetch"
# ^ verify the force-fetch entrypoint name in aggregator/worldtwin/ first; it has moved between revisions.
```

## Expected boot behaviour — do NOT kill it

On start, the FastAPI lifespan runs a **WAL TRUNCATE before workers spawn**. On a
large history DB the health endpoint can be unresponsive for 1–5 minutes. That is
normal — wait it out.

## Confirm health

```bash
ssh -i "$KEY" $H "cd /home/opc/worldtwin && docker compose logs -f aggregator"   # Ctrl-C when steady
curl -s http://129.151.191.74/api/health
```

## Recovery (if it won't come up / OOM loop)

**Single-container only — never restart the docker daemon** (kills every other
tenant on the box):
```bash
ssh -i "$KEY" $H "docker kill aggregator; docker rm -f aggregator; cd /home/opc/worldtwin && docker compose up -d aggregator"
```
If it's an OOM/WAL/disk loop, use the `/disk-maintenance` skill instead of
restart-spamming (a restart storm got the Space-Track IP suspended once).
