"""Guards for the committed answer key for reading service bulletins (data/bulletins/, from scripts/build_bulletin_key.py)."""
import json
import re
from collections import Counter
from pathlib import Path

from carsafety.bulletins import FILE, PUBLISHED_SOURCES, TYPES, text_key
from carsafety.labels import LABELS

KEY = Path(__file__).resolve().parent.parent / "data" / "bulletins"
ROWS = [json.loads(line) for line in (KEY / "key.jsonl").read_text(encoding="utf-8").splitlines()]
META = json.loads((KEY / "key.json").read_text(encoding="utf-8"))
FIELDS = {"id", "split", "type", "added", "document", "issued", "makes", "models", "years", "labels", "summary"}


def test_the_key_is_built_from_the_published_download():
    assert (META["source"], META["sha256"]) == (FILE, PUBLISHED_SOURCES[FILE])


def test_each_type_has_the_same_number_in_each_split():
    counts = Counter((r["split"], r["type"]) for r in ROWS)
    assert counts == {(split, t): META["per_type"][split] for split in ("dev", "test") for t in TYPES}
    assert all(META["pool"][r["split"]][r["type"]] >= META["per_type"][r["split"]] for r in ROWS)


def test_dev_and_test_are_split_by_date_and_never_share_a_summary():
    assert all((r["added"] >= META["test_from"]) == (r["split"] == "test") for r in ROWS)
    assert len({r["id"] for r in ROWS}) == len(ROWS)
    assert len({text_key(r["summary"]) for r in ROWS}) == len(ROWS)


def test_every_row_has_nhtsas_coded_fields_in_a_clean_form():
    for r in ROWS:
        assert set(r) == FIELDS and r["summary"].strip() == r["summary"] and r["summary"], r["id"]
        assert all(label in LABELS for label in r["labels"]), r["id"]
        assert all(isinstance(y, int) and 1950 <= y <= 2030 for y in r["years"]), r["id"]
        assert r["makes"] and r["models"], r["id"]


def test_no_full_vin_in_the_summaries():
    # Manufacturers' documents, with no personal details; the only contact details in the key are a company's
    # support line and email (checked Oct 12, 2026).
    assert not any(re.search(r"\b[A-HJ-NPR-Z0-9]{17}\b", r["summary"]) for r in ROWS)
