# Deploy runbook — WorldTwin

Single-server deployment to Oracle Cloud (`opc@129.151.191.74`). The SSH key path
and resolved live paths are in `CLAUDE.local.md` (git-ignored) — read that first.
The `.claude/skills/deploy-frontend`, `restart-aggregator`, and `disk-maintenance`
skills wrap these procedures; this doc is the human-readable reference behind them.

There is **no CI/CD**. Deploy is `scp` + (for backend) a container restart.

## Layout on the box

```
/home/opc/worldtwin/
├── docker-compose.yml      # aggregator service (:8090, 3GiB limit) + caddy
├── .env                    # API keys — never leaves the box
├── weather/                # LIVE frontend  (Caddy mounts read-only as /srv/weather)
│   └── js/
├── aggregator/
│   └── worldtwin/sources/  # LIVE plugins
├── scripts/                # cron jobs (audit, wal_truncate, mem_watchdog, editor_probe)
└── cache -> /data/cache    # JSON caches (Caddy serves these gzipped, max-age 10s)
```

`/home/opc/openclaw-platform/weather` is a **symlink** to `/home/opc/worldtwin/weather`.
Deploy to the worldtwin path; both resolve to the same files.

## Frontend deploy (no build, no restart)

Caddy serves `weather/` from a **read-only** mount, so static files go live the
moment they land — no container restart.

```bash
KEY="<see CLAUDE.local.md>"; H="opc@129.151.191.74"

# 1. Bump the cache-buster if you changed config.json layer ids
#    (edit ?v=BUILD_ID in frontend/index.html)

# 2. Copy changed files (frontend/ in the repo is the source of truth —
#    NOT Solo/new_plugins, which is stale)
scp -i "$KEY" frontend/js/<file>.js  $H:/home/opc/worldtwin/weather/js/
scp -i "$KEY" frontend/index.html    $H:/home/opc/worldtwin/weather/
scp -i "$KEY" frontend/config.json   $H:/home/opc/worldtwin/weather/

# 3. Verify: hard-reload http://129.151.191.74/worldtwin/ and confirm
#    config.json loads + browser console has 0 errors (use chrome-devtools).
```

Rollback: keep a `.bak` of any file you overwrite (`cp x.js x.js.bak` on the box
before scp), restore it if the live page breaks.

## Backend (aggregator) deploy

The container runs the **modular package** (`python -m worldtwin`). Editing the
legacy `aggregator/aggregator.py` monolith does nothing.

```bash
# Add/change a plugin: copy the source file, then restart to pick it up
scp -i "$KEY" aggregator/worldtwin/sources/<id>.py \
    $H:/home/opc/worldtwin/aggregator/worldtwin/sources/

ssh -i "$KEY" $H "cd /home/opc/worldtwin && docker compose restart aggregator"
```

- **`restart`** reloads `.env` (use it after rotating/adding an API key).
- **Rebuild** (only when dependencies or Dockerfile change):
  ```bash
  ssh -i "$KEY" $H "cd /home/opc/worldtwin && docker compose build aggregator --no-cache && docker compose up -d"
  ```
- **Force an immediate fetch** (bypass the per-plugin scheduler, semaphore-bounded):
  ```bash
  ssh -i "$KEY" $H "cd /home/opc/worldtwin && docker compose exec -T aggregator python3 -m worldtwin._force_fetch"
  ```
  (Check the actual force-fetch entrypoint name in `aggregator/worldtwin/` before
  relying on it — it has moved between revisions.)

### Boot behaviour to expect

On start, `server.py`'s FastAPI **lifespan runs a WAL TRUNCATE before scheduler
workers spawn**. On a large history DB this can block the health endpoint for
1–5 minutes. That is expected — don't kill the container thinking it hung.

## Verify

```bash
curl -s http://129.151.191.74/api/health
curl -s http://129.151.191.74/api/cache/<id>.json | head -c 300   # non-empty?
ssh -i "$KEY" $H "cd /home/opc/worldtwin && docker compose logs --tail 40 aggregator"
```

A layer is "deployed" only when its cache file is non-empty AND the frontend
renders it with a clean console.
