# REVIVAL_V1 — executing MASTER_PLAN Stages 0–3 (+slices of 2/5) in one autonomous session

*Written 2026-09-24 by Claude (Fable 5), on the owner's instruction to implement the vision
("do what you must, don't stop until it works"). This document is the session's execution
contract. It follows docs/MASTER_PLAN.md (2026-08-01) and deviates only where reality
changed after the plan was written, or where an action requires the owner (money, outward
communication). Every deviation is listed in §5.*

## 1. What ships this session

Six logical commits, each independently STOP-SAFE:

- **A — Safety (Stage 0a subset).** Legal-breach files quarantined off the served paths
  (spacetrack_gp.json, webcams.json, orphans trade.json/country_exports.json) — moved to
  `/data/quarantine/` (not destroyed: evidence + reversibility; the breach is *serving*, and
  quarantine ends that). webcams plugin `enabled=False`. Maintenance lock in
  `mem_watchdog.sh` (90-min expiry) honoured by `wal_truncate.sh` (fixes the Sunday race);
  `wal_truncate.sh` additionally exits early when WAL < 1 MB (ends the pointless weekly
  restart of a frozen store). Aggregator compose: `HEALTHCHECK` + `cpus: 2.0`. Caddy memory
  cap 128→512 MiB via `docker update` (zero-downtime; persisted in the platform compose
  file, file edit only — no `up`). `/api/history/sources` 400s without `prefix`; snapshot
  decompression capped 8 MB.
- **B — Honesty (Stage 0b).** `scheduler.py`: `mark_error` on `result is None`;
  NET_SEM(16)/CPU_SEM(2) split; `t0` inside the acquire; `_status` persisted to
  `/cache/v1/_status.json`, seeded at boot, durable `last_success_at`. `models.py`: one
  edit adding defaulted `max_staleness_s, retired_reason, heavy, max_bytes, history_policy,
  family, provenance`. `server.py`: `/api/health` **computed, never asserted** — every
  enabled layer present, `ok` from fetch-age vs `refresh_s`-relative grace AND
  `max_staleness_s`; `retired` a first-class excluded state; response stays
  backward-compatible (same per-layer keys; consumers `weather/js/ui.js` and
  `app/src/components/Freshness.tsx` verified against it). **Broken-feed repairs:**
  gdacs_events per-`eventtype` loop over EQ/TC/FL/VO/DR/WF (verified live 2026-09-24 —
  deviation from the plan's rss_7d.xml, see §5.3); imf_data → `api.imf.org` SDMX (plan
  verified 200 from this box); population → vendored `mledoze/countries` +
  `world_bank SP.POP.TOTL`. **Sentencing:** the long tail flips `enabled=False` +
  `retired_reason` per the §4 tier table; enabled set = locked core (quakes, fires 600→3600,
  gdacs_events, volcanoes 86400→604800 + usgs_volcano_hans, flights, swpc_aurora,
  cloudflare_radar 1800→21600) + country_polygons + brief-only noaa_co2, fred (Q2 silence
  default: locked set now, candidates admitted later one at a time through the gate).
  gaming/youtube/sports/pulse_mode/global_events-GKG/gemini_narrative stop publishing.
  Tombstone envelopes (`state:'retired'`, reason, `data:[]`) written for retired/dropped
  layers — previous cache bytes moved to `/data/quarantine/retired-caches/`, so the flip is
  fully reversible. Exception: spacetrack_gp + webcams are hard 404s, never tombstones. The
  one permitted Cesium-client code change: `weather/js/layer-browser.js` renders
  `state:'retired'` inline with reason, toggle disabled. ships: world-bbox → chokepoint
  bboxes, prune moved into the WS ingest loop. Licence-string corrections (the twelve) +
  `docs/LICENCES.md`.
- **C — Contract (Stage 2 subset).** `cache.write_manifest()` atomic in the envelope commit
  path (`/data/cache/v1/manifest.json`, all 92 entries incl. tombstones, computed `state`);
  `cache.write_counts()` daily ledger (`counts.json`, no-entry-never-zero); `.data.json`
  duplicate write deleted + existing duplicates quarantined; `nightly_audit.py` rewritten to
  assertions A–F over the manifest (Gmail send path untouched); audit footer URL fixed.
