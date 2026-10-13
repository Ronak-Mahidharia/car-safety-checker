"""Read a manufacturer's communication and fill in a form for a driver, with the exact words behind every field.

A local model (through Ollama) answers in JSON held to a schema: what a driver may notice, the kind of fix, whether
the manufacturer extends a warranty, the model years named, and NHTSA's components, each after a quote copied from
the summary. Every answer then goes through the evidence check (`check`): a field whose quote isn't in the summary,
or a model year its quote doesn't name, isn't shown. The rules (`by_rules`) are the baseline without AI.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter

from . import metrics
from .bulletins import OVER_THE_AIR, WARRANTY, stated_years
from .embeddings import OLLAMA_URL
from .labels import LABELS
from .llm import _post

FIXES = ("software update", "part replacement", "repair or adjustment", "inspection or diagnosis", "information only",
         "not stated")
SYSTEM = ("You read one communication a vehicle manufacturer sent its dealers, as NHTSA published it, and fill in a "
          "form for a driver. Use only what the text says. Never add what you know or guess.")
FORM = """Fill in the form from the summary alone. Each field comes after its quote: the shortest exact words from the summary that show it (at most 25 words), copied character for character, or "" when the summary doesn't say.
- symptom: what a driver may notice, in a few plain words; "" if the summary doesn't say
- fix: what the dealer or the update does: "software update", "part replacement", "repair or adjustment", "inspection or diagnosis", "information only", or "not stated"
- warranty_extension: true only if the summary says the manufacturer extends or adds warranty coverage
- model_years: every model year the summary names, as four-digit numbers (a range counts each year in it); [] if none
- components: the categories above that the summary is about, at most 3; [] if unclear
Answer in JSON."""
SCHEMA = {
    "type": "object",
    "properties": {
        "symptom_quote": {"type": "string"}, "symptom": {"type": "string"},
        "fix_quote": {"type": "string"}, "fix": {"type": "string", "enum": list(FIXES)},
        "warranty_quote": {"type": "string"}, "warranty_extension": {"type": "boolean"},
        "years_quote": {"type": "string"}, "model_years": {"type": "array", "items": {"type": "integer"}},
        "components_quote": {"type": "string"},
        "components": {"type": "array", "items": {"type": "string", "enum": list(LABELS)}, "maxItems": 3},
    },
}
SCHEMA["required"] = list(SCHEMA["properties"])
EMPTY = {"symptom": "", "fix": "not stated", "warranty_extension": False, "model_years": [], "components": []}
QUOTES = {"symptom": "symptom_quote", "fix": "fix_quote", "warranty_extension": "warranty_quote",
          "model_years": "years_quote", "components": "components_quote"}

# Rules without AI. "warrant" alone also finds bulletins that only say a repair is covered by the usual warranty;
# the stricter rule needs words that name an extension or a program (written before any dev bulletin was read).
WARRANTY_WORD = re.compile(r"warrant", re.I)
WARRANTY_RULE = re.compile(
    r"(?:warranty|coverage)\s+(?:extension|enhancement|program)|extend(?:s|ed|ing)?\s+(?:\w+\s+){0,4}(?:warranty|coverage)"
    r"|extended\s+(?:\w+\s+){0,2}(?:warranty|coverage)|special\s+coverage"
    r"|(?:customer|owner)\s+(?:service|satisfaction|care)\s+program", re.I)
FIX_RULES = (("software update", re.compile(r"software|reprogram|re-program|\bflash|calibration|over[- ]the[- ]air|\bOTA\b", re.I)),
             ("part replacement", re.compile(r"\breplac", re.I)),
             ("repair or adjustment", re.compile(r"\brepair|\badjust|\balign|\bclean|\btighten|\breseal|\binstall", re.I)),
             ("inspection or diagnosis", re.compile(r"\binspect|\bdiagnos|\bcheck", re.I)))
_PLAIN = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‐": "-", "‑": "-", "‒": "-", "–": "-",
                        "—": "-", "−": "-", "●": " ", "•": " ", "▪": " "})
# A quote may join a few pieces of the summary (list items, or parts left out with "..."); each must be in it.
_PIECES = re.compile(r"(?<=[.;!?])\s+|\s*\n\s*|\s*(?:\.\.\.|…)\s*")


def prompt(summary: str) -> str:
    categories = "NHTSA's component categories:\n" + "\n".join(f"- {label}" for label in LABELS)
    return f'{categories}\n\nThe summary:\n"""\n{summary}\n"""\n\n{FORM}'


def ask(summary: str, model: str, url: str = OLLAMA_URL, think: bool | None = None) -> dict:
    """The model's raw answer for one summary, with its time and tokens."""
    payload = {"model": model, "stream": False, "format": SCHEMA,
               "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt(summary)}],
               "options": {"temperature": 0, "seed": 2026, "num_ctx": 8192}}
    if think is not None:
        payload["think"] = think
    started = time.time()
    response = _post(url, "/api/chat", payload)
    return {"raw": response.get("message", {}).get("content", ""), "seconds": round(time.time() - started, 3),
            "prompt_tokens": response.get("prompt_eval_count", 0), "output_tokens": response.get("eval_count", 0)}


