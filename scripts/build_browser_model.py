"""Build the small keyword model that runs in the browser, and check it.

On the 2024 dev split, vocabularies of 20,000 to 100,000 terms scored the same as the full
model's 272,088 (0.7381 against 0.7374 micro F1 at 20,000), so the browser model uses the
smallest one within 0.002 of the best dev score: 20,000 terms. Weights are stored as 8-bit
integers with one scale per label.

Checks, in order:
  1. The plain-Python re-implementation (browser_model.py) with full-precision weights
     reproduces scikit-learn's probabilities, so the steps and the exported vocabulary are right.
  2. The 8-bit weights give the same micro F1 on dev and nearly always the same answers.
  3. The test split and the fixed 1,000-complaint sample are scored once.

Writes web/public/model/{model.json,weights.bin}, web/src/model/expected.json (answers the
browser code must reproduce), and docs/results/browser-model.md.

    python scripts/build_browser_model.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from carsafety.browser_model import BrowserModel
from carsafety.metrics import score

ROOT = Path(__file__).resolve().parent.parent
PROCESSED, MODEL_DIR = ROOT / "data" / "processed", ROOT / "web" / "public" / "model"
FEATURES, TRAIN_SAMPLE, SEED = 20_000, 200_000, 2026


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def to_sets(probs: np.ndarray, classes: list[str], threshold: float) -> list[set[str]]:
    return [({classes[i] for i in np.flatnonzero(row >= threshold)} or {classes[int(row.argmax())]}) for row in probs]


def main() -> None:
    train, dev, test = (load(PROCESSED / f"{n}.jsonl") for n in ("train", "dev", "test"))
    sample = load(ROOT / "data" / "sample" / "test_sample.jsonl")
    train = [train[i] for i in np.random.default_rng(SEED).choice(len(train), size=TRAIN_SAMPLE, replace=False)]

    binarizer = MultiLabelBinarizer()
    y = binarizer.fit_transform([r["labels"] for r in train])
    classes = [str(c) for c in binarizer.classes_]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=5, max_features=FEATURES, sublinear_tf=True, strip_accents="unicode")
    x = vectorizer.fit_transform(r["text"] for r in train)
    x.sort_indices()
    model = OneVsRestClassifier(LogisticRegression(max_iter=1000, solver="liblinear"), n_jobs=-1).fit(x, y)
    dev_probs = model.predict_proba(vectorizer.transform(r["text"] for r in dev))
    truth_dev = [r["labels"] for r in dev]
    threshold = max((round(float(t), 2) for t in np.arange(0.15, 0.61, 0.05)),
                    key=lambda t: score(truth_dev, to_sets(dev_probs, classes, t))["micro_f1"])

    vocabulary = [None] * len(vectorizer.vocabulary_)
    for term, i in vectorizer.vocabulary_.items():
        vocabulary[i] = term
    weights = np.vstack([e.coef_[0] for e in model.estimators_])
    bias = np.array([e.intercept_[0] for e in model.estimators_])
    idf = vectorizer.idf_

    # Check 1: full-precision weights through the plain-Python steps match scikit-learn.
    exact = BrowserModel(classes, vocabulary, idf, weights, bias, threshold)
    check_rows = dev[:2000]
    ours = np.vstack([exact.probabilities(r["text"]) for r in check_rows])
    max_diff_exact = float(np.abs(ours - dev_probs[:len(check_rows)]).max())

    # 8-bit weights, one scale per label.
    scale = np.abs(weights).max(axis=1) / 127
    quantized = np.clip(np.round(weights / scale[:, None]), -127, 127).astype(np.int8)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / "weights.bin").write_bytes(quantized.tobytes())
    meta = {
        "format": 1,
        "description": "Car Safety Checker keyword model: TF-IDF (1-2 word terms) + logistic regression per label",
        "labels": classes, "vocabulary": vocabulary,
        "idf": [round(float(v), 6) for v in idf], "bias": [float(v) for v in bias], "scale": [float(v) for v in scale],
        "threshold": threshold, "trained_on": f"{TRAIN_SAMPLE:,} NHTSA complaints received 2015 to 2023 (seed {SEED})",
    }
    (MODEL_DIR / "model.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Check 2: the exported 8-bit model, read back from disk, against the full-precision one.
    small = BrowserModel.load(MODEL_DIR)
    small_dev = [small.predict(r["text"]) for r in dev]
    full_dev = to_sets(dev_probs, classes, threshold)
    agree_dev = sum(a == b for a, b in zip(small_dev, full_dev)) / len(dev)
    f1_full_dev, f1_small_dev = score(truth_dev, full_dev)["micro_f1"], score(truth_dev, small_dev)["micro_f1"]

    # Check 3: score the test split and the fixed sample, once.
    test_scores = score([r["labels"] for r in test], [small.predict(r["text"]) for r in test])
    sample_preds = [small.predict(r["text"]) for r in sample]
    sample_scores = score([r["labels"] for r in sample], sample_preds)

    expected = []
    for r, labels in zip(sample, sample_preds):
        p = small.probabilities(r["text"])
        top = np.argsort(-p)[:3]
        expected.append({"id": r["id"], "labels": sorted(labels), "top": [[classes[i], round(float(p[i]), 6)] for i in top]})
    expected_path = ROOT / "web" / "src" / "model" / "expected.json"
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_text(json.dumps(expected, separators=(",", ":")), encoding="utf-8")

    sizes = {name: (MODEL_DIR / name).stat().st_size for name in ("model.json", "weights.bin")}
    lines = ["# Browser model", "", "Generated by `scripts/build_browser_model.py`. Don't edit by hand.", "",
             f"The live demo runs a small version of the keyword model in the browser: {len(vocabulary):,} terms instead of "
             "272,088, with 8-bit weights. The problem description is analyzed on the visitor's device and isn't sent anywhere.", "",
             "## Size", "", "| File | Size |", "|---|---|"]
    lines += [f"| `{n}` | {s / 1e6:.2f} MB |" for n, s in sizes.items()]
    lines += ["", "## Checks", "",
              f"- The plain-Python steps with full-precision weights match scikit-learn's probabilities on {len(check_rows):,} dev "
              f"complaints (largest difference {max_diff_exact:.1e}).",
              f"- 8-bit weights: dev micro F1 {f1_small_dev:.4f}, against {f1_full_dev:.4f} with full-precision weights; "
              f"the same answer for {agree_dev:.2%} of {len(dev):,} dev complaints.",
              f"- Threshold {threshold}, chosen on the dev split.", "",
              "## Scores (test data, scored once)", "",
              "| Data | Micro precision | Micro recall | Micro F1 | Macro F1 | Exact match |", "|---|---|---|---|---|---|"]
    for name, s in ((f"Full test split ({len(test):,} complaints)", test_scores), (f"Fixed test sample ({len(sample):,})", sample_scores)):
        lines.append(f"| {name} | {s['micro_precision']:.3f} | {s['micro_recall']:.3f} | **{s['micro_f1']:.3f}** | "
                     f"{s['macro_f1']:.3f} | {s['exact_match']:.3f} |")
    lines += ["", "For comparison, the full keyword model scores 0.719 micro F1 on the full test split and 0.718 on the sample "
              "([baselines](baselines.md))."]
    (ROOT / "docs" / "results" / "browser-model.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
