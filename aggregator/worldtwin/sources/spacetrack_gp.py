"""Space-Track — full SATCAT + GP (general perturbations) for every tracked object.

Cookie-session login pattern. Free tier 200 queries/hour; we use ~3 queries
per fetch, refresh every 8 hours = 9 queries/day. Well under budget.

Replaces CelesTrak (531 objects) with the full 25,000+ active payloads +
rocket bodies + debris tracked by US Space Force.
"""
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

SPACE_TRACK_USER = os.environ.get("SPACE_TRACK_USER", "")
SPACE_TRACK_PASS = os.environ.get("SPACE_TRACK_PASS", "")

LAYER = LayerMeta(
    id="spacetrack_gp",
    name="Space-Track — Full Satellite Catalogue",
    category="space",
    kind="raw",
    source="Space-Track.org (US Space Force)",
    source_url="https://www.space-track.org/",
    license="Space-Track Terms (free non-commercial)",
    refresh_s=28800,  # 8 hours to respect 200 query/hr budget
    initial_delay_s=125,
    description=(
        "Full SATCAT + GP elements for every tracked object: 25k+ active payloads, "
        "rocket bodies, and debris. TLEs shipped raw for client-side SGP4."
    ),
    requires_key=True,
    key_env="SPACE_TRACK_USER+SPACE_TRACK_PASS",
    enabled=bool(SPACE_TRACK_USER and SPACE_TRACK_PASS),
)


async def fetch(client: httpx.AsyncClient):
    if not (SPACE_TRACK_USER and SPACE_TRACK_PASS):
        return None
    # Use a SEPARATE httpx client with its own cookie jar for this call
    # so we don't contaminate the shared aggregator client.
    async with httpx.AsyncClient(
        timeout=120,
        headers={"User-Agent": "WorldTwin/1.0 (jannolouwrens@gmail.com)"},
        follow_redirects=True,
    ) as st:
        try:
            # 1. Login
            r = await st.post(
                "https://www.space-track.org/ajaxauth/login",
                data={"identity": SPACE_TRACK_USER, "password": SPACE_TRACK_PASS},
            )
            if r.status_code != 200:
                print(f"[spacetrack_gp] login {r.status_code}")
                return None

            # 2. Query active payloads (decay_date IS NULL) + limit to last 2 years of epoch
            #    This gives us ~25k active objects without pulling historical garbage.
            r = await st.get(
                "https://www.space-track.org/basicspacedata/query/class/gp/"
                "decay_date/null-val/epoch/%3Enow-30/orderby/norad_cat_id/"
                "format/json/emptyresult/show",
            )
            if r.status_code != 200:
                print(f"[spacetrack_gp] gp query {r.status_code}: {r.text[:120]}")
                return None
            gp = r.json() if r.content else []

            # 3. Build output
            by_type: dict[str, int] = {}
            by_country: dict[str, int] = {}
            by_regime: dict[str, int] = {}
            catalogue: list[dict[str, Any]] = []

            for row in gp:
                # Many fields at Space-Track — we cherry-pick the useful ones.
                try:
                    period = float(row.get("PERIOD") or 0)
                    incl = float(row.get("INCLINATION") or 0)
                    apo = float(row.get("APOAPSIS") or 0)  # km above surface
                    per = float(row.get("PERIAPSIS") or 0)
                except (ValueError, TypeError):
                    period = incl = apo = per = 0
                # Orbital regime
                avg_alt = (apo + per) / 2
                if avg_alt < 2000:
                    regime = "LEO"
                elif avg_alt < 10000:
                    regime = "MEO"
                elif 35000 < avg_alt < 36500:
                    regime = "GEO"
                elif avg_alt > 36500:
                    regime = "HEO"
                else:
                    regime = "MEO"
                obj_type = (row.get("OBJECT_TYPE") or "UNKNOWN").strip()
                country = (row.get("COUNTRY_CODE") or "UNK").strip()
                by_type[obj_type] = by_type.get(obj_type, 0) + 1
                by_country[country] = by_country.get(country, 0) + 1
                by_regime[regime] = by_regime.get(regime, 0) + 1
                catalogue.append({
                    "norad": int(row.get("NORAD_CAT_ID", 0) or 0),
                    "name": row.get("OBJECT_NAME", ""),
                    "type": obj_type,
                    "country": country,
                    "launch": row.get("LAUNCH_DATE", ""),
                    "launch_site": row.get("SITE", ""),
                    "period_min": period,
                    "inclination_deg": incl,
                    "apoapsis_km": apo,
                    "periapsis_km": per,
                    "regime": regime,
                    "rcs_size": row.get("RCS_SIZE") or "",
                    "tle_line1": row.get("TLE_LINE1") or "",
                    "tle_line2": row.get("TLE_LINE2") or "",
                    "epoch": row.get("EPOCH") or "",
                })

            # Keep top 3000 payloads + rocket bodies + a sample of debris
            payloads = [c for c in catalogue if c["type"] == "PAYLOAD"]
            rocket_bodies = [c for c in catalogue if c["type"] == "ROCKET BODY"]
            debris = [c for c in catalogue if c["type"] == "DEBRIS"]

            return {
                "source": "Space-Track GP",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "total": len(catalogue),
                "count": len(catalogue),
                "by_type": by_type,
                "by_regime": by_regime,
                "by_country_top10": dict(sorted(by_country.items(), key=lambda x: -x[1])[:10]),
                # Frontend-friendly caps to avoid multi-MB JSON
                "payloads": payloads[:3000],
                "rocket_bodies": rocket_bodies[:500],
                "debris_sample": debris[:500],
            }
        except Exception as e:
            print(f"[spacetrack_gp] error: {e}")
            return None


register(LAYER, fetch)
