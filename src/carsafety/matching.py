"""What to show once the vehicle and the likely components are known.

web/src/lib/match.ts does the same in the browser, and the tests check both follow the same rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .nhtsa import Complaint, Recall

Vector = dict[int, float]


@dataclass(frozen=True)
class ShownRecall:
    recall: Recall
    advisory: bool  # "Do Not Drive" or "Park Outside"
    matches: bool  # its component is one of the likely ones


def order_recalls(recalls: Iterable[Recall], labels: Iterable[str]) -> list[ShownRecall]:
    """Every recall for the vehicle, never just the matching ones.

    NHTSA's API lists one component per recall, so a recall that also covers the problem could look
    unrelated. Order: Do Not Drive and Park Outside advisories first, then recalls for the likely
    components, then the rest; newest first within each group (unknown dates last).
    """
    likely = set(labels)
    shown = [ShownRecall(r, r.do_not_drive or r.park_outside, r.label is not None and r.label in likely) for r in recalls]
    # Python's sort keeps the order of equal items, so sorting by the least important key first works.
    shown.sort(key=lambda s: s.recall.received or "", reverse=True)
    shown.sort(key=lambda s: not s.matches)
    shown.sort(key=lambda s: not s.advisory)
    return shown


def similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity of two vectors that already have length 1."""
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    return sum(value * large.get(i, 0.0) for i, value in small.items())


def match_complaints(complaints: Iterable[Complaint], labels: Iterable[str], description: str,
                     vectorize: Callable[[str], Vector], limit: int = 10) -> tuple[int, list[tuple[Complaint, float]]]:
    """Complaints filed under at least one likely component, the most similar wording first.

    Returns how many complaints were filed under the likely components, and the closest ones with their
    similarity (ties: newest first). `vectorize` turns text into the keyword model's tf-idf vector.
    """
    likely = set(labels)
    query = vectorize(description)
    candidates = [c for c in complaints if any(label in likely for label in c.labels)]
    scored = [(c, similarity(query, vectorize(c.summary))) for c in candidates]
    scored.sort(key=lambda item: item[0].filed or "", reverse=True)
    scored.sort(key=lambda item: item[1], reverse=True)
    return len(candidates), scored[:limit]
