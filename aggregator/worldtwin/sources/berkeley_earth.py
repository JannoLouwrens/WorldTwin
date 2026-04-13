"""Berkeley Earth — global surface temperature anomaly (monthly).
Free CSV download. Provides the historical climate context that current
weather data lacks. Shows how today compares to the 1951-1980 baseline.
"""
from datetime import datetime, timezone
import httpx
from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="berkeley_earth",
    name="Berkeley Earth — Temperature Anomaly",
    category="weather",
    kind="raw",
    source="Berkeley Earth Surface Temperatures",
    source_url="https://berkeleyearth.org/data/",
    license="CC BY-NC 4.0",
    refresh_s=604800 * 4,  # monthly data, check every 4 weeks
    initial_delay_s=130,
    description="Monthly global mean surface temperature anomaly relative to 1951-1980 baseline.",
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    try:
        # Berkeley Earth monthly global mean
        r = await client.get(
            "https://berkeley-earth-temperature.s3.us-west-1.amazonaws.com/Global/Land_and_Ocean_summary.txt",
            timeout=30,
        )
        if r.status_code != 200:
            # Fallback URL
            r = await client.get(
                "http://berkeleyearth.lbl.gov/auto/Global/Land_and_Ocean_summary.txt",
                timeout=30,
            )
        if r.status_code != 200:
            print(f"[berkeley_earth] HTTP {r.status_code}")
            return None

        lines = r.text.strip().split("\n")
        # Parse — format is ANNUAL: Year  Anomaly  Uncertainty  10yr-Anomaly  10yr-Unc  ...
        # Comment lines start with %
        annual = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                year = int(float(parts[0]))
                anomaly = float(parts[1])
                unc = None
                if len(parts) > 2 and parts[2] != "NaN":
                    unc = float(parts[2])
                if year >= 1950:
                    annual.append({
                        "year": year,
                        "period": str(year),
                        "anomaly_c": round(anomaly, 3),
                        "uncertainty_c": round(unc, 3) if unc else None,
                    })
            except (ValueError, IndexError):
                continue

        latest = annual[-1] if annual else None

        # Trend: last 5 years average vs previous 5
        recent = [a["anomaly_c"] for a in annual[-5:]]
        prev = [a["anomaly_c"] for a in annual[-10:-5]]
        trend = None
        if len(recent) >= 3 and len(prev) >= 3:
            trend = round(sum(recent) / len(recent) - sum(prev) / len(prev), 3)

        return {
            "source": "Berkeley Earth",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "baseline": "1951-1980 average",
            "count": len(annual),
            "latest": latest,
            "trend_5yr_vs_prev_5yr": trend,
            "annual": annual,
        }
    except Exception as e:
        print(f"[berkeley_earth] error: {e}")
        return None


register(LAYER, fetch)
