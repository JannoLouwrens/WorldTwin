# World Twin Platform — Client SDK Guide

A unified, self-describing real-time data backend for multi-platform Earth
visualizations. Build Unity games, mobile apps, web dashboards, Discord bots,
CLI tools — all against the same contract.

**Base URL**: `http://129.151.191.74/v1/`

**Authentication**: None (yet). CORS is fully open.

---

## 1. The Contract in 60 Seconds

Every layer of data (quakes, flights, trade flows, Steam games, ISS…) is
returned as an **Envelope** with a consistent shape:

```json
{
  "id": "quakes",
  "name": "Earthquakes (M2.5+ past day)",
  "category": "nature",
  "kind": "points",
  "source": "USGS Earthquake Hazards Program",
  "source_url": "https://earthquake.usgs.gov/...",
  "license": "Public domain (US Government)",
  "fetched_at": "2026-04-10T07:30:56.205690+00:00",
  "expires_at": "2026-04-10T07:32:56.205690+00:00",
  "units": "magnitude (Richter)",
  "count": 39,
  "data": [
    {
      "lat": 36.9942,
      "lon": -104.968,
      "id": "us6000snvx",
      "value": 3.5,
      "label": "M3.5",
      "props": {
        "place": "18 km SSE of Stonewall Gap, Colorado",
        "depth_km": 7.613,
        "time_ms": 1775804394260,
        "usgs_url": "https://earthquake.usgs.gov/..."
      }
    }
  ]
}
```

**The `kind` field tells you the shape of `data`.** There are only 7 kinds, so
your client code only needs 7 render paths total, no matter how many layers
you add.

---

## 2. The 7 Data Shapes (Kinds)

### `points`
```jsonc
{ "kind": "points", "data": [
  { "lat": 35.6, "lon": 139.7, "value": 8.2, "label": "Tokyo", "props": { ... } }
]}
```
For: quakes, fires, flights, volcanoes, webcams, radio, sports, ISS, satellites.

### `flows`
```jsonc
{ "kind": "flows", "data": [
  {
    "from": {"lat": -25.27, "lon": 133.78, "name": "Australia"},
    "to":   {"lat": 35.86,  "lon": 104.19, "name": "China"},
    "value": 84534764274,
    "label": "Iron Ore: Australia → China",
    "props": {"commodity": "Iron Ore", "hs": "2601", "year": 2023}
  }
]}
```
For: trade, money flows, migration, shipping routes.

### `regions`
```jsonc
{ "kind": "regions", "data": [
  { "iso3": "USA", "value": 331002651, "label": "United States", "props": {...} }
]}
```
For: country-level choropleths. Join on `iso3` to your own country polygons.

### `timeseries`
```jsonc
{ "kind": "timeseries", "data": [
  { "t": "2024-01-01", "v": 3.25, "label": "GDP Q1" }
]}
```
For: FRED indicators, historical data, time charts.

### `tiles`
```jsonc
{ "kind": "tiles", "data": {
  "url_template": "https://host/{z}/{x}/{y}.png",
  "min_zoom": 0, "max_zoom": 6,
  "attribution": "RainViewer"
}}
```
For: radar, satellite imagery, tile overlays.

### `scalar`
```jsonc
{ "kind": "scalar", "data": { "value": 8282474995, "label": "World population" } }
```
For: single-value widgets.

### `raw`
```jsonc
{ "kind": "raw", "data": { /* source-specific shape */ } }
```
Escape hatch for data that doesn't fit the other kinds (TLEs, mixed Steam + Twitch,
economy bundle with forex + crypto).

---

## 3. Core Endpoints

| Method | Path | Returns |
|--------|------|---------|
| `GET` | `/v1/` | API root: version, uptime |
| `GET` | `/v1/layers` | **Discovery**: list every layer + metadata + status |
| `GET` | `/v1/layers/{id}` | Full envelope for one layer |
| `GET` | `/v1/layers/{id}/data` | Just the `.data` (no envelope) — low bandwidth |
| `GET` | `/v1/categories` | List categories |
| `GET` | `/v1/categories/{id}` | All layers in a category |
| `GET` | `/v1/health` | Per-layer OK/FAIL status |
| `GET` | `/v1/stats` | Record counts, errors |
| `GET` | `/v1/schema` | JSON schema of envelope + all 7 kinds |
| `GET` | `/v1/docs` | **HTML admin browser** — live system overview |
| `GET` | `/v1/swagger` | OpenAPI / Swagger UI |

### Legacy (current web frontend only — do not use for new apps)

| `GET` | `/api/cache/{id}.json` | Raw upstream format for the existing CesiumJS web app |

