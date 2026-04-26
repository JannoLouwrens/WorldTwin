# WorldTwin History Store — Architecture

_Designed 2026-04-26._

> **Vision.** A lab where anyone — from the king of Rome to a sceptical citizen —
> can read the world from raw, dated, cross-checked sources instead of someone
> else's framing, and trace every claim back to the instrument that measured it.

---

## Why this exists

Today, every plugin's most recent fetch lives in `/data/cache/<layer>.json`.
The next fetch overwrites the previous one. Yesterday's Brent crude reading,
last week's Hormuz vessel count, last month's Iran inflation projection —
**gone the moment the cache file is rewritten.**

This breaks the vision in three ways:

1. **No traceability through time.** A user can see "Brent crude $103.4/bbl" but
   not "and yesterday it was $98.6, the day before $116.6, three days ago $114.9."
   The Inspector can show "fetched 12 minutes ago" but cannot show the actual
   sequence of values that fetch is part of.
2. **No replay.** If a user wants to set the dashboard to "as of last Tuesday,"
   we have no Tuesday data left to show.
3. **No source rot detection.** If FRED silently changes the calculation of an
   index, or NOAA revises a CO2 reading, we have no record of the prior value
   to diff against.

**The History Store fixes this** by appending every cache write to a SQLite
database that lives forever (or until compaction policy retires the row). The
plugin code does not change. The frontend does not change. A new substrate
quietly accumulates the lab's institutional memory.

---

## Two-table schema

The store has **two tables** in one SQLite file at `/data/history/history.sqlite`.
Both are append-only. Neither requires migrations as plugins evolve.

### Table 1 — `observations` (the queryable EAV store)

The primary store. One row per data point per fetch. Optimised for "show me
this number through time" queries.

```sql
CREATE TABLE IF NOT EXISTS observations (
  source_id    TEXT NOT NULL,    -- e.g. 'fred.DCOILBRENTEU', 'wb.NY.GDP.MKTP.CD.USA',
                                 --      'usgs.us2025abc', 'pulse.composite.IRN'
  observed_at  TEXT NOT NULL,    -- ISO8601 — when the world was at this value
                                 --   (the data's own timestamp; e.g. for a
                                 --    historical year-keyed sample, '2024-01-01')
  fetched_at   TEXT NOT NULL,    -- ISO8601 — when we pulled it from upstream
  value_num    REAL,             -- numeric reading when applicable
  value_text   TEXT,             -- categorical / event title / qualitative
  value_json   TEXT,             -- structured payload for complex events
  meta_json    TEXT,             -- units, country_iso3, lat/lon, source_url,
                                 --   any other context useful to the Inspector
  PRIMARY KEY (source_id, observed_at, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_obs_source_observed ON observations(source_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_observed        ON observations(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_fetched         ON observations(fetched_at DESC);
```

**Rationale per column:**

- `source_id` — globally unique, dotted path. The first segment is the cache
  layer ID (FRED, WB, etc.) so we can query all rows for a layer with a prefix
  scan. Subsequent segments encode the specific data point.
- `observed_at` — when the data POINT refers to. Crucial: a 2024 inflation
  number fetched today has `observed_at='2024-12-31'`, `fetched_at=today`.
- `fetched_at` — when we observed the world. Lets us track revisions.
  If FRED revises last month's Brent number, we get a NEW row with the same
  `(source_id, observed_at)` and a later `fetched_at`. Both rows persist.
- `value_num` / `value_text` / `value_json` — three columns so a single table
  holds heterogeneous data without forcing strings or numbers into the wrong
  column. SQLite is dynamically typed so the columns cost nothing when null.
- `meta_json` — overflow for context: units, country code, lat/lon, anything
  the Inspector wants to surface. Stored as JSON so the schema never breaks
  when a plugin adds a new metadata field.

### Table 2 — `snapshots` (the forensic receipt)

A second table holds the raw cache JSON of each fetch, verbatim. Used for
forensics ("what did the plugin produce on date X"), for re-decomposition if
we ever change the EAV mapping, and for replay.

