"""The small keyword model that runs in the browser, re-implemented in plain Python.

It reads only the exported files (model.json and weights.bin) and repeats scikit-learn's
math step by step, so tests can prove two things: the export is complete, and the
browser version (which follows the same steps) gives the same answers.

The steps, matching TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
strip_accents="unicode") and one logistic regression per label:
  1. lowercase, then remove accents
  2. split into words of 2 or more letters or digits, plus every pair of neighboring words
  3. for each known term: (1 + log(count)) * idf, then scale the vector to length 1
  4. for each label: probability = sigmoid(weights . vector + bias)
  5. choose labels at or above the threshold, or else the single most likely one
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

import numpy as np

TOKEN = re.compile(r"(?u)\b\w\w+\b")  # scikit-learn's default token pattern


def preprocess(text: str) -> str:
    """Lowercase, then strip accents the way scikit-learn's strip_accents="unicode" does."""
    text = text.lower()
    try:
        text.encode("ascii")
        return text
    except UnicodeEncodeError:
        return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def terms(text: str) -> list[str]:
    """Single words and neighboring-word pairs, in scikit-learn's order."""
    tokens = TOKEN.findall(preprocess(text))
    return tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]


class BrowserModel:
    def __init__(self, labels: list[str], vocabulary: list[str], idf: np.ndarray, weights: np.ndarray,
                 bias: np.ndarray, threshold: float):
        self.labels, self.idf, self.weights, self.bias, self.threshold = labels, idf, weights, bias, threshold
        self.index = {term: i for i, term in enumerate(vocabulary)}

    @classmethod
    def load(cls, folder: str | Path) -> "BrowserModel":
        folder = Path(folder)
        meta = json.loads((folder / "model.json").read_text(encoding="utf-8"))
        quantized = np.frombuffer((folder / "weights.bin").read_bytes(), dtype=np.int8)
        weights = quantized.reshape(len(meta["labels"]), len(meta["vocabulary"])).astype(np.float64)
        weights *= np.asarray(meta["scale"], dtype=np.float64)[:, None]
        return cls(meta["labels"], meta["vocabulary"], np.asarray(meta["idf"], dtype=np.float64), weights,
                   np.asarray(meta["bias"], dtype=np.float64), meta["threshold"])

    def probabilities(self, text: str) -> np.ndarray:
        counts: dict[int, int] = {}
        for term in terms(text):
            i = self.index.get(term)
            if i is not None:
                counts[i] = counts.get(i, 0) + 1
        if not counts:
            return 1 / (1 + np.exp(-self.bias))
        columns = np.fromiter(counts, dtype=np.int64)
        values = np.array([(1 + math.log(counts[i])) * self.idf[i] for i in columns])
        values /= np.linalg.norm(values)
        return 1 / (1 + np.exp(-(self.weights[:, columns] @ values + self.bias)))

    def predict(self, text: str) -> set[str]:
        p = self.probabilities(text)
        chosen = {self.labels[i] for i in np.flatnonzero(p >= self.threshold)}
        return chosen or {self.labels[int(p.argmax())]}

    def top(self, text: str, n: int = 3) -> list[tuple[str, float]]:
        """The n most likely labels with their probabilities, most likely first (ties: label order)."""
        p = self.probabilities(text)
        return [(self.labels[i], float(p[i])) for i in np.argsort(-p, kind="stable")[:n]]

    def vector(self, text: str) -> dict[int, float]:
        """Steps 1 to 3: the text's tf-idf vector, scaled to length 1, as column -> value. Empty if no term is known."""
        counts: dict[int, int] = {}
        for term in terms(text):
            i = self.index.get(term)
            if i is not None:
                counts[i] = counts.get(i, 0) + 1
        values = {i: (1 + math.log(n)) * float(self.idf[i]) for i, n in counts.items()}
        length = math.sqrt(sum(v * v for v in values.values()))
        return {i: v / length for i, v in values.items()} if values else {}