---

## 4. Discovery-Driven Apps

Don't hardcode layers. **Hit `/v1/layers` at startup and build your UI dynamically.**

```jsonc
// GET /v1/layers
{
  "count": 21,
  "layers": [
    {
      "id": "quakes",
      "name": "Earthquakes (M2.5+ past day)",
      "category": "nature",
      "kind": "points",
      "source": "USGS Earthquake Hazards Program",
      "source_url": "...",
      "license": "...",
      "refresh_s": 120,
      "units": "magnitude (Richter)",
      "description": "...",
      "status": { "ok": true, "count": 39, "last_fetch": "..." },
      "url": "/v1/layers/quakes",
      "data_url": "/v1/layers/quakes/data"
    },
    ...
  ]
}
```

**Now your Unity app knows:**
- What layers exist (21)
- What kind of renderer each needs (`points` → billboards, `flows` → arcs, `regions` → choropleth)
- Which are healthy and should be shown
- How often to poll them (use `refresh_s` — it IS the source of truth)

---

## 5. Client Examples

### JavaScript (browser / Node / Deno)

```javascript
const API = "http://129.151.191.74/v1";

// 1. Discover
const layers = await fetch(`${API}/layers`).then(r => r.json());
console.log(`${layers.count} layers available`);

// 2. Fetch one layer
const quakes = await fetch(`${API}/layers/quakes`).then(r => r.json());
console.log(`${quakes.count} quakes, latest fetched at ${quakes.fetched_at}`);

// 3. Render all points (kind === "points")
for (const p of quakes.data) {
  renderMarker(p.lat, p.lon, p.label, p.props);
}

// 4. Polling the right way — respect refresh_s
const meta = layers.layers.find(l => l.id === "quakes");
setInterval(async () => {
  const d = await fetch(`${API}/layers/quakes/data`).then(r => r.json());
  updateMarkers(d);
}, meta.refresh_s * 1000);
```

### C# (Unity)

```csharp
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using UnityEngine;

public class WorldTwinClient : MonoBehaviour
{
    const string API = "http://129.151.191.74/v1";
    static readonly HttpClient http = new();

    public async Task<Envelope> GetLayer(string id)
    {
        var json = await http.GetStringAsync($"{API}/layers/{id}");
        return JsonSerializer.Deserialize<Envelope>(json);
    }

    async void Start()
    {
        var quakes = await GetLayer("quakes");
        foreach (var p in quakes.data)
        {
            // p.lat, p.lon, p.value, p.label, p.props
            SpawnQuakeMarker(p.lat, p.lon, p.value);
        }
    }
}

public record Envelope(
    string id, string name, string category, string kind,
    string source, string source_url, string license,
    string fetched_at, string expires_at, string units,
    int count, Point[] data
);

public record Point(
    double lat, double lon, string id, double? value,
    string label, System.Text.Json.JsonElement props
);
```

### Swift (iOS)

```swift
struct Envelope<T: Codable>: Codable {
    let id, name, category, kind, source: String
    let fetched_at, expires_at: String
    let count: Int
    let data: [T]
}

struct PointRecord: Codable {
    let lat, lon: Double
    let value: Double?
    let label: String?
    let id: String?
}

func fetchLayer(_ id: String) async throws -> Envelope<PointRecord> {
    let url = URL(string: "http://129.151.191.74/v1/layers/\(id)")!
    let (data, _) = try await URLSession.shared.data(from: url)
    return try JSONDecoder().decode(Envelope<PointRecord>.self, from: data)
}

// Usage
let quakes = try await fetchLayer("quakes")
for p in quakes.data { print(p.label ?? "", p.lat, p.lon) }
```

### Python

```python
import httpx

API = "http://129.151.191.74/v1"

with httpx.Client() as client:
    layers = client.get(f"{API}/layers").json()
    print(f"{layers['count']} layers")

    trade = client.get(f"{API}/layers/trade").json()
    for flow in trade["data"][:5]:
        print(f"{flow['label']}: ${flow['value']/1e9:.1f}B")
```

### cURL

```bash
# Quick health check
curl -s http://129.151.191.74/v1/health | jq '.ok'

# Get all volcanoes
curl -s http://129.151.191.74/v1/layers/volcanoes/data | jq '.[0:3]'

# List layers by category
curl -s http://129.151.191.74/v1/categories/nature | jq '.layers[] | .id'
```

---

## 6. Categories

Every layer belongs to one of 12 categories. Build category-based UIs
(map modes, tabs, filters) from `/v1/categories`:

