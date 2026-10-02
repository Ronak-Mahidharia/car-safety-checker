"""Embeddings: numbers that capture what a complaint means, so similar ones can be found.

Texts are embedded with a free model running locally in Ollama (nothing leaves the
computer). nomic-embed-text expects a task prefix: "search_document: " for stored
complaints and "search_query: " for a new description.
"""
from __future__ import annotations

import json
import urllib.request

import numpy as np

OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
PREFIX = {"document": "search_document: ", "query": "search_query: "}


def embed(texts: list[str], kind: str, model: str = EMBED_MODEL, batch: int = 64, url: str = OLLAMA_URL,
          progress=None) -> np.ndarray:
    """Embed texts as "document" (stored) or "query" (searched for). Returns unit-length rows."""
    prefix = PREFIX[kind]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch):
        payload = {"model": model, "input": [prefix + t for t in texts[start:start + batch]], "truncate": True}
        request = urllib.request.Request(f"{url}/api/embed", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=600) as response:
            vectors.extend(json.load(response)["embeddings"])
        if progress:
            progress(len(vectors))
    array = np.asarray(vectors, dtype=np.float32)
    return array / np.linalg.norm(array, axis=1, keepdims=True)  # unit length: a dot product is then cosine similarity


def top_k(queries: np.ndarray, index: np.ndarray, k: int, chunk: int = 256) -> tuple[np.ndarray, np.ndarray]:
    """For each query, the positions and similarities of the k most similar stored rows, best first."""
    positions = np.empty((len(queries), k), dtype=np.int64)
    scores = np.empty((len(queries), k), dtype=np.float32)
    for start in range(0, len(queries), chunk):  # in chunks, so memory stays small
        sims = queries[start:start + chunk].astype(np.float32) @ index.T.astype(np.float32)
        best = np.argpartition(-sims, k - 1, axis=1)[:, :k]
        best_sims = np.take_along_axis(sims, best, axis=1)
        order = np.argsort(-best_sims, axis=1)
        positions[start:start + chunk] = np.take_along_axis(best, order, axis=1)
        scores[start:start + chunk] = np.take_along_axis(best_sims, order, axis=1)
    return positions, scores


def vote(neighbor_labels: list[list[list[str]]], neighbor_scores: np.ndarray, threshold: float) -> list[set[str]]:
    """Similarity-weighted vote over each query's neighbors' labels.

    A label is chosen when its share of the total similarity is at least the threshold.
    If none qualifies, the label with the largest share is chosen (every complaint has one).
    """
    predictions = []
    for labels_per_neighbor, scores in zip(neighbor_labels, neighbor_scores):
        weight: dict[str, float] = {}
        for labels, score in zip(labels_per_neighbor, scores):
            for label in labels:
                weight[label] = weight.get(label, 0.0) + float(score)
        total = float(np.sum(scores)) or 1.0
        chosen = {label for label, w in weight.items() if w / total >= threshold}
        predictions.append(chosen or {max(weight, key=weight.get)})
    return predictions
