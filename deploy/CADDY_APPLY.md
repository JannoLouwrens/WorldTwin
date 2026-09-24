# CADDY_APPLY — orchestrator runbook for Caddyfile.candidate (Edit G / REVIVAL §1.G, §6.13)

Applies `/home/opc/worldtwin/deploy/Caddyfile.candidate` to the LIVE
`/home/opc/openclaw-platform/Caddyfile` (bind-mounted read-only at
`/etc/caddy/Caddyfile` inside the `caddy` container).

Related but separate: `deploy/quarantine.sh` is the runnable REVIVAL §6.1
implementation (legal-breach cache quarantine + 404 probe sweep); it runs in
the deploy sequence after the aggregator restart, NOT as part of this Caddy
apply.

**Change scope (verified by diff, nothing else):**
1. `log` directive at the top of the `worldtwin.duckdns.org` site block only
   (JSON file on the caddy-data volume, 20MiB x 6 rotation, ip_mask 24/48,
   Cookie/Authorization deleted, User-Agent kept).
2. `Cache-Control` `public, max-age=10` → `public, max-age=60` in BOTH
   `handle /api/cache/*` blocks (`:80` and `worldtwin.duckdns.org`).
   The two `/v1/cache/*` blocks intentionally keep `max-age=10`.
3. Two NEW `handle` blocks in the `worldtwin.duckdns.org` site block serving
   `/robots.txt` and `/sitemap.xml` from `/srv/weather` (crawlers only ever
   fetch these at the host root — RFC 9309).
4. Catch-all fix in the same block: `redir /worldtwin/ 302` →
   `redir * /worldtwin/ 302`. The bare form parses `/worldtwin/` as an inline
   matcher and `302` as the redirect target, so unmatched paths currently get
   an empty 200 instead of the redirect (verified live).

The `:80` tenant block and `finebubble.duckdns.org` block are untouched —
their catch-alls (`respond ... 200`) are intentional.

**Invariants:** never `docker restart`/recreate/`compose up` the caddy
container — only an in-process `caddy reload`. Never `mv` or `sed -i` the
live file — it is bind-mounted, so the mount is pinned to the inode; the
write MUST be inode-preserving (`cp` onto the existing path).

---

## 0. Preconditions

```bash
# Candidate present and its diff vs live is EXACTLY the four scoped changes
# listed above: log block, two Cache-Control lines, the two new
# /robots.txt + /sitemap.xml handles, and the `redir * /worldtwin/ 302`
# catch-all fix (all within the worldtwin.duckdns.org block except the one
# :80 /api/cache Cache-Control line):
diff /home/opc/openclaw-platform/Caddyfile /home/opc/worldtwin/deploy/Caddyfile.candidate
# Caddy healthy:
docker ps --format '{{.Names}}\t{{.Status}}' | grep '^caddy'
```

If the diff shows anything beyond the four changes described above — STOP.

## 1. Baseline probe capture (BEFORE touching anything)

Run the probe script from §6 and save its output:

```bash
bash /home/opc/worldtwin/deploy/caddy_probes.snippet.sh > /tmp/caddy-probes.before.txt 2>&1 || true
# (If you haven't extracted the snippet, copy the probe block from §6 into a file first.)
```

Backend-dependent routes (VPN paths, /water, /demo/mcp, /mcp, /lrh/) are
compared before-vs-after, not against absolute values.

## 2. Timestamped backup

```bash
TS=$(date +%Y%m%d-%H%M%S)
cp -a /home/opc/openclaw-platform/Caddyfile "/home/opc/openclaw-platform/Caddyfile.bak.${TS}"
echo "backup: /home/opc/openclaw-platform/Caddyfile.bak.${TS}"
```

## 3. Inode-preserving apply

```bash
# cp truncates and rewrites the SAME inode. NEVER mv, NEVER sed -i,
# NEVER an editor that writes-then-renames — the container would keep
# seeing the old content forever.
cp /home/opc/worldtwin/deploy/Caddyfile.candidate /home/opc/openclaw-platform/Caddyfile
```

## 4. Assert the container sees the new bytes, then validate

```bash
H_HOST=$(sha256sum /home/opc/openclaw-platform/Caddyfile | awk '{print $1}')
H_CTR=$(docker exec caddy sha256sum /etc/caddy/Caddyfile | awk '{print $1}')
[ "$H_HOST" = "$H_CTR" ] && echo "SHA256 MATCH: $H_HOST" || { echo "SHA256 MISMATCH — inode was replaced. Roll back (step 7) NOW."; }

docker exec caddy caddy validate --config /etc/caddy/Caddyfile
# Must end with: Valid configuration
```

