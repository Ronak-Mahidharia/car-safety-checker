"""Read manufacturers' service bulletins with a local model, and score its forms against what NHTSA coded.

    python scripts/run_extraction.py --split dev     # both models on the 120 dev bulletins
    python scripts/run_extraction.py --split test    # the model dev chose, once, on the 300 test bulletins
    python scripts/run_extraction.py                 # only rebuild the report from the kept answers (no model)

The model sees only the summary, never NHTSA's coded fields (data/bulletins/key.jsonl, from
scripts/build_bulletin_key.py). It is chosen on dev by a rule fixed before any answer was read: the higher mean of
three scores, warranty-extension F1 and component micro F1 (both as shown, after the evidence check) and the share of
summaries naming no model year where it named none; on a tie, the faster one. Every answer is kept in
docs/results/bulletins/, so the report (docs/results/bulletins.md and .json) is rebuilt from them without a model,
and a run picks up where it stopped. Ollama must be running for --split.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

from carsafety.browser_model import BrowserModel
from carsafety.bulletins import TYPES, WARRANTY
from carsafety.extract import ask, by_rules, parse, score
from carsafety.llm import supports_thinking

ROOT = Path(__file__).resolve().parent.parent
KEY = ROOT / "data" / "bulletins"
OUT = ROOT / "docs" / "results" / "bulletins"
REPORT = ROOT / "docs" / "results" / "bulletins.md"
MODEL_DIR = ROOT / "web" / "public" / "model"
MODELS = ("qwen3:8b", "granite4:3b")
HAND_CHECKED, HAND_SEED = 40, 2026
RULES, WORD = "Rules, no AI (the stricter warranty rule)", "Rules, no AI (any mention of a warranty)"
VERDICTS = ("right", "rightly empty", "wrong", "wrongly empty")  # for a fix, empty means "not stated"


def slug(model: str) -> str:
    return model.replace(":", "-").replace(".", "-")


def load_key() -> tuple[list[dict], dict]:
    with (KEY / "key.jsonl").open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    return rows, json.loads((KEY / "key.json").read_text(encoding="utf-8"))


def answers(split: str, model: str) -> dict[str, dict]:
    path = OUT / f"{split}-{slug(model)}.jsonl"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {record["id"]: record for record in map(json.loads, f)}


def run(split: str, model: str, rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    done = answers(split, model)
    think = False if supports_thinking(model) else None  # Qwen3 would "think" first; off, as in the other runs
    with (OUT / f"{split}-{slug(model)}.jsonl").open("a", encoding="utf-8") as f:
        for n, row in enumerate(rows, 1):
            if row["id"] in done:
                continue
            record = {"id": row["id"]} | ask(row["summary"], model, think=think)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{split} {model} {n}/{len(rows)}: {record['seconds']:.1f} s", flush=True)


def model_scores(split: str, model: str, rows: list[dict], meta: dict) -> dict | None:
    kept = answers(split, model)
    if any(row["id"] not in kept for row in rows):
        return None
    s = score(rows, [parse(kept[row["id"]]["raw"]) for row in rows], pool=meta["pool"][split])
    seconds = [kept[row["id"]]["seconds"] for row in rows]
    return s | {"seconds_median": statistics.median(seconds), "seconds_total": round(sum(seconds), 1)}


def rule_scores(split: str, rows: list[dict], meta: dict) -> dict[str, dict]:
    keyword = BrowserModel.load(MODEL_DIR)
    forms = [by_rules(row["summary"], keyword.predict) for row in rows]
    word = [form | {"warranty_extension": form["warranty_word"]} for form in forms]
    return {RULES: score(rows, forms, checked=False, pool=meta["pool"][split]),
            WORD: score(rows, word, checked=False, pool=meta["pool"][split])}


def choice_score(s: dict) -> float:
    years = s["years"]
    return (s["warranty"]["f1"] + s["components"]["micro_f1"] +
            1 - years["gave_years_anyway"] / years["bulletins_naming_none"]) / 3


def choose(dev: dict[str, dict]) -> str | None:
    scored = {m: s for m, s in dev.items() if m in MODELS and s is not None}
    if len(scored) < len(MODELS):
        return None
    return max(scored, key=lambda m: (choice_score(scored[m]), -scored[m]["seconds_median"]))


def hand_check(rows: list[dict], model: str) -> dict | None:
    """The judged sample of test forms (data/bulletins/hand_check.json), if it was judged for this model."""
    path = KEY / "hand_check.json"
    if not path.exists():
        return None
    judged = json.loads(path.read_text(encoding="utf-8"))
    test_ids = [row["id"] for row in rows if row["split"] == "test"]
    if judged["model"] != model or [j["id"] for j in judged["bulletins"]] != hand_sample(test_ids):
        raise SystemExit("data/bulletins/hand_check.json isn't for this model's test sample.")
    counts = {field: {v: sum(j[field] == v for j in judged["bulletins"]) for v in VERDICTS} for field in ("symptom", "fix")}
    if any(j[field] not in VERDICTS for j in judged["bulletins"] for field in counts):
        raise SystemExit(f"data/bulletins/hand_check.json: every verdict must be one of {', '.join(VERDICTS)}.")
    return {"model": model, "bulletins": len(judged["bulletins"]), "rule": judged["rule"], "counts": counts}


def hand_sample(test_ids: list[str]) -> list[str]:
    return sorted(random.Random(HAND_SEED).sample(sorted(test_ids, key=int), HAND_CHECKED), key=int)


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def row_cells(name: str, s: dict) -> str:
    w, c, y, o = s["warranty"], s["components"], s["years"], s["over_the_air_as_software"]
    unsupported = pct(s["evidence"]["all"]["unsupported_share"]) if "evidence" in s else "n/a"
    seconds = f"{s['seconds_median']:.2f}" if "seconds_median" in s else "n/a"
    return (f"| {name} | {pct(w['precision'])} | {pct(w['recall'])} | {w['f1']:.3f} | "
            f"{pct(w['estimated_precision_over_pool'])} | {c['micro_f1']:.3f} | {pct(y['precision'])} | "
            f"{y['gave_years_anyway']} of {y['bulletins_naming_none']} | {o['software_update']} of {o['bulletins']} | "
            f"{unsupported} | {seconds} |")


HEADER = ("| Method | Warranty: precision | recall | F1 | precision, whole split (est.) | Components: micro F1 | "
          "Model years: right | Years named when the summary names none | Over the air: said software update | "
          "Fields without evidence | Seconds (median) |\n|---|---|---|---|---|---|---|---|---|---|---|")


def report(rows: list[dict], meta: dict) -> dict:
    results: dict = {"key": {k: meta[k] for k in ("source", "sha256", "communications", "distinct_summaries",
                                                    "test_from", "seed", "per_type", "pool")}}
    lines = ["# Results: reading manufacturers' service bulletins", "",
             "Generated by `scripts/run_extraction.py`. Don't edit by hand.", "",
             f"NHTSA publishes the communications manufacturers send their dealers ({meta['communications']:,} in "
             f"`{meta['source']}`, SHA-256 `{meta['sha256'][:12]}…`). A local model reads each summary and fills in a "
             "form for a driver, with a quote from the summary before every field (`src/carsafety/extract.py`); a field "
             "whose quote isn't in the summary isn't shown. NHTSA's own coded fields are the answer key, and the model "
             "never sees them: the type (is it a warranty extension? an over-the-air update?), the model years, and "
             "the components.", "",
             f"The key (`data/bulletins/`): {meta['per_type']['dev']} dev and {meta['per_type']['test']} test "
             f"communications of each of NHTSA's six types, at random (seed {meta['seed']}). Dev is what NHTSA added "
             f"before 2026, test what it added from Jan 1, 2026, and each summary is used once. Because every type is "
             "sampled equally, the warranty precision is also estimated over all of the split's communications, "
             "weighing each type by how many it has.", ""]
    dev_rows = [r for r in rows if r["split"] == "dev"]
    results["dev"] = rule_scores("dev", dev_rows, meta)
    for model in MODELS:
        s = model_scores("dev", model, dev_rows, meta)
        if s is not None:
            results["dev"][model] = s
    chosen = results["chosen"] = choose(results["dev"])
    test_rows = [r for r in rows if r["split"] == "test"]
    tested = model_scores("test", chosen, test_rows, meta) if chosen else None
    results["test"] = {}
    if tested is not None:  # nothing is scored on test, the rules included, until the chosen model's one run
        results["test"] = rule_scores("test", test_rows, meta) | {chosen: tested}
    lines += ["## Dev: choosing the model", "",
              "The rule, fixed before any answer was read: the higher mean of warranty F1, component micro F1, and the "
              "share of summaries naming no model year where the model named none; on a tie, the faster.", "", HEADER]
    lines += [row_cells(name, s) for name, s in results["dev"].items()]
    if chosen:
        lines += ["", f"Chosen: **{chosen}** (mean {choice_score(results['dev'][chosen]):.3f}; "
                      + ", ".join(f"{m} {choice_score(results['dev'][m]):.3f}" for m in MODELS if m != chosen) + ")."]
    if chosen and chosen in results["test"]:
        t = results["test"][chosen]
        lines += ["", "## Test, run once", "", HEADER] + [row_cells(name, s) for name, s in results["test"].items()]
        lines += ["", "### The evidence check, on test", "",
                  "| Field | Filled in | With its quote in the summary |", "|---|---|---|"]
        for field, e in t["evidence"].items():
            if field != "all":
                lines.append(f"| {field} | {e['filled']} | {e['supported']} |")
        lines += ["", f"Warranty extension said, by NHTSA's type ({chosen}, as shown): "
                      + "; ".join(f"{k} {v} of {sum(r['type'] == k for r in rows if r['split'] == 'test')}"
                                  for k, v in t["warranty"]["said_by_type"].items()) + "."]
        checked = hand_check(rows, chosen)
        if checked:
            results["hand_check"] = checked
            lines += ["", f"### Read one by one: the symptom and the fix in {checked['bulletins']} test forms", "",
                      f"Drawn at random from the test forms (seed {HAND_SEED}); each verdict and its reason is in "
                      f"`data/bulletins/hand_check.json`. {checked['rule']}", "",
                      "| Field | " + " | ".join(VERDICTS) + " |", "|---|" + "---|" * len(VERDICTS)]
            for field, c in checked["counts"].items():
                lines.append(f"| {field} | " + " | ".join(str(c[v]) for v in VERDICTS) + " |")
    lines += ["", "Column notes: warranty columns count NHTSA's type Warranty Program/Extension as the truth; "
                  "components are scored on the communications NHTSA gave a component (the rest have none); model "
                  "years are right when NHTSA lists the year for the communication, scored on summaries that name a "
                  "year; over the air counts NHTSA's type Over The Air. The rules' years are the years the summary "
                  "names, and their components are the website's keyword model, trained on owner complaints.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    (REPORT.with_suffix(".json")).write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "test"], help="ask the model(s) first (needs Ollama)")
    args = parser.parse_args(argv)
    rows, meta = load_key()
    if args.split == "dev":
        for model in MODELS:
            run("dev", model, [r for r in rows if r["split"] == "dev"])
    elif args.split == "test":
        dev = {m: model_scores("dev", m, [r for r in rows if r["split"] == "dev"], meta) for m in MODELS}
        chosen = choose(dev)
        if chosen is None:
            raise SystemExit("Run --split dev first: the model is chosen on dev.")
        run("test", chosen, [r for r in rows if r["split"] == "test"])
    results = report(rows, meta)
    print(REPORT.read_text(encoding="utf-8"))
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