def parse(raw: str) -> dict | None:
    """The form from a raw answer, or None if it isn't valid JSON for the schema."""
    try:
        answer = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(answer, dict) or set(SCHEMA["required"]) - set(answer):
        return None
    form = {"symptom": str(answer["symptom"]).strip(), "fix": answer["fix"] if answer["fix"] in FIXES else "not stated",
            "warranty_extension": answer["warranty_extension"] is True,
            "model_years": sorted({y for y in answer["model_years"] if isinstance(y, int) and 1950 <= y <= 2049}),
            "components": sorted({c for c in answer["components"] if c in LABELS})}
    return form | {quote: str(answer[quote]) for quote in QUOTES.values()}


def plain(text: str) -> str:
    """Text for comparing quotes: no capitals, the same spacing, straight quotes and plain dashes, no bullets."""
    return " ".join(text.translate(_PLAIN).lower().split())


def found(quote: str, text: str) -> bool:
    """Every piece of the quote is in the text, apart from spacing, capitals, quote marks, dashes, and bullets, and
    together they aren't a scrap."""
    t = plain(text)
    pieces = [piece for piece in (plain(part).strip(" .,;:\"'-") for part in _PIECES.split(quote)) if piece]
    return bool(pieces) and sum(map(len, pieces)) >= min(8, len(t)) and all(piece in t for piece in pieces)


def filled(form: dict, field: str) -> bool:
    return form[field] != EMPTY[field]


def check(form: dict | None, summary: str) -> dict:
    """What can be shown: each filled field whose quote is in the summary (only the years its quote names)."""
    if form is None:
        return {"shown": dict(EMPTY), "filled": [], "supported": [], "years_listed": [], "years_supported": []}
    shown, supported = dict(EMPTY), []
    for field, quote in QUOTES.items():
        if not filled(form, field) or not found(form[quote], summary):
            continue
        if field == "model_years":
            named = stated_years(form[quote])
            shown[field] = [y for y in form[field] if y in named]
            if shown[field] == form[field]:
                supported.append(field)
        else:
            shown[field] = form[field]
            supported.append(field)
    return {"shown": shown, "filled": [f for f in QUOTES if filled(form, f)], "supported": supported,
            "years_listed": form["model_years"], "years_supported": shown["model_years"]}


