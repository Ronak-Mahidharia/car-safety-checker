"""Vehicle model names, and which of NHTSA's records belong to the vehicle someone picks.

NHTSA's API names the same vehicle in more than one way (checked Oct 3, 2026):
  - Its complaint search takes the names in its vehicle list ("AIR BEV", "MUSTANG MACH-E",
    "F-150 (SUPER CREW) LIGHTNING BEV"), but each complaint record names the model the way recalls are
    filed ("AIR", "MUSTANG MACH E", "F-150 LIGHTNING BEV").
  - Its recall search takes only those recall names, and the vehicle list leaves some out (it offers
    only "AIR BEV" for the 2026 Lucid Air), so the picker also offers every name in NHTSA's recall file
    (web/public/vehicles/, built by scripts/build_vehicle_index.py).
  - A complaint search can return another model's records too: the 2023 "F-150 (SUPER CREW) LIGHTNING
    BEV" search returns 94 complaints whose records name the F-150 HYBRID.

So a search covers related names (spelled the same apart from punctuation, or with more words), and
the models named on the complaint records decide which recalls and complaints are the vehicle's own.
Recalls under related names that the records don't tie to the vehicle are kept apart, never dropped:
"MUSTANG" is related to "MUSTANG MACH-E" but is a different car. web/src/lib/vehicles.ts does the same
in the browser. NHTSA's searches ignore capitals, so names are kept in capitals.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .nhtsa import Complaint, Fetch, NhtsaError, Recall, Vehicle, complaints, http_get, listed_models, recalls

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


def words(name: str) -> list[str]:
    """A name's words in capitals, without punctuation: "F-150 (SUPER CREW)" -> ["F150", "SUPER", "CREW"]."""
    return [word for word in (re.sub(r"[^A-Z0-9]", "", part) for part in name.upper().split()) if word]


def same_name(a: str, b: str) -> bool:
    """Spelled the same apart from spaces and punctuation: "MUSTANG MACH-E" and "MUSTANG MACH E"."""
    key = "".join(words(a))
    return key != "" and key == "".join(words(b))


def within(part: str, whole: str) -> bool:
    """True if `whole` is `part` with more words, in order and starting with the same word.

    "AIR" is within "AIR BEV", and "F-150 LIGHTNING BEV" is within "F-150 (SUPER CREW) LIGHTNING BEV".
    """
    p, w = words(part), words(whole)
    if not p or len(p) >= len(w) or p[0] != w[0]:
        return False
    rest = iter(w)
    return all(word in rest for word in p)  # each word found after the one before


def related(a: str, b: str) -> bool:
    """Names that may be the same vehicle: spelled the same, or one is the other with more words."""
    return same_name(a, b) or within(a, b) or within(b, a)


def related_names(name: str, names: list[str]) -> list[str]:
    """The chosen name first, then every related name from the list."""
    return [name, *(other for other in names if other != name and related(name, other))]


def closest_recall_names(name: str, recall_file_names: Iterable[str]) -> list[str]:
    """The recall-file names that are this name or within it, keeping only the most specific.

    For "F-150 (SUPER CREW) LIGHTNING BEV" that's "F-150 LIGHTNING BEV", not "F-150".
    """
    fitting = [r for r in recall_file_names if same_name(r, name) or within(r, name)]
    return [r for r in fitting if not any(within(r, other) for other in fitting)]


def identify(chosen: str, record_models: Iterable[str | None]) -> list[str]:
    """Which model the chosen vehicle is, from the models its complaint records name.

    A search can return another model's records too, so the first of these that finds any is kept:
      1. models spelled like the chosen name or within it ("AIR" for "AIR BEV")
      2. models the chosen name is within
      3. every model named: the 2023 "F-150 (SUPER CREW) HEV" records name the F-150 HYBRID
    With no records, it's the chosen name.
    """
    named: list[str] = []
    for m in record_models:  # each model once, spellings aside ("E 450" and "E450")
        if m and not any(same_name(m, n) for n in named):
            named.append(m)
    for close in ([m for m in named if same_name(m, chosen) or within(m, chosen)], [m for m in named if within(chosen, m)]):
        if close:
            return close
    return named or [chosen]


