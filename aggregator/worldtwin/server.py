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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from . import __version__, cache, registry, scheduler

API_VERSION = "1.0.0"
BOOT_TIME = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Import all sources so they self-register
    registry.autodiscover()
    layers = registry.all_layers()
    print(f"[server] registered {len(layers)} layers")
    # Shared HTTP client
    app.state.client = httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": f"WorldTwin-Aggregator/{__version__}"},
    )
    app.state.tasks = scheduler.start_all(app.state.client)
    try:
        yield
    finally:
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
