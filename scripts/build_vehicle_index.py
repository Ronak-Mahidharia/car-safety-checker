"""Build the list of vehicle names from NHTSA's recall file, for the website's vehicle picker.

NHTSA's recall and complaint records often name the same vehicle differently. For example, the
2026 Lucid Air's recalls are filed under "AIR" and its complaints under "AIR BEV", and NHTSA's
vehicle-list API offers only "AIR BEV". A recall is found only by the exact model name it's filed
under, so the picker also offers every name in the recall file, and a search covers related
names (one name is the other plus more words).

Writes web/public/vehicles/years.json (the model years) and one web/public/vehicles/<year>.json per
model year ({make: [model, ...]}). Also prints how often recall and complaint records name a vehicle
the same way, for docs/website.md.

    python scripts/build_vehicle_index.py
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from carsafety.complaints import FIELDS as COMPLAINT_FIELDS
from carsafety.recalls import FIELDS as RECALL_FIELDS

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "web" / "public" / "vehicles"
RECALLS = RAW / "FLAT_RCL_POST_2010.txt"


def vehicle_names(path: Path, fields: list[str], kind_field: str, kind: str) -> dict[tuple[str, str], set[str]]:
    """(model year, make) -> model names, from rows of one kind ("V" = vehicle). Keeps nothing else."""
    iy, im, io, ik = (fields.index(f) for f in ("YEARTXT", "MAKETXT", "MODELTXT", kind_field))
    names: dict[tuple[str, str], set[str]] = defaultdict(set)
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) <= max(iy, im, io, ik) or row[ik] != kind:
                continue
            year, make, model = row[iy].strip(), row[im].strip().upper(), row[io].strip().upper()
            if len(year) == 4 and year.isdigit() and year != "9999" and make and model:
                names[(year, make)].add(model)
    return names


def related(a: str, b: str) -> bool:
    """Same rule as web/src/lib/vehicles.ts: equal, or one is the other plus more words."""
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


def main() -> None:
    recalls = vehicle_names(RECALLS, RECALL_FIELDS, "RCLTYPECD", "V")

    by_year: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for (year, make), models in recalls.items():
        by_year[year][make] = sorted(models)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    years = sorted(by_year, reverse=True)
    for year in years:
        makes = dict(sorted(by_year[year].items()))
        (OUT / f"{year}.json").write_text(json.dumps(makes, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "years.json").write_text(json.dumps(years), encoding="utf-8")

    # How often do recall and complaint records use the same name? (model years 2015 to 2026)
    complaints: dict[tuple[str, str], set[str]] = defaultdict(set)
    for path in sorted(RAW.glob("COMPLAINTS_RECEIVED_*.txt")):
        for key, models in vehicle_names(path, COMPLAINT_FIELDS, "PROD_TYPE", "V").items():
            complaints[key] |= models
    same = only_related = neither = 0
    for (year, make), models in recalls.items():
        others = complaints.get((year, make))
        if not ("2015" <= year <= "2026") or not others:
            continue
        for model in models:
            if model in others:
                same += 1
            elif any(related(model, other) for other in others):
                only_related += 1
            else:
                neither += 1
    total = same + only_related + neither

    digest = hashlib.sha256(RECALLS.read_bytes()).hexdigest()
    size = sum(p.stat().st_size for p in OUT.glob("*.json"))
    print(f"{sum(len(m) for m in recalls.values()):,} vehicle names, {len(recalls):,} year and make pairs, "
          f"{len(years)} model years ({years[-1]} to {years[0]}), {size / 1e6:.2f} MB in {OUT.relative_to(ROOT)}")
    print(f"source: {RECALLS.name}, SHA-256 {digest}")
    print(f"recall names for 2015-2026 vehicles whose make and year have complaints: {total:,}")
    print(f"  same model name in complaints: {same:,} ({same / total:.1%})")
    print(f"  only a related name (more words): {only_related:,} ({only_related / total:.1%})")
    print(f"  no matching name (mostly vehicles without complaints): {neither:,} ({neither / total:.1%})")


if __name__ == "__main__":
    main()