@dataclass(frozen=True)
class Found:
    """What a search found, split by whether NHTSA's records tie it to the chosen vehicle."""
    names: list[str]  # every name searched, the chosen one first
    models: list[str]  # the models the vehicle's complaint records name (or the chosen name)
    own_names: list[str]  # the names whose recalls are the vehicle's own
    recalls: list[Recall]  # the vehicle's own
    related_recalls: list[Recall]  # filed under related names that may be a different vehicle
    complaints: list[Complaint]  # the vehicle's own
    left_out: dict[str, int]  # complaints the chosen name's search returned whose records name another model


def search(vehicle: Vehicle, listed: list[str], recall_file_names: Iterable[str], fetch: Fetch = http_get) -> Found:
    """Recalls and complaints for a vehicle, under its name and every related name in `listed`.

    The complaints found under the chosen name (or one spelled the same) say which model it is.
    Recalls are its own when filed under the chosen name, a name spelled the same, those models, or
    the closest recall-file names within them; recalls under other related names are kept apart.
    Complaints are its own when their record names one of those models. Complaints the chosen name's
    own search returns also count when their record names a version of one with more words (the 2015
    "FUSION HEV" search returns FUSION HYBRID complaints) or no model at all; the rest are left out. A
    record found twice is kept once.
    """
    def under(name: str) -> Vehicle:
        return Vehicle(vehicle.year, vehicle.make, name)

    names = related_names(vehicle.model, listed)
    found_recalls = {name: recalls(under(name), fetch) for name in names}
    found_complaints = {name: complaints(under(name), fetch) for name in names}

    chosen = [name for name in names if same_name(name, vehicle.model)]
    named = [c.record_model for name in chosen for c in found_complaints[name] if c.record_model]
    own_models = identify(vehicle.model, named)
    # Every spelling the records use is searched: NHTSA files 2020 Mercedes-Benz recall 20V228000 under "E450",
    # while complaint records name both "E450" and "E 450".
    spellings = [m for m in dict.fromkeys(named) if any(same_name(m, o) for o in own_models)] or own_models
    file_names = list(recall_file_names)
    own_names = list(dict.fromkeys([*chosen, *(r for m in spellings for r in (m, *closest_recall_names(m, file_names)))]))
    for name in own_names:  # the records can point to a name the related names didn't include
        if name not in found_recalls:
            found_recalls[name] = recalls(under(name), fetch)

    own: dict[str, Recall] = {}
    for name in own_names:
        for recall in found_recalls[name]:
            own.setdefault(recall.campaign, recall)
    others: dict[str, Recall] = {}
    for name in names:
        for recall in found_recalls[name]:
            if recall.campaign not in own:
                others.setdefault(recall.campaign, recall)

    mine: dict[str, Complaint] = {}
    left_out: dict[str, int] = {}
    seen: set[str] = set()
    # The chosen name's own search first, so its complaints are judged as such.
    for name in [*chosen, *(n for n in names if n not in chosen)]:
        searched_for = name in chosen  # NHTSA's own search for the chosen name returned it
        for complaint in found_complaints[name]:
            if complaint.odi_number in seen:
                continue
            seen.add(complaint.odi_number)
            model = complaint.record_model
            if model is None:
                own_one = searched_for
            else:
                own_one = any(same_name(model, m) for m in own_models) or (searched_for and any(within(m, model) for m in own_models))
            if own_one:
                mine[complaint.odi_number] = complaint
            elif model is not None and searched_for:
                left_out[model] = left_out.get(model, 0) + 1

    return Found(names=list(dict.fromkeys([*names, *own_names])), models=own_models, own_names=own_names,
                 recalls=list(own.values()), related_recalls=list(others.values()), complaints=list(mine.values()),
                 left_out=left_out)
