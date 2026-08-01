"""ACLED — PERMANENTLY DISABLED per ACLED policy (2026-04).

ACLED denied API access for this project via their EULA clause 3.1:

    "external use of ACLED data is only permitted where the resulting
    output is sufficiently transformative and cannot be reverse-engineered
    to reconstruct ACLED's dataset. The integration of ACLED data into
    tools such as you propose results in ACLED data being displayed in a
    format that does not meet this requirement."

This is a policy decision, not a technical one — no whitelist, tier
upgrade, or workaround fixes it. Map visualization of ACLED event data
is explicitly forbidden by their license.

The full OAuth 2.0 password-grant + refresh implementation is preserved
in git history (see commits before 2026-04-09) in case ACLED ever
renegotiates. For now this source stays registered as disabled so the
layer metadata endpoint can still surface it as "unavailable".

Conflict event data for this project now comes from:
  - gdelt_events.py  — real-time GDELT Events 2.0 (CAMEO 18/19/20)
  - ucdp.py          — UCDP GED (academic, awaiting free token)
"""
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="acled",
    name="ACLED Conflict Events",
    category="war",
    kind="points",
    source="ACLED — Armed Conflict Location & Event Data",
    source_url="https://acleddata.com/",
    license="ACLED EULA — map visualization not permitted (clause 3.1)",
    refresh_s=86400,
    initial_delay_s=99999,
    units="fatalities",
    description=(
        "Unavailable. ACLED denied API access for this project per their "
        "EULA clause 3.1, which prohibits displaying ACLED data in formats "
        "that are not 'sufficiently transformative'. See source file "
        "comment for the full quoted denial."
    ),
    requires_key=True,
    key_env="(denied by ACLED policy)",
    enabled=False,
)


async def fetch(client: httpx.AsyncClient):
    return None


register(LAYER, fetch)
