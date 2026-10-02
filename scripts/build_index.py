"""Embed past complaints once, so similar ones can be looked up quickly.

Embeds the same 200,000 training complaints the keyword baseline learned from, plus a
5,000-complaint dev subset (for tuning) and the fixed 1,000-complaint test sample.
Needs Ollama running with nomic-embed-text. Takes about 30 minutes on an Apple M5.
Writes data/processed/index/ (not committed).

    python scripts/build_index.py
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import numpy as np

from carsafety.embeddings import EMBED_MODEL, OLLAMA_URL, embed

ROOT = Path(__file__).resolve().parent.parent
PROCESSED, OUT = ROOT / "data" / "processed", ROOT / "data" / "processed" / "index"
TRAIN_SAMPLE, DEV_SAMPLE, SEED = 200_000, 5_000, 2026  # same training sample as run_baselines.py


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def model_digest() -> str:
    with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=30) as response:
        models = json.load(response)["models"]
    return next(m["digest"] for m in models if m["name"].split(":")[0] == EMBED_MODEL)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    train, dev = load(PROCESSED / "train.jsonl"), load(PROCESSED / "dev.jsonl")
    rng = np.random.default_rng(SEED)
    train = [train[i] for i in rng.choice(len(train), size=min(TRAIN_SAMPLE, len(train)), replace=False)]
    dev = [dev[i] for i in np.random.default_rng(SEED).choice(len(dev), size=min(DEV_SAMPLE, len(dev)), replace=False)]
    sample = load(ROOT / "data" / "sample" / "test_sample.jsonl")
    started = time.time()

    def progress(done: int, total: int = len(train)) -> None:
        if done % 10_240 < 64 or done == total:
            rate = done / max(time.time() - started, 1e-9)
            print(f"  train {done:,}/{total:,} ({rate:.0f}/s, about {(total - done) / max(rate, 1e-9) / 60:.0f} min left)", flush=True)

    for name, rows, kind in (("train", train, "document"), ("dev", dev, "query"), ("test_sample", sample, "query")):
        vectors = embed([r["text"] for r in rows], kind, progress=progress if name == "train" else None)
        np.save(OUT / f"{name}_vectors.npy", vectors.astype(np.float16))  # half precision halves the file size
        with (OUT / f"{name}_rows.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({"id": r["id"], "make": r["make"], "model": r["model"], "model_year": r["model_year"],
                                    "labels": r["labels"], "text": r["text"]}, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows):,} embedded", flush=True)
    meta = {"model": EMBED_MODEL, "model_digest": model_digest(), "train": len(train), "dev": len(dev),
            "test_sample": len(sample), "seed": SEED, "seconds": round(time.time() - started)}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
