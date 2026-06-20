---
name: deploy-frontend
description: Deploy the WorldTwin CesiumJS frontend to the Oracle server (scp frontend/ to /home/opc/worldtwin/weather/, served by Caddy at /worldtwin/) and verify the live page. Use when asked to deploy, ship, or push frontend/UI/JS/config changes to WorldTwin or update the live globe.
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, mcp__chrome-devtools__navigate_page, mcp__chrome-devtools__list_console_messages, mcp__chrome-devtools__take_screenshot
---

# Deploy the WorldTwin frontend

Manual-only (touches the live server). Read `CLAUDE.local.md` for the SSH key
path and confirm the live deploy path before starting. Full reference:
`docs/deploy.md`.

`KEY` and `H` below come from `CLAUDE.local.md`: read the SSH key path from there
(`KEY="<path from CLAUDE.local.md>"`, `H="opc@129.151.191.74"`).

## Steps

1. **Confirm the source of truth.** Deploy from this repo's `frontend/` only.
   `Solo/new_plugins` is stale — never deploy from it.

2. **Bump the cache-buster if `config.json` layer ids changed.** Edit
   `?v=BUILD_ID` in `frontend/index.html`. Skip if you only edited a JS file's
   internals. Stale config + removed ids = 404 spam.

3. **Copy the changed files** (only what changed — surgical):
   ```bash
   scp -i "$KEY" frontend/js/<file>.js  $H:/home/opc/worldtwin/weather/js/
   scp -i "$KEY" frontend/index.html    $H:/home/opc/worldtwin/weather/
   scp -i "$KEY" frontend/config.json   $H:/home/opc/worldtwin/weather/
   ```
   Caddy mounts `weather/` **read-only** → no container restart needed for static
   files. (`/home/opc/openclaw-platform/weather` is a symlink to the same dir.)

4. **Verify** at `http://129.151.191.74/worldtwin/`:
   - `navigate_page` there, hard-reload.
   - `list_console_messages` → confirm **0 JS errors**.
   - `take_screenshot` → confirm the globe renders and the changed feature works.
   - `curl -s http://129.151.191.74/api/cache/<id>.json | head -c 200` if the
     change depends on a cache.

5. **Rollback** if broken: before overwriting, you should have kept a `.bak`
   (`ssh -i "$KEY" $H "cp <path> <path>.bak"`); restore it and reload.

Done = clean console + visible correct render. "Should work" is not done.
