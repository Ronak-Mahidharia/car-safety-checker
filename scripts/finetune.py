"""Fine-tune a small open model to tag complaints with NHTSA's components, on this Mac.

    python scripts/finetune.py train                  # LoRA and a classification head, 50,000 complaints (hours)
    python scripts/finetune.py predict --split dev    # its probabilities for the 5,000 dev complaints
    python scripts/finetune.py predict --split test   # and for the fixed 1,000-complaint test sample (run once)

The model is Qwen3 1.7B (Apache-2.0), 4-bit, through MLX, so it runs only on Apple silicon:
pip install -r requirements-finetune.txt (in its own environment, Python 3.13). It doesn't write component names: a
classification head reads the model's last hidden state and gives each of the 31 components a probability, the way the
keyword model does, so it can't misspell one, and its confidence can route a complaint (scripts/run_router.py).

The design, fixed before training:
- 50,000 complaints from the train split (received before 2024), drawn with the project's seed
- LoRA of rank 8 on the last 16 layers, and a linear head; binary cross-entropy for each component
- one pass over them in batches of 8, at most 384 tokens of complaint each; Adam, the learning rate warming up to
  1e-4 over 100 steps and then falling to 1e-5; a checkpoint every 1,000 steps
- the checkpoint and the threshold are chosen on the dev complaints, and the test sample is predicted once

Writes data/processed/finetune/ (checkpoints, the training log, and the probabilities); nothing there is committed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
import numpy as np
from mlx.utils import tree_flatten
from mlx_lm import load
from mlx_lm.tuner.utils import linear_to_lora_layers

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from carsafety.labels import LABELS  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "finetune"
BASE = "mlx-community/Qwen3-1.7B-4bit"
SEED, TRAIN_SIZE, BATCH, MAX_TOKENS, CHARS = 2026, 50_000, 8, 384, 1_500
LORA = {"rank": 8, "scale": 20.0, "dropout": 0.0}
LAYERS, PEAK_LR, END_LR, WARMUP, EVERY = 16, 1e-4, 1e-5, 100, 1_000
SUFFIX = "\nComponents:"


class Classifier(nn.Module):
    """The language model with LoRA, read at each complaint's last token by a linear head over the components."""

    def __init__(self, lm, hidden: int, labels: int):
        super().__init__()
        self.lm, self.head = lm, nn.Linear(hidden, labels)

    def __call__(self, tokens, lengths):
        hidden = self.lm.model(tokens)
        last = hidden[mx.arange(tokens.shape[0]), lengths - 1]
        return self.head(last.astype(mx.float32))


def build(adapters: Path | None = None):
    model, tokenizer = load(BASE)
    model.freeze()
    linear_to_lora_layers(model, LAYERS, LORA)
    classifier = Classifier(model, model.args.hidden_size, len(LABELS))
    if adapters is not None:
        classifier.load_weights(str(adapters), strict=False)
    return classifier, tokenizer


def encode(tokenizer, text: str) -> list[int]:
    """The complaint, cut to its first CHARS characters and MAX_TOKENS tokens, then the suffix the head reads."""
    body = tokenizer.encode(f"Complaint: {text[:CHARS].strip()}", add_special_tokens=False)
    tail = tokenizer.encode(SUFFIX, add_special_tokens=False)
    return body[:MAX_TOKENS - len(tail)] + tail


def batch(tokenizer, rows: list[dict]):
    ids = [encode(tokenizer, r["text"]) for r in rows]
    width = max(len(i) for i in ids)
    pad = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    tokens = np.full((len(ids), width), pad, dtype=np.int32)
    for n, i in enumerate(ids):
        tokens[n, :len(i)] = i
    targets = np.array([[1.0 if label in r["labels"] else 0.0 for label in LABELS] for r in rows], dtype=np.float32)
    return mx.array(tokens), mx.array([len(i) for i in ids]), mx.array(targets)


def training_rows(size: int = TRAIN_SIZE) -> list[dict]:
    with (PROCESSED / "train.jsonl").open(encoding="utf-8") as f:
        lines = f.readlines()
    picked = np.random.default_rng(SEED).choice(len(lines), size=size, replace=False)
    rows = [json.loads(lines[i]) for i in picked]
    return [r for r in rows if r["labels"] and r["text"].strip()]


