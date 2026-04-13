"""IDMC Internal Displacement — near real-time IDU events.
Uses the publicly available Google Sheets CSV export maintained by IDMC/HDX.
No API key required. Returns geocoded displacement events worldwide.
"""
import csv
import io
from datetime import datetime, timezone
import httpx
from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="idmc_displacement",
    name="Internal Displacement (IDMC)",
    category="war",
    kind="points",
    source="IDMC via HDX (Google Sheets export)",
    source_url="https://www.internal-displacement.org/",
    license="CC BY-NC-SA 3.0 IGO",
    refresh_s=86400,
    initial_delay_s=100,
    description="Internally displaced persons events worldwide — conflict + disaster displacement with geocoded coordinates.",
    requires_key=False,
)

HDX_CSV_URL = "https://data.humdata.org/dataset/459fc96c-f196-44c1-a0a5-1b5a7b3592dd/resource/0fb4e415-abdb-481a-a3c6-8821e79919be/download/internal-displacements-new-displacements-idps.csv"


async def fetch(client: httpx.AsyncClient):
    try:
        r = await client.get(HDX_CSV_URL, timeout=30, follow_redirects=True)
        if r.status_code != 200:
            print(f"[idmc] HTTP {r.status_code}")
            return None

        reader = csv.DictReader(io.StringIO(r.text))
        by_country = {}

        for row in reader:
            try:
                iso3 = row.get("iso3", "").strip()
                country = row.get("country_name", "").strip()
                year = row.get("year", "").strip()
                new_disp = row.get("new_displacement", "") or row.get("new_displacement_rounded", "")
                total_disp = row.get("total_displacement", "") or row.get("total_displacement_rounded", "")

                new_val = int(float(new_disp)) if new_disp and new_disp not in ("", "0") else 0
                total_val = int(float(total_disp)) if total_disp and total_disp not in ("", "0") else 0

                if not iso3 or (new_val == 0 and total_val == 0):
                    continue

                rec = by_country.setdefault(iso3, {
                    "country": country, "iso3": iso3,
                    "years": {},
                    "latest_new": 0, "latest_total": 0, "latest_year": "",
                })
                rec["years"][year] = {
                    "new_displacement": new_val,
                    "total_displacement": total_val,
                }
                # Track latest year
                if year > rec["latest_year"]:
                    rec["latest_year"] = year
                    rec["latest_new"] = new_val
                    rec["latest_total"] = total_val

            except (ValueError, TypeError):
                continue

        return {
            "source": "IDMC via HDX",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(by_country),
            "countries": by_country,
        }
    except Exception as e:
        print(f"[idmc] error: {e}")
        return None


register(LAYER, fetch)
