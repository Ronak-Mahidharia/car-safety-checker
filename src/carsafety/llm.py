"""Ask a local AI model (through Ollama) which components a complaint is about.

The model may only answer with NHTSA's 31 categories: each request includes a JSON schema
that lists them, and anything else is dropped. Temperature 0 makes answers repeatable.
Two modes:
  - on its own (zero-shot): the category list and the complaint
  - with examples (RAG): also the most similar past complaints and the categories NHTSA
    recorded for them
"""
from __future__ import annotations

import json
import time
import urllib.request

from .embeddings import OLLAMA_URL
from .labels import LABELS

SYSTEM = ("You classify U.S. vehicle safety complaints by the vehicle component involved, using "
          "NHTSA's component categories. Choose only the categories the complaint is actually about.")

SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {"type": "array", "items": {"type": "string", "enum": list(LABELS)}, "minItems": 1, "maxItems": 3},
    },
    "required": ["labels"],
}


# Prompt wordings, compared on dev complaints only (never on the test set).
QUESTIONS = {
    "v1": 'Which categories is this complaint about? Usually one, at most three. Answer in JSON: {"labels": [...]}',
    "v2": ("Which categories is this complaint about? Most complaints are about one category. Add a second or "
           "third only if the complaint clearly describes a problem with that component too. "
           'Answer in JSON: {"labels": [...]}'),
}
PROMPT_VERSION = "v1"


def build_prompt(text: str, examples: list[dict] | None = None, example_chars: int = 600,
                 version: str | None = None, suggestions: list[tuple[str, float]] | None = None) -> str:
    """The question for the model: categories, then any examples and suggestions, then the complaint."""
    parts = ["Categories:\n" + "\n".join(f"- {label}" for label in LABELS)]
    if examples:
        shown = [f"Example {i} (categories: {', '.join(ex['labels'])}):\n{ex['text'][:example_chars]}"
                 for i, ex in enumerate(examples, 1)]
        parts.append("Similar past complaints, with the categories NHTSA recorded for them:\n\n" + "\n\n".join(shown))
    if suggestions:
        listed = ", ".join(f"{label} {probability:.2f}" for label, probability in suggestions)
        parts.append("A keyword model trained on past complaints suggests these categories, with its confidence "
                     f"from 0 to 1: {listed}. It is often right, but not always.")
    parts.append(f"Complaint:\n{text}")
    parts.append(QUESTIONS[version or PROMPT_VERSION])
    return "\n\n".join(parts)


def _post(url: str, path: str, payload: dict, timeout: int = 600) -> dict:
    request = urllib.request.Request(f"{url}{path}", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def supports_thinking(model: str, url: str = OLLAMA_URL) -> bool:
    """Some models (like Qwen3) "think" before answering by default; we turn that off for speed."""
    return "thinking" in _post(url, "/api/show", {"model": model}, timeout=60).get("capabilities", [])


def classify(text: str, model: str, examples: list[dict] | None = None, url: str = OLLAMA_URL,
             think: bool | None = None, version: str | None = None,
             suggestions: list[tuple[str, float]] | None = None) -> tuple[set[str], dict]:
    """Return the predicted categories and details (time, tokens, raw answer)."""
    payload = {
        "model": model,
        "stream": False,
        "format": SCHEMA,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": build_prompt(text, examples, version=version, suggestions=suggestions)}],
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    if think is not None:
        payload["think"] = think
    started = time.time()
    response = _post(url, "/api/chat", payload)
    raw = response.get("message", {}).get("content", "")
    try:
        answer = json.loads(raw)
        labels = {label for label in answer.get("labels", []) if label in LABELS}
    except (json.JSONDecodeError, AttributeError):
        labels = set()
    return labels, {"seconds": round(time.time() - started, 3), "prompt_tokens": response.get("prompt_eval_count", 0),
                    "output_tokens": response.get("eval_count", 0), "raw": raw}
