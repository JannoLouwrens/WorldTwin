"""FastAPI HTTP server — exposes the v1 public API contract.

Endpoints:
  GET /v1/                    — API root, version
  GET /v1/layers              — list every layer with metadata
  GET /v1/layers/{id}         — full envelope for one layer
  GET /v1/layers/{id}/data    — just the .data payload (low bandwidth)
  GET /v1/categories          — list categories
  GET /v1/categories/{id}     — layers in a category
  GET /v1/health              — per-layer status
  GET /v1/stats               — counts / errors / elapsed per layer
  GET /v1/schema              — JSON schema of the envelope + standard shapes
  GET /v1/docs                — HTML admin browser

Legacy endpoints kept alive for the current CesiumJS frontend:
  GET /api/health             — old health
  GET /api/{layer}             — old per-layer endpoint
  (cache files at /cache/{layer}.json are served directly by Caddy)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response

from . import __version__, cache, registry, scheduler

API_VERSION = "1.0.0"
BOOT_TIME = datetime.now(timezone.utc)


async def _mem_diagnostic_loop():
    """Background coroutine — every 5 minutes, force a `gc.collect()` and
    log RSS. The original tracemalloc version (kept in git history)
    identified that ucdp_ged's 139 MB JSON cache loads into ~700 MB peak
    Python heap; the long-term leak (sanity.py global accumulator) is
    fixed. Periodic gc reduces fragmentation between fetches."""
    import asyncio, gc, resource
    print("[mem] periodic gc loop started", flush=True)
    while True:
        try:
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            raise
        try:
            collected = gc.collect()
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            print(f"[mem] gc.collect freed {collected} objects; max_rss={rss_kb/1024:.0f}MB", flush=True)
        except Exception as e:
            print(f"[mem] gc loop error: {e}", flush=True)


async def _wal_checkpoint_loop():
    """Background coroutine — periodically attempt TRUNCATE checkpoint.

    NOTE on what works and what doesn't:
    - Writer connections set `wal_autocheckpoint=5000` which DOES reclaim
      WAL pages every ~20 MB. The WAL doesn't grow without bound — pages
      get reused, which is what matters for correctness and performance.
    - But TRUNCATE (which actually shrinks the FILE on disk) cannot run
      reliably under our write load: 90 plugin workers nearly always have
      a writer in flight, and the TRUNCATE call needs the write lock.
      It hangs indefinitely whether called via asyncio.to_thread, a
      dedicated thread executor, OR a subprocess.
    - Operational fix when WAL grows large: stop the aggregator briefly
      and run `python -c "import sqlite3; c=sqlite3.connect('/history/history.sqlite'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)')"`
      from a stopped-state. See docs/architecture/HISTORY_STORE.md for the
      maintenance script.

    This loop is left in place but does NOTHING — kept as a hook for
    future improvement (e.g., write-traffic-aware quiet-window detection).
    """
    import asyncio
    print("[wal] loop started — checkpoint via writers' autocheckpoint=5000; TRUNCATE is a manual op", flush=True)
    while True:
        try:
            await asyncio.sleep(3600)  # Hourly heartbeat
        except asyncio.CancelledError:
            raise
        print("[wal] heartbeat (autocheckpoint runs inside writers)", flush=True)


async def _history_compact_loop():
    """Nightly retention enforcement for the history store.

    history.compact() existed since May but was NEVER scheduled — that,
    plus the restart storm re-snapshotting all 90 layers ~100x/day,
    filled the 100 GB /data volume in six weeks (54 GB db + 45 GB WAL,
    purged 2026-06-11). This loop is the missing piece: run compact()
    daily, and if the DB threatens the disk again, emergency-prune.
    """
    import asyncio
    from . import history
    SIZE_LIMIT = 30 * 1024**3  # 30 GB hard ceiling — disk is 100 GB
    print("[compact] nightly history retention loop started", flush=True)
    await asyncio.sleep(1800)  # first pass 30 min after boot
    while True:
        try:
            deleted = await asyncio.to_thread(history.compact)
            size_gb = history.db_total_bytes() / 1024**3
            print(f"[compact] retention pass done {deleted} — db {size_gb:.2f} GB", flush=True)
            if history.db_total_bytes() > SIZE_LIMIT:
                print("[compact] CRITICAL: db over 30 GB — emergency prune", flush=True)
                res = await asyncio.to_thread(history.emergency_prune)
                print(f"[compact] emergency prune: {res}", flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[compact] error: {e}", flush=True)
        await asyncio.sleep(86400)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bump the asyncio default executor — we have 90 plugins, every fetch
    # tail (cache.write_envelope + cache.write_legacy + history.snapshot)
    # runs through asyncio.to_thread. The default 32-thread pool fills up
    # and starves API requests behind it.
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=128, thread_name_prefix="wt")
    )
    # Import all sources so they self-register
    registry.autodiscover()
    layers = registry.all_layers()
    print(f"[server] registered {len(layers)} layers; thread-pool=128")

    # Background WAL checkpoint loop — keeps history.sqlite-wal bounded.
    app.state.wal_task = asyncio.create_task(_wal_checkpoint_loop())
    # Memory diagnostic — prints top allocators every 60s. Remove once leak
    # is identified.
    app.state.mem_task = asyncio.create_task(_mem_diagnostic_loop())
    # Nightly history retention — the missing scheduler for history.compact()
    app.state.compact_task = asyncio.create_task(_history_compact_loop())
    # Shared HTTP client. Connection limits prevent unbounded growth of
    # the pool when many plugins fire simultaneously against many distinct
    # hosts (we hit ~80 unique upstream domains across 90 plugins).
    app.state.client = httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": f"WorldTwin-Aggregator/{__version__}"},
        limits=httpx.Limits(
            max_connections=50,
            max_keepalive_connections=10,
            keepalive_expiry=30.0,
        ),
    )
    app.state.tasks = scheduler.start_all(app.state.client)
    try:
        yield
    finally:
        app.state.wal_task.cancel()
        app.state.mem_task.cancel()
        for t in app.state.tasks:
            t.cancel()
        await app.state.client.aclose()


app = FastAPI(
    title="World Twin Platform API",
    description="A unified, self-describing real-time data backend for multi-platform Earth visualizations.",
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/v1/swagger",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# /v1/ — root
# ---------------------------------------------------------------------------

@app.get("/v1/")
async def root() -> dict[str, Any]:
    """API root — version info and uptime."""
    now = datetime.now(timezone.utc)
    uptime = (now - BOOT_TIME).total_seconds()
    return {
        "name": "World Twin Platform",
        "version": API_VERSION,
        "aggregator_version": __version__,
        "uptime_s": round(uptime),
        "started_at": BOOT_TIME.isoformat(),
        "docs": "/v1/docs",
        "schema": "/v1/schema",
        "layers": "/v1/layers",
        "health": "/v1/health",
    }


# ---------------------------------------------------------------------------
# /v1/layers — list and fetch layers
# ---------------------------------------------------------------------------

@app.get("/v1/layers")
async def list_layers() -> dict[str, Any]:
    """List every registered layer with metadata (no data).
    Use this to build UIs dynamically or discover what's available.
    """
    metas = registry.all_metas()
    statuses = cache.all_status()
    return {
        "count": len(metas),
        "layers": [
            {
                **m.public(),
                "status": statuses.get(m.id, {"ok": False, "error": "never fetched"}),
                "url": f"/v1/layers/{m.id}",
                "data_url": f"/v1/layers/{m.id}/data",
            }
            for m in metas
        ],
    }


@app.get("/v1/layers/{layer_id}")
async def get_layer(layer_id: str) -> Response:
    """Full envelope (metadata + data) for one layer."""
    if "/" in layer_id or ".." in layer_id:
        raise HTTPException(400, "Invalid layer id")
    reg = registry.get(layer_id)
    if reg is None:
        raise HTTPException(404, f"Unknown layer: {layer_id}")
    path = cache.envelope_path(layer_id)
    if not path.exists():
        raise HTTPException(503, f"Layer '{layer_id}' has not been fetched yet")
    return FileResponse(path, media_type="application/json")


@app.get("/v1/layers/{layer_id}/data")
async def get_layer_data(layer_id: str) -> Response:
    """Just the `data` payload (no envelope). Useful for low-bandwidth clients."""
    if "/" in layer_id or ".." in layer_id:
        raise HTTPException(400, "Invalid layer id")
    reg = registry.get(layer_id)
    if reg is None:
        raise HTTPException(404, f"Unknown layer: {layer_id}")
    path = cache.data_path(layer_id)
    if not path.exists():
        raise HTTPException(503, f"Layer '{layer_id}' has not been fetched yet")
    return FileResponse(path, media_type="application/json")


# ---------------------------------------------------------------------------
# /v1/categories
# ---------------------------------------------------------------------------

@app.get("/v1/categories")
async def list_categories() -> dict[str, Any]:
    cats = registry.categories()
    return {
        "count": len(cats),
        "categories": [
            {
                "id": cat_id,
                "layer_count": len(metas),
                "layers": [m.id for m in metas],
                "url": f"/v1/categories/{cat_id}",
            }
            for cat_id, metas in sorted(cats.items())
        ],
    }


@app.get("/v1/categories/{category_id}")
async def get_category(category_id: str) -> dict[str, Any]:
    cats = registry.categories()
    metas = cats.get(category_id)
    if not metas:
        raise HTTPException(404, f"Unknown category: {category_id}")
    return {
        "id": category_id,
        "count": len(metas),
        "layers": [m.public() for m in metas],
    }


# ---------------------------------------------------------------------------
# /v1/health and /v1/stats
# ---------------------------------------------------------------------------

@app.get("/v1/health")
async def health() -> dict[str, Any]:
    statuses = cache.all_status()
    total = len(registry.all_metas())
    ok = sum(1 for v in statuses.values() if v.get("ok"))
    return {
        "ok": ok,
        "total": total,
        "unhealthy": total - ok,
        "time": datetime.now(timezone.utc).isoformat(),
        "layers": statuses,
    }


@app.get("/v1/stats")
async def stats() -> dict[str, Any]:
    statuses = cache.all_status()
    total_records = sum((s.get("count") or 0) for s in statuses.values())
    errors = [
        {"id": lid, "error": s.get("error")}
        for lid, s in statuses.items()
        if not s.get("ok") and s.get("error")
    ]
    return {
        "total_records": total_records,
        "layer_count": len(registry.all_metas()),
        "healthy_count": sum(1 for s in statuses.values() if s.get("ok")),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# /v1/schema — JSON schema of the envelope and data shapes
# ---------------------------------------------------------------------------

@app.get("/v1/schema")
async def schema() -> dict[str, Any]:
    """JSON schema describing the envelope and the 7 standard data shapes.
    Client developers use this to generate types in any language.
    """
    return {
        "envelope": {
            "type": "object",
            "required": ["id", "name", "category", "kind", "source", "fetched_at", "expires_at", "count", "data"],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "category": {"type": "string", "enum": [
                    "nature", "war", "economy", "resources", "gaming",
                    "sports", "social", "space", "transit", "infra", "health", "meta"
                ]},
                "kind": {"type": "string", "enum": [
                    "points", "flows", "regions", "timeseries", "tiles", "scalar", "raw"
                ]},
                "source": {"type": "string"},
                "source_url": {"type": "string"},
                "license": {"type": "string"},
                "fetched_at": {"type": "string", "format": "date-time"},
                "expires_at": {"type": "string", "format": "date-time"},
                "units": {"type": "string"},
                "count": {"type": "integer"},
                "data": {"description": "shape defined by `kind`"},
            },
        },
        "shapes": {
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["lat", "lon"],
                    "properties": {
                        "id": {"type": "string"},
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "value": {"type": "number"},
                        "label": {"type": "string"},
                        "popup": {"type": "string"},
                        "props": {"type": "object"},
                    },
                },
            },
            "flows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["from", "to"],
                    "properties": {
                        "from": {"type": "object", "required": ["lat", "lon"]},
                        "to": {"type": "object", "required": ["lat", "lon"]},
                        "value": {"type": "number"},
                        "label": {"type": "string"},
                        "props": {"type": "object"},
                    },
                },
            },
            "regions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["iso3", "value"],
                    "properties": {
                        "iso3": {"type": "string"},
                        "value": {"description": "number, string, or nested"},
                        "label": {"type": "string"},
                        "props": {"type": "object"},
                    },
                },
            },
            "timeseries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["t", "v"],
                    "properties": {
                        "t": {"type": "string", "description": "ISO 8601 timestamp"},
                        "v": {"description": "value"},
                        "label": {"type": "string"},
                    },
                },
            },
            "tiles": {
                "type": "object",
                "required": ["url_template"],
                "properties": {
                    "url_template": {"type": "string"},
                    "min_zoom": {"type": "integer"},
                    "max_zoom": {"type": "integer"},
                    "attribution": {"type": "string"},
                },
            },
            "scalar": {
                "type": "object",
                "required": ["value"],
                "properties": {
                    "value": {},
                    "label": {"type": "string"},
                    "props": {"type": "object"},
                },
            },
            "raw": {"description": "passthrough — unstructured"},
        },
    }


# ---------------------------------------------------------------------------
# /v1/docs — HTML admin browser
# ---------------------------------------------------------------------------

@app.get("/v1/docs", response_class=HTMLResponse)
async def admin_docs() -> HTMLResponse:
    metas = registry.all_metas()
    statuses = cache.all_status()
    total_records = sum((s.get("count") or 0) for s in statuses.values())
    ok_count = sum(1 for s in statuses.values() if s.get("ok"))
    cats = registry.categories()

    # Build HTML
    rows = []
    for meta in sorted(metas, key=lambda m: (m.category, m.id)):
        st = statuses.get(meta.id, {})
        ok = st.get("ok", False)
        count = st.get("count")
        err = st.get("error") or ""
        last = st.get("last_fetch", "never")
        elapsed = st.get("elapsed_s", 0)
        dot = "🟢" if ok else "🔴"
        rows.append(f"""
          <tr>
            <td>{dot}</td>
            <td><code>{meta.id}</code></td>
            <td><b>{meta.name}</b><br><span class="mt">{meta.description or ''}</span></td>
            <td><span class="pill cat-{meta.category}">{meta.category}</span></td>
            <td><span class="pill kind">{meta.kind}</span></td>
            <td>{meta.source}<br><a href="{meta.source_url}" target="_blank" class="mt">source ↗</a></td>
            <td>{count if count is not None else '—'}</td>
            <td>{meta.refresh_s}s</td>
            <td>{elapsed:.2f}s</td>
            <td class="mt">{last[:19] if last != 'never' else 'never'}</td>
            <td>
              <a href="/v1/layers/{meta.id}" target="_blank">envelope</a><br>
              <a href="/v1/layers/{meta.id}/data" target="_blank">data</a>
            </td>
          </tr>
        """)
        if err and not ok:
            rows.append(f'<tr class="err"><td colspan="11"><code>{err[:400]}</code></td></tr>')

    cat_pills = " ".join(
        f'<span class="pill cat-{cat}">{cat} ({len(ls)})</span>'
        for cat, ls in sorted(cats.items())
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>World Twin Platform — API</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e17;color:#e8ecf1;padding:24px;line-height:1.5}}
  h1{{font-size:28px;margin-bottom:4px;font-weight:800;letter-spacing:-.5px;background:linear-gradient(90deg,#64b5f6,#b388ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
  .sub{{opacity:.6;font-size:13px;margin-bottom:24px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px}}
  .stat{{background:#141a28;padding:14px;border-radius:10px;border:1px solid #1f2738}}
  .stat .v{{font-size:28px;font-weight:800;color:#64b5f6}}
  .stat .l{{font-size:11px;opacity:.5;text-transform:uppercase;letter-spacing:.1em;margin-top:4px}}
  .cats{{margin-bottom:20px;display:flex;gap:6px;flex-wrap:wrap}}
  .pill{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;background:#1f2738;color:#8a96ad}}
  .pill.kind{{background:#1a2332;color:#64b5f6}}
  .pill.cat-nature{{background:#1a3a1f;color:#7eb77e}}
  .pill.cat-war{{background:#3a1a1a;color:#e57373}}
  .pill.cat-economy{{background:#1a3a2a;color:#81c784}}
  .pill.cat-resources{{background:#3a2a1a;color:#ffb74d}}
  .pill.cat-gaming{{background:#2a1a3a;color:#ce93d8}}
  .pill.cat-sports{{background:#3a3a1a;color:#fff176}}
  .pill.cat-social{{background:#1a2a3a;color:#81d4fa}}
  .pill.cat-space{{background:#2a2a3a;color:#b39ddb}}
  .pill.cat-transit{{background:#1a3a3a;color:#80cbc4}}
  .pill.cat-infra{{background:#3a2a3a;color:#f48fb1}}
  .pill.cat-health{{background:#3a1a2a;color:#f06292}}
  .pill.cat-meta{{background:#2a2a2a;color:#b0bec5}}
  table{{width:100%;border-collapse:collapse;background:#0f1420;border-radius:10px;overflow:hidden}}
  th{{text-align:left;padding:12px 10px;font-size:11px;text-transform:uppercase;letter-spacing:.08em;background:#141a28;border-bottom:1px solid #1f2738;color:#8a96ad;font-weight:700}}
  td{{padding:12px 10px;border-bottom:1px solid #141a28;font-size:13px;vertical-align:top}}
  tr.err td{{background:#2a0f15;color:#ff8a80;font-family:ui-monospace,monospace;font-size:11px;padding:8px 10px}}
  .mt{{opacity:.5;font-size:11px}}
  a{{color:#64b5f6;text-decoration:none}}
  a:hover{{text-decoration:underline}}
  code{{font-family:ui-monospace,'SF Mono',Menlo,monospace;background:#1f2738;padding:2px 6px;border-radius:4px;font-size:11px;color:#b3d4fc}}
  .nav{{display:flex;gap:20px;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #1f2738}}
  .nav a{{font-weight:600}}
</style>
</head>
<body>
  <h1>🌍 World Twin Platform</h1>
  <div class="sub">Unified real-time Earth data backend · v{API_VERSION}</div>
  <div class="nav">
    <a href="/v1/">Root</a>
    <a href="/v1/layers">Layers JSON</a>
    <a href="/v1/categories">Categories</a>
    <a href="/v1/health">Health</a>
    <a href="/v1/schema">Schema</a>
    <a href="/v1/swagger">Swagger</a>
  </div>
  <div class="grid">
    <div class="stat"><div class="v">{len(metas)}</div><div class="l">Layers</div></div>
    <div class="stat"><div class="v">{ok_count}</div><div class="l">Healthy</div></div>
    <div class="stat"><div class="v">{total_records:,}</div><div class="l">Total records cached</div></div>
    <div class="stat"><div class="v">{len(cats)}</div><div class="l">Categories</div></div>
  </div>
  <div class="cats">{cat_pills}</div>
  <table>
    <thead>
      <tr>
        <th></th>
        <th>ID</th>
        <th>Name</th>
        <th>Category</th>
        <th>Kind</th>
        <th>Source</th>
        <th>Count</th>
        <th>Refresh</th>
        <th>Fetch time</th>
        <th>Last</th>
        <th>Links</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>"""
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# /api/history/* — read-only access to the History Store
#
# Vision: trace every claim back to the instrument that measured it.
# These endpoints let the frontend Inspector show the full time-series
# of any cited value and "view at any past date" via snapshot replay.
# ---------------------------------------------------------------------------

