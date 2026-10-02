"""Tests for the AI classifier. No Ollama or internet needed: the server is faked."""
import io
import json

import pytest

from carsafety import llm
from carsafety.labels import LABELS
from carsafety.llm import build_prompt, classify


def test_prompt_lists_every_category_and_ends_with_the_complaint():
    prompt = build_prompt("THE CAR STALLED ON THE HIGHWAY.")
    assert all(f"- {label}" in prompt for label in LABELS)
    assert "THE CAR STALLED ON THE HIGHWAY." in prompt
    assert "Similar past complaints" not in prompt


def test_prompt_with_examples_shows_their_labels_and_trims_long_text():
    examples = [{"labels": ["ENGINE", "POWER TRAIN"], "text": "A" * 1000}]
    prompt = build_prompt("THE CAR STALLED.", examples, example_chars=50)
    assert "Example 1 (categories: ENGINE, POWER TRAIN):" in prompt
    assert "A" * 50 in prompt and "A" * 51 not in prompt


def test_prompt_with_suggestions_lists_them_with_confidence():
    prompt = build_prompt("THE CAR STALLED.", suggestions=[("ENGINE", 0.81), ("POWER TRAIN", 0.4)])
    assert "ENGINE 0.81, POWER TRAIN 0.40" in prompt
    assert prompt.index("keyword model") < prompt.index("Complaint:")
    assert "keyword model" not in build_prompt("THE CAR STALLED.")


@pytest.fixture
def fake_server(monkeypatch):
    sent = []

    def install(answer: str):
        def fake_urlopen(request, timeout):
            sent.append(json.loads(request.data))
            return io.BytesIO(json.dumps({"message": {"content": answer}, "prompt_eval_count": 120, "eval_count": 9}).encode())
        monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
        return sent
    return install


def test_classify_keeps_only_real_categories_and_sends_safe_settings(fake_server):
    sent = fake_server('{"labels": ["ENGINE", "MADE UP CATEGORY"]}')
    labels, info = classify("THE CAR STALLED.", model="example-model", think=False)
    assert labels == {"ENGINE"}
    request = sent[0]
    assert request["options"]["temperature"] == 0
    assert request["format"]["properties"]["labels"]["items"]["enum"] == list(LABELS)
    assert request["think"] is False
    assert info["prompt_tokens"] == 120 and info["output_tokens"] == 9


def test_classify_treats_a_broken_answer_as_no_prediction(fake_server):
    sent = fake_server("not json at all")
    labels, info = classify("THE CAR STALLED.", model="example-model")
    assert labels == set()
    assert "think" not in sent[0]  # only sent when we know the model supports it
    assert info["raw"] == "not json at all"
