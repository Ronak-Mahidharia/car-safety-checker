"""Build the fixtures that check the website's TypeScript gives the same answers as the Python code.

Writes three files to web/src/lib/fixtures/:
  - labels.json: every component name in NHTSA's complaint files (received 2015 to 2026) and recall
    file, with the label src/carsafety/labels.py gives it. It also has complaint-API-style lists of
    several components ("ENGINE,FUEL SYSTEM, GASOLINE") and how they split.
  - privacy.json: made-up text with emails, phone numbers, and VINs, and what
    src/carsafety/privacy.py makes of it.
  - names.json: vehicle names and how src/carsafety/vehicles.py compares them: names NHTSA uses for
    the same or similar vehicles, edge cases, and 1,000 names picked at random from NHTSA's recall file
    (web/public/vehicles/). tests/test_vehicles.py checks the Python code still gives these answers.

Needs the files from scripts/download_data.py. Only the component column is kept from each row.

    python scripts/build_web_fixtures.py
"""
from __future__ import annotations

import csv
import json
import random
import re
from pathlib import Path

from carsafety.complaints import FIELDS as COMPLAINT_FIELDS
from carsafety.labels import normalize
from carsafety.privacy import scrub
from carsafety.recalls import FIELDS as RECALL_FIELDS
from carsafety.vehicles import INDEX, closest_recall_names, identify, recall_names, related, same_name, within, words

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "web" / "src" / "lib" / "fixtures"

# The complaints API joins a complaint's components with a comma and no space, while names that
# contain a comma ("FUEL SYSTEM, GASOLINE") have a space after it. Same rule as web/src/lib/labels.ts.
SPLIT = re.compile(r",(?=\S)")

EDGE_CASES = ["", "   ", "engine", " Engine And Engine Cooling : cooling ", "VISIBILITY:WIPER", "unknown or other",
              "OTHER", "Other/Unknown:", "AIR BAGS:FRONTAL", "Service Brakes, Hydraulic:ABS", "ÉCLAIRAGE"]

PRIVACY_CASES = [
    "",
    "[removed]",
    "Call me at 555-123-4567, (555) 123-4567, 555.123.4567, or 555 123 4567.",
    "With a country code: +1 555 123 4567, +1-555-123-4567, 1 (555) 123-4567, 15551234567.",
    "Digits around it: 1234555-123-45678 and order 98765551234567 stay.",
    "Email john.doe+cars@example.com or JANE_DOE@MAIL.CO.UK, then a period.",
    "An email at the end of a sentence: write to john@example.com. Then more text.",
    "Accented email: josé@ejemplo.es and ünal@örnek.com.tr",
    "VIN 1HGCM82633A004352 is masked; 1hgcm82633a004352 (lowercase) is not.",
    "A VIN with I, O, or Q is not a VIN: 1HGCM82633A00435I 1HGCM82633A00435O.",
    "Too short or long: 1HGCM82633A00435 and 1HGCM82633A0043521.",
    "Glued to letters: X1HGCM82633A004352 é1HGCM82633A004352 1HGCM82633A004352é",
    "Seventeen digits 12345678901234567 look like a VIN too.",
    "Other digits: ٥٥٥-١٢٣-٤٥٦٧ (Arabic-Indic).",
    "No-break spaces: 555 123 4567.",
    "An email with a number 5551234567@example.com is masked once.",
    "Dates and money are left alone: 01/15/2024, 2024-01-15, $1,234.56, 120,000 miles.",
    "THE DEALER (DEALER NAME) SAID CALL 800 555 0199 EXT 12 OR EMAIL SERVICE@DEALER.COM",
    "Line\nbreaks\r\naround 555-123-4567\nand\tTABS",
]


# Names NHTSA uses for the same or similar vehicles (seen in its API on Oct 3, 2026): names in its vehicle
# list and recall file, and names complaint records give. "CRV" is a misspelling someone could type.
NAME_GROUPS = {
    ("2022", "FORD"): ["MUSTANG", "MUSTANG MACH-E", "MUSTANG MACH E", "MUSTANG GT 500"],
    ("2023", "FORD"): ["F-150", "F-150 LIGHTNING", "F-150 LIGHTNING BEV", "F-150 HYBRID", "F-150 (REGULAR CAB) GAS",
                       "F-150 (SUPER CAB) GAS", "F-150 (SUPER CREW) GAS", "F-150 (SUPER CREW) HEV",
                       "F-150 (SUPER CREW) LIGHTNING BEV"],
    ("2026", "LUCID"): ["AIR", "AIR BEV", "GRAVITY", "GRAVITY BEV"],
    ("2024", "CHEVROLET"): ["BLAZER", "BLAZER EV", "TRAILBLAZER", "EQUINOX", "EQUINOX EV"],
    ("2019", "HONDA"): ["CR-V", "CRV", "HR-V", "CIVIC", "ACCORD"],
    ("2023", "TESLA"): ["MODEL 3", "MODEL Y", "MODEL Y (ALL VARIANTS)", "MODEL Y RWD EARLY RELEASE", "MODEL Y RWD LATER RELEASE"],
    ("2023", "VOLKSWAGEN"): ["ID 4", "ID.4"],
}
NAME_EDGE_CASES = ["", "   ", "-", "air bev", " Air  Bev ", "MODEL Y (ALL VARIANTS) ", "C-HR", "C HR", "CHR", "E-TRON GT",
                   "AIRSTREAM", "MODEL 3 LONG RANGE", "GRAND CHEROKEE", "GRAND CHEROKEE L", "GRAND WAGONEER", "ÉCLAIR 2"]
