"""Combine the keyword model with similar-complaint voting.

Both give every label a score from 0 to 1: the keyword model's probability, and the label's
share of the nearest complaints' similarity. `blend` averages them with no AI model involved;
`top_suggestions` picks the keyword model's best guesses to show an AI model (the hybrid).
"""
from __future__ import annotations

import numpy as np


def vote_shares(neighbor_labels: list[list[list[str]]], neighbor_scores: np.ndarray, classes: list[str]) -> np.ndarray:
    """Each label's share of the neighbors' total similarity, as a (complaints x labels) array."""
    position = {label: i for i, label in enumerate(classes)}
    shares = np.zeros((len(neighbor_labels), len(classes)), dtype=np.float32)
    for row, (labels_per_neighbor, scores) in enumerate(zip(neighbor_labels, neighbor_scores)):
        total = float(np.sum(scores)) or 1.0
        for labels, score in zip(labels_per_neighbor, scores):
            for label in labels:
                if label in position:
                    shares[row, position[label]] += float(score) / total
    return shares


def blend(keyword_probs: np.ndarray, shares: np.ndarray, classes: list[str], weight: float, threshold: float) -> list[set[str]]:
    """Weighted average: `weight` for the keyword model, the rest for the vote. Always at least one label."""
    combined = weight * keyword_probs + (1 - weight) * shares
    predictions = []
    for row in combined:
        chosen = {classes[i] for i in np.flatnonzero(row >= threshold)}
        predictions.append(chosen or {classes[int(row.argmax())]})
    return predictions


def top_suggestions(keyword_probs: np.ndarray, classes: list[str], n: int = 3) -> list[list[tuple[str, float]]]:
    """The keyword model's n most likely labels for each complaint, with their probabilities."""
    order = np.argsort(-keyword_probs, axis=1)[:, :n]
    return [[(classes[i], round(float(probs[i]), 2)) for i in idx] for idx, probs in zip(order, keyword_probs)]
