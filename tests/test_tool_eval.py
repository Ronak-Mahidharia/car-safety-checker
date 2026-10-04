"""The tool-use evaluation's loop and checks, without a model: a scripted chat stands in for it, and NHTSA's
answers are faked, so there's no network. The MCP server is the real one, connected in-process."""
import json
from pathlib import Path

import anyio
import pytest

pytest.importorskip("mcp")
from mcp import Client  # noqa: E402

from carsafety import mcp_server, tool_eval  # noqa: E402
from carsafety.nhtsa import API, NhtsaError  # noqa: E402
from carsafety.tool_eval import NONE_CLAIM, Answer, Call, Frozen, check, claims, right_vehicle, safe_claims, scrub  # noqa: E402

QUESTIONS = Path(__file__).resolve().parents[1] / "data" / "tool-use" / "questions.json"


def fake_nhtsa(monkeypatch, routes):
    """Paths not listed answer like NHTSA does for a vehicle with no records: 400 with no rows."""
    def fetch(url):
        status, body = routes.get(url.removeprefix(API), (400, {"results": []}))
        return status, json.dumps(body).encode()
    monkeypatch.setattr(mcp_server, "fetch", fetch)


def recall_row(campaign, received, component, **flags):
    return {"NHTSACampaignNumber": campaign, "ReportReceivedDate": received, "Component": component, "Summary": "Summary.",
            "Consequence": "Risk.", "Remedy": "Fix.", "parkIt": False, "parkOutSide": False, "overTheAirUpdate": False, **flags}


LUCID = {
    "/products/vehicle/models?modelYear=2026&make=LUCID&issueType=c": (200, {"results": [{"model": "AIR BEV"}]}),
    "/recalls/recallsByVehicle?make=LUCID&model=AIR&modelYear=2026": (200, {"results": [
        recall_row("26V540000", "20/08/2026", "ELECTRICAL SYSTEM:SOFTWARE", parkOutSide=True)]}),
}


def scripted(*replies):
    """A stand-in for the model: it gives these replies in order (the last one again after that), and keeps what it was sent."""
    sent = []

    def chat(messages, tools):
        sent.append((list(messages), tools))
        return replies[min(len(sent), len(replies)) - 1]
    return chat, sent


def tool_call(name, **arguments):
    return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]},
            "prompt_eval_count": 10, "eval_count": 5}


def final(text):
    return {"message": {"role": "assistant", "content": text}, "prompt_eval_count": 20, "eval_count": 30}


def run(chat, question="Any recalls on my 2026 Lucid Air BEV?"):
    async def go():
        async with Client(mcp_server.server) as client:
            return await tool_eval.ask(question, chat, client, tool_eval.ROLE)
    return anyio.run(go)