@app.get("/api/history/series/{source_id}")
async def history_series(
    source_id: str,
    since: str | None = None,
    until: str | None = None,
    limit: int = 5000,
    dedupe: bool = True,
) -> dict[str, Any]:
    """Time-series rows for one source_id, ordered by observed_at desc.
    Use this to render a sparkline of any cited value through history.

    `dedupe=true` (default) collapses re-fetches of the same observed_at
    to a single row (the latest). Pass `dedupe=false` to see every fetch."""
    if ".." in source_id or "/" in source_id:
        raise HTTPException(400, "Invalid source_id")
    # Unauthenticated endpoint — clamp so ?limit=99999999 can't materialize
    # millions of row dicts and OOM the 3G container with one curl.
    limit = max(1, min(limit, 50_000))
    try:
        import asyncio
        from . import history
        rows = await asyncio.to_thread(
            history.query_series, source_id, since, until, limit, dedupe
        )
        return {
            "source_id": source_id,
            "count": len(rows),
            "since": since,
            "until": until,
            "dedupe": dedupe,
            "rows": rows,
        }
    except Exception as e:
        raise HTTPException(500, f"History query failed: {type(e).__name__}: {e}")


def _read_snapshot_bytes(layer_id: str, at: str | None) -> tuple[bytes | None, str | None, float | None, int | None]:
    """Return the gzipped payload bytes plus metadata, OR (None,)*4 if not found.
    Skips json.loads/dump round-trip — the payload is already valid JSON inside
    the zlib blob. Streaming the bytes directly cuts a 5.5 MB FRED snapshot
    from 60s+ to <1s by avoiding two FastAPI serialisations.

    Uses ephemeral read connection so it doesn't pin the WAL."""
    import zlib
    from . import history
    c = history._read_conn()
    try:
        if at:
            row = c.execute(
                "SELECT fetched_at, payload, payload_kb, rows_added FROM snapshots "
                "WHERE layer_id = ? AND fetched_at <= ? ORDER BY fetched_at DESC LIMIT 1",
                (layer_id, at),
            ).fetchone()
        else:
            row = c.execute(
                "SELECT fetched_at, payload, payload_kb, rows_added FROM snapshots "
                "WHERE layer_id = ? ORDER BY fetched_at DESC LIMIT 1",
                (layer_id,),
            ).fetchone()
        if not row:
            return (None, None, None, None)
        raw = zlib.decompress(row["payload"])
        return (raw, row["fetched_at"], row["payload_kb"], row["rows_added"])
    finally:
        c.close()


