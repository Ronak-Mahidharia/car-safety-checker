"""Build the list of vehicle names from NHTSA's recall file, for the website's vehicle picker.

NHTSA's recall search takes only the names recalls are filed under, and its vehicle-list API leaves
some of them out: it offers only "AIR BEV" for the 2026 Lucid Air, whose recalls are filed under
"AIR". So the picker also offers every name in the recall file, and the search uses them to find a
vehicle's recalls (see src/carsafety/vehicles.py). scripts/check_vehicle_names.py measures how the
names compare in NHTSA's live API.

Writes web/public/vehicles/years.json (the model years) and one web/public/vehicles/<year>.json per
model year ({make: [model, ...]}).

    python scripts/build_vehicle_index.py
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

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

    digest = hashlib.sha256(RECALLS.read_bytes()).hexdigest()
    size = sum(p.stat().st_size for p in OUT.glob("*.json"))
    print(f"{sum(len(m) for m in recalls.values()):,} vehicle names, {len(recalls):,} year and make pairs, "
          f"{len(years)} model years ({years[-1]} to {years[0]}), {size / 1e6:.2f} MB in {OUT.relative_to(ROOT)}")
    print(f"source: {RECALLS.name}, SHA-256 {digest}")


if __name__ == "__main__":
    main()