def train(out: Path = OUT, size: int = TRAIN_SIZE) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = training_rows(size)
    mx.random.seed(SEED)  # the LoRA and head start the same way every time
    classifier, tokenizer = build()
    steps = len(rows) // BATCH
    warmup = min(WARMUP, max(1, steps // 10))  # a quick check's few steps warm up for a tenth of them
    schedule = optim.join_schedules([optim.linear_schedule(PEAK_LR / 100, PEAK_LR, warmup),
                                     optim.cosine_decay(PEAK_LR, max(1, steps - warmup), END_LR)], [warmup])
    optimizer = optim.Adam(learning_rate=schedule)

    def loss_fn(model, tokens, lengths, targets):
        return nn.losses.binary_cross_entropy(model(tokens, lengths), targets, with_logits=True, reduction="mean")
    step_fn = nn.value_and_grad(classifier, loss_fn)
    order = np.random.default_rng(SEED + 1).permutation(len(rows))
    log, started, running = [], time.time(), []
    trainable = sum(v.size for _, v in tree_flatten(classifier.trainable_parameters()))
    print(f"{len(rows):,} complaints, {steps:,} steps; {trainable:,} trainable parameters", flush=True)
    for step in range(1, steps + 1):
        chosen = [rows[i] for i in order[(step - 1) * BATCH:step * BATCH]]
        loss, grads = step_fn(classifier, *batch(tokenizer, chosen))
        optimizer.update(classifier, grads)
        mx.eval(classifier.trainable_parameters(), optimizer.state, loss)
        running.append(loss.item())
        if step % 100 == 0 or step == steps:
            entry = {"step": step, "loss": round(sum(running) / len(running), 5), "seconds": round(time.time() - started),
                     "peak_gb": round(mx.get_peak_memory() / 1e9, 2)}
            log.append(entry)
            running = []
            print(json.dumps(entry), flush=True)
            (out / "train_log.json").write_text(json.dumps(log, indent=1) + "\n")
        if step % EVERY == 0 or step == steps:
            weights = dict(tree_flatten(classifier.trainable_parameters()))
            mx.save_safetensors(str(out / f"step-{step:05d}.safetensors"), weights)
    (out / "config.json").write_text(json.dumps(
        {"base": BASE, "seed": SEED, "train_complaints": len(rows), "batch": BATCH, "max_tokens": MAX_TOKENS,
         "chars": CHARS, "lora": LORA, "layers": LAYERS, "peak_lr": PEAK_LR, "end_lr": END_LR, "warmup": WARMUP,
         "steps": steps, "trainable_parameters": trainable, "labels": list(LABELS),
         "minutes": round((time.time() - started) / 60, 1)}, indent=1) + "\n")


def predict(split: str, checkpoint: str, out: Path = OUT) -> None:
    rows_path = PROCESSED / "index" / "dev_rows.jsonl" if split == "dev" else ROOT / "data" / "sample" / "test_sample.jsonl"
    with rows_path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    classifier, tokenizer = build(out / checkpoint)
    classifier.eval()
    found, started = [], time.time()
    for start in range(0, len(rows), 16):
        chosen = rows[start:start + 16]
        tokens, lengths, _ = batch(tokenizer, [dict(r, labels=r.get("labels", [])) for r in chosen])
        probs = mx.sigmoid(classifier(tokens, lengths))
        mx.eval(probs)
        found += [{"id": r["id"], "probs": [round(float(p), 5) for p in row]} for r, row in zip(chosen, probs.tolist())]
    seconds = (time.time() - started) / len(rows)
    name = out / f"{split}-{Path(checkpoint).stem}.jsonl"
    name.write_text("".join(json.dumps(r) + "\n" for r in found))
    name.with_suffix(".json").write_text(json.dumps({"complaints": len(found), "ms_each": round(seconds * 1000, 2),
                                                     "batch": 16}) + "\n")
    print(f"{len(found):,} complaints, {seconds * 1000:.1f} ms each (batches of 16); wrote {name}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", choices=["train", "predict"])
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--checkpoint", default=None, help="a checkpoint's file name in data/processed/finetune/")
    parser.add_argument("--limit", type=int, default=TRAIN_SIZE, help="fewer training complaints, for a quick check")
    parser.add_argument("--out", type=Path, default=OUT, help="where to write (a quick check writes elsewhere)")
    args = parser.parse_args(argv)
    if args.what == "train":
        train(args.out, args.limit)
    else:
        if not args.checkpoint:
            raise SystemExit("Name the checkpoint, such as --checkpoint step-06250.safetensors.")
        predict(args.split, args.checkpoint, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