@app.get("/api/history/snapshot/{layer_id}")
async def history_snapshot(layer_id: str, at: str | None = None):
    """Closest snapshot at-or-before the `at` timestamp (default: latest).
    Use this to time-travel the dashboard — show the full payload as it
    existed at any historical moment."""
    if ".." in layer_id or "/" in layer_id:
        raise HTTPException(400, "Invalid layer_id")
    try:
        import asyncio, json
        raw, fetched_at, payload_kb, rows_added = await asyncio.to_thread(
            _read_snapshot_bytes, layer_id, at
        )
        if raw is None:
            raise HTTPException(404, f"No snapshot found for {layer_id} at-or-before {at}")
        # Stream raw bytes — avoid json.loads + Pydantic re-serialisation that
        # was timing out on 5 MB FRED snapshots. The `raw` bytes are already
        # valid JSON inside the zlib blob; splice them into our envelope.
        meta = {
            "layer_id": layer_id,
            "fetched_at": fetched_at,
            "payload_kb": payload_kb,
            "rows_added": rows_added,
        }
        head = json.dumps(meta)
        assert head.endswith("}")
        body = head[:-1].encode("utf-8") + b',"payload":' + raw + b"}"
        return Response(content=body, media_type="application/json")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Snapshot read failed: {type(e).__name__}: {e}")