Do not reload unless BOTH the sha256 match and validate pass.

## 5. Reload (graceful, in-process)

```bash
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Note: the reload closes currently-proxied WebSockets ONCE — that includes
the owner's VPN tunnels on `/xr8k3vq2ws*` and `/wt7g2xk9tunnel*`. The
clients reconnect automatically; no action needed.

## 6. Post-reload probes — every route of all three site blocks

Run and diff against the §1 baseline. Expected statuses per the LIVE config:

```bash
#!/bin/bash
# caddy probe sweep — bare IP (:80), worldtwin.duckdns.org, finebubble.duckdns.org
s() { curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$@"; }
h() { curl -skI --max-time 10 "$@" | tr -d '\r' | grep -i "^$2:" ; }
W='--resolve worldtwin.duckdns.org:443:127.0.0.1'
F='--resolve finebubble.duckdns.org:443:127.0.0.1'

echo "=== :80 (bare IP / tenant block) ==="
echo "GET /                       -> $(s http://127.0.0.1/)                (expect 200 'OpenClaw Platform')"
echo "GET /xr8k3vq2ws             -> $(s http://127.0.0.1/xr8k3vq2ws)      (XRay VLESS-WS: non-upgrade GET returns backend's 4xx — MUST EQUAL BASELINE; 101 only under a real WS handshake)"
echo "GET /wt7g2xk9tunnel         -> $(s http://127.0.0.1/wt7g2xk9tunnel)  (wstunnel: same rule — equal baseline; 101 under real handshake)"
echo "GET /worldtwin/             -> $(s http://127.0.0.1/worldtwin/)      (expect 200)"
echo "GET /weather/               -> $(s http://127.0.0.1/weather/)        (expect 200, back-compat alias)"
echo "GET /weatherwiz             -> $(s http://127.0.0.1/weatherwiz)      (expect 301 -> /weatherwiz/)"
echo "GET /weatherwiz/            -> $(s http://127.0.0.1/weatherwiz/)     (expect 200)"
echo "GET /api/cache/quakes.json  -> $(s http://127.0.0.1/api/cache/quakes.json) (expect 200)"
echo "    Cache-Control:             $(h http://127.0.0.1/api/cache/quakes.json Cache-Control) (MUST be: public, max-age=60  <- NEW)"
echo "GET /api/health             -> $(s http://127.0.0.1/api/health)      (expect 200; 502 = aggregator down, not a Caddy fault)"
echo "GET /v1/cache/quakes.json   -> $(s http://127.0.0.1/v1/cache/quakes.json) (200 or 404 per file presence — equal baseline)"
echo "    Cache-Control:             $(h http://127.0.0.1/v1/cache/quakes.json Cache-Control) (MUST STILL be: public, max-age=10 — unchanged by design)"
echo "GET /v1/                    -> $(s http://127.0.0.1/v1/)             (proxied to aggregator — equal baseline)"
echo "GET /jj                     -> $(s http://127.0.0.1/jj)              (expect 401 without credentials)"
echo "GET /admin                  -> $(s http://127.0.0.1/admin)           (expect 401 without credentials)"
echo "GET /water                  -> $(s http://127.0.0.1/water)           (expect 301 -> /water/)"
echo "GET /water/                 -> $(s http://127.0.0.1/water/)          (backend 172.19.0.1:8077 — equal baseline; 200 when the water app is up)"

echo "=== worldtwin.duckdns.org (TLS) ==="
echo "GET /                       -> $(s $W https://worldtwin.duckdns.org/)            (expect 302 -> /worldtwin/)"
echo "GET /worldtwin/             -> $(s $W https://worldtwin.duckdns.org/worldtwin/)  (expect 200)"
echo "GET /api/health             -> $(s $W https://worldtwin.duckdns.org/api/health)  (expect 200)"
echo "GET /api/cache/quakes.json  -> $(s $W https://worldtwin.duckdns.org/api/cache/quakes.json) (expect 200)"
echo "    Cache-Control:             $(h "https://worldtwin.duckdns.org/api/cache/quakes.json" Cache-Control $W) (MUST be: public, max-age=60  <- NEW)"
echo "GET /v1/cache/quakes.json   -> $(s $W https://worldtwin.duckdns.org/v1/cache/quakes.json) (200/404 — equal baseline; Cache-Control still max-age=10)"
echo "GET /robots.txt             -> $(s $W https://worldtwin.duckdns.org/robots.txt)   (expect 200 with 'Sitemap:' in body <- NEW handle; pre-fix baseline is an empty 200)"
echo "    Sitemap line:              $(curl -sk --max-time 10 $W https://worldtwin.duckdns.org/robots.txt | grep -i '^Sitemap:')"
echo "GET /sitemap.xml            -> $(s $W https://worldtwin.duckdns.org/sitemap.xml)  (expect 200 <- NEW handle; pre-fix baseline is an empty 200)"
echo "GET /anything-else          -> $(s $W https://worldtwin.duckdns.org/anything-else) (expect 302 -> /worldtwin/ AFTER this apply; pre-fix live returns an empty 200 — broken bare-redir catch-all)"
echo "    Location:                  $(h https://worldtwin.duckdns.org/anything-else Location $W) (MUST be: /worldtwin/ after apply)"

echo "=== finebubble.duckdns.org (TLS, Host-header curls) ==="
echo "GET /                       -> $(s $F https://finebubble.duckdns.org/)         (expect 200 'ok')"
echo "GET /demo                   -> $(s $F https://finebubble.duckdns.org/demo)     (expect 401 without credentials)"
echo "GET /demo/mcp               -> $(s $F https://finebubble.duckdns.org/demo/mcp) (proxied jj-demo:8091, no basic auth — equal baseline)"
echo "GET /mcp                    -> $(s $F https://finebubble.duckdns.org/mcp)      (proxied jj-app:8091 — equal baseline)"
echo "GET /jj                     -> $(s $F https://finebubble.duckdns.org/jj)       (expect 401 without credentials)"
echo "GET /lrh                    -> $(s $F https://finebubble.duckdns.org/lrh)      (expect 308 -> /lrh/)"
echo "GET /lrh/                   -> $(s $F https://finebubble.duckdns.org/lrh/)     (proxied lrh-chatbot:8000 — equal baseline; 200 when up)"

echo "=== new access log ==="
docker exec caddy ls -l /data/logs/ 2>&1   # worldtwin.json must exist after the worldtwin.duckdns.org requests above
docker exec caddy sh -c 'tail -1 /data/logs/worldtwin.json' 2>/dev/null | head -c 600; echo
# Assert in that sample line: remote_ip ends .0 (v4 /24 mask), NO Cookie, NO Authorization, User-Agent PRESENT.
```

**Pass criteria:** every "expect NNN" matches; every "equal baseline" route
returns the same status as the §1 capture; both `/api/cache/*` probes show
`Cache-Control: public, max-age=60`; both `/v1/cache/*` probes still show
`max-age=10`; `/robots.txt` returns 200 with a `Sitemap:` line in the body;
`/sitemap.xml` returns 200; `/anything-else` returns 302 with
`Location: /worldtwin/` (these three are expected to DIFFER from the §1
baseline, which captures the pre-fix empty 200s); `/data/logs/worldtwin.json`
exists, its lines carry a masked `remote_ip` and a `User-Agent`, and carry no
Cookie/Authorization.

Any tenant route regressing (`/`, `/jj`, `/admin`, `/water/`, `/demo*`,
`/mcp`, `/lrh/`, VPN paths) → roll back immediately.

## 7. Rollback

```bash
# Same inode-preserving rule applies to the rollback.
# Find the newest step-2 backup (Caddyfile.bak.<YYYYmmdd-HHMMSS>). The 2* prefix
# excludes all legacy Caddyfile.bak.* files (epoch-named, .water, .wstun, .xray, .lrh)
# — NEVER restore those; they predate current tenant routes.
BAK=$(ls -1 /home/opc/openclaw-platform/Caddyfile.bak.2* 2>/dev/null | sort | tail -1)
[ -n "$BAK" ] && echo "restoring $BAK" \
  && cp "$BAK" /home/opc/openclaw-platform/Caddyfile \
  || { echo "NO timestamped backup found or cp failed — STOP. Do not guess among legacy .bak files, and do NOT run validate/reload: the sha256 check would falsely match the unchanged (bad) live file."; false; }
# Proceed below ONLY if the restore above succeeded:
H_HOST=$(sha256sum /home/opc/openclaw-platform/Caddyfile | awk '{print $1}')
H_CTR=$(docker exec caddy sha256sum /etc/caddy/Caddyfile | awk '{print $1}')
[ "$H_HOST" = "$H_CTR" ] || echo "SHA256 MISMATCH after rollback — investigate the mount before reloading"
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
# Re-run the §6 probes; all routes must match the §1 baseline (Cache-Control back to max-age=10).
```

(The rollback reload closes the proxied VPN WebSockets once more — they
reconnect automatically.)
