#!/bin/bash
# caddy probe sweep — bare IP (:80), worldtwin.duckdns.org, finebubble.duckdns.org
# Companion to CADDY_APPLY.md §1 (baseline) and §6 (post-reload). Read-only.
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
echo "GET /anything-else          -> $(s $W https://worldtwin.duckdns.org/anything-else) (expect 302 -> /worldtwin/ AFTER the candidate applies; pre-fix live returns an empty 200 — broken bare-redir catch-all)"
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
