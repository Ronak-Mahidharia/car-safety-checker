"""Check the vehicle-name rules against NHTSA's live API, for docs/website.md.

NHTSA's complaint search takes the names in its vehicle list ("AIR BEV"), its recall search takes the
names in its recall file ("AIR"), and each complaint record names the model the way recalls are filed
(see src/carsafety/vehicles.py). This samples names from NHTSA's vehicle list and, for each one with
complaints, compares two ways to find its recalls:
  - the old rule: the chosen name plus names that are it with more words, or that it is with more words
  - the new search: the models the complaint records name decide which recalls are the vehicle's own
It counts how often the old rule showed recalls NHTSA files under other models' names as the vehicle's
own, and how often it missed recalls filed under the vehicle's recall names. It also counts:
  - complaints NHTSA's search returns whose records name another model, which the search leaves out
  - campaigns NHTSA's recall file lists under a vehicle's recall names that the API doesn't return under
    them, and the names the API uses for those campaigns instead

Model years and makes are sampled in proportion to their complaints in NHTSA's complaint files (model
years 2015 to 2026), so common vehicles are picked more often; names are then picked at random from
NHTSA's vehicle list for each. Only NHTSA's public API is called, one request at a time, and each answer
is kept in memory for the run. The files only supply counts and campaign numbers; no personal field is
read. Needs the files from scripts/download_data.py.

    python scripts/check_vehicle_names.py    # about 1,500 requests, several minutes
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

from carsafety import nhtsa
from carsafety.complaints import FIELDS as COMPLAINT_FIELDS
from carsafety.recalls import FIELDS as RECALL_FIELDS
from carsafety.vehicles import recall_names, same_name, search, vehicle_models

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def old_related_names(name: str, names: list[str]) -> list[str]:
    """The rule before Oct 3, 2026: the name, plus names that are it with more words, or the reverse."""
    return [name, *(o for o in names if o != name and (o.startswith(f"{name} ") or name.startswith(f"{o} ")))]


def complaint_counts() -> Counter:
    """(model year, make) -> vehicle complaints in NHTSA's complaint files, model years 2015 to 2026."""
    iy, im, ik = (COMPLAINT_FIELDS.index(f) for f in ("YEARTXT", "MAKETXT", "PROD_TYPE"))
    counts: Counter = Counter()
    for path in sorted(RAW.glob("COMPLAINTS_RECEIVED_*.txt")):
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if len(row) > max(iy, im, ik) and row[ik] == "V" and "2015" <= row[iy].strip() <= "2026":
                    counts[(row[iy].strip(), row[im].strip().upper())] += 1
    return counts


def file_campaigns() -> dict[tuple[str, str, str], set[str]]:
    """(model year, make, model) -> vehicle campaigns in NHTSA's recall file."""
    ic, iy, im, io, ik = (RECALL_FIELDS.index(f) for f in ("CAMPNO", "YEARTXT", "MAKETXT", "MODELTXT", "RCLTYPECD"))
    found: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    with (RAW / "FLAT_RCL_POST_2010.txt").open(encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) > max(ic, iy, im, io, ik) and row[ik] == "V":
                found[(row[iy].strip(), row[im].strip().upper(), row[io].strip().upper())].add(row[ic].strip())
    return found


class Gentle:
    """NHTSA's API, one request at a time with a short pause, each answer kept for the run."""

    def __init__(self) -> None:
        self.answers: dict[str, tuple[int, bytes]] = {}
        self.asked = 0

    def __call__(self, url: str) -> tuple[int, bytes]:
        if url not in self.answers:
            for attempt in range(5):
                time.sleep(0.1 * 2 ** attempt)
                self.asked += 1
                status, body = nhtsa.http_get(url)
                if status not in (429, 500, 502, 503, 504):
                    break
            self.answers[url] = (status, body)
        return self.answers[url]


