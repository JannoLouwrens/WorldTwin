---
name: server-ssh-recipes
description: Reference for SSHing into the Oracle Cloud server (129.151.191.74) and inspecting the live OpenClaw + WorldTwin container stack — container names, networks, Caddy routes, cron, logs, and the SSH key location. Use when asked how to reach the server, list containers, read Caddy routes, check cron, or understand the multi-tenant topology.
---

# Server / SSH reference

Read-only orientation for the box that hosts WorldTwin alongside the OpenClaw
multi-tenant platform. The IP and key path are also in `CLAUDE.local.md` (the
one place machine facts live; keep them out of committed files).

## Connect

The SSH key path is in the git-ignored `CLAUDE.local.md` (so it isn't published in
this private-but-shared repo). Read it from there:

```bash
KEY="<key path from CLAUDE.local.md>"   # the .key file is NOT in ~/.ssh
H="opc@129.151.191.74"
ssh -i "$KEY" -o StrictHostKeyChecking=no $H "<cmd>"
```

Oracle Cloud ARM free tier · Oracle Linux 9.7 · 4 OCPU / 22 GB RAM · `/data` =
100 GB block volume. Janno also reaches this box from his phone via
Tailscale + Termius.

## Container & network map

```
worldtwin_edge            caddy, aggregator                 ← WorldTwin only
openclaw-platform_frontend caddy, admin, jj-app, company-*  ← caddy bridges here to route tenants
openclaw-platform_backend  admin, jj-app, agent-live, searxng, company-*
```

`caddy` is the single ingress (:80/:443). WorldTwin = `caddy` + `aggregator` on
`worldtwin_edge`. Everything `company-*` / `jj-app` / `admin` / `agent-live` /
`searxng` is the OpenClaw platform — **separate tenants, leave them alone.**

```bash
ssh -i "$KEY" $H "docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'"
```

## Compose projects

```
/home/opc/worldtwin/            docker-compose.yml  (aggregator :8090 3GiB, + caddy)
/home/opc/openclaw-platform/    the tenant platform (caddy + company agents)
```
`/home/opc/openclaw-platform/weather` is a **symlink → /home/opc/worldtwin/weather**.

## Caddy routes (read-only inspect)

```bash
ssh -i "$KEY" $H "docker exec caddy cat /etc/caddy/Caddyfile"
```
Key routes: `/worldtwin*` + `/weather*` → `/srv/weather` (static frontend);
`/api/cache/*` + `/v1/cache/*` → gzipped from `/srv/cache`; `/api/*` + `/v1/*` →
`reverse_proxy aggregator:8090`; `/jj*` → `jj-app`; `/admin*` → `admin`
(basic_auth); `/water/*` and `/weatherwiz/*` are other tenants.
**There is no `/proxy/*` route — keep it that way** (a proxy relay leaked a key once).

## Cron (WorldTwin jobs; `crontab -l`)

```
17 6 * * *  scripts/nightly_audit.py    → /var/log/wt-audit.log    (freshness email)
17 5 * * *  scripts/editor_probe.sh      → /var/log/wt-editor.log
43 3 * * 0  scripts/wal_truncate.sh      → /var/log/wt-wal-truncate.log  (Sundays)
*/2 * * * * scripts/mem_watchdog.sh      → /var/log/wt-mem-watchdog.log
```
(`platform_monitor.sh` /30 min and `jj-backup.sh` nightly belong to OpenClaw/J&J.)

## Logs

```bash
ssh -i "$KEY" $H "cd /home/opc/worldtwin && docker compose logs --tail 60 aggregator"
ssh -i "$KEY" $H "tail -n 40 /var/log/wt-*.log"
```

## Golden rule

Recovery is **single-container only**. Never `systemctl restart docker` — it
kills every tenant on this box. See `/disk-maintenance` and `docs/operations.md`.
Broader platform context: `Solo/Multi-Tenant-AI-Agent-Oracle-Cloud-Deployment-Guide.md`.
