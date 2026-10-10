"""Download NHTSA's complaint files (received 2015 onward) and the recalls file.

Saves them to data/raw/, checks each zip is intact, unzips it, and prints its SHA-256
so results can be tied to an exact version of the data, saying whether each complaint file
is the one the published answer key was built from. NHTSA updates its files in place, so a
later download usually differs. Skips files already present unless --force is given.

    python scripts/download_data.py
"""
from __future__ import annotations

import argparse
import shutil
import urllib.request
import zipfile
from pathlib import Path

from carsafety.complaints import PUBLISHED_SOURCES, sha256

BASE = "https://static.nhtsa.gov/odi/ffdd"
FILES = [
    "cmpl/COMPLAINTS_RECEIVED_2015-2019.zip",
    "cmpl/COMPLAINTS_RECEIVED_2020-2024.zip",
    "cmpl/COMPLAINTS_RECEIVED_2025-2026.zip",
    "rcl/FLAT_RCL_POST_2010.zip",
]
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="download again even if the file exists")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = RAW / Path(name).name
        if args.force or not target.exists():
            print(f"downloading {name} ...")
            with urllib.request.urlopen(f"{BASE}/{name}", timeout=600) as response, target.open("wb") as out:
                shutil.copyfileobj(response, out)
        with zipfile.ZipFile(target) as archive:
            bad = archive.testzip()
            if bad:
                raise SystemExit(f"{target.name} is damaged ({bad}); delete it and run again")
            archive.extractall(RAW)
        digest = sha256(target)
        note = ""
        if target.name in PUBLISHED_SOURCES:
            note = (" (the published answer key's file)" if digest == PUBLISHED_SOURCES[target.name]
                    else " (NHTSA has updated it since the published answer key was built)")
        print(f"{target.name}: {target.stat().st_size:,} bytes, sha256 {digest}{note}")


if __name__ == "__main__":
    main()
