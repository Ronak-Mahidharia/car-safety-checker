"""Recall order and complaint matching. The cases and answers mirror web/src/lib/match.test.ts."""
import re

import pytest

from carsafety.matching import match_complaints, order_recalls, similarity
from carsafety.nhtsa import Complaint, Recall


def recall(campaign, received, label, do_not_drive=False, park_outside=False):
    return Recall(campaign=campaign, received=received, component=label or "UNKNOWN OR OTHER", label=label, summary="",
                  consequence="", remedy="", do_not_drive=do_not_drive, park_outside=park_outside, over_the_air=False,
                  source="", listed_as="TEST")


RECALLS = [
    recall("A-old-engine", "2019-05-21", "ENGINE"),
    recall("B-new-tires", "2024-01-10", "TIRES"),
    recall("C-park-outside", "2018-02-01", "ELECTRICAL SYSTEM", park_outside=True),
    recall("D-new-engine", "2023-03-09", "ENGINE"),
    recall("E-no-date", None, "TIRES"),
    recall("F-do-not-drive", "2017-07-07", "AIR BAGS", do_not_drive=True),
]


def test_every_recall_is_listed_advisories_then_matches_then_the_rest():
    shown = order_recalls(RECALLS, ["ENGINE"])
    assert [s.recall.campaign for s in shown] == ["C-park-outside", "F-do-not-drive", "D-new-engine", "A-old-engine", "B-new-tires", "E-no-date"]
    assert [s.recall.campaign for s in shown if s.matches] == ["D-new-engine", "A-old-engine"]
    assert [s.recall.campaign for s in shown if s.advisory] == ["C-park-outside", "F-do-not-drive"]


def test_without_a_description_advisories_come_first_then_newest_first():
    order = [s.recall.campaign for s in order_recalls(RECALLS, [])]
    assert order == ["C-park-outside", "F-do-not-drive", "B-new-tires", "D-new-engine", "A-old-engine", "E-no-date"]


def test_similarity_of_unit_vectors():
    a = {1: 0.6, 2: 0.8}
    assert similarity(a, {2: 1.0}) == pytest.approx(0.8)
    assert similarity(a, a) == pytest.approx(1.0)
    assert similarity(a, {}) == 0


WORDS: dict[str, int] = {}


def vectorize(text):
    """A stand-in for the model's tf-idf vectors: one column per word, scaled to length 1."""
    counts: dict[int, int] = {}
    for word in re.findall(r"[a-z]+", text.lower()):
        i = WORDS.setdefault(word, len(WORDS))
        counts[i] = counts.get(i, 0) + 1
    length = sum(n * n for n in counts.values()) ** 0.5
    return {i: n / length for i, n in counts.items()}


def complaint(odi, labels, summary, filed):
    return Complaint(odi_number=odi, filed=filed, components=tuple(labels), labels=tuple(labels), summary=summary,
                     crash=False, fire=False, injuries=0, deaths=0, source="", listed_as="TEST")


COMPLAINTS = [
    complaint("1", ["ENGINE"], "engine hesitates and stalls", "2025-01-01"),
    complaint("2", ["TIRES"], "engine hesitates and stalls", "2025-01-02"),
    complaint("3", ["ENGINE", "ELECTRICAL SYSTEM"], "check engine light", "2025-01-03"),
    complaint("4", ["ENGINE"], "engine hesitates", "2025-01-04"),
    complaint("5", ["ENGINE"], "radio stopped working", "2026-01-01"),
]


def test_complaints_under_a_likely_component_closest_wording_first():
    filed_under, shown = match_complaints(COMPLAINTS, ["ENGINE"], "the engine hesitates", vectorize)
    assert filed_under == 4
    assert [c.odi_number for c, _ in shown] == ["4", "1", "3", "5"]


def test_ties_go_newest_first_and_the_limit_holds():
    _, shown = match_complaints(COMPLAINTS, ["ENGINE"], "nothing in common", vectorize, limit=2)
    assert [c.odi_number for c, _ in shown] == ["5", "4"]


def test_nothing_when_no_complaint_is_filed_under_the_likely_components():
    assert match_complaints(COMPLAINTS, ["SEATS"], "seat broke", vectorize) == (0, [])