```sql
CREATE TABLE IF NOT EXISTS snapshots (
  layer_id    TEXT NOT NULL,
  fetched_at  TEXT NOT NULL,         -- ISO8601 UTC
  payload_kb  REAL,                  -- size of the payload before any compression
  payload     BLOB NOT NULL,         -- compressed JSON (zlib)
  rows_added  INTEGER,               -- how many observation rows this fetch produced
  PRIMARY KEY (layer_id, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_snap_layer_time ON snapshots(layer_id, fetched_at DESC);
```

`payload` is zlib-compressed (~4-10× reduction on JSON) to keep growth bounded.
Reading a snapshot is `zlib.decompress(row.payload).decode()`.

---

## Source categories

Every plugin falls into one of four categories. The category determines how
much of "everything" we save, and what backfill (if any) is owed.

| Category | Examples | Save policy |
|---|---|---|
| **Bounded historical** | World Bank, IMF, V-Dem, Maddison, HYDE, EPICA CO2, NOAA Mauna Loa, paleo temp, Clio-Infra, Brecke wars, COW alliances | Pull the full historical depth on first fetch; small deltas on each refresh thereafter. **Save everything.** |
| **Live event stream** | UCDP, GDACS, NHC cyclones, WHO outbreaks, USGS today's quakes, NASA DONKI, NASA NEOWS, NASA FIRMS, GFW dark vessels, ReliefWeb, Wikidata battles, IDMC displacement, EONET disasters | Capture every NEW event; never overwrite. Storage grows ~10-100 MB/year per source. **Save everything.** |
| **High-velocity firehose** | GDELT Events (800M records since 1979), OpenAQ unbounded history, AISStream live ship pings, OpenSky live flight pings, satellite GP catalogues | Cannot save in full on a single host. **Save the slice we sample** at the cadence we sample it. The vision is satisfied by being able to prove what the source said *at the moments we sampled*. |
| **Static reference** | country_polygons, geoBoundaries, country_culture, country_relations (curated blocs) | Doesn't change meaningfully between fetches. **Snapshot table only**, no observations rows. One row per refresh in snapshots; an audit trail of "did the bloc list change this week" is enough. |

---

## Ingestion contract

Every plugin already calls `cache.write_legacy(layer_id, payload)` after its
fetch. We hook the History Store in there:

```python
# In aggregator/worldtwin/cache.py
def write_legacy(layer_id, legacy_data):
    legacy_data = sanity.sweep_and_tag(legacy_data)   # existing
    _atomic_write(CACHE_DIR / f"{layer_id}.json", legacy_data)
    history.snapshot(layer_id, legacy_data)           # new — fire and forget
```

`history.snapshot()` does two things:

1. **Append to `snapshots`** — compressed payload + row count.
2. **Decompose the payload into `observations` rows** using a plugin-aware
   walker that knows the common shapes (FRED-style `series` arrays, WB-style
   country×indicator dicts, GeoJSON `features`, generic event lists, etc.).

The decomposer is permissive: if a plugin's payload has a shape we don't
recognise, we still store the snapshot but emit zero observations rows. The
snapshot is enough to recover later.

---

## Decomposer rules

The decomposer walks the payload and emits observations using these patterns,
applied in order:

| Pattern | Detection | Emission |
|---|---|---|
| **FRED-style series dict** | top-level `series` is a dict whose values have `.series` arrays of `{t, v}` | one row per (series_id, sample) with `source_id = '<layer>.<series_id>'`, `observed_at = sample.t`, `value_num = sample.v` |
| **World Bank country×indicator** | `countries` is a dict whose values are dicts of indicator objects with `.value`, `.year`, `.history` | one row per (iso3, indicator, year). `source_id = '<layer>.<indicator>.<iso3>'` |
| **History-keyed country dict** | `countries[iso3].history = {year: value}` (V-Dem, Clio, etc.) | one row per year |
| **Series of [year, value] tuples** | any list of `[int, float]` pairs | one row per pair |
| **GeoJSON FeatureCollection** | top-level `features` is a list of `{geometry, properties}` | one row per feature with `value_json = full feature`, `meta_json = lat/lon` |
| **Generic event list** | any top-level list named `events`, `outbreaks`, `storms`, `chokepoints`, etc. | one row per event with `value_json = event`, `value_text = title`, `meta_json = lat/lon if present` |
| **Headline+history** | `{headline: {…}, series: [...]}` (NOAA CO2, paleo temp) | one row per series sample + one row for the headline |
| **Fallback** | none of the above | snapshot only, no observations |

