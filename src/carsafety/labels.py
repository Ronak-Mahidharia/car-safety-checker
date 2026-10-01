"""Turn NHTSA's component descriptions into a clean, stable set of labels.

A complaint row's COMPDESC looks like "SERVICE BRAKES:DISC BRAKE:CALIPER". We keep the
top-level part (before the first ":"). NHTSA renamed some categories over the years,
so old names are merged into the current ones. "Unknown"-style values aren't a real
answer, so they map to None and are never scored.
"""
from __future__ import annotations

# Old or variant names -> the current NHTSA category.
MERGE = {
    "ENGINE AND ENGINE COOLING": "ENGINE",
    "SERVICE BRAKES, HYDRAULIC": "SERVICE BRAKES",
    "SERVICE BRAKES, AIR": "SERVICE BRAKES",
    "SERVICE BRAKES, ELECTRIC": "SERVICE BRAKES",
    "SERVICE BRAKES, HYDRAULIC; AUTOHOLD BRAKE SYSTEM/BRAKE HOLD": "SERVICE BRAKES",
    "FUEL SYSTEM, GASOLINE": "FUEL/PROPULSION SYSTEM",
    "FUEL SYSTEM, DIESEL": "FUEL/PROPULSION SYSTEM",
    "FUEL SYSTEM, OTHER": "FUEL/PROPULSION SYSTEM",
    "HYBRID PROPULSION SYSTEM": "FUEL/PROPULSION SYSTEM",
    "VISIBILITY": "VISIBILITY/WIPER",
    "ELECTRONIC STABILITY CONTROL": "ELECTRONIC STABILITY CONTROL (ESC)",
    "COMMUNICATIONS": "COMMUNICATION",
    # Sub-parts from NHTSA's car-seat form
    "CHEST CLIP, BUCKLE, HARNESS": "CHILD SEAT",
    "CARRY HANDLE, SHELL, BASE": "CHILD SEAT",
    "TETHER, LOWER ANCHOR (ON CAR SEAT OR VEHICLE)": "CHILD SEAT",
    "INSERT, PADDING": "CHILD SEAT",
    "I SUSPECT THE CAR SEAT IS COUNTERFEIT": "CHILD SEAT",
}

# Values that mean "the owner didn't know". Not a label.
UNKNOWN = {"", "UNKNOWN OR OTHER", "OTHER/UNKNOWN", "OTHER/I AM NOT SURE", "NONE", "OTHER"}


def normalize(compdesc: str) -> str | None:
    """Return the clean top-level label for one COMPDESC value, or None if unknown."""
    top = compdesc.split(":", 1)[0].strip().upper()
    if top in UNKNOWN:
        return None
    return MERGE.get(top, top)


def normalize_all(compdescs) -> tuple[str, ...]:
    """Clean labels for all of a complaint's rows: sorted, unique, unknowns dropped."""
    return tuple(sorted({label for c in compdescs if (label := normalize(c)) is not None}))