def by_rules(summary: str, components) -> dict:
    """The form without AI: the stricter warranty rule, the first fix rule that matches, the years the text names, and
    the keyword model's components (`components` is the browser model's predict)."""
    fix = next((name for name, rule in FIX_RULES if rule.search(summary)), "not stated")
    return {"symptom": "", "fix": fix, "warranty_extension": bool(WARRANTY_RULE.search(summary)),
            "model_years": sorted(stated_years(summary)), "components": sorted(components(summary)),
            "warranty_word": bool(WARRANTY_WORD.search(summary))}


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def score(rows: list[dict], forms: list[dict | None], checked: bool = True, pool: dict[str, int] | None = None) -> dict:
    """Score forms against NHTSA's coded fields for the key's rows (one split), in the same order.

    checked: the forms are the model's, so only what passes the evidence check counts as shown; the rules' forms are
    shown as they are. pool: how many communications of each type the split's sample was drawn from, to estimate
    the warranty precision over all of them (the sample has as many of each type).
    """
    if len(rows) != len(forms):
        raise ValueError(f"{len(rows)} rows but {len(forms)} forms")
    checks = [check(form, row["summary"]) if checked else None for row, form in zip(rows, forms)]
    shown = [c["shown"] if checked else (form or dict(EMPTY)) for c, form in zip(checks, forms)]
    said, sampled = Counter(), Counter(row["type"] for row in rows)
    tp = fp = fn = 0
    for row, s in zip(rows, shown):
        truth = row["type"] == WARRANTY
        tp, fp, fn = tp + (truth and s["warranty_extension"]), fp + (not truth and s["warranty_extension"]), fn + (truth and not s["warranty_extension"])
        said[row["type"]] += s["warranty_extension"]
    warranty = _prf(tp, fp, fn) | {"said_by_type": {t: said[t] for t in sampled}}
    if pool:
        weight = {t: pool[t] / sampled[t] for t in sampled}
        right = said[WARRANTY] * weight[WARRANTY]
        wrong = sum(said[t] * weight[t] for t in sampled if t != WARRANTY)
        warranty["estimated_precision_over_pool"] = right / (right + wrong) if right + wrong else 0.0
    labeled = [(row, s) for row, s in zip(rows, shown) if row["labels"]]
    parts = metrics.score([set(row["labels"]) for row, _ in labeled], [set(s["components"]) for _, s in labeled])
    components = {"bulletins": len(labeled), "none_given": sum(not s["components"] for _, s in labeled)} | {
        k: parts[k] for k in ("micro_precision", "micro_recall", "micro_f1")}
    named = [stated_years(row["summary"]) for row in rows]
    listed = [form["model_years"] if form else [] for form in forms] if checked else [s["model_years"] for s in shown]
    stating = [(row, s, n) for row, s, n in zip(rows, shown, named) if n]
    given = sum(len(s["model_years"]) for _, s, _ in stating)
    years = {"bulletins_naming_years": len(stating), "years_given": given,
             "in_nhtsa_years": sum(len(set(s["model_years"]) & set(row["years"])) for row, s, _ in stating),
             "named_years": sum(len(n) for _, _, n in stating),
             "named_years_given": sum(len(set(s["model_years"]) & n) for _, s, n in stating),
             "bulletins_naming_none": sum(not n for n in named),
             "gave_years_anyway": sum(bool(raw) for raw, n in zip(listed, named) if not n)}
    years["precision"] = years["in_nhtsa_years"] / given if given else 0.0
    years["recall_of_named"] = years["named_years_given"] / years["named_years"] if years["named_years"] else 0.0
    over_the_air = [s for row, s in zip(rows, shown) if row["type"] == OVER_THE_AIR]
    out = {"bulletins": len(rows), "warranty": warranty, "components": components, "years": years,
           "over_the_air_as_software": {"bulletins": len(over_the_air),
                                        "software_update": sum(s["fix"] == "software update" for s in over_the_air)}}
    if checked:
        evidence = {field: {"filled": sum(field in c["filled"] for c in checks),
                            "supported": sum(field in c["supported"] for c in checks)} for field in QUOTES}
        filled_all = sum(e["filled"] for e in evidence.values())
        out["evidence"] = evidence | {"all": {"filled": filled_all,
                                              "supported": sum(e["supported"] for e in evidence.values())}}
        out["evidence"]["all"]["unsupported_share"] = 1 - out["evidence"]["all"]["supported"] / filled_all if filled_all else 0.0
        out["invalid_answers"] = sum(form is None for form in forms)
    return out
