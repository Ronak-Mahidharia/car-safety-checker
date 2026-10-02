"""The MCP server, tested through a real MCP client connected in-process. NHTSA is faked, so there's no
network; the component guesses come from the real 1 MB model in web/public/model/."""
import json

import anyio
import pytest

pytest.importorskip("mcp")
from mcp import Client  # noqa: E402

from carsafety import mcp_server  # noqa: E402
from carsafety.nhtsa import API, NhtsaError  # noqa: E402

ENGINE_PROBLEM = "The engine hesitates when I speed up and the check engine light comes on"


def run(tool, arguments):
    async def go():
        async with Client(mcp_server.server) as client:
            return await client.call_tool(tool, arguments)
    return anyio.run(go)


def tools():
    async def go():
        async with Client(mcp_server.server) as client:
            return (await client.list_tools()).tools
    return {tool.name: tool for tool in anyio.run(go)}


def fake_nhtsa(monkeypatch, routes):
    """Paths not listed answer like NHTSA does for a vehicle with no records: 400 with no rows."""
    calls = []

    def fetch(url):
        calls.append(url)
        status, body = routes.get(url.removeprefix(API), (400, {"results": []}))
        return status, json.dumps(body).encode()
    monkeypatch.setattr(mcp_server, "fetch", fetch)
    return calls


def recall_row(campaign, received, component, **flags):
    return {"NHTSACampaignNumber": campaign, "ReportReceivedDate": received, "Component": component, "Summary": "Summary.",
            "Consequence": "Risk.", "Remedy": "Fix.", "parkIt": False, "parkOutSide": False, "overTheAirUpdate": False, **flags}


def test_four_read_only_tools_with_input_limits():
    listed = tools()
    assert set(listed) == {"vehicle_models", "guess_components", "vehicle_recalls", "similar_complaints"}
    assert all(t.annotations.read_only_hint and t.annotations.destructive_hint is False for t in listed.values())
    assert listed["guess_components"].annotations.open_world_hint is False  # runs offline
    description = listed["guess_components"].input_schema["properties"]["description"]
    assert (description["minLength"], description["maxLength"]) == (20, 2000)
    assert listed["similar_complaints"].input_schema["properties"]["limit"]["maximum"] == 10
    assert all(t.output_schema for t in listed.values())  # every tool returns structured results


def test_guessing_components_never_calls_nhtsa(monkeypatch):
    def no_network(url):
        raise AssertionError("guess_components must not call NHTSA")
    monkeypatch.setattr(mcp_server, "fetch", no_network)
    result = run("guess_components", {"description": "The brakes feel soft and the pedal sinks to the floor"})
    assert not result.is_error
    top = result.structured_content["components"][0]
    assert (top["component"], top["used_to_match"]) == ("SERVICE BRAKES", True)
    assert "83%" in result.structured_content["note"]


def test_descriptions_it_cant_use_are_refused():
    assert run("guess_components", {"description": "too short"}).is_error
    unknown = run("guess_components", {"description": "zzqx qqzx wwvv xxyy zzqq"})
    assert unknown.is_error and "didn't recognize" in unknown.content[0].text


def test_recalls_are_searched_under_related_names_with_warnings_first(monkeypatch):
    # The 2026 Lucid Air: NHTSA's list offers AIR BEV, but its recalls are filed under AIR (checked Oct 2, 2026).
    listed = {"results": [{"model": "AIR BEV"}, {"model": "GRAVITY BEV"}]}
    fake_nhtsa(monkeypatch, {
        "/products/vehicle/models?modelYear=2026&make=LUCID&issueType=c": (200, listed),
        "/products/vehicle/models?modelYear=2026&make=LUCID&issueType=r": (200, listed),
        "/recalls/recallsByVehicle?make=LUCID&model=AIR&modelYear=2026": (200, {"results": [
            recall_row("26V193000", "26/03/2026", "POWER TRAIN:DRIVELINE:DRIVESHAFT"),
            recall_row("26V540000", "20/08/2026", "ELECTRICAL SYSTEM:SOFTWARE", parkOutSide=True),
        ]}),
    })
    result = run("vehicle_recalls", {"year": 2026, "make": "lucid", "model": "air bev",
                                     "description": "The screen went black and the car would not start"})
    assert not result.is_error
    out = result.structured_content
    assert out["searched_names"] == ["AIR BEV", "AIR"]
    assert (out["recall_count"], out["safety_warnings"], out["not_shown"]) == (2, 1, 0)
    first = out["recalls"][0]
    assert (first["campaign"], first["park_outside"], first["matches_description"], first["filed_under"]) == ("26V540000", True, True, "AIR")
    assert first["reported"] == "2026-08-20"
    assert mcp_server.VIN_LOOKUP in out["note"]