def _list_sources_sync(prefix: str | None, limit: int) -> list[dict]:
    """Range-scan when a prefix is supplied — `LIKE 'fred.%'` is 158s on
    5M rows because SQLite scans the whole index. `>= 'fred.' AND < 'fred.~'`
    converts to an O(matches) seek and runs in <1s. Sort in Python instead
    of in SQL because ORDER BY n DESC requires a temp B-tree.

    Uses ephemeral read connection so it doesn't pin the WAL."""
    from . import history
    c = history._read_conn()
    try:
        args: list[Any] = []
        if prefix:
            # '~' (0x7E) is the highest printable ASCII char, so any source_id
            # starting with `prefix` sorts strictly less than `prefix + '~'`.
            sql = (
                "SELECT source_id, COUNT(*) AS n, MIN(observed_at) AS lo, MAX(observed_at) AS hi "
                "FROM observations "
                "WHERE source_id >= ? AND source_id < ? "
                "GROUP BY source_id"
            )
            args.extend([prefix, prefix + "~"])
        else:
            # No prefix: push the truncation into SQL. The decomposer mints
            # a source_id per aircraft/quake/video, so DISTINCT source_ids
            # reach millions — fetchall() of all groups was an OOM bomb.
            # The ORDER BY temp B-tree stays inside SQLite, bounded.
            sql = (
                "SELECT source_id, COUNT(*) AS n, MIN(observed_at) AS lo, MAX(observed_at) AS hi "
                "FROM observations "
                "GROUP BY source_id ORDER BY n DESC LIMIT ?"
            )
            args.append(limit)
        rows = c.execute(sql, args).fetchall()
        rows.sort(key=lambda r: -r["n"])
        out = []
        for row in rows[:limit]:
            out.append({
                "source_id": row["source_id"],
                "count": row["n"],
                "observed_min": row["lo"],
                "observed_max": row["hi"],
            })
        return out
    finally:
        c.close()


