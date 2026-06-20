# AGENTS.md — WorldTwin

Canonical, tool-agnostic brief for any AI coding agent working in this repo
(Claude Code, Antigravity, Cursor, …). Claude Code loads this via `@AGENTS.md`
at the top of `CLAUDE.md`. Keep it accurate and lean; push depth into the
referenced docs rather than restating it here.

## What this is

WorldTwin is an **evidence-first 3D geospatial intelligence globe**. A FastAPI
**plugin aggregator** (~95 auto-discovered Python data sources → atomic JSON
caches + a SQLite history store) feeds a **vanilla-JS CesiumJS frontend**. It
runs in Docker Compose on a single Oracle Cloud ARM free-tier box, served behind
the OpenClaw platform's Caddy. Live: `http://129.151.191.74/worldtwin/`
(`/weather/` is a back-compat alias for the same app).

The soul of the project is the Charter in `VISION.md`: every number carries its
source and timestamp; no fabricated/interpolated data without explicit marking;
gaps are shown, not hidden; the record is replayable. **Honour it** — when in
doubt, show less and mark provenance rather than fabricate.

## How I work (NON-NEGOTIABLE — applies to every change)

1. **Think Before Coding.** Don't assume; don't hide confusion; surface
   tradeoffs. Read the relevant module + `ARCHITECTURE.md` first. State the plan
   in 1–3 sentences. If multiple interpretations exist, present them — don't pick
   silently. If a simpler approach exists, say so. If something is unclear, stop
   and ask. Find the existing pattern and match it.
2. **Simplicity First.** Minimum code that solves the problem; nothing
   speculative. No new dependency, abstraction, service, or unrequested
   "flexibility". No error handling for impossible scenarios. If 200 lines could
   be 50, rewrite. Ask: "would a senior engineer call this overcomplicated?"
   This is a RAM-constrained box (3 GiB aggregator) — never add background
   services or metric collectors.
3. **Surgical Changes.** Touch only what the task needs. Don't reformat, rename,
   or "improve" adjacent code/comments/formatting. Don't refactor what isn't
   broken. Match existing style even if you'd do it differently. Remove only the
   imports/vars your change orphaned; leave pre-existing dead code (mention it,
   don't delete). Every changed line must trace directly to the request.
4. **Goal-Driven Execution.** Define a success criterion and loop until verified.
   Turn the task into a checkable goal ("add validation" → "write a test for bad
   input, then make it pass"). For multi-step work, state a brief plan with a
   verify check per step. Verify it actually works (`curl` the endpoint / load
   the page / 0 JS errors) before claiming done. Then stop — don't gold-plate.

## Commands

```bash
# Aggregator (backend) — runs uvicorn on :8090
python -m worldtwin                 # entry: aggregator/worldtwin/__main__.py → server.py
curl http://localhost:8090/api/health

# Frontend — NO build step. Serve frontend/ with any static server and point
# /api + /v1 + /worldtwin at the aggregator. Edit JS, reload, done.
```

There is **no test suite** and **no bundler/transpiler**. Verification is
empirical: hit the endpoint, load the globe, check the browser console is clean.
The "editor" (data correctness) is enforced by `scripts/nightly_audit.py` as a
cron probe, not by unit tests.

## Architecture (read `ARCHITECTURE.md` before any structural change)

- **Backend is the modular package `aggregator/worldtwin/`**: `registry.py`
  auto-discovers `sources/*.py`; `scheduler.py` refreshes each on its own clock;
  `server.py` is the FastAPI app (lifespan + routes); `cache.py` does atomic JSON
  writes; `history.py` is the SQLite WAL history store.
  - **`aggregator/worldtwin/aggregator.py` (and `aggregator/aggregator.py`) is a
    LEGACY monolith. Production does NOT run it. Do not edit it.** The Dockerfile
    only copies the `worldtwin/` package and runs `python -m worldtwin`.
- **Add a data source = drop ONE file** in `sources/` exporting
  `LAYER = LayerMeta(...)` + `async def fetch(client)` + `register(LAYER, fetch)`.
  No scheduler edit needed. This is real, not aspirational — see `aggregator/SDK.md`.
- **Frontend is modular vanilla JS in `frontend/`** (NOT a monolith).
  `config.json` is the single source of truth for layers/modes/mapmodes;
  `index.html` loads ~30 ordered modules; `layers.js`/`layers2.js` hold
  renderers; `mapmode.js` is the choropleth engine; `preloader.js` streams
  caches. The frontend reads `/api/cache/{id}.json`; layer ids map 1:1 to cache
  files. See `ARCHITECTURE.md` for the module load order and the
  `window.*` globals contract.
- **One AI call only**: `sources/ai_narrative.py` (Gemini, Claude fallback). Don't
  scatter LLM calls elsewhere.

## Secrets & safety (incidents have burned us — see `docs/operations.md`)

- **All API keys live ONLY in `.env`** (git-ignored). Never hardcode a key in
  code, docs, comments, config, or notebooks. Never commit `.env`. If a key
  leaks, scrub history with `git filter-repo` (not `git rm`) **and rotate**.
- **All external APIs are called server-side from plugins.** Never add a
  `/proxy/*` Caddy route or any client-side relay that forwards a key (this
  leaked the Windy key once).
- **Recovery is single-container only.** This box is multi-tenant. Never
  `systemctl restart docker` or do any daemon-wide restart — it SIGKILLs every
  other tenant. Recover the aggregator alone: `docker kill aggregator` / `rm -f`.

## Gotchas that have actually bitten

- Don't remove the boot **WAL-TRUNCATE** in `server.py` lifespan; it must run
  before scheduler workers spawn.
- Don't raise `PRAGMA wal_autocheckpoint` above 5000 or `mmap_size` above 256 MB
  (caused a 45 GB WAL → `/data` 100 % full → OOM incident).
- `SPACETRACK_DISABLED=1` is a kill-switch — don't flip it without checking rate
  limits (an eager query storm caused a multi-day Space-Track IP suspension).
- Mapmode repaint updates `window.MAPMODE_COLORS` read by a `CallbackProperty` —
  never set colours per-entity (1620 polygons/frame).
- Never `await` inside the frontend `batch()` helper (corrupts
  `suspendEvents`/`resumeEvents` nesting).
- The preloader is **not** awaited on boot (progressive first paint) — heavy
  layers lazy-fetch on toggle.
- Bump the `?v=BUILD_ID` cache-buster in `index.html` when you change
  `config.json` layer ids, or removed ids cause 404 spam.

## Reference map (read on demand — not auto-loaded)

| Need | File |
|---|---|
| System design, module order, globals, cache index | `ARCHITECTURE.md` |
| Every plugin: source / auth / refresh / status | `CATALOG.md`, `docs/sources/INDEX.md` |
| Source reliability + bias per feed | `DATA_TRUST_ASSESSMENT.md` |
| Write a new plugin (the contract) | `aggregator/SDK.md` |
| UI panel positions | `GUI_LAYOUT.md` |
| History/replay store internals | `docs/architecture/HISTORY_STORE.md` |
| Deploy/restart/force-fetch runbook | `docs/deploy.md` |
| Incident-derived ops rules (WAL, disk, memory) | `docs/operations.md` |
| Product direction + the Charter | `VISION.md` |

Server IP, SSH key path, and live container facts are **not** in this file —
they live in the `.claude/skills/` (for Claude Code) and `CLAUDE.local.md`
(git-ignored), because this repo is shared.
