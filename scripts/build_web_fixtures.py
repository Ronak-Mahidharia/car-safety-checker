"""Build the fixtures that check the website's TypeScript gives the same answers as the Python code.

Writes two files to web/src/lib/fixtures/:
  - labels.json: every component name in NHTSA's complaint files (received 2015 to 2026) and recall
    file, with the label src/carsafety/labels.py gives it. It also has complaint-API-style lists of
    several components ("ENGINE,FUEL SYSTEM, GASOLINE") and how they split.
  - privacy.json: made-up text with emails, phone numbers, and VINs, and what
    src/carsafety/privacy.py makes of it.

Needs the files from scripts/download_data.py. Only the component column is kept from each row.

    python scripts/build_web_fixtures.py
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from carsafety.complaints import FIELDS as COMPLAINT_FIELDS
from carsafety.labels import normalize
from carsafety.privacy import scrub
from carsafety.recalls import FIELDS as RECALL_FIELDS

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
    print(f"{len(names):,} component names ({len(tops)} top-level), {len(split_cases):,} lists, "
          f"{len(privacy_cases)} privacy cases -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
