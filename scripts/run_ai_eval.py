"""Score the AI approaches on complaints the system has never seen.

  --split dev    200 dev complaints (received in 2024), for choosing settings and prompt wording
  --split test   the fixed 1,000-complaint test sample (2025 onward), for the final numbers only

Approaches:
  knn    similar-complaint voting: the labels of the most similar past complaints
         (k and threshold chosen on the 5,000 dev complaints in the index)
  alone  a local AI model reads the complaint and picks categories
  rag    the same, plus the 8 most similar past complaints and their NHTSA labels

AI answers are cached in data/processed/predictions/, so an interrupted run resumes where it
stopped. The test split also writes docs/results/ai.md.

    python scripts/run_ai_eval.py --split dev --models granite4:3b --modes alone --prompt v1 v2
    python scripts/run_ai_eval.py --split test --models granite4:3b qwen3:8b --modes knn alone rag
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import numpy as np

from carsafety.embeddings import top_k, vote
from carsafety.llm import PROMPT_VERSION, classify, supports_thinking
from carsafety.metrics import score
from carsafety.recalls import agreement, find, read_recalls

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
INDEX, PREDICTIONS = PROCESSED / "index", PROCESSED / "predictions"
SEED, DEV_INDEX_SIZE, DEV_PROMPT_SIZE, EXAMPLES = 2026, 5_000, 200, 8


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def dev_rows() -> list[dict]:
    """The same 5,000 dev complaints build_index.py embedded (same seed), in the same order."""
    dev = load(PROCESSED / "dev.jsonl")
    return [dev[i] for i in np.random.default_rng(SEED).choice(len(dev), size=DEV_INDEX_SIZE, replace=False)]


def tune_knn(train_rows: list[dict], train_vectors: np.ndarray) -> tuple[int, float, float]:
    """Choose k and the vote threshold on the 5,000 dev complaints."""
    dev = load(INDEX / "dev_rows.jsonl")
    positions, scores = top_k(np.load(INDEX / "dev_vectors.npy"), train_vectors, k=40)
    truth = [r["labels"] for r in dev]
    best = (0, 0.0, -1.0)
    for k in (5, 10, 20, 40):
        neighbor_labels = [[train_rows[p]["labels"] for p in row[:k]] for row in positions]
        for threshold in np.arange(0.20, 0.61, 0.05):
            f1 = score(truth, vote(neighbor_labels, scores[:, :k], float(threshold)))["micro_f1"]
            if f1 > best[2]:
                best = (k, round(float(threshold), 2), f1)
    return best


def run_ai(rows: list[dict], model: str, mode: str, split: str, version: str, examples: list[list[dict]] | None) -> dict:
    """Ask the model about every complaint (cached), then score the answers."""
    PREDICTIONS.mkdir(parents=True, exist_ok=True)
    cache = PREDICTIONS / f"{split}-{model.replace(':', '_')}-{mode}-{version}.jsonl"
    done = {r["id"]: r for r in load(cache)} if cache.exists() else {}
    think = False if supports_thinking(model) else None
    with cache.open("a", encoding="utf-8") as out:
        for i, row in enumerate(rows):
            if row["id"] in done:
                continue
            labels, info = classify(row["text"], model, examples=examples[i] if examples else None,
                                    think=think, version=version)
            record = {"id": row["id"], "labels": sorted(labels), "seconds": info["seconds"],
                      "prompt_tokens": info["prompt_tokens"], "output_tokens": info["output_tokens"], "raw": info["raw"]}
            out.write(json.dumps(record) + "\n")
            out.flush()
            done[row["id"]] = record
            if len(done) % 100 == 0:
                print(f"    {model} {mode} {version}: {len(done)}/{len(rows)}", flush=True)
    answers = [done[row["id"]] for row in rows]
    predicted = [set(a["labels"]) for a in answers]
    result = score([row["labels"] for row in rows], predicted)
    result["seconds_median"] = statistics.median(a["seconds"] for a in answers)
    result["prompt_tokens_mean"] = statistics.mean(a["prompt_tokens"] for a in answers)
    result["no_answer"] = sum(1 for a in answers if not a["labels"])
    return result, predicted


def summary(name: str, s: dict) -> str:
    secs = f"{s['seconds_median']:.2f}" if "seconds_median" in s else "under 0.01"
    return (f"| {name} | {s['micro_precision']:.3f} | {s['micro_recall']:.3f} | **{s['micro_f1']:.3f}** | "
            f"{s['macro_f1']:.3f} | {s['exact_match']:.3f} | {secs} |")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--modes", nargs="+", default=["knn", "alone", "rag"])
    parser.add_argument("--prompt", nargs="+", default=[PROMPT_VERSION],
                        help="prompt wording(s) to use, or 'auto' (test split): for each model and mode, "
                             "the wording with the higher micro F1 on the dev split")
    args = parser.parse_args()
    dev_results = PROCESSED / "ai_results_dev.json"
    if args.prompt == ["auto"]:
        if args.split != "test" or not dev_results.exists():
            raise SystemExit("--prompt auto needs --split test and an earlier dev run")
        dev = json.loads(dev_results.read_text())

    if args.split == "dev":
        rows, vectors_file = dev_rows()[:DEV_PROMPT_SIZE], INDEX / "dev_vectors.npy"
    else:
        rows, vectors_file = load(ROOT / "data" / "sample" / "test_sample.jsonl"), INDEX / "test_sample_vectors.npy"

    needs_index = "knn" in args.modes or "rag" in args.modes
    if needs_index:
        train_rows = load(INDEX / "train_rows.jsonl")
        train_vectors = np.load(INDEX / "train_vectors.npy")
        query_vectors = np.load(vectors_file)[:len(rows)]
        positions, scores = top_k(query_vectors, train_vectors, k=40)
        examples = [[train_rows[p] for p in row[:EXAMPLES]] for row in positions]
    results, predicted = {}, {}

    if "knn" in args.modes:
        k, threshold, dev_f1 = tune_knn(train_rows, train_vectors)
        neighbor_labels = [[train_rows[p]["labels"] for p in row[:k]] for row in positions]
        name = f"Similar-complaint voting (k={k}, threshold {threshold})"
        predicted[name] = vote(neighbor_labels, scores[:, :k], threshold)
        results[name] = score([r["labels"] for r in rows], predicted[name])
        print(f"  knn: k={k}, threshold={threshold} (dev micro F1 {dev_f1:.3f})", flush=True)
    for model in args.models:
        for mode in [m for m in args.modes if m in ("alone", "rag")]:
            description = f"{model}, {'with similar examples (RAG)' if mode == 'rag' else 'on its own'}"
            if args.prompt == ["auto"]:
                tried = {name.rsplit(" ", 1)[1]: s["micro_f1"] for name, s in dev.items() if name.startswith(description + ", prompt")}
                if not tried:
                    raise SystemExit(f"no dev results for {description}")
                versions = [max(tried, key=tried.get)]
                print(f"  {description}: prompt {versions[0]} chosen on dev ({tried})", flush=True)
            else:
                versions = args.prompt
            for version in versions:
                label = f"{description}, prompt {version}"
                results[label], predicted[label] = run_ai(rows, model, mode, args.split, version,
                                                          examples if mode == "rag" else None)
                print(f"  {label}: micro F1 {results[label]['micro_f1']:.3f}", flush=True)

    header = ["| Approach | Micro precision | Micro recall | Micro F1 | Macro F1 | Exact match | Seconds per complaint (median) |",
              "|---|---|---|---|---|---|---|"]
    table = [summary(name, s) for name, s in results.items()]
    print("\n".join(header + table))
    out_path = PROCESSED / f"ai_results_{args.split}.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}  # keep results from earlier runs
    out.update({name: {k: v for k, v in s.items() if k != "per_label"} for name, s in results.items()})
    out_path.write_text(json.dumps(out, indent=2))

    if args.split == "test":
        baselines = json.loads((PROCESSED / "baselines.json").read_text())
        rows_md = [summary(f"Baseline: {name[0].lower()}{name[1:]}", baselines[name]["sample"])
                   for name in ("Most common label", "Keyword model (TF-IDF + logistic regression)")]
        ai_names = [n for n in results if not n.startswith("Similar-complaint")]
        best_name = max(ai_names, key=lambda n: results[n]["micro_f1"])
        lines = ["# AI results", "", "Generated by `scripts/run_ai_eval.py --split test`. Don't edit by hand.", "",
                 f"Scored on the fixed test sample: {len(rows):,} complaints received from 2025 onward, never used for tuning. "
                 "Settings and prompt wording were chosen on complaints received in 2024. "
                 "All models run locally in Ollama, so the cost is $0.", "",
                 *header, *rows_md, *table, "",
                 f"## Per label: {best_name} (the AI approach with the highest micro F1)", "",
                 "| Label | Precision | Recall | F1 | Complaints |", "|---|---|---|---|---|"]
        lines += [f"| {s.label} | {s.precision:.3f} | {s.recall:.3f} | {s.f1:.3f} | {s.support} |"
                  for s in sorted(results[best_name]["per_label"], key=lambda s: -s.support) if s.support]

        # End to end: the recalls each approach would show, compared with the recalls for the true components.
        recalls = read_recalls(ROOT / "data" / "raw" / "FLAT_RCL_POST_2010.txt")
        campaigns_per_row = [find(recalls, r["make"], r["model"], r["model_year"]) for r in rows]
        keyword = {p["id"]: set(p["labels"]) for p in load(PREDICTIONS / "test-keyword.jsonl")}
        approaches = {"Baseline: keyword model (TF-IDF + logistic regression)": [keyword[r["id"]] for r in rows], **predicted}
        truth = [r["labels"] for r in rows]
        matched = {name: agreement(truth, preds, campaigns_per_row) for name, preds in approaches.items()}
        with_recalls = next(iter(matched.values()))["complaints_with_matching_recalls"]
        lines += ["", "## Finding the right recalls", "",
                  f"For each test complaint, the right recalls are that vehicle's NHTSA recalls for the components NHTSA "
                  f"recorded. {with_recalls} of the {len(rows):,} complaints have at least one.", "",
                  "| Approach | Share of right recalls found | Share of recalls shown that are right |", "|---|---|---|"]
        lines += [f"| {name} | {a['recall']:.3f} | {a['precision']:.3f} |" for name, a in matched.items()]
        (PROCESSED / "ai_recall_agreement_test.json").write_text(json.dumps(matched, indent=2))

        # Publish every approach's answers on the test sample, so anyone can re-check the scores.
        published = ROOT / "docs" / "results" / "predictions"
        published.mkdir(parents=True, exist_ok=True)
        for name, preds in approaches.items():
            slug = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
            slug = "-".join(part for part in slug.split("-") if part)
            with (published / f"{slug}.jsonl").open("w", encoding="utf-8") as out:
                for row, labels in zip(rows, preds):
                    out.write(json.dumps({"id": row["id"], "labels": sorted(labels)}) + "\n")
        lines += ["", f"Every approach's answers on these {len(rows):,} complaints are in `docs/results/predictions/`, "
                  "next to the true labels in `data/sample/test_sample.jsonl`."]
        (ROOT / "docs" / "results" / "ai.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
