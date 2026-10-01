"""Scoring for multi-label predictions: which components a complaint is about.

A complaint can concern several components, so each prediction is a set of labels.
We report:
  - micro precision/recall/F1: pooled over every label decision, so common labels weigh more
  - macro F1: the plain average of per-label F1, so rare labels count as much as common ones
  - exact match: the share of complaints where the predicted set equals the true set
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class LabelScore:
    label: str
    precision: float
    recall: float
    f1: float
    support: int  # how many complaints truly have this label


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def score(truth: Sequence[Iterable[str]], predicted: Sequence[Iterable[str]], labels: Iterable[str] | None = None) -> dict:
    """Compare true and predicted label sets, one pair per complaint."""
    if len(truth) != len(predicted):
        raise ValueError(f"truth has {len(truth)} items but predicted has {len(predicted)}")
    tp, fp, fn = Counter(), Counter(), Counter()
    exact = 0
    for t, p in zip(truth, predicted):
        t, p = set(t), set(p)
        exact += t == p
        for label in t & p:
            tp[label] += 1
        for label in p - t:
            fp[label] += 1
        for label in t - p:
            fn[label] += 1
    all_labels = sorted(set(labels) if labels is not None else set(tp) | set(fp) | set(fn))
    per_label = [LabelScore(label, *_prf(tp[label], fp[label], fn[label]), support=tp[label] + fn[label]) for label in all_labels]
    micro_p, micro_r, micro_f1 = _prf(sum(tp.values()), sum(fp.values()), sum(fn.values()))
    scored = [s for s in per_label if s.support > 0]
    macro_f1 = sum(s.f1 for s in scored) / len(scored) if scored else 0.0
    return {
        "n": len(truth),
        "micro_precision": micro_p,
        "micro_recall": micro_r,
        "micro_f1": micro_f1,
        "macro_f1": macro_f1,
        "exact_match": exact / len(truth) if truth else 0.0,
        "per_label": per_label,
    }