| Category | Description | Example layers |
|----------|-------------|----------------|
| `nature` | Weather, geological, natural events | quakes, fires, volcanoes, disasters, rainviewer |
| `war` | Conflicts, crises | conflicts, crises |
| `economy` | GDP, forex, crypto, indicators | economy, fred |
| `resources` | Commodities, trade, energy flows | trade |
| `gaming` | Games, streams, esports | gaming |
| `sports` | Live matches, races | sports |
| `social` | News, trends, social media | news, trends, radio |
| `space` | Satellites, ISS, astronomy | iss, satellites |
| `transit` | Aircraft, ships, trains | flights |
| `infra` | Cables, grid, webcams | cables, webcams |
| `health` | Disease, pollution | air_quality |
| `meta` | Country data, world stats | population |

---

## 7. Adding a New Data Source

**The backend is designed so adding a new layer = dropping one file.**

1. Create `worldtwin/sources/my_source.py`:

```python
import httpx
from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="my_layer",
    name="My New Layer",
    category="nature",
    kind="points",
    source="Awesome API",
    source_url="https://api.example.com/data",
    refresh_s=300,
    description="Describe what this shows.",
)

async def fetch(client: httpx.AsyncClient):
    r = await client.get(LAYER.source_url, timeout=30)
    r.raise_for_status()
    raw = r.json()
    # Normalize into v1 points
    points = [point(lat=x["lat"], lon=x["lng"], label=x["name"]) for x in raw]
    # Return (v1_data, legacy_data). Same tuple if they're the same shape.
    return points, raw

register(LAYER, fetch)
```

2. **That's it.** On restart, the registry auto-discovers the new module,
   the scheduler starts a worker on the interval you specified, and the
   endpoint `/v1/layers/my_layer` comes online. It appears in `/v1/layers`,
   shows up in the admin docs, and gets its own cache file automatically.

---

## 8. Keys / Environment Variables

Most sources work without a key. These are optional:

| Env var | Source | Free signup | Unlocks |
|---------|--------|-------------|---------|
| `TWITCH_CLIENT_ID` + `TWITCH_CLIENT_SECRET` | Twitch Helix | https://dev.twitch.tv/console | Gaming regional viewer bubbles |
| `FRED_API_KEY` | St. Louis Fed FRED | https://fredaccount.stlouisfed.org/apikey | US interest rates, inflation, unemployment, oil prices, forex history |
| `FIRMS_KEY` | NASA FIRMS | (already set) | Active fire detections |
| `WINDY_KEY` | Windy Webcams | (already set) | Webcam imagery |

Set them in `docker-compose.yml` under the `aggregator` service `environment:` block,
then `docker compose up -d aggregator`.

---

## 9. Performance Tips

1. **Respect `refresh_s`**: don't poll faster than the source updates. The cache
   won't change any quicker.
2. **Use `/data`** instead of full envelope when you don't need metadata
   (saves 20–40% bandwidth).
3. **Poll `/v1/health`** first to know which layers are worth fetching.
4. **Cache on the client too**: the envelope has `fetched_at` and `expires_at`
   to tell you when stale data is acceptable.
5. **For 3D globes**: prefer `kind: "points"` layers — you can render thousands
   of them efficiently with instanced billboards. For massive datasets
   (fires > 3000), downsample client-side using the `value` field.

---

## 10. Roadmap

Planned layers (dropping into `worldtwin/sources/` as they're built):

- **Bluesky Jetstream** firehose (social) — free, no key, live
- **Overpass API** (OSM) — every hospital, port, power plant on Earth
- **Global Forest Watch** — deforestation alerts
- **CEPII BACI** — cleaner bilateral trade data
- **Wikipedia Pageviews by country** — per-country trending
- **OWID Grapher** — one endpoint for Freedom House + WID + happiness + V-Dem
- **AISStream live ships** — filter to tankers for real-time oil flows

---

## 11. Stability Guarantees

- **`/v1/*` contract is frozen.** Breaking changes will ship as `/v2/*`.
- **Legacy `/api/cache/*.json`** stays for as long as the current CesiumJS
  frontend needs it.
- **Adding new layers** is a non-breaking change.
- **Adding new fields to `props`** is a non-breaking change (treat `props`
  as an open dictionary in your client).
- **Removing a layer** will be announced in `/v1/layers` deprecation flags
  before removal.

---

## 12. Questions / Issues

The backend is open-source in spirit — everything is in
`worldtwin/sources/` for transparency. Each file is small (50–150 lines)
and self-contained. Read the code; it's the most honest documentation.

Admin status at any time: **http://129.151.191.74/v1/docs**
