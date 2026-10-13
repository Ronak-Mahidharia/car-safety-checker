"""Build the answer key for reading manufacturers' service bulletins: a fixed sample of the communications NHTSA
published, with the fields NHTSA coded for each (its type, vehicles, model years, and components), which the model
never sees.

    python scripts/build_bulletin_key.py     # after scripts/download_data.py

From NHTSA's TSBS_RECEIVED_2025-2026 file: dev is what NHTSA added to the file before 2026, test what it added from
Jan 1, 2026. A summary that several communications share (revisions, repeats) is kept only in the first one added, so
dev and test never share a summary. Then, for each of NHTSA's six types, 20 dev and 50 test communications drawn at
random (seed 2026), so the rare types can be measured too: warranty extensions are 2.5% of the file. Writes
data/bulletins/key.jsonl and key.json, which records the download's SHA-256 and how many communications of each type
every sample was drawn from, to weigh the results back to the whole file.

NHTSA updates the file in place. If the download differs from the one the published key was built from
(carsafety.bulletins.PUBLISHED_SOURCES), the script stops before writing; --replace-published builds anyway.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from carsafety.bulletins import FILE, PUBLISHED_SOURCES, TYPES, read_bulletins, text_key
from carsafety.complaints import sha256

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
KEY = ROOT / "data" / "bulletins"
SEED, TEST_FROM = 2026, "20260101"
PER_TYPE = {"dev": 20, "test": 50}
UNKNOWN_YEAR = "9999"
STOP = """{file} differs from the download the published answer key was built from (NHTSA updates its files in place).
Nothing was written. To build a new key from it, which replaces the published one and changes every score measured
on it, run: python scripts/build_bulletin_key.py --replace-published"""


def entry(b, split: str) -> dict:
    return {"id": b.id, "split": split, "type": b.type, "added": b.added, "document": b.document, "issued": b.issued,
            "makes": sorted({make for make, _, _ in b.vehicles}),
            "models": sorted({model for _, model, _ in b.vehicles}),
            "years": sorted({int(year) for _, _, year in b.vehicles if year != UNKNOWN_YEAR}),
            "labels": list(b.labels), "summary": b.summary}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", type=Path, default=RAW, help="the folder with NHTSA's files (default: data/raw)")
    parser.add_argument("--replace-published", action="store_true",
                        help="build from a download that differs from the published one, replacing the published key")
    args = parser.parse_args(argv)
    source = args.raw / FILE
    digest = sha256(source)
    if digest != PUBLISHED_SOURCES[FILE] and not args.replace_published:
        raise SystemExit(STOP.format(file=source))
    bulletins = read_bulletins(source)
    first: dict[str, object] = {}
    for b in sorted(bulletins, key=lambda b: (b.added, int(b.id))):
        first.setdefault(text_key(b.summary), b)
    pool: dict[str, dict[str, list]] = {split: {t: [] for t in TYPES} for split in PER_TYPE}
    for b in first.values():
        if b.type not in TYPES:
            raise SystemExit(f"NHTSA ID {b.id} has a type this key doesn't know: {b.type!r}")
        pool["test" if b.added >= TEST_FROM else "dev"][b.type].append(b)
    rng = random.Random(SEED)
    rows = []
    for split, per_type in PER_TYPE.items():
        for t in TYPES:
            candidates = sorted(pool[split][t], key=lambda b: int(b.id))
            rows += [entry(b, split) for b in sorted(rng.sample(candidates, per_type), key=lambda b: int(b.id))]
    KEY.mkdir(parents=True, exist_ok=True)
    with (KEY / "key.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    meta = {"source": FILE, "sha256": digest, "bytes": source.stat().st_size, "communications": len(bulletins),
            "distinct_summaries": len(first), "test_from": TEST_FROM, "seed": SEED, "per_type": PER_TYPE,
            "pool": {split: {t: len(pool[split][t]) for t in TYPES} for split in PER_TYPE},
            "types_in_file": dict(Counter(b.type for b in bulletins).most_common())}
    (KEY / "key.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=1))
    print(f"wrote {len(rows)} communications to {KEY / 'key.jsonl'}")


if __name__ == "__main__":
    main()
