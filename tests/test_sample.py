"""Guards for the committed test sample, the fixed set the AI is scored on."""
import json
from pathlib import Path

from carsafety.labels import normalize
from carsafety.privacy import scrub

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample" / "test_sample.jsonl"
COLUMNS = {"id", "received", "make", "model", "model_year", "crash", "fire", "injured", "deaths", "text", "labels"}


def records():
    with SAMPLE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_sample_has_1000_unique_test_complaints():
    rows = records()
    assert len(rows) == 1000
    assert len({r["id"] for r in rows}) == 1000
    assert all(r["received"] >= "20250101" for r in rows)  # all from the test period


def test_sample_has_only_the_expected_fields():
    assert all(set(r) == COLUMNS for r in records())


def test_every_complaint_has_clean_known_labels():
    for r in records():
        assert r["labels"], r["id"]
        assert all(normalize(label) == label for label in r["labels"]), r["id"]


def test_no_emails_phone_numbers_or_vins_left():
    for r in records():
        assert scrub(r["text"]) == r["text"], r["id"]
