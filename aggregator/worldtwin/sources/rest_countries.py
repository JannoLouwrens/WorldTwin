"""REST Countries — population, borders, flags, languages."""
import httpx

from ..models import LayerMeta, region
from ..registry import register

LAYER = LayerMeta(
    id="population",
    name="Countries & Population",
    category="meta",
    kind="regions",
    source="REST Countries",
    source_url="https://restcountries.com/v3.1/all",
    license="Public",
    refresh_s=86400,
    initial_delay_s=28,
    description="Every country with population, area, capital, languages, and flag.",
)


async def fetch(client: httpx.AsyncClient):
    # REST Countries v3.1 /all caps at 10 fields per request
    r1 = await client.get(
        "https://restcountries.com/v3.1/all",
        params={"fields": "name,population,latlng,cca2,cca3,area,region,subregion,capital,flags"},
        timeout=60,
    )
    r1.raise_for_status()
    data1 = r1.json()
    if not isinstance(data1, list):
        # restcountries.com intermittently returns an error dict (and the
        # bare /all without fields is now rejected) — a dict here caused an
        # AttributeError every cycle and froze the cache.
        print(f"[population] unexpected body: {str(data1)[:200]}")
        return None
    core = {c.get("cca3"): c for c in data1 if isinstance(c, dict) and c.get("cca3")}
    try:
        r2 = await client.get(
            "https://restcountries.com/v3.1/all",
            params={"fields": "cca3,currencies,languages,tld,idd,timezones"},
            timeout=60,
        )
        if r2.status_code == 200:
            data2 = r2.json()
            if isinstance(data2, list):
                for c in data2:
                    cca3 = c.get("cca3") if isinstance(c, dict) else None
                    if cca3 in core:
                        core[cca3].update({k: v for k, v in c.items() if k != "cca3"})
    except Exception:
        pass

    regions = []
    legacy = []
    for c in core.values():
        if not (c.get("population") and c.get("latlng") and len(c["latlng"]) >= 2):
            continue
        legacy.append(c)
        regions.append(region(
            iso3=c.get("cca3", ""),
            value=c.get("population"),
            label=((c.get("name") or {}).get("common") or c.get("cca3", "")),
            cca2=c.get("cca2"),
            lat=c["latlng"][0],
            lon=c["latlng"][1],
            area=c.get("area"),
            region=c.get("region"),
            subregion=c.get("subregion"),
            capital=(c.get("capital") or [None])[0],
            flag=((c.get("flags") or {}).get("svg") or (c.get("flags") or {}).get("png")),
            languages=list((c.get("languages") or {}).values())[:3],
            currencies=list((c.get("currencies") or {}).keys())[:2],
        ))
    return regions, legacy


register(LAYER, fetch)