# Which model a vehicle is, from the models its complaint records name (None: the record names none).
IDENTIFY_CASES = [
    ["AIR BEV", ["AIR", "AIR", None]],
    ["AIR", []],
    ["MUSTANG MACH-E", ["MUSTANG MACH E"]],
    ["F-150 (SUPER CREW) LIGHTNING BEV", ["F-150 LIGHTNING BEV", "F-150 HYBRID", "F-150 LIGHTNING BEV"]],
    ["F-150 (SUPER CREW) HEV", ["F-150 HYBRID"]],
    ["F-150", ["F-150", "F-150 HYBRID"]],
    ["CR-V", ["CR-V", None]],
    ["E-CLASS", ["E 450", "E 350", "E350", "E450", "AMG E53"]],
    ["TBD", [None, None]],
]


def name_cases() -> dict[str, list]:
    """How src/carsafety/vehicles.py compares names, for web/src/lib/vehicles.test.ts."""
    years = json.loads((INDEX / "years.json").read_text(encoding="utf-8"))
    every = sorted({model for year in years for models in recall_names(year).values() for model in models})
    picked = random.Random(3).sample(every, 1000)
    grouped = [name for names in NAME_GROUPS.values() for name in names]
    words_cases = [[name, words(name)] for name in dict.fromkeys(grouped + NAME_EDGE_CASES + picked)]
    pair_names = [names for names in NAME_GROUPS.values()] + [NAME_EDGE_CASES]
    pairs = [[a, b, same_name(a, b), within(a, b), related(a, b)] for names in pair_names for a in names for b in names]
    closest = []
    for (year, make), names in NAME_GROUPS.items():
        file_names = list(recall_names(year).get(make, ()))
        closest += [[name, file_names, closest_recall_names(name, file_names)] for name in names]
    return {"words": words_cases, "pairs": pairs, "closest": closest,
            "identify": [[chosen, models, identify(chosen, models)] for chosen, models in IDENTIFY_CASES]}


def components(path: Path, fields: list[str], name: str) -> set[str]:
    """Distinct values of one column, keeping nothing else from each row."""
    index = fields.index(name)
    values: set[str] = set()
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) > index:
                values.add(row[index])
    return values


def write(path: Path, sections: dict[str, list]) -> None:
    """One case per line, so changes are easy to review."""
    parts = []
    for key, cases in sections.items():
        lines = ",\n".join(json.dumps(case, ensure_ascii=False) for case in cases)
        parts.append(f"{json.dumps(key)}: [\n{lines}\n]")
    path.write_text("{\n" + ",\n".join(parts) + "\n}\n", encoding="utf-8")


def main() -> None:
    names: set[str] = set()
    for path in sorted(RAW.glob("COMPLAINTS_RECEIVED_*.txt")):
        names |= components(path, COMPLAINT_FIELDS, "COMPDESC")
    names |= components(RAW / "FLAT_RCL_POST_2010.txt", RECALL_FIELDS, "COMPNAME")

    # The comma rule only works if no category name has a comma followed directly by a letter.
    tops = sorted({n.split(":", 1)[0].strip().upper() for n in names} - {""})
    clashes = [t for t in tops if re.search(r",\S", t)]
    if clashes:
        raise SystemExit(f"These names break the comma rule: {clashes}")

    normalize_cases = [[n, normalize(n)] for n in sorted(names | set(EDGE_CASES))]
    lists = sorted({joined for t in tops for joined in (f"{t},ENGINE", f"AIR BAGS,{t}", f"STEERING,{t},TIRES")})
    split_cases = [[s, SPLIT.split(s)] for s in lists]
    privacy_cases = [[text, scrub(text)] for text in PRIVACY_CASES]

    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "labels.json", {"normalize": normalize_cases, "split": split_cases})
    write(OUT / "privacy.json", {"scrub": privacy_cases})
    vehicle_names = name_cases()
    write(OUT / "names.json", vehicle_names)
    print(f"{len(names):,} component names ({len(tops)} top-level), {len(split_cases):,} lists, "
          f"{len(privacy_cases)} privacy cases, {len(vehicle_names['words']):,} vehicle names and "
          f"{len(vehicle_names['pairs']):,} pairs -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