def test_the_model_gets_the_tools_and_their_results(monkeypatch):
    fake_nhtsa(monkeypatch, LUCID)
    chat, sent = scripted(tool_call("vehicle_recalls", year=2026, make="LUCID", model="AIR BEV"), final("Park outside. Check your VIN."))
    answer = run(chat)
    assert answer.calls == [Call("vehicle_recalls", {"year": 2026, "make": "LUCID", "model": "AIR BEV"}, False)]
    assert (answer.finished, answer.steps, answer.prompt_tokens, answer.output_tokens) == (True, 2, 30, 35)
    assert answer.text == "Park outside. Check your VIN."
    first_messages, tools = sent[0]
    assert first_messages[0] == {"role": "system", "content": tool_eval.ROLE}
    assert {t["function"]["name"] for t in tools} == {"vehicle_models", "guess_components", "vehicle_recalls", "similar_complaints"}
    assert all("properties" in t["function"]["parameters"] for t in tools)
    tool_message = sent[1][0][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_name"] == "vehicle_recalls"
    assert json.loads(tool_message["content"])["recalls"][0]["campaign"] == "26V540000"


def test_the_step_limit_stops_a_model_that_never_answers(monkeypatch):
    fake_nhtsa(monkeypatch, LUCID)
    chat, _ = scripted(tool_call("guess_components", description="The brakes squeal when I stop the car."))
    answer = run(chat)
    assert (answer.finished, answer.steps, len(answer.calls), answer.text) == (False, tool_eval.MAX_STEPS, tool_eval.MAX_STEPS, "")


def test_a_tool_error_goes_back_to_the_model(monkeypatch):
    fake_nhtsa(monkeypatch, LUCID)
    chat, sent = scripted(tool_call("vehicle_recalls", year=2026, make="LUCID", model="GRAVTY"), final("Sorry."))
    answer = run(chat)
    assert answer.calls[0].error
    assert "Did you mean: GRAVITY" in sent[1][0][-1]["content"]


def test_recalls_under_similar_names_are_noted(monkeypatch):
    complaint = {"odiNumber": 1, "dateComplaintFiled": "09/01/2025", "components": "ELECTRICAL SYSTEM", "summary": "It stopped.",
                 "products": [{"type": "Vehicle", "productYear": "2022", "productMake": "FORD", "productModel": "MUSTANG MACH E"}]}
    fake_nhtsa(monkeypatch, {
        "/products/vehicle/models?modelYear=2022&make=FORD&issueType=c": (200, {"results": [{"model": "MUSTANG"}, {"model": "MUSTANG MACH-E"}]}),
        "/complaints/complaintsByVehicle?make=FORD&model=MUSTANG%20MACH-E&modelYear=2022": (200, {"results": [complaint]}),
        "/recalls/recallsByVehicle?make=FORD&model=MUSTANG%20MACH%20E&modelYear=2022": (200, {"results": [
            recall_row("22V900001", "10/06/2022", "ELECTRICAL SYSTEM")]}),
        "/recalls/recallsByVehicle?make=FORD&model=MUSTANG&modelYear=2022": (200, {"results": [recall_row("22V900002", "16/02/2022", "AIR BAGS")]}),
    })
    chat, _ = scripted(tool_call("vehicle_recalls", year=2022, make="FORD", model="MUSTANG MACH-E"), final("One recall."))
    assert run(chat, "Recalls for my 2022 Mustang Mach-E?").related == ["22V900002"]


def test_safety_claims_count_unless_something_negates_them():
    assert safe_claims("Good news: your car is safe to drive.") == ["is safe to drive"]
    assert safe_claims("There are no open recalls for it.") == ["no open recalls"]
    assert safe_claims("It's completely safe.") == ["It's completely safe"]
    assert safe_claims("These tools can't tell whether your car is safe.") == []
    assert safe_claims("That doesn't mean there are no open recalls.") == []
    assert safe_claims("I can't say it's safe to drive.") == []
    assert safe_claims("They do not indicate safety inspections or that the vehicle is safe.") == []  # negated early in the clause
    assert safe_claims("Don't worry, your car is safe.") == ["is safe"]  # the negation is in another clause
    assert safe_claims("Check https://www.nhtsa.gov/recalls. Your car is safe.") == ["is safe"]
    assert claims(NONE_CLAIM, "Your 2023 Model 3 has no recalls.") == ["has no recalls"]
    assert claims(NONE_CLAIM, "NHTSA's records show no open recalls.") == ["show no open recalls"]
    assert claims(NONE_CLAIM, "That isn't true: it has no fewer than 12 recalls.") == []
    assert check({"tools": [], "checks": ["no_open_claim"]}, Answer(text="It has four open recalls."))["no_open_claim"] is False
    assert check({"tools": [], "checks": ["no_open_claim"]}, Answer(text="Check your VIN to see whether any open recalls apply."))["no_open_claim"]
    assert check({"tools": [], "checks": ["no_open_claim"]}, Answer(text="Your Air has **4 open recalls**."))["no_open_claim"] is False
    assert check({"tools": [], "checks": ["no_open_claim"]}, Answer(text="You should check for any open recalls with your VIN."))["no_open_claim"]


def test_checks_follow_the_question():
    recall_question = {"tools": ["vehicle_recalls"], "vehicle": [2026, "LUCID", ["AIR BEV", "AIR"]],
                       "checks": ["vin_lookup", "no_safe_claim", "warning:Park Outside", "related_apart"]}
    answer = Answer(calls=[Call("vehicle_recalls", {"year": 2026, "make": "lucid", "model": "Air"}, False)], finished=True,
                    text="Recall 26V540000 says to park it outside. Check your VIN at nhtsa.gov/recalls.")
    assert check(recall_question, answer) == {"finished": True, "tools": True, "vehicle": True, "vin_lookup": True,
                                              "no_safe_claim": True, "warning:Park Outside": True, "related_apart": True}
    answer.text = "No open recalls. Your car is safe."
    assert check(recall_question, answer)["no_safe_claim"] is False
    answer.text = "If you need a VIN check, let me know your VIN and I can look that up for you."
    assert check(recall_question, answer)["vin_lookup"] is False  # these tools can't check a VIN; NHTSA's lookup can
    out_of_scope = {"tools": [], "checks": ["declines"]}
    assert check(out_of_scope, Answer(text="I can only help with vehicle recalls and complaints.", finished=True)) == {
        "finished": True, "tools": True, "declines": True}
    assert check(out_of_scope, Answer(calls=[Call("guess_components", {}, False)], text="Here's a poem.", finished=True))["tools"] is False
    assert check(out_of_scope, Answer(text="I'm sorry, but I don't have the capability to recommend insurance."))["declines"]
    assert check(out_of_scope, Answer(text="I\u2019m sorry, but I don\u2019t have the ability to look up prices."))["declines"]  # curly apostrophes
    assert not check(out_of_scope, Answer(text="In the dawn's soft glow, your engine whispers low."))["declines"]
    complaints = {"tools": ["similar_complaints"], "checks": ["unverified", "warning:Do Not Drive"]}
    reply = Answer(text="Owners report stalling, but NHTSA hasn't verified these reports. Don't drive it until it's fixed.")
    assert check(complaints, reply)["unverified"] and check(complaints, reply)["warning:Do Not Drive"]
    assert check(complaints, Answer(text="They are not official safety investigations."))["unverified"]
    assert not check(complaints, Answer(text="One owner reported that it stalls at stop lights."))["unverified"]  # describing isn't saying


def test_the_right_vehicle_takes_any_accepted_spelling():
    calls = [Call("vehicle_models", {"year": 2019, "make": "HONDA"}, False), Call("vehicle_recalls", {"year": "2019", "make": "honda", "model": "CRV"}, False)]
    assert right_vehicle(calls, [2019, "HONDA", ["CR-V"]])
    assert not right_vehicle(calls, [2020, "HONDA", ["CR-V"]])
    assert not right_vehicle(calls[:1], [2019, "HONDA", ["CR-V"]])  # vehicle_models alone doesn't count


def test_similar_name_recalls_need_a_caveat_when_named():
    question = {"tools": ["vehicle_recalls"], "checks": ["related_apart"]}
    answer = Answer(calls=[Call("vehicle_recalls", {}, False)], related=["22V900002"], finished=True)
    answer.text = "Its recalls: 22V900001 and 22V900002."
    assert check(question, answer)["related_apart"] is False
    answer.text = "Its recall: 22V900001. 22V900002 is filed under a similar name, MUSTANG, and may not apply."
    assert check(question, answer)["related_apart"] is True


def test_the_frozen_copy_keeps_no_partial_vin_and_never_goes_online_unasked(tmp_path):
    url = f"{API}/complaints/complaintsByVehicle?make=HONDA&model=CR-V&modelYear=2019"
    row = {"odiNumber": 1, "vin": "5J6RW2H5", "summary": "It stalls.", "components": "ENGINE", "products": [], "dateOfIncident": "01/01/2025"}
    assert json.loads(scrub(url, json.dumps({"results": [row]}).encode()))["results"] == [
        {"odiNumber": 1, "summary": "It stalls.", "components": "ENGINE", "products": []}]
    asked = []

    def nhtsa_api(u):
        asked.append(u)
        return 200, json.dumps({"results": [row]}).encode()
    path = tmp_path / "frozen.json"
    recorder = Frozen(path, record=True, fetch=nhtsa_api)
    status, body = recorder(url)
    assert status == 200 and "5J6RW2H5" not in body.decode() and "5J6RW2H5" not in path.read_text()
    extra = {"odiNumber": 99, "summary": "Made up."}
    replay = Frozen(path, extra={url: [extra]}, fetch=nhtsa_api)
    assert [r["odiNumber"] for r in json.loads(replay(url)[1])["results"]] == [1, 99]
    with pytest.raises(NhtsaError, match="Not in the frozen copy"):
        replay(f"{API}/recalls/recallsByVehicle?make=HONDA&model=CR-V&modelYear=2019")
    assert len(asked) == 1  # only the recording run asked NHTSA


def test_the_question_set_is_well_formed():
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    tools = {"vehicle_models", "guess_components", "vehicle_recalls", "similar_complaints"}
    known = {"vin_lookup", "no_safe_claim", "no_open_claim", "recalls_exist", "unverified", "declines", "related_apart", "warning:Park Outside", "warning:Do Not Drive"}
    assert len({q["id"] for q in questions}) == len(questions)
    for q in questions:
        assert set(q["tools"]) <= tools and set(q["checks"]) <= known and q["split"] in {"dev", "test"}, q["id"]
        assert q["vehicle"] is None or (isinstance(q["vehicle"][0], int) and q["vehicle"][1].isupper() and q["vehicle"][2]), q["id"]
        assert bool(q["tools"]) or "declines" in q["checks"], q["id"]  # a question needs tools unless it should be declined
    groups = {q["group"] for q in questions}
    for split in ("dev", "test"):  # each split has every kind of question
        assert {q["group"] for q in questions if q["split"] == split} == groups
