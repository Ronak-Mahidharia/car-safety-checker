"""Choose the fine-tuned model's settings and the router's on dev complaints, then score them once on the test sample.

    python scripts/run_router.py --split dev     # after scripts/finetune.py predict --split dev, for each checkpoint
    python scripts/run_router.py --split test    # after scripts/finetune.py predict --split test --checkpoint <chosen>

dev: the 5,000 dev complaints in the index (received in 2024), the ones the other settings were chosen on. For each
checkpoint, its threshold; the checkpoint with the highest micro F1 (on a tie, the earlier one); then the router's
confidence (src/carsafety/router.py). Writes data/processed/finetune/choice.json.

test: the fixed 1,000-complaint test sample (2025 onward), run once with the dev choice: the keyword model, the
fine-tuned model, and the router, with the share of right recalls each finds. Writes docs/results/router.md and
router.json, and the fine-tuned model's and the router's answers to docs/results/predictions/ (the keyword model's are
the published baseline's, which it checks).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np

from carsafety.labels import LABELS
from carsafety.metrics import score
from carsafety.recalls import agreement, find, read_recalls
from carsafety.router import CONFIDENCES, THRESHOLDS, best_confidence, best_threshold, labels_from, route

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
TUNED = PROCESSED / "finetune"
RESULTS = ROOT / "docs" / "results"
BASELINE = RESULTS / "predictions" / "baseline-keyword-model-tf-idf-logistic-regression.jsonl"
NAMES = {"keyword": "Keyword model (TF-IDF + logistic regression)",
         "tuned": "Fine-tuned Qwen3 1.7B (LoRA and a classification head)",
         "router": "Router: the keyword model when sure, else the fine-tuned model"}


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def tuned_probs(path: Path, rows: list[dict]) -> np.ndarray:
    predicted = load(path)
    if [p["id"] for p in predicted] != [r["id"] for r in rows]:
        raise SystemExit(f"{path.name} isn't for these complaints, in this order.")
    return np.array([p["probs"] for p in predicted])


def keyword(rows: list[dict]) -> tuple[np.ndarray, list[set[str]], float]:
    """The saved keyword model's probabilities, its components at its own threshold, and its milliseconds a
    complaint."""
    saved = joblib.load(PROCESSED / "keyword_model.joblib")
    started = time.perf_counter()
    probs = saved["model"].predict_proba(saved["vectorizer"].transform(r["text"] for r in rows))
    ms = (time.perf_counter() - started) * 1000 / len(rows)
    return probs, labels_from(probs, list(saved["classes"]), saved["threshold"]), ms


def choose(rows: list[dict]) -> dict:
    truth = [r["labels"] for r in rows]
    kw_probs, kw_labels, _ = keyword(rows)
    checkpoints = {}
    for path in sorted(TUNED.glob("dev-step-*.jsonl")):
        threshold, f1 = best_threshold(truth, tuned_probs(path, rows), LABELS)
        checkpoints[path.stem.removeprefix("dev-")] = {"threshold": threshold, "micro_f1_by_threshold": f1}
    if not checkpoints:
        raise SystemExit("No dev predictions: run scripts/finetune.py predict --split dev --checkpoint ... first.")
    best = max(checkpoints, key=lambda c: (checkpoints[c]["micro_f1_by_threshold"][checkpoints[c]["threshold"]],
                                           -int(c.split("-")[1])))
    threshold = checkpoints[best]["threshold"]
    tuned_labels = labels_from(tuned_probs(TUNED / f"dev-{best}.jsonl", rows), LABELS, threshold)
    confidence, tried = best_confidence(truth, kw_probs, kw_labels, tuned_labels)
    return {"dev_complaints": len(rows), "checkpoint": best, "threshold": threshold, "confidence": confidence,
            "checkpoints": checkpoints, "confidences": {str(c): tried[c] for c in CONFIDENCES},
            "keyword_dev_micro_f1": score(truth, kw_labels)["micro_f1"], "thresholds": list(THRESHOLDS)}


def scored(truth, labels, campaigns) -> dict:
    s = score(truth, labels)
    found = agreement(truth, labels, campaigns)
    return {k: round(s[k], 4) for k in ("micro_f1", "macro_f1", "exact_match")} | {
        "recalls_found": round(found["recall"], 4), "recalls_shown_right": round(found["precision"], 4)}


def test(rows: list[dict], choice: dict) -> dict:
    truth = [r["labels"] for r in rows]
    kw_probs, kw_labels, kw_ms = keyword(rows)
    path = TUNED / f"test-{choice['checkpoint']}.jsonl"
    if not path.exists():
        raise SystemExit(f"No {path.name}: run scripts/finetune.py predict --split test "
                         f"--checkpoint {choice['checkpoint']}.safetensors first.")
    tuned_labels = labels_from(tuned_probs(path, rows), LABELS, choice["threshold"])
    routed, sent = route(kw_probs, kw_labels, tuned_labels, choice["confidence"])
    timing = json.loads(path.with_suffix(".json").read_text()) if path.with_suffix(".json").exists() else {}
    recalls = read_recalls(ROOT / "data" / "raw" / "FLAT_RCL_POST_2010.txt")
    campaigns = [find(recalls, r["make"], r["model"], r["model_year"]) for r in rows]
    answers = {"keyword": kw_labels, "tuned": tuned_labels, "router": routed}
    out = {"complaints": len(rows), "choice": {k: choice[k] for k in ("checkpoint", "threshold", "confidence")},
           "sent": int(sent.sum()), "keyword_ms": round(kw_ms, 3), "tuned_ms": timing.get("ms_each"),
           "results": {name: scored(truth, labels, campaigns) for name, labels in answers.items()}}
    published = load(BASELINE)  # the keyword model's answers are already published: check them, don't copy them
    if [(p["id"], p["labels"]) for p in published] != [(r["id"], sorted(k)) for r, k in zip(rows, kw_labels)]:
        raise SystemExit(f"The keyword model's answers differ from the published ones in {BASELINE.name}.")
    for name, labels in answers.items():
        if name == "keyword":
            continue
        slug = "".join(c if c.isalnum() else "-" for c in NAMES[name].lower()).strip("-")
        slug = "-".join(part for part in slug.split("-") if part)  # as run_ai_eval.py names its files
        with (RESULTS / "predictions" / f"{slug}.jsonl").open("w", encoding="utf-8") as f:
            for row, labels_, was_sent in zip(rows, labels, sent):
                entry = {"id": row["id"], "labels": sorted(labels_)}
                if name == "router":
                    entry["sent"] = bool(was_sent)
                f.write(json.dumps(entry) + "\n")
    return out


def training() -> dict:
    """What the training run recorded (data/processed/finetune/, written by scripts/finetune.py train)."""
    config = json.loads((TUNED / "config.json").read_text())
    log = json.loads((TUNED / "train_log.json").read_text())
    return {"base": config["base"], "complaints": config["train_complaints"], "steps": config["steps"],
            "trainable_parameters": config["trainable_parameters"], "hours": round(config["minutes"] / 60, 2),
            "peak_gb": max(entry["peak_gb"] for entry in log), "last_loss": log[-1]["loss"]}


def render(choice: dict, out: dict) -> str:
    """docs/results/router.md, from the dev choice and the test results."""
    t, r = out["training"], out["results"]
    lines = ["# Results: a fine-tuned model, and a router", "", "Generated by `scripts/run_router.py`. Don't edit by hand.",
             "", f"`{t['base']}` (Apache-2.0) with LoRA adapters and a classification head over the 31 components "
             f"(`scripts/finetune.py`), trained on {t['complaints']:,} training complaints (received before 2024) for "
             f"{t['steps']:,} steps on this Mac: {t['trainable_parameters']:,} trainable parameters, {t['hours']} hours, "
             f"peak memory {t['peak_gb']} GB. The router (`src/carsafety/router.py`) answers with the keyword model when "
             "its top component's probability reaches the router's confidence, and sends the rest to the fine-tuned model.",
             "", f"## Chosen on the {choice['dev_complaints']:,} dev complaints (received in 2024)", "",
             "| Checkpoint | Best threshold | Micro F1 |", "|---|---|---|"]
    for name, c in choice["checkpoints"].items():
        f1 = c["micro_f1_by_threshold"]  # read back from JSON, its keys are strings
        lines.append(f"| {name} | {c['threshold']} | {f1.get(str(c['threshold']), f1.get(c['threshold'])):.3f} |")
    lines += ["", f"Chosen: **{choice['checkpoint']}** at threshold {choice['threshold']}. The keyword model on these "
                  f"complaints: micro F1 {choice['keyword_dev_micro_f1']:.3f}.", "",
              "| Router confidence | Micro F1 | Sent to the fine-tuned model |", "|---|---|---|"]
    for c, row in choice["confidences"].items():
        lines.append(f"| {c} | {row['micro_f1']:.3f} | {row['sent']:.1%} |")
    lines += ["", f"Chosen: **{choice['confidence']}**.", "",
              f"## The {out['complaints']:,} test complaints, run once", "",
              "| Approach | Micro F1 | Macro F1 | Exact match | Right recalls found | Recalls shown that are right |",
              "|---|---|---|---|---|---|"]
    for name, row in r.items():
        lines.append(f"| {NAMES[name]} | {row['micro_f1']:.3f} | {row['macro_f1']:.3f} | {row['exact_match']:.1%} | "
                     f"{row['recalls_found']:.1%} | {row['recalls_shown_right']:.1%} |")
    lines += ["", f"The router sent {out['sent']} of the {out['complaints']:,} complaints to the fine-tuned model. Time "
                  f"per complaint: keyword model {out['keyword_ms']} ms, fine-tuned model {out['tuned_ms']} ms (batches "
                  "of 16 on this Mac's GPU).", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    args = parser.parse_args(argv)
    if args.split == "dev":
        rows = load(PROCESSED / "index" / "dev_rows.jsonl")
        choice = choose(rows)
        (TUNED / "choice.json").write_text(json.dumps(choice, indent=1) + "\n")
        print(f"chose {choice['checkpoint']} at threshold {choice['threshold']}, confidence {choice['confidence']}; "
              f"keyword model on these dev complaints: micro F1 {choice['keyword_dev_micro_f1']:.3f}")
        for name, c in choice["checkpoints"].items():
            print(f"  {name}: threshold {c['threshold']}, micro F1 {c['micro_f1_by_threshold'][c['threshold']]:.3f}")
        for c, t in choice["confidences"].items():
            print(f"  router at {c}: micro F1 {t['micro_f1']:.3f}, {t['sent']:.1%} sent on")
        return 0
    choice = json.loads((TUNED / "choice.json").read_text())
    rows = load(ROOT / "data" / "sample" / "test_sample.jsonl")
    out = test(rows, choice) | {"training": training(), "dev": choice}
    (RESULTS / "router.json").write_text(json.dumps(out, indent=1) + "\n")
    (RESULTS / "router.md").write_text(render(choice, out))
    print((RESULTS / "router.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
