"""Route each complaint to one of two models: the keyword model, which runs instantly anywhere, when it's sure of its
top component, and the fine-tuned model (scripts/finetune.py), which needs a strong computer, when it isn't.

- Each model turns its probabilities into components the same way: every component at or above its threshold, or its
  single most likely one if none is (every complaint has at least one).
- The keyword model is "sure" when its most likely component's probability is at least the router's confidence.
- Every setting is chosen on dev complaints: the highest micro F1 wins, and on a tie the lower threshold, or for the
  router the setting that sends fewer complaints to the bigger model.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from carsafety.metrics import score

THRESHOLDS = tuple(round(0.15 + 0.05 * i, 2) for i in range(10))  # 0.15 to 0.60, as for the keyword model
CONFIDENCES = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


def labels_from(probs: np.ndarray, classes: Sequence[str], threshold: float) -> list[set[str]]:
    """Components at or above the threshold; if none, the single most likely one."""
    out = []
    for row in np.asarray(probs):
        chosen = {classes[i] for i in np.flatnonzero(row >= threshold)}
        out.append(chosen or {classes[int(row.argmax())]})
    return out


def best_threshold(truth: list, probs: np.ndarray, classes: Sequence[str],
                   thresholds: Sequence[float] = THRESHOLDS) -> tuple[float, dict]:
    """The threshold with the highest micro F1 (the lower one on a tie), and the F1 at each."""
    f1 = {t: score(truth, labels_from(probs, classes, t))["micro_f1"] for t in thresholds}
    best = max(thresholds, key=lambda t: (f1[t], -t))
    return best, f1


def route(keyword_probs: np.ndarray, keyword_labels: list[set[str]], tuned_labels: list[set[str]],
          confidence: float) -> tuple[list[set[str]], np.ndarray]:
    """The keyword model's components where it's sure, the fine-tuned model's elsewhere, and which were sent on."""
    sent = np.asarray(keyword_probs).max(axis=1) < confidence
    return [t if s else k for k, t, s in zip(keyword_labels, tuned_labels, sent)], sent


def best_confidence(truth: list, keyword_probs: np.ndarray, keyword_labels: list[set[str]],
                    tuned_labels: list[set[str]], confidences: Sequence[float] = CONFIDENCES) -> tuple[float, dict]:
    """The confidence with the highest micro F1 (on a tie, the one sending fewer complaints on), with each one's F1
    and share sent."""
    tried = {}
    for c in confidences:
        labels, sent = route(keyword_probs, keyword_labels, tuned_labels, c)
        tried[c] = {"micro_f1": score(truth, labels)["micro_f1"], "sent": float(sent.mean())}
    best = max(confidences, key=lambda c: (tried[c]["micro_f1"], -tried[c]["sent"]))
    return best, tried
