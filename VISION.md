# WorldTwin — Vision & Design Decisions

*Written 2026-06-11, after a full end-to-end review of the system (backend, 90 plugins,
history store, frontend, data visualization, live deployment).*

## The vision is already in the codebase

This project's soul is not "a globe with layers." It is written, verbatim, in its own
source code:

> *"Vision: A lab where anyone can read the world from raw, dated, cross-checked
> sources."* — `cache.py`

> *"…so the lab REMEMBERS."* — the History Store

> *"A lab admits its own gaps. Silence becomes information."* — the dossier
> coverage panel

> *"A news source built from actual data — not headlines… see what's happening
> instead of reading what someone says is happening."* — the welcome card

And one decision made during review that defines the ethic better than any slogan:
the satellites layer was plotting random positions as placeholders — **it was disabled
rather than shipped**, because the one thing a news source of actual data can never
do is show fake data.

So the vision, named: **evidence-first news.** Not commentary, not headlines —
the primary readings themselves, with provenance, freshness, admitted gaps, and
memory. Every mechanism built so far (provenance tooltips with source + year +
reconstruction tags, the sanity sweep that nulls impossible values *and says so*,
the empty-clobber guard that refuses to pretend an outage is "no events", the
content-hashed history that can replay any past day) is an editorial standard
implemented as engineering. That is rare and it is the moat.

---

## The Charter (doctrine, make it public)

Five rules the system already lives by — formalize them on a `/charter` page and
link it from the welcome card:

1. **Every number carries its source and its timestamp.** No orphan claims.
2. **No fabricated or interpolated data without explicit marking.** (Reconstructions
   are labeled reconstructions.)
3. **Gaps are shown, not hidden.** A silent source is displayed as silent.
4. **The record is permanent.** What we showed on any date is replayable; corrections
   add to history, they don't erase it.
5. **Raw is one click away.** Any rendered value can be traced to the cached payload
   and the upstream URL.

---

## Design decisions

### Now — reach (the site cannot spread as an IP address)

**D1. Domain + HTTPS + Cloudflare free tier in front.**
`http://129.151.191.74` cannot be shared, embedded, indexed, or trusted by a browser.
A ~R150/yr domain + Cloudflare (free) gives TLS, a global CDN over the static JSON
caches (marginal cost per reader → ~0 on the free-tier box), and DDoS shielding.
Single highest-leverage change; near-zero cost.

**D2. URL = state.**
Serialize camera, mapmode, active layers, and scrubber year into query params; parse
them on boot. Every interesting view becomes a shareable link — the growth loop is
"look at THIS", and right now that link cannot be made. Also the prerequisite for
embeds. (~150 LOC: `url-state.js`.)

**D3. Fast first globe.**
Split `world_bank.json` (18 MB) into `latest` (~2 MB hot path) + lazily fetched
history; enable gzip/zstd in Caddy for `/api/cache/*`. Target: globe interactive
< 3 s on a median connection.

### Next — the front door (people don't arrive wanting 65 toggles)

**D4. The Daily Earth Brief.**
An auto-generated "what changed on Earth in the last 24 h" page — 3–5 stories, each
anchored to numbers and deep-linked (D2) to the exact globe view. The Gemini
narrative pipeline already exists; give it a permanent URL, an RSS feed, and a
share-card image. This is the habit-forming entry point; the globe is the rabbit hole
behind it.

**D5. Provenance chip as a universal UI primitive.**
One component — `source · fetched-age · license` — rendered identically in tooltips,
cards, dossier, and briefing. Freshness past 2× refresh turns it amber. Trust must
be *visible at every number*, not asserted on an about page.

**D6. One detail surface.**
Three card systems currently stack at top-right (Cesium infoBox, pickCard, dossier).
Collapse to one: the dossier is the single right-lane surface; entity clicks render
a compact section inside it. One lane, one card, zero overlap.

### Then — the distinctive features no one else has

**D7. The Time Machine as the signature.**
"See Earth on any day" — a prominent date picker powered by the history store's
snapshot replay. Earth.nullschool shows now; Bloomberg shows markets; nobody offers
*the planet's dashboard, replayable*. The memory is the product.

**D8. Beachhead audiences, in order.**
1. **Educators/students** — the 800,000 BC → today scrubber is a living history
   textbook; one teacher = thirty recurring readers. Make a "classroom mode" lens.
2. **Journalists** — per-layer embed widgets + a citation generator ("WorldTwin,
   UCDP GED, fetched 2026-06-11").
3. **Data-curious social** — D4's shareable moments.
Defer pro/defense analysts: they need SLAs a free-tier box cannot promise.

**D9. Editorial discipline as CI.**
The audits that found empty-with-status-ok caches were manual. Make them a nightly
probe: every cache checked for emptiness, staleness, and shape drift against its
renderer; failures page loudly. A newsroom has editors; this newsroom's editor is
a cron job.

**D10. Stay honest about the box.**
One free ARM VM is part of the story ("the whole world's dashboard runs on a free
server") but capacity planning is a vision constraint: CDN-first (D1), static-first
(already true — Caddy serves caches without touching Python), and graceful
degradation before any paid scaling.

---

## Sequence

| Phase | Items | Outcome |
|---|---|---|
| Now | D1 domain+TLS+CDN, D3 fast boot, D2 URL state | shareable, fast, linkable |
| Next | D4 Daily Brief, D5 provenance chip, D6 one card | a front door + visible trust |
| Then | D7 time machine, D8 outreach, D9 CI editor | the moat, the audience, the discipline |

The thesis behind all of it: **in an era when anyone can generate convincing text,
the scarce good is verifiable observation.** WorldTwin's bet is that showing people
the instrument readings — sourced, dated, gap-admitting, replayable — is a better
foundation for understanding the world than any summary of them. The codebase
already believes this. These decisions just let the world see it.