---

## Read API

A small FastAPI endpoint family added under `/api/history/`:

```
GET /api/history/source/<source_id>?since=ISO&until=ISO&limit=N
    → list of {observed_at, value_num, value_text, fetched_at, meta} for one series

GET /api/history/snapshot/<layer_id>?at=ISO
    → the closest snapshot at or before `at` (decompressed JSON)

GET /api/history/diff/<source_id>?from=ISO&to=ISO
    → the value at `from` and at `to`, plus all revisions in between

GET /api/history/sources?prefix=fred
    → list of distinct source_ids, with row count + observed_at range per source

GET /api/history/coverage
    → top-level summary: total observations, total snapshots, per-layer counts
```

All read-only. Caddy adds these to its proxy alongside the existing `/api/cache/*`.

---

## Retention + compaction policy

Storage is bounded by a nightly compactor:

| Age | Snapshot retention | Observation retention |
|---|---|---|
| <30 days | All snapshots | All rows |
| 30 days – 1 year | Daily snapshots (delete intra-day duplicates) | All rows |
| 1 – 5 years | Weekly snapshots | All rows |
| >5 years | Monthly snapshots | All rows |

**Observations are NEVER compacted.** They are the canonical record. Storage
growth is linear and small (~5-10 GB/year for the full 88 plugins).

Snapshots compaction runs as a nightly cron job. The job is idempotent — it
deletes only the older duplicates, never the most-recent-for-the-window.

---

## Failure modes + idempotency

- `(source_id, observed_at, fetched_at)` is the PRIMARY KEY. Re-running a
  fetch produces identical rows that get `INSERT OR IGNORE`d. Idempotent.
- The substrate uses SQLite WAL mode (`journal_mode=WAL`) for concurrent
  reads while a write is in progress.
- All writes happen inside the aggregator process. The reader endpoints open
  the DB read-only.
- If the SQLite file is lost or corrupted, the live cache JSON files at
  `/data/cache/*.json` are still authoritative. The store can be rebuilt by
  re-running the one-time backfill against the cache files.

---

## Migration plan

1. ✅ **Migrate `/cache` to `/data/cache`** so the new SQLite db has room to grow.
2. ✅ **Write this design doc.**
3. **Build `aggregator/worldtwin/history.py`** with the schema + decomposer.
4. **Hook `history.snapshot()` into `cache.write_legacy()`** so every existing
   plugin starts persisting from this moment forward, with no plugin code
   changes.
5. **Run a one-time backfill** against the existing `/data/cache/*.json`
   files so we don't lose what's already pulled.
6. **Verify** by opening the DB, counting rows, sampling queries.
7. **Subsequent sessions:** deepen each plugin's fetch logic to pull full
   historical depth from its API where possible.

---

## What this is NOT

- **Not a replacement for upstream APIs.** We still need them for new data;
  we just stop relying on them for old data.
- **Not a fix for high-velocity firehoses** (GDELT, OpenAQ unbounded). Those
  remain sample-only.
- **Not a fix for paid APIs** (ACLED full historical). Those remain bounded
  by what their free tier permits.
- **Not a frontend feature.** The UI changes (Inspector "view at date" picker,
  Diff "compare to" selector) come in subsequent sessions once the store has
  accumulated material to show.

The History Store is **substrate**, not feature. Once it's been running for a
week, every other lab capability becomes more powerful.
