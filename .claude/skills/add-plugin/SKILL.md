---
name: add-plugin
description: Add a new backend data source to the WorldTwin aggregator by creating one file in aggregator/worldtwin/sources/ that exports a LayerMeta + async fetch(), registers it, then wiring its layer id into frontend/config.json and verifying it caches. Use when asked to add a data source, API, dataset, or backend layer to WorldTwin.
---

# Add a WorldTwin data source (plugin)

A plugin is **one file** in `aggregator/worldtwin/sources/<id>.py`. The registry
auto-discovers every non-`_` file; no scheduler edit is ever needed. Full
contract: `aggregator/SDK.md`. Per-source notes: `docs/sources/INDEX.md`.

## 1. Copy the shape of an existing simple source

Read `aggregator/worldtwin/sources/usgs_quakes.py` for the canonical pattern, and
`aggregator/worldtwin/models.py` for the `LayerMeta` fields and the 7 `kind`
shapes (`points`, `flows`, `regions`, `timeseries`, `tiles`, `scalar`, `raw`) and
shape helpers (`point()`, etc.).

```python
"""<one-line: what this source is>."""
import httpx
from ..models import LayerMeta, point          # or region/flow/timeseries helper
from ..registry import register

LAYER = LayerMeta(
    id="my_source",                  # MUST match the cache file + config.json id
    name="Human Readable Name",
    category="nature",               # one of the Category literals in models.py
    kind="points",                   # one of the 7 Kind literals
    source="Provider name",
    source_url="https://…",          # canonical upstream link (provenance!)
    license="Public domain / CC-BY / see source",
    refresh_s=600,                   # cadence — match source update rate & rate limit
    initial_delay_s=5,               # stagger startup so 95 plugins don't stampede
    units="…",
    description="…",
    requires_key=False,              # True if it needs an env var
    key_env="",                      # e.g. "EIA_API_KEY" — for documentation
)

async def fetch(client: httpx.AsyncClient):
    r = await client.get(LAYER.source_url, timeout=30)
    r.raise_for_status()
    data = r.json()
    points = [point(lat=…, lon=…, id=…, value=…, label=…) for d in data]
    return points                    # or `return points, raw_dict` (tuple) if you
                                     # also want the raw payload stored for history

register(LAYER, fetch)               # MUST be at module level
```

## 2. Non-negotiable rules

- **Secrets:** read keys only via `os.environ.get("KEY_ENV")`. Never echo a key
  into the returned data. Set `requires_key=True` + `key_env` so it self-documents.
- **Cap point counts** before returning — the frontend and the box can't take
  unbounded payloads (existing caps: fires ~2000, flights ~600, trade ~200).
  Downsample/cluster server-side.
- **Graceful degradation:** on 429/503/timeout, keep the last good cache (return
  early / raise so the scheduler keeps the stale file) rather than overwriting it
  with an empty array — an empty cache reads as "no events", which violates the
  Charter (gaps must be shown, not faked).
- **Provenance:** set `source`, `source_url`, `license` truthfully; the UI shows them.

## 3. Wire the frontend

Add the layer id to `frontend/config.json` (envelope + renderer + which modes it
appears in). If it uses a standard `kind`, no JS is needed; for a bespoke
renderer use the `/add-frontend-layer` skill.

## 4. Deploy & verify

Use `/restart-aggregator` (scp the source file → `docker compose restart
aggregator`), then force-fetch and confirm:

```bash
curl -s http://129.151.191.74/api/cache/my_source.json | head -c 300   # non-empty
```

Done = cache file non-empty + (if wired) the layer renders with a clean console.
