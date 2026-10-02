"""Vehicle model names, from NHTSA's vehicle-list API and from NHTSA's recall file.

NHTSA's recall and complaint records often name the same vehicle differently: the 2026 Lucid Air's
recalls are filed under "AIR" and its complaints under "AIR BEV", and the vehicle-list API offers only
"AIR BEV". A recall is found only by the exact model name it's filed under, so this combines the API's
list with every name in NHTSA's recall file (web/public/vehicles/, built by
scripts/build_vehicle_index.py), and a search covers related names. web/src/lib/vehicles.ts does the
same in the browser. NHTSA's searches ignore capitals, so names are kept in capitals.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .nhtsa import Fetch, NhtsaError, http_get, listed_models

INDEX = Path(__file__).resolve().parents[2] / "web" / "public" / "vehicles"


@lru_cache(maxsize=4)
def _years(folder: Path) -> frozenset[str]:
    return frozenset(json.loads((folder / "years.json").read_text(encoding="utf-8")))


@lru_cache(maxsize=64)
def recall_names(year: str, folder: Path = INDEX) -> dict[str, tuple[str, ...]]:
    """The recall file's makes and models for one model year ({} for a year it doesn't have)."""
    if year not in _years(folder):
        return {}
    data = json.loads((folder / f"{year}.json").read_text(encoding="utf-8"))
    return {make: tuple(models) for make, models in data.items()}


def vehicle_models(year: str, make: str, fetch: Fetch = http_get, folder: Path = INDEX) -> list[str]:
    """Model names from both sources, in capitals, sorted, without repeats.

    Either source is enough if the other fails; both failing raises NhtsaError.
    """
    make = make.strip().upper()
    names: list[str] = []
    failures: list[Exception] = []
    try:
        names += listed_models(year, make, fetch)
    except NhtsaError as error:
        failures.append(error)
    try:
        names += recall_names(year, folder).get(make, ())
    except (OSError, ValueError) as error:
        failures.append(error)
    if len(failures) == 2:
        raise NhtsaError("Couldn't load the vehicle names.") from failures[0]
    return sorted({name.strip().upper() for name in names if name.strip()})


def related(a: str, b: str) -> bool:
    """True if the names are equal or one is the other plus more words ("AIR" and "AIR BEV")."""
    return a == b or a.startswith(f"{b} ") or b.startswith(f"{a} ")


def related_names(name: str, names: list[str]) -> list[str]:
    """The chosen name first, then every related name from the list."""
    return [name, *(other for other in names if other != name and related(name, other))]
