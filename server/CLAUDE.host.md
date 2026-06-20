# CLAUDE.md — host orientation for opc@129.151.191.74

> Source of truth for this file lives in the WorldTwin repo at
> `server/CLAUDE.host.md`. It is deployed to `/home/opc/CLAUDE.md`. Edit it in the
> repo and re-deploy; don't hand-edit on the box (changes get overwritten).

You are running Claude Code **on the server**. This is a single Oracle Cloud ARM
free-tier box hosting **two things**: the WorldTwin globe and the OpenClaw
multi-tenant AI-agent platform. Read this before touching anything — a fresh
session here has no idea other tenants share the box.

## The one rule that matters most

**Recovery is single-container only. NEVER `systemctl restart docker` or any
daemon-wide restart** — it SIGKILLs every tenant (Caddy ingress, the company-*
agents, jj-app, admin, searxng). To recover a service, act on its container
alone: `docker kill <name>; docker rm -f <name>; docker compose up -d <name>`.

Two more load-bearing don'ts:
- Don't raise WorldTwin's SQLite ceilings (`wal_autocheckpoint` > 5000 or
  `mmap_size` > 256 MB) — caused a 45 GB WAL that filled `/data`.
- Don't exceed the aggregator's 3 GiB memory limit or add background services —
  no headroom on a free-tier box.

## Container & network map

```
worldtwin_edge             caddy, aggregator                    ← WorldTwin
openclaw-platform_frontend caddy, admin, jj-app, company-*      ← caddy routes tenants here
openclaw-platform_backend  admin, jj-app, agent-live, searxng, company-*
```
`caddy` is the only ingress (:80/:443). `company-lakeside/sportsstock/bergen/
kayakco` are separate customer agents — **do not disturb.**

## Compose projects

```
/home/opc/worldtwin/          WorldTwin: aggregator (:8090) + caddy.  App source + runbooks here.
/home/opc/openclaw-platform/  The tenant platform (caddy + company agents).
```

## Cron

```
17 6 * * *  /home/opc/worldtwin/scripts/nightly_audit.py     (freshness email)
17 5 * * *  /home/opc/worldtwin/scripts/editor_probe.sh
43 3 * * 0  /home/opc/worldtwin/scripts/wal_truncate.sh       (Sundays)
*/2 * * * * /home/opc/worldtwin/scripts/mem_watchdog.sh       (aggregator-only restart at 90%)
*/30 * * * * /home/opc/openclaw-platform/scripts/platform_monitor.sh
0 2 * * *   /home/opc/jackandjill/backup.sh
```

## Where the real docs are

WorldTwin app source, architecture, deploy/ops runbooks, and per-task skills live
in **`/home/opc/worldtwin/`** — if the repo is checked out there, read its
`AGENTS.md` and `docs/`. Platform context:
`/home/opc/openclaw-platform/` and the deployment guide in the WorldTwin repo.

## Quick health

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
df -h / /data
curl -s http://localhost/api/health
```
