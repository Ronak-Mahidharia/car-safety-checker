"""Reading a bulletin into a form: the evidence check, the rules, and the scores."""
import json

import pytest

from carsafety import extract
from carsafety.extract import EMPTY, SCHEMA, by_rules, check, found, parse, score

MAZDA = ("Mazda has decided to extend the warranty coverage for the thermostat on certain 2018-2021 CX-5 vehicles. "
         "You may notice: -Engine takes longer to warm up. -Poor heater performance, especially at idle. "
         "The dealer will replace the fail‐safe thermostat.")


def answer(**fields):
    form = {"symptom_quote": "", "symptom": "", "fix_quote": "", "fix": "not stated", "warranty_quote": "",
            "warranty_extension": False, "years_quote": "", "model_years": [], "components_quote": "", "components": []}
    return json.dumps(form | fields)


def test_a_quote_counts_only_if_every_piece_of_it_is_in_the_text():
    assert found("extend the warranty coverage", MAZDA)
    assert found("Engine takes longer to warm up. Poor heater performance, especially at idle.", MAZDA)  # list items
    assert found("replace the fail–safe thermostat", MAZDA)  # another dash
    assert found("“Mazda has decided” ... for the thermostat", MAZDA)
    assert not found("Engine takes longer to cool down.", MAZDA)
    assert not found("extend the warranty coverage. The repair is free.", MAZDA)  # one piece isn't there
    assert not found("the", MAZDA) and not found("", MAZDA) and not found("... .", MAZDA)  # scraps


def test_only_fields_with_their_evidence_are_shown():
    form = parse(answer(warranty_quote="extend the warranty coverage", warranty_extension=True,
                        fix_quote="The dealer will repair it for free", fix="part replacement",
                        years_quote="certain 2018-2021 CX-5", model_years=[2018, 2019, 2022],
                        components_quote="thermostat", components=["ENGINE"]))
    result = check(form, MAZDA)
    assert result["shown"]["warranty_extension"] is True
    assert result["shown"]["fix"] == "not stated"  # its quote isn't in the summary
    assert result["shown"]["model_years"] == [2018, 2019]  # 2022 isn't in its quote
    assert result["shown"]["components"] == ["ENGINE"]
    assert result["filled"] == ["fix", "warranty_extension", "model_years", "components"]
    assert result["supported"] == ["warranty_extension", "components"]  # the years only partly
    assert check(None, MAZDA)["shown"] == EMPTY


def test_answers_outside_the_form_are_dropped():
    assert parse("not json") is None
    assert parse(json.dumps({"symptom": "x"})) is None  # fields missing
    form = parse(answer(model_years=[2019, 9999, 1900, "2020"], components=["ENGINE", "FLUX CAPACITOR"], fix="magic",
                        warranty_extension="yes"))
    assert form["model_years"] == [2019] and form["components"] == ["ENGINE"]
    assert form["fix"] == "not stated" and form["warranty_extension"] is False


def test_the_model_is_asked_with_the_schema_at_temperature_0(monkeypatch):
    sent = {}

    def fake_post(url, path, payload, timeout=600):
        sent.update(payload, path=path)
        return {"message": {"content": answer()}, "prompt_eval_count": 900, "eval_count": 80}
    monkeypatch.setattr(extract, "_post", fake_post)
    record = extract.ask(MAZDA, "qwen3:8b", think=False)
    assert sent["path"] == "/api/chat" and sent["format"] == SCHEMA and sent["think"] is False
    assert sent["options"]["temperature"] == 0
    assert MAZDA in sent["messages"][1]["content"] and "ENGINE" in sent["messages"][1]["content"]
    assert (record["prompt_tokens"], record["output_tokens"]) == (900, 80) and parse(record["raw"]) is not None
    assert list(SCHEMA["properties"])[0] == "symptom_quote"  # the quote comes before its field


def test_the_rules():
    form = by_rules(MAZDA, lambda text: {"ENGINE"})
    assert (form["warranty_extension"], form["warranty_word"]) == (True, True)
    assert form["fix"] == "part replacement" and form["model_years"] == [2018, 2019, 2020, 2021]
    covered = by_rules("Repairs are covered by the normal warranty. Reprogram the PCM.", lambda text: set())
    assert (covered["warranty_extension"], covered["warranty_word"]) == (False, True)
    assert covered["fix"] == "software update"  # the first rule that matches


def key_row(nhtsa_id, kind, labels=(), years=(), summary="A summary that names no year."):
    return {"id": nhtsa_id, "type": kind, "labels": list(labels), "years": list(years), "summary": summary}


def test_the_scores_count_what_is_shown():
    rows = [key_row("1", "Warranty Program/Extension", ["ENGINE"], [2019, 2020], "Extends coverage on 2019-2020 cars."),
            key_row("2", "Warranty Program/Extension", ["SEATS"]),
            key_row("3", "Service Bulletin/Repair Instructions", ["ENGINE"]),
            key_row("4", "Over The Air")]
    forms = [parse(answer(warranty_quote="Extends coverage", warranty_extension=True, years_quote="2019-2020 cars",
                          model_years=[2019, 2020, 2021], components_quote="Extends coverage", components=["ENGINE"])),
             parse(answer(warranty_quote="not in the summary", warranty_extension=True)),
             parse(answer(warranty_quote="A summary that names", warranty_extension=True, years_quote="made up",
                          model_years=[2024])),
             None]
    s = score(rows, forms, pool={"Warranty Program/Extension": 20, "Service Bulletin/Repair Instructions": 100,
                                 "Over The Air": 2})
    w = s["warranty"]
    assert (w["precision"], w["recall"]) == (0.5, 0.5)  # 1 right; 1 hidden for its quote; 1 wrong
    assert w["estimated_precision_over_pool"] == pytest.approx(10 / (10 + 100))  # each type weighed by its pool
    assert s["components"]["bulletins"] == 3 and s["components"]["micro_precision"] == 1.0
    assert s["years"]["bulletins_naming_years"] == 1
    assert (s["years"]["years_given"], s["years"]["in_nhtsa_years"]) == (2, 2)  # 2021 isn't in its quote
    assert (s["years"]["bulletins_naming_none"], s["years"]["gave_years_anyway"]) == (3, 1)  # before the check
    assert s["over_the_air_as_software"] == {"bulletins": 1, "software_update": 0}
    assert s["invalid_answers"] == 1
    assert s["evidence"]["warranty_extension"] == {"filled": 3, "supported": 2}
    assert s["evidence"]["model_years"] == {"filled": 2, "supported": 0}
