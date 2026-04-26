"""CEPII BACI — clean bilateral trade matrix 1995-2024.

BACI ("Base pour l'Analyse du Commerce International") is CEPII's harmonised,
reconciled version of UN Comtrade. ~200 countries × 5,000 HS6 products ×
30 years = ~50M bilateral flow records. The single biggest deepening of our
trade-domain data.

Strategy:
  - On first run (no marker), download the latest BACI HS22 zip (~2-3 GB),
    extract, parse to year-by-year sub-files, write a summary cache.
  - On subsequent runs, just write a stub cache pointing to the existing data.
  - The History Store decomposer picks up the per-year flow lists.

Source: CEPII BACI v202601 (Jan 2026 release).
License: Etalab 2.0 (open, no auth).

NOTE: this is a HEAVY plugin — initial backfill takes ~10-30 min and writes
~3 GB to /data. It's gated by a marker file at /cache/.baci_backfill_done so
the heavy work runs once. Refresh: every 30 days (CEPII updates BACI annually).
"""
from __future__ import annotations

import csv
import io
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="cepii_baci",
    name="CEPII BACI Bilateral Trade Matrix (1995-2024)",
    category="resources",
    kind="raw",
    source="CEPII BACI v202601 (UN Comtrade reconciled)",
    source_url="https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37",
    license="Etalab 2.0 (open)",
    refresh_s=86400 * 30,  # monthly check; actual CEPII refresh is annual
    initial_delay_s=400,
    units="USD (1000s) and metric tonnes",
    description=(
        "Harmonised reconciled bilateral trade matrix from CEPII. ~200 "
        "countries × 5,000 HS6 products × 30 years (1995-2024) = ~50M flows. "
        "Replaces our shallow Comtrade preview with the canonical academic "
        "trade dataset."
    ),
    requires_key=False,
)

BACI_URL = "https://www.cepii.fr/DATA_DOWNLOAD/baci/data/BACI_HS22_V202601.zip"
DATA_DIR = Path(os.environ.get("CACHE_DIR", "/cache")) / "_baci"
MARKER = Path(os.environ.get("CACHE_DIR", "/cache")) / ".baci_backfill_done"


async def _download_and_extract(client: httpx.AsyncClient) -> dict:
    """One-shot download of the BACI zip + parse to per-year summaries.

    Returns a metadata dict with: years_loaded, total_flows, totals_by_year.
    The per-flow detail is too big to keep in the cache JSON; we save it as
    parquet-like CSVs in DATA_DIR for History Store backfill to ingest.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[cepii_baci] downloading {BACI_URL} ...")
    try:
        r = await client.get(BACI_URL, timeout=600, follow_redirects=True)
        if r.status_code != 200:
            print(f"[cepii_baci] download {r.status_code}")
            return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        print(f"[cepii_baci] download failed: {e}")
        return {"error": str(e)}

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    csv_files = [n for n in zf.namelist() if n.endswith(".csv")
                 and "BACI_HS22_Y" in n]
    print(f"[cepii_baci] {len(csv_files)} year files in zip")

    years_loaded = []
    totals_by_year: dict[int, dict[str, float]] = {}
    by_year_top_flows: dict[int, list[dict]] = {}
    grand_total_flows = 0

    for csv_name in sorted(csv_files):
        # File pattern: BACI_HS22_Y2024_V202601.csv
        try:
            year = int(csv_name.split("_Y")[1][:4])
        except (IndexError, ValueError):
            continue
        with zf.open(csv_name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="ignore")
            reader = csv.DictReader(text)
            year_flows = []
            year_total_value = 0.0
            year_total_qty = 0.0
            count = 0
            for row in reader:
                # BACI columns: t (year), i (exporter), j (importer), k (HS6), v (value 1000USD), q (qty tonnes)
                try:
                    val = float(row.get("v") or 0)
                    qty = float(row.get("q") or 0) if row.get("q", "").strip() not in ("", "NA") else 0
                    year_total_value += val
                    year_total_qty += qty
                    count += 1
                    # Keep top flows for the cache (full set goes to disk)
                    year_flows.append({
                        "t": int(row.get("t", year)),
                        "i": int(row.get("i", 0)),
                        "j": int(row.get("j", 0)),
                        "k": row.get("k", ""),
                        "v": val,
                        "q": qty,
                    })
                except (ValueError, TypeError):
                    continue

            # Sort by value desc, keep top 100 for the live cache
            year_flows.sort(key=lambda f: -f["v"])
            top_100 = year_flows[:100]

            years_loaded.append(year)
            totals_by_year[year] = {
                "total_value_1000usd": year_total_value,
                "total_qty_t": year_total_qty,
                "flow_count": count,
            }
            by_year_top_flows[year] = top_100
            grand_total_flows += count

            # Save the full year data to disk for History Store ingestion
            year_path = DATA_DIR / f"baci_y{year}.csv"
            with year_path.open("w", encoding="utf-8") as out:
                w = csv.DictWriter(out, fieldnames=["t", "i", "j", "k", "v", "q"])
                w.writeheader()
                for fl in year_flows:
                    w.writerow(fl)
            print(f"[cepii_baci] year {year}: {count:,} flows, total ${year_total_value/1e6:.1f}B")

    return {
        "years_loaded": years_loaded,
        "totals_by_year": totals_by_year,
        "by_year_top_flows": by_year_top_flows,
        "grand_total_flows": grand_total_flows,
        "data_dir": str(DATA_DIR),
    }


async def fetch(client: httpx.AsyncClient):
    if not MARKER.exists():
        # First run — full backfill
        print("[cepii_baci] first run — performing one-shot bulk import")
        meta = await _download_and_extract(client)
        if "error" in meta:
            return {
                "source": "CEPII BACI",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": 0,
                "error": meta["error"],
            }
        try:
            MARKER.write_text(datetime.now(timezone.utc).isoformat())
        except Exception:
            pass
    else:
        # Subsequent runs — just report the existing data
        meta = {
            "years_loaded": sorted(int(p.stem[6:]) for p in DATA_DIR.glob("baci_y*.csv")),
            "totals_by_year": {},
            "by_year_top_flows": {},
            "grand_total_flows": 0,
            "data_dir": str(DATA_DIR),
            "note": "subsequent run — re-trigger with: rm /cache/.baci_backfill_done",
        }

    return {
        "source": "CEPII BACI v202601",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "year_range": [
            min(meta["years_loaded"]) if meta.get("years_loaded") else None,
            max(meta["years_loaded"]) if meta.get("years_loaded") else None,
        ],
        "count": meta.get("grand_total_flows", 0),
        "years_loaded": meta.get("years_loaded", []),
        "totals_by_year": meta.get("totals_by_year", {}),
        "by_year_top_flows": meta.get("by_year_top_flows", {}),
        "data_dir": meta.get("data_dir"),
    }


register(LAYER, fetch)