- **D — The brief (Stage 1).** `scripts/build_brief.py`, stdlib only, reads static files
  only (manifest + envelopes + yesterday's brief JSON), writes
  `weather/brief/{YYYY-MM-DD.html,YYYY-MM-DD.json,index.html,feed.xml}`. Six sections per
  the Stage-4 content spec: pipeline-state masthead, largest quake, highest GDACS alert,
  fires vs own 7-day median (from counts.json; renders "record since <date>" until 7 days
  exist), instrument-of-the-day, went_dark/came_back **delta** vs yesterday's JSON;
  exception-led lede with "Nothing crossed a threshold today" fallback; per-item windowing
  that publishes absence by name; absence contract (never partial, `_failures.log`, 3-day
  banner). RSS 2.0 forward-dated only. Cron `47 6 * * *` (see §6.17 and §4); generated for
  today immediately.
  Archive git repo initialised in `weather/brief/` with a daily local commit
  (`archive_push.sh`; off-Oracle push prepared but requires an owner deploy key — §5.6).
- **E — Doctrine surfaces (Stage 3 subset, no domain).** `weather/charter.html`: the five
  rules verbatim, "Not in this version", the archive retention window, and **the required
  Q4 disclosure: all recorded observations and snapshots covering 2026-06-11 → 2026-08-09
  were destroyed on 2026-08-09; the archive restarts 2026-09-24**. `weather/status.html`:
  the full 92-row ledger rendered client-side from manifest.json — counts computed, never
  hardcoded. `robots.txt`, `sitemap.xml`, real 404 behaviour where cheap. Masthead links
  (Brief · Status · Charter · New globe) added to the legacy client and v2 (§5.5 notes the
  extra Cesium edit). deploy/README.md corrected: 443 verified open externally 2026-09-24.
- **F — v2 client (Stage 5 subset).** `aggregator/worldtwin/render.py` (adaptive bins,
  `cos(lat)` area weighting, `LEAN_GZ_BUDGET=120_000`) + one call in the envelope commit
  path; `app/src`: `lib/renderSlice.ts`, `layers/families.ts` (3 validated hues + ramps),
  registry → quakes, gdacs_events (on once fix verified), volcanoes on:true, fires (render
  slice), flights, cloudflare_radar outages; toggle reducer enforcing 1 focused / ≤3
  context / ≤1 per family / ≤4 total; per-layer TTL-multiple freshness (fresh ≤1×, late
  1–3×, stale >3×, 6 h floor) with hollow stale marks; header counter "N / 92 sources
  reporting" from manifest.counts; glow-then-symbol ordering; touchPitch off +
  disableRotation; `maximum-scale=1` dropped. Deferred to a later session: terminator,
  Plane sparkline (needs ≥2 days of counts), table view, urlState, GIBS label swap, tile
  mirror.
- **G — Ingress (one validated Caddy reload, Edit 1 scope-reduced).** Access log (ip_mask
  24/48, Cookie/Authorization deleted) to the caddy-data volume; `precompressed gzip` and
  corrected Cache-Control on both `/api/cache/*` blocks. Applied by the orchestrator only
  (never an agent): backup → edit → `caddy validate` → `caddy reload` → immediate probe of
  every tenant route + worldtwin routes. Rollback = restore backup + reload.

## 2. Verification (the "use Playwright" mandate)

Every deploy step ends in a browser check on the box (Xvfb/llvmpipe per
scripts/shoot-globe.mjs; SwiftShader for v2-smoke):
1. `smoke-test.mjs` against `/worldtwin/` — 10 plausibility checks still pass; legacy boots
   with tombstoned layers showing reasons, not silent no-ops.
2. `v2-smoke.mjs` against `/worldtwin/v2/` — both viewports, zero console errors, layer
   sheet rows show counts + sources.
3. New `brief-smoke.mjs` — `/worldtwin/brief/` index + today's page + feed.xml parse; charter
   + status render with computed counts.
4. `shoot-globe.mjs` screenshots reviewed (I read the PNGs) for the Stage-5 visual
   assertions that apply (no glow over shapes, focused > context).
5. Backend asserts via curl: health computed (gdacs_events present; no hardcoded ok),
   manifest fresh, tombstones served, spacetrack/webcams 404, counts.json entry for today.
6. `docker logs` clean-scan: worker count ≈ enabled set, no tracebacks, gdacs fetch OK.

## 3. Execution order and file ownership (no plan writes a file it does not own)

1. Pre-work (orchestrator): commit the two dirty Playwright diffs; mkdir /data/quarantine.
2. backend agent: scheduler.py, cache.py, models.py, server.py, render.py, history.py gates.
3. sources agent: sources/*.py (flag flips, gdacs, imf, population, ships, cadences,
   licence strings), docs/LICENCES.md, scripts/write_tombstones.py.
4. product agent: build_brief.py, brief-smoke.mjs, charter/status/robots/sitemap, masthead
   links, archive_push.sh, nightly_audit.py rewrite, deploy/README fix.
5. ops agent: mem_watchdog.sh, wal_truncate.sh, both compose files, Caddyfile candidate
   (staged copy — orchestrator applies).
6. frontend agent: app/src/** only.
7. Orchestrator, in the §6.2/§6.12 order: v2 build+deploy FIRST (explaining UI live before
   the count drop) → refresh .maintenance → `docker compose up -d` aggregator (recreate,
   not `docker restart`, so HEALTHCHECK+cpus apply) → verify "[scheduler] started 11
   workers" → host-side quarantine (deploy/quarantine.sh, sudo for the root-owned v1
   tree) → `docker exec aggregator python -m worldtwin.tombstones` → gzip-encoded 404
   probes → Caddy apply → crontab → Playwright loop → commits → remove .maintenance.

Tracks 2–6 run in parallel where files don't overlap; the envelope-commit call sites
(cache.py) are backend-owned — sources/frontend agents never touch them.

## 4. Live-box safety rails (non-negotiable)

Single-container actions only (aggregator). Caddy: `docker update` memory (no recreate) and
one validated in-process reload; **never** restart/recreate, never touch tenant blocks, no
mount/port/compose-`up` changes on the platform stack. No history re-enablement
(HISTORY_POLICY_DEFAULT stays "none"). Nothing writes to history.sqlite. All quarantines
are moves, not deletions. Every cron added is flock+timeout-guarded, ≤1 min/core, off the
06:15–06:45 window except the plan-specified brief slot 06:35→06:47 (audit at 06:17
finishes in seconds; brief moved to 06:47 to respect the window rule).

## 5. Deviations from MASTER_PLAN, with reasons

1. **No backfilled briefs / no facts extraction.** Stage 0a's `backfill_brief_facts.py` is
   impossible: the history store was emptied to 0 rows on 2026-08-09. The archive begins
   2026-09-24 and the destroyed range is disclosed on /charter (Q4's "accept and record",
   which the plan already named as the default).
2. **No domain purchase (Stage 3), no community posting (Stage 1 distribution), no
   CelesTrak delisting email.** Money and outward-facing owner-voice actions. The pilot runs
   on worldtwin.duckdns.org — which external probing on 2026-09-24 proved fully reachable
   (the OCI 443 block documented in deploy/README.md was lifted ~Aug 21–31), so the plan's
   "DNSBL-biased denominator" caveat is noted but the link is at least shareable.
3. **GDACS via the parameterised JSON API, not rss_7d.xml.** The plan believed the JSON API
   dead; it isn't — it now requires exactly one `eventtype` per request. Verified working
   from this box today with a byte-compatible response shape; a six-value loop is a smaller,
   lower-risk diff than a new XML parser. If GDACS breaks the JSON contract again, fall back
   to the plan's RSS approach.
4. **gemini_narrative retired (enabled=False + tombstone), not deleted.** D4's outcome — no
   generated content served anywhere — is achieved; keeping the file is STOP-SAFE and
   reversible, and deleting code is a one-keystroke owner decision later. The nightly audit
   email's LLM "council" section is likewise stubbed to deterministic-only.
5. **A second one-line Cesium-client edit (masthead links).** The plan allows exactly one
   (layer-browser retired rendering). Without the Stage-3 root move, the brief/charter/
   status/v2 surfaces are undiscoverable from the front door; a nav row is the minimum
   deviation that makes the pilot measurable. Documented here so the accretion rule stays
   enforceable.
6. **Archive push is local-first.** `git init` + daily commit in weather/brief/ ships now;
   the off-Oracle push (Stage 4/D19) needs a new GitHub deploy key only the owner can mint.
   Flagged prominently in the final report — until then the archive has no off-box copy.
7. **Candidate layers deferred** per Q2's silence default. nhc_cyclones first when admitted.
8. **Caddy Edit 1 scope-reduced** to log + precompressed + Cache-Control (drops /beacon,
   junk-404s, @notget for now) — smallest change that makes visitors measurable, on the
   shared ingress where diff size is risk.

## 6. Design-review deltas (2026-09-24, three-judge adversarial review — all binding)

1. **Quarantine by glob, both trees, all variants.** `{spacetrack_gp,webcams,trade,country_exports}*`
   moved from BOTH `/data/cache/` and `/data/cache/v1/` — `.json`, `.json.gz`, `.data.json`,
   `.data.json.gz`. Acceptance probes curl every variant URL **with `Accept-Encoding: gzip`**
   and assert 404 (Caddy `precompressed gzip` serves stale sidecars otherwise; both live
   `/api/cache/*` blocks already carry `precompressed gzip`, so that part of Edit G is a no-op).
2. **Order: restart first, then quarantine + tombstones.** `enabled=False` only takes effect
   at `start_all`; webcams re-fetched at 09:04 today. Sequence: deploy code → restart
   aggregator → verify worker count == enabled set in logs → host-side quarantine moves →
   `docker exec aggregator python -m worldtwin.tombstones` → probes. Orchestrator holds a
   refreshed `.maintenance` lock across this window.
3. **Tombstones to BOTH trees** (`/cache/<id>.json` legacy + `/cache/v1/<id>.json`), written
   via `cache._atomic_write` (which auto-drops stale `.gz` sidecars for small files);
   `.data.json` siblings quarantined host-side for ALL layers (the write is being deleted
   anyway). Tombstone mtimes backdated so the restart-amnesia gate can never make a future
   un-retire sleep out a full refresh_s.
4. **HEALTHCHECK via python, not curl** (image is python:3.12-slim, no curl):
   `test: ["CMD","python","-c","import urllib.request;urllib.request.urlopen('http://localhost:8090/api/health',timeout=5)"]`,
   interval 60 s, retries 3.
5. **sanity.sweep_and_tag runs once in the scheduler, feeding both writers** (restores the
   plan's Commit-0b item this design had dropped; v2 currently consumes un-sanitised v1 files).
6. **Manifest/counts writes serialized**: module-level `threading.Lock` around build+write;
   `_atomic_write` gains unique tmp names (`tempfile.mkstemp` in-directory). In-memory
   manifest dict seeded at boot from registry + one disk scan (all ~92 entries present from
   first flush), updated per envelope commit, flushed atomically.
7. **Computed `ok` derives from the envelope's own `fetched_at` / durable `last_success_at`
   — never `_status.last_fetch`** (mark_error updates it). Grace: `now − last_success_at <
   max(3×refresh_s, 1800 s)`, plus `max_staleness_s` vs `max(data_period)` where declared.
   `mark_error` preserves `last_success_at`. Health emits exactly the enabled set (registry-
   filtered); retired layers excluded from the error budget and from the legacy pill's math.
8. **No secrets on served paths**: `_status` persists to `/history/_status.json` (mounted,
   not served), AND `mark_error` scrubs URLs/query strings from error text before storing —
   httpx errors embed full request URLs incl. `api_key=`/FIRMS path keys (this also fixes
   the pre-existing `/api/health` leak). Manifest `state_detail` uses scrubbed text only.
9. **cloudflare_radar**: split `ddos_targets` out of the payload (plan-mandated) AND the v2
   registry gives it an explicit extractor reading `data.outages` by name — the generic
   first-array extractor would render DDoS centroids as outages whenever `outages == []`.
10. **gdacs partial-failure semantics**: all six eventtype requests must succeed or fetch()
    returns None (keep cache; failure surfaces via computed staleness). No silently smaller
    feed. Existing (eventid, episodeid) dedupe handles the concatenated lists.
11. **ships/imf_data/population NOT rewritten now** — all three are RETIRE/DROP tier; the
    tier table applies Action-column fixes at un-retire time. Retiring ships also ends the
    ~1/min websocket churn. (Deviation §5.9: their repairs move to un-retire.)
12. **Enabled set locked (11 workers)**: quakes, fires (3600), gdacs_events, volcanoes
    (604800), usgs_volcano_hans, flights, swpc_aurora, cloudflare_radar (21600),
    country_polygons, noaa_co2, fred. spacetrack_gp and webcams get `enabled=False` AND
    hard-404 (belt and braces). v2 built+deployed with the source counter and its context
    sentence BEFORE the aggregator restart, so the explaining UI is live before the visible
    count drop; counter falls back to /api/health-derived counts until manifest.json exists.
13. **Caddy apply protocol**: candidate generated from the LIVE 205-line file (it has a
    third site block since the plan); inode-preserving write (`cp`/`cat >`, never mv/sed -i
    — the file is bind-mounted); assert in-container sha256 == host file; `caddy validate`;
    reload; post-reload probes enumerate every route of all three site blocks (incl. /admin,
    /jj, /demo, /mcp, /lrh, /water, VPN paths) AND assert the new Cache-Control values, not
    just status codes. Note: reload closes proxied WebSockets once (owner's VPN reconnects).
    `log` directive goes in the worldtwin.duckdns.org block ONLY (tenant/VPN traffic stays
    unlogged by choice); rotation bounded 20 MiB × 6; /var/oled is at 64% with 5.6 GB free —
    the rewritten audit adds a /var/oled floor assertion.
14. **docker update needs both flags**: `docker update --memory 512m --memory-swap 512m caddy`
    (current MemorySwap=256 MiB rejects a bare --memory 512m).
15. **wal_truncate takes the lock with `trap 'rm -f "$LOCK"' EXIT INT TERM`**; watchdog
    honours it with 90-min expiry (wal_truncate worst case ~12 min).
16. **layer-browser edit also covers the two hard-404 ids** (spacetrack_gp, webcams render
    as "removed for licence compliance", toggles disabled) so Stage-0's "every toggle states
    why" holds for exactly the two legal cases; tombstones cover the rest.
17. **Brief day-1 bootstrap**: no yesterday-JSON → went_dark/came_back render "first day of
    record" honestly; instrument pool reduced to enabled sources (Cloudflare outages, SWPC
    Kp, NOAA CO₂, FRED Brent); audit assertion F points at weather/brief/ (the actual path);
    `weather/brief/` added to the parent .gitignore (embedded archive repo must not churn
    the parent tree). Retired sources are never listed as "went dark" — retirement is a
    dated tombstone, not a failure.
18. **RENDER_CAP deleted in the same commit that lands renderSlice.ts**; `.data.json`
    removal noted in the commit message as also removing the undocumented `/api/{layer_id}`
    fallback (no checked-in client uses it).

## 7. Acceptance (this session)

Stage-0 acceptance items that apply, plus: today's brief exists, validates, and is linked;
/charter discloses the destroyed range; /status lists 92 with computed counts; health shows
gdacs_events fetching OK and no hardcoded ok; scheduler worker count equals the enabled
set; spacetrack/webcams 404; all three Playwright suites pass; every tenant route returns
the same status before and after the Caddy reload; `git log` shows the work in reviewable
commits; and the surfaces added remain correct, or visibly and honestly dark, with zero
human attention for 60 days.
