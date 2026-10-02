"""Tests for embedding search and voting. No Ollama or internet needed: the server is faked."""
import io
import json

import numpy as np

from carsafety import embeddings
from carsafety.embeddings import embed, top_k, vote
from carsafety.labels import LABELS, MERGE, normalize


def test_top_k_returns_the_most_similar_rows_best_first():
    index = np.eye(4, dtype=np.float32)  # four stored rows pointing in different directions
    queries = np.array([[0.9, 0.1, 0, 0], [0, 0, 0.2, 0.98]], dtype=np.float32)
    positions, scores = top_k(queries, index, k=2)
    assert positions[0].tolist() == [0, 1]
    assert positions[1].tolist() == [3, 2]
    assert scores[0][0] > scores[0][1]


def test_vote_weighs_closer_neighbors_more_and_always_picks_one():
    labels = [[["ENGINE"], ["ENGINE", "POWER TRAIN"], ["STEERING"]]]
    scores = np.array([[0.9, 0.8, 0.3]])  # shares: ENGINE 0.85, POWER TRAIN 0.40, STEERING 0.15
    assert vote(labels, scores, threshold=0.5) == [{"ENGINE"}]
    assert vote(labels, scores, threshold=0.3) == [{"ENGINE", "POWER TRAIN"}]
    assert vote(labels, scores, threshold=0.99) == [{"ENGINE"}]  # nothing qualifies, so the best one


def test_embed_adds_the_task_prefix_and_normalizes(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        body = json.loads(request.data)
        sent.append(body)
        return io.BytesIO(json.dumps({"embeddings": [[3.0, 4.0]] * len(body["input"])}).encode())

    monkeypatch.setattr(embeddings.urllib.request, "urlopen", fake_urlopen)
    vectors = embed(["the brakes are soft"], kind="query")
    assert sent[0]["input"] == ["search_query: the brakes are soft"]
    assert np.allclose(vectors, [[0.6, 0.8]])


def test_label_list_is_the_31_clean_categories():
    assert len(LABELS) == 31 and len(set(LABELS)) == 31
    assert all(normalize(label) == label for label in LABELS)
    assert set(MERGE.values()) <= set(LABELS)
