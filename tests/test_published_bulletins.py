"""Reading service bulletins: every published score must come back from the committed answers alone (the key in
data/bulletins/, each kept answer in docs/results/bulletins/, and the website's keyword model), and the README must
match."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_extraction", ROOT / "scripts" / "run_extraction.py")
run_extraction = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_extraction)
RESULTS = json.loads((ROOT / "docs" / "results" / "bulletins.json").read_text(encoding="utf-8"))
ROWS, META = run_extraction.load_key()


def split(name):
    return [r for r in ROWS if r["split"] == name]


def test_every_dev_score_and_the_choice_come_back():
    dev = run_extraction.rule_scores("dev", split("dev"), META)
    for model in run_extraction.MODELS:
        dev[model] = run_extraction.model_scores("dev", model, split("dev"), META)
    assert json.loads(json.dumps(dev)) == RESULTS["dev"]
    assert run_extraction.choose(dev) == RESULTS["chosen"]


def test_the_test_run_is_the_chosen_models_only_and_its_scores_come_back():
    chosen = RESULTS["chosen"]
    assert sorted(p.name for p in (ROOT / "docs" / "results" / "bulletins").glob("test-*.jsonl")) == [
        f"test-{run_extraction.slug(chosen)}.jsonl"]
    test = run_extraction.rule_scores("test", split("test"), META) | {
        chosen: run_extraction.model_scores("test", chosen, split("test"), META)}
    assert json.loads(json.dumps(test)) == RESULTS["test"]


def test_every_answer_kept_is_for_a_key_bulletin_in_its_split():
    for path in (ROOT / "docs" / "results" / "bulletins").glob("*.jsonl"):
        which = path.stem.split("-", 1)[0]
        kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert [k["id"] for k in kept] == [r["id"] for r in split(which)], path.name


def test_the_hand_check_is_the_drawn_sample_with_a_verdict_and_a_reason_each():
    judged = json.loads((ROOT / "data" / "bulletins" / "hand_check.json").read_text(encoding="utf-8"))
    assert [j["id"] for j in judged["bulletins"]] == run_extraction.hand_sample([r["id"] for r in split("test")])
    assert all(j["why"] and j["symptom"] in run_extraction.VERDICTS and j["fix"] in run_extraction.VERDICTS
               for j in judged["bulletins"])
    assert run_extraction.hand_check(ROWS, RESULTS["chosen"]) == RESULTS["hand_check"]


def test_the_readme_numbers_match():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    t = RESULTS["test"][RESULTS["chosen"]]
    word = RESULTS["test"][run_extraction.WORD]
    w = t["warranty"]
    for text in (f"{w['precision'] * 100:.1f}%", f"{w['recall'] * 100:.1f}%", f"{w['f1']:.3f}",
                 f"{w['estimated_precision_over_pool'] * 100:.1f}%", f"{word['warranty']['estimated_precision_over_pool'] * 100:.1f}%",
                 f"{t['years']['gave_years_anyway']} of the {t['years']['bulletins_naming_none']}",
                 f"{t['evidence']['all']['unsupported_share'] * 100:.1f}%", f"{t['components']['micro_f1']:.3f}",
                 f"{RESULTS['test'][run_extraction.RULES]['components']['micro_f1']:.3f}"):
        assert text in readme, text
    hand = RESULTS["hand_check"]["counts"]
    for field in ("symptom", "fix"):
        assert f"{hand[field]['right'] + hand[field]['rightly empty']} of 40" in readme, field