def share(part: int, whole: int) -> str:
    return f"{part:,} of {whole:,} ({part / whole:.1%})" if whole else "0"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pairs", type=int, default=30, help="model year and make pairs to sample")
    parser.add_argument("--names", type=int, default=8, help="names to pick from NHTSA's vehicle list for each pair")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    counts, campaigns = complaint_counts(), file_campaigns()
    rng = random.Random(args.seed)
    keys = sorted(counts)
    pairs: list[tuple[str, str]] = []
    while len(pairs) < min(args.pairs, len(keys)):
        pick = rng.choices(keys, weights=[counts[k] for k in keys])[0]
        if pick not in pairs:
            pairs.append(pick)

    fetch = Gentle()
    rows, skipped = [], 0
    for year, make in pairs:
        listed = vehicle_models(year, make, fetch)
        file_names = recall_names(year).get(make, ())
        api_names = nhtsa.listed_models(year, make, fetch)
        for name in sorted(rng.sample(api_names, min(args.names, len(api_names)))):
            vehicle = nhtsa.Vehicle(year, make, name)
            under_name = nhtsa.complaints(vehicle, fetch)
            if not under_name:
                skipped += 1
                continue
            found = search(vehicle, listed, file_names, fetch)
            own = {r.campaign for r in found.recalls}
            old: set[str] = set()
            for other in old_related_names(name, listed):
                old |= {r.campaign for r in nhtsa.recalls(nhtsa.Vehicle(year, make, other), fetch)}
            # Campaigns the recall file lists under the vehicle's names that no search of them found.
            lost = set().union(*(campaigns.get((year, make, n), set()) for n in found.own_names)) - own
            rows.append({
                "vehicle": f"{year} {make} {name}", "complaints": len(under_name), "models": found.models,
                "renamed": not any(same_name(name, m) for m in found.models),
                "other_model": sum(found.left_out.values()),
                "old_wrong": sorted(old - own), "old_missed": sorted(own - old), "lost": sorted(lost),
            })
        print(f"  {year} {make}: {len(rows)} names so far, {fetch.asked:,} requests", flush=True)

    # Where the API files the campaigns it doesn't return under the recall file's name.
    lost_names: dict[str, list] = {}
    for campaign in sorted({c for row in rows for c in row["lost"]}):
        status, body = fetch(f"{nhtsa.API}/recalls/campaignNumber?{nhtsa.query(campaignNumber=campaign)}")
        found_rows = json.loads(body).get("results", []) if body else []
        lost_names[campaign] = sorted({(r.get("ModelYear"), r.get("Make"), r.get("Model")) for r in found_rows})

    n, weight = len(rows), sum(r["complaints"] for r in rows)
    def tally(key):
        hit = [r for r in rows if r[key]]
        return f"{share(len(hit), n)} names; {share(sum(r['complaints'] for r in hit), weight)} complaints"
    print(f"\n{len(pairs)} model year and make pairs; {n:,} names with complaints ({skipped:,} picked names had none); "
          f"{weight:,} complaints; {fetch.asked:,} requests")
    print(f"records name a different model than the name searched: {tally('renamed')}")
    print(f"old rule showed recalls filed under other models' names: {tally('old_wrong')}")
    print(f"old rule missed recalls filed under the vehicle's names:  {tally('old_missed')}")
    either = [r for r in rows if r["old_wrong"] or r["old_missed"]]
    print(f"either: {share(len(either), n)} names; {share(sum(r['complaints'] for r in either), weight)} complaints")
    print(f"search returned complaints about another model, left out: {tally('other_model')}; "
          f"{sum(r['other_model'] for r in rows):,} such complaints")
    print(f"recall-file campaigns the API doesn't return under the vehicle's recall names: {len(lost_names)}")
    for key in ("renamed", "old_wrong", "old_missed", "other_model"):
        print(f"\n{key}:")
        for r in [r for r in rows if r[key]][:25]:
            print(f"  {r['vehicle']} ({r['complaints']} complaints) models {r['models']} | wrong {len(r['old_wrong'])} "
                  f"missed {len(r['old_missed'])} other model {r['other_model']}")
    print("\nlost campaigns and the names the API files them under:")
    for campaign, names in lost_names.items():
        print(f"  {campaign}: {names[:6]}")


if __name__ == "__main__":
    main()
