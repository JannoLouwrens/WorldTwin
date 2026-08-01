# deploy/

Deployment fragments that live outside this repo's own tree on the server.

## Caddyfile.worldtwin-tls.snippet

HTTPS for WorldTwin on `worldtwin.duckdns.org`, as a **separate Caddy site
block**. Appended to `/home/opc/openclaw-platform/Caddyfile` — that file is the
single ingress for the whole box, so the deliberate design here is that this
block adds a new hostname and changes nothing about the existing `:80` block
that carries the tenant routes (`/admin`, `/jj`, `company-*`) and the VPN paths.
Requests to the bare IP keep behaving exactly as they do today.

Caddy obtains and renews the Let's Encrypt certificate itself over HTTP-01 on
port 80, which is already open. No Cloudflare, no certbot, no cron.

### Prerequisites

1. `worldtwin.duckdns.org` must exist and resolve to this box (`129.151.191.74`).
   Create it at https://duckdns.org under the same account as `finebubble`.
2. Inbound TCP 443 must be permitted in the OCI security list for this VM.
   Port 80 already is. Caddy is already listening on 443.

### Applying it

```bash
cd /home/opc/openclaw-platform
cp Caddyfile Caddyfile.bak.$(date +%s)                    # rollback point
cat /home/opc/worldtwin/deploy/Caddyfile.worldtwin-tls.snippet >> Caddyfile

# Validate BEFORE reloading — an invalid config here takes down every tenant.
docker cp Caddyfile caddy:/tmp/Caddyfile.check
docker exec caddy caddy validate --config /tmp/Caddyfile.check --adapter caddyfile

# Graceful reload: on failure Caddy keeps serving the previous config.
docker exec -w /etc/caddy caddy caddy reload --config /etc/caddy/Caddyfile
```

Then confirm certificate issuance and that the tenants are undisturbed:

```bash
docker logs --tail 40 caddy | grep -i "certificate\|error"
curl -sI https://worldtwin.duckdns.org/worldtwin/ | head -3
curl -sI http://129.151.191.74/admin  | head -3     # should still be 401, not a redirect
```

### Rolling back

```bash
cd /home/opc/openclaw-platform
cp Caddyfile.bak.<timestamp> Caddyfile
docker exec -w /etc/caddy caddy caddy reload --config /etc/caddy/Caddyfile
```

### Note on the DuckDNS updater

`/home/opc/duckdns/update.sh` reads its token from `/home/opc/duckdns/.token`,
which does **not exist** — so the updater exits 1 on every run. It is not in
cron either. This is currently harmless because the box has a static public IP,
but if that ever changes, DNS will silently go stale. Restore the token file
(chmod 600) and add `worldtwin` to the `domains=` list if you want it
self-healing.