@app.get("/api/history/sources")
async def history_sources(prefix: str | None = None, limit: int = 500) -> dict[str, Any]:
    """List distinct source_ids in the store, with row count + observed_at range.
    Optional prefix filter (e.g. ?prefix=fred. shows all FRED series).

    Runs in a thread because the GROUP BY scan over 1.6M+ rows can take
    seconds on contended SQLite — would block the entire asyncio event loop."""
    limit = max(1, min(limit, 2000))
    try:
        import asyncio
        out = await asyncio.to_thread(_list_sources_sync, prefix, limit)
        return {"prefix": prefix, "count": len(out), "sources": out}
    except Exception as e:
        raise HTTPException(500, f"Sources query failed: {type(e).__name__}: {e}")


@app.get("/api/history/coverage")
async def history_coverage() -> dict[str, Any]:
    """Top-level summary of the History Store: total counts, per-layer counts."""
    try:
        import asyncio
        from . import history
        return await asyncio.to_thread(history.coverage)
    except Exception as e:
        raise HTTPException(500, f"Coverage query failed: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# /api/* legacy — back-compat shim for the current CesiumJS frontend
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def legacy_health() -> dict[str, Any]:
    """Back-compat: old health endpoint shape."""
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "layers": cache.all_status(),
    }


@app.get("/api/_stats")
async def legacy_stats() -> dict[str, Any]:
    return cache.all_status()


@app.get("/api/{layer_id}")
async def legacy_layer(layer_id: str) -> Response:
    """Back-compat: /api/{layer} → return legacy JSON shape from /cache/legacy/."""
    if "/" in layer_id or ".." in layer_id:
        raise HTTPException(400, "Invalid layer id")
    # Legacy files live at /cache/legacy/<id>.json
    legacy_path = cache.CACHE_DIR / "legacy" / f"{layer_id}.json"
    if legacy_path.exists():
        return FileResponse(legacy_path, media_type="application/json")
    # Fall back to v1 data
    data_path = cache.data_path(layer_id)
    if data_path.exists():
        return FileResponse(data_path, media_type="application/json")
    raise HTTPException(404, f"Layer '{layer_id}' not cached")