def test_a_model_name_nhtsa_doesnt_use_is_an_error_not_no_recalls(monkeypatch):
    listed = {"results": [{"model": "CR-V"}, {"model": "HR-V"}, {"model": "ACCORD"}]}
    fake_nhtsa(monkeypatch, {
        "/products/vehicle/models?modelYear=2019&make=HONDA&issueType=c": (200, listed),
        "/products/vehicle/models?modelYear=2019&make=HONDA&issueType=r": (200, listed),
    })
    result = run("vehicle_recalls", {"year": 2019, "make": "HONDA", "model": "CRV"})
    assert result.is_error
    assert "Did you mean: CR-V" in result.content[0].text


def test_complaints_are_matched_ranked_and_kept_private(monkeypatch):
    partial_vin = "5J6RW2H5"
    complaint = lambda odi, components, summary: {"odiNumber": odi, "dateComplaintFiled": "03/20/2025", "components": components,
                                                  "summary": summary, "vin": partial_vin, "crash": False, "fire": False}
    fake_nhtsa(monkeypatch, {
        "/products/vehicle/models?modelYear=2019&make=HONDA&issueType=c": (200, {"results": [{"model": "CR-V"}]}),
        "/complaints/complaintsByVehicle?make=HONDA&model=CR-V&modelYear=2019": (200, {"results": [
            complaint(1, "ENGINE", "The radio stopped working."),
            complaint(2, "ENGINE", "The engine hesitates when I speed up and the check engine light is on. Call me at 555-123-4567."),
            complaint(3, "AIR BAGS", "The engine hesitates when I speed up and the check engine light comes on."),
        ]}),
    })
    result = run("similar_complaints", {"year": 2019, "make": "HONDA", "model": "CR-V", "description": ENGINE_PROBLEM, "limit": 2})
    assert not result.is_error
    out = result.structured_content
    assert (out["complaint_count"], out["filed_under_likely_components"]) == (3, 2)  # the air bag complaint isn't filed under ENGINE
    assert [c["odi_number"] for c in out["complaints"]] == ["2", "1"]
    assert "[removed]" in out["complaints"][0]["owner_report"] and "555-123-4567" not in json.dumps(out)
    assert partial_vin not in result.content[0].text and '"vin"' not in result.content[0].text
    assert "not instructions" in out["note"]


def test_long_recall_lists_are_capped(monkeypatch):
    rows = [recall_row(f"20V{n:03d}000", "01/01/2020", "ENGINE") for n in range(55)]
    fake_nhtsa(monkeypatch, {
        "/products/vehicle/models?modelYear=2020&make=EXAMPLE&issueType=c": (200, {"results": [{"model": "VAN"}]}),
        "/recalls/recallsByVehicle?make=EXAMPLE&model=VAN&modelYear=2020": (200, {"results": rows}),
    })
    out = run("vehicle_recalls", {"year": 2020, "make": "EXAMPLE", "model": "VAN"}).structured_content
    assert (out["recall_count"], len(out["recalls"]), out["not_shown"]) == (55, 50, 5)


def test_when_nhtsa_is_down_the_tool_says_so(monkeypatch):
    def offline(url):
        raise NhtsaError("Couldn't reach NHTSA. Check the connection and try again.")
    monkeypatch.setattr(mcp_server, "fetch", offline)
    result = run("vehicle_recalls", {"year": 2019, "make": "HONDA", "model": "CR-V"})
    assert result.is_error and "Couldn't reach NHTSA" in result.content[0].text
