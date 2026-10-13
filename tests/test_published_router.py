"""The fine-tuned model and the router: the published scores must come back from the committed answers alone (the
test sample's labels and each approach's components in docs/results/predictions/), and the README must match."""
import json
from pathlib import Path

from carsafety.metrics import score

ROOT = Path(__file__).resolve().parent.parent
RESULTS = json.loads((ROOT / "docs" / "results" / "router.json").read_text())
SLUGS = {"keyword": "baseline-keyword-model-tf-idf-logistic-regression",  # the published baseline's answers
         "tuned": "fine-tuned-qwen3-1-7b-lora-and-a-classification-head",
         "router": "router-the-keyword-model-when-sure-else-the-fine-tuned-model"}


def rows(name):
    path = ROOT / "docs" / "results" / "predictions" / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def truth():
    sample = ROOT / "data" / "sample" / "test_sample.jsonl"
    return {r["id"]: set(r["labels"]) for r in map(json.loads, sample.read_text(encoding="utf-8").splitlines())}


def test_every_published_score_comes_back_from_the_committed_answers():
    labels = truth()
    for name, slug in SLUGS.items():
        answers = rows(slug)
        assert [a["id"] for a in answers] == list(labels)  # the same 1,000 complaints, in the sample's order
        s = score([labels[a["id"]] for a in answers], [set(a["labels"]) for a in answers])
        for key in ("micro_f1", "macro_f1", "exact_match"):
            assert round(s[key], 4) == RESULTS["results"][name][key], (name, key)


def test_the_router_answers_with_one_model_or_the_other():
    keyword, tuned, routed = (rows(SLUGS[n]) for n in ("keyword", "tuned", "router"))
    assert sum(r["sent"] for r in routed) == RESULTS["sent"]
    for k, t, r in zip(keyword, tuned, routed):
        assert r["labels"] == (t["labels"] if r["sent"] else k["labels"]), r["id"]


def test_the_test_run_used_the_dev_choice():
    dev = RESULTS["dev"]
    assert RESULTS["choice"] == {k: dev[k] for k in ("checkpoint", "threshold", "confidence")}
    best = max(dev["checkpoints"], key=lambda c: (dev["checkpoints"][c]["micro_f1_by_threshold"][str(dev["checkpoints"][c]["threshold"])],
                                                  -int(c.split("-")[1])))
    assert best == dev["checkpoint"]


def test_the_readme_numbers_match():
    readme = (ROOT / "README.md").read_text(encoding="utf-8").replace("**", "")
    tables = [line.rstrip(" |").split(" | ") for line in readme.splitlines() if line.startswith("| ")]
    for name, starts in (("tuned", ("| Fine-tuned", "Fine-tuned")), ("router", ("| Router", "Router"))):
        r = RESULTS["results"][name]
        scores, recalls = [cells for cells in tables if cells[0].startswith(starts[0])][:2]
        assert scores[1:4] == [f"{r['micro_f1']:.3f}", f"{r['macro_f1']:.3f}", f"{r['exact_match']:.1%}"], scores
        assert recalls[1:3] == [f"{r['recalls_found']:.1%}", f"{r['recalls_shown_right']:.1%}"], recalls
    assert f"{RESULTS['sent']} of the 1,000" in readme
