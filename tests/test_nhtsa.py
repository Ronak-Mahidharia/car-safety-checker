"""The NHTSA API client, tested against a stand-in for NHTSA's server (no network).

The cases mirror web/src/lib/nhtsa.test.ts and dates.test.ts, so both versions follow the same rules.
Recall rows are shortened copies of real public records (checked Oct 2, 2026); complaint rows are made up.
"""
import json
import urllib.error
from dataclasses import asdict

import pytest

from carsafety import nhtsa
from carsafety.nhtsa import API, CachedFetch, NhtsaError, Vehicle


def server(routes):
    """A fake fetch: path -> (status, body). Anything else is a 404, so a wrong URL fails the test."""
    calls = []

    def fetch(url):
        calls.append(url)
        status, body = routes.get(url.removeprefix(API), (404, "not found"))
        return status, (body if isinstance(body, bytes) else json.dumps(body).encode() if not isinstance(body, str) else body.encode())
    return fetch, calls


CRV = Vehicle("2019", "HONDA", "CR-V")
CRV_QUERY = "make=HONDA&model=CR-V&modelYear=2019"


def recall_row(**fields):
    return {"Manufacturer": "Example", "parkIt": False, "parkOutSide": False, "overTheAirUpdate": False,
            "Summary": "Summary.", "Consequence": "Consequence.", "Remedy": "Remedy.", "Notes": "Notes.", **fields}


def test_dates_follow_each_endpoints_order():
    # Recalls are day/month/year, matching RCDATE in NHTSA's recall file.
    assert nhtsa.parse_day_first("05/12/2019") == "2019-12-05"  # 19V865000, RCDATE 20191205
    assert nhtsa.parse_day_first("25/03/2021") == "2021-03-25"  # 21V215000, RCDATE 20210325
    # Complaints are month/day/year.
    assert nhtsa.parse_month_first("09/29/2026") == "2026-09-29"
    # Bad dates are rejected, not guessed.
    assert nhtsa.parse_day_first("31/02/2024") is None
    assert nhtsa.parse_month_first("13/01/2024") is None
    assert nhtsa.parse_month_first("2024-01-15") is None


def test_urls_are_encoded_like_javascript():
    assert Vehicle("2014", "JEEP", "GRAND CHEROKEE").query() == "make=JEEP&model=GRAND%20CHEROKEE&modelYear=2014"
    assert nhtsa.encode("PIONEER PR (4)") == "PIONEER%20PR%20(4)"  # encodeURIComponent leaves ( ) alone


def test_a_400_with_no_rows_means_no_records():
    fetch, _ = server({f"/recalls/recallsByVehicle?{CRV_QUERY}": (400, {"Count": 0, "Message": "Results returned successfully", "results": []})})
    assert nhtsa.recalls(CRV, fetch) == []


def test_other_failures_are_errors():
    fetch, _ = server({f"/recalls/recallsByVehicle?{CRV_QUERY}": (500, {})})
    with pytest.raises(NhtsaError):
        nhtsa.recalls(CRV, fetch)
    fetch, _ = server({f"/recalls/recallsByVehicle?{CRV_QUERY}": (200, "not json")})
    with pytest.raises(NhtsaError):
        nhtsa.recalls(CRV, fetch)


def test_no_connection_is_an_error(monkeypatch):
    def offline(*args, **kwargs):
        raise urllib.error.URLError("no network")
    monkeypatch.setattr(nhtsa.urllib.request, "urlopen", offline)
    with pytest.raises(NhtsaError, match="Couldn't reach NHTSA"):
        nhtsa.http_get(f"{API}/recalls/recallsByVehicle?{CRV_QUERY}")


def test_recalls_read_dates_advisories_labels_and_links():
    fetch, _ = server({f"/recalls/recallsByVehicle?{CRV_QUERY}": (200, {"results": [
        recall_row(NHTSACampaignNumber="19V865000", ReportReceivedDate="05/12/2019", Component="STRUCTURE:FRAME AND MEMBERS"),
        recall_row(NHTSACampaignNumber="26V517000", ReportReceivedDate="06/08/2026", Component="SERVICE BRAKES, HYDRAULIC", parkIt=True),
        recall_row(NHTSACampaignNumber="26V540000", ReportReceivedDate="20/08/2026", Component="ELECTRICAL SYSTEM:SOFTWARE", parkOutSide=True),
        recall_row(NHTSACampaignNumber="19V865000", ReportReceivedDate="05/12/2019", Component="STRUCTURE"),
    ]})})
    frame, brakes, software = nhtsa.recalls(CRV, fetch)  # the repeated campaign is listed once
    assert (frame.campaign, frame.received, frame.label, frame.do_not_drive, frame.park_outside) == ("19V865000", "2019-12-05", "STRUCTURE", False, False)
    assert frame.source == f"{API}/recalls/campaignNumber?campaignNumber=19V865000"
    assert (brakes.received, brakes.label, brakes.do_not_drive) == ("2026-08-06", "SERVICE BRAKES", True)
    assert (software.received, software.label, software.park_outside) == ("2026-08-20", "ELECTRICAL SYSTEM", True)


def test_complaints_keep_only_what_is_needed():
    partial_vin = "1ABCD23EFG4"
    row = {"odiNumber": 12345678, "manufacturer": "Example Motors", "crash": True, "fire": False, "numberOfInjuries": 2,
           "numberOfDeaths": 0, "dateOfIncident": "07/17/2026", "dateComplaintFiled": "09/29/2026", "vin": partial_vin,
           "components": "SERVICE BRAKES,FUEL SYSTEM, GASOLINE,UNKNOWN OR OTHER",
           "summary": "BRAKES FAILED. CALL ME AT 555-123-4567 OR JOHN@EXAMPLE.COM. VIN 1HGCM82633A004352.",
           "products": [{"type": "Vehicle", "productYear": "2019", "productMake": "HONDA", "productModel": "CR-V"}]}
    fetch, _ = server({f"/complaints/complaintsByVehicle?{CRV_QUERY}": (200, {"count": 1, "results": [row]})})
    [complaint] = nhtsa.complaints(CRV, fetch)
    kept = asdict(complaint)
    assert sorted(kept) == sorted(["odi_number", "filed", "components", "labels", "summary", "crash", "fire", "injuries",
                                   "deaths", "source", "listed_as", "record_model"])
    assert partial_vin not in json.dumps(kept)
    # The period after the email is masked with it, the same as privacy.py and the website.
    assert complaint.summary == "BRAKES FAILED. CALL ME AT [removed] OR [removed] VIN [removed]."
    assert complaint.components == ("SERVICE BRAKES", "FUEL SYSTEM, GASOLINE", "UNKNOWN OR OTHER")
    assert complaint.labels == ("FUEL/PROPULSION SYSTEM", "SERVICE BRAKES")
    assert (complaint.odi_number, complaint.filed, complaint.crash, complaint.injuries) == ("12345678", "2026-09-29", True, 2)
    assert complaint.source == f"{API}/complaints/odinumber?odinumber=12345678"
    assert (complaint.listed_as, complaint.record_model) == ("CR-V", "CR-V")


def test_complaint_records_name_their_own_model():
    # The complaint search takes NHTSA's vehicle-list names, but each record names the model the way recalls
    # are filed: the 2026 Lucid Air's complaints are found under AIR BEV and name AIR (checked Oct 3, 2026).
    lucid = Vehicle("2026", "LUCID", "AIR BEV")
    product = lambda year, make, model, kind="Vehicle": {"type": kind, "productYear": year, "productMake": make, "productModel": model}
    assert nhtsa.record_model({"products": [product("2026", "LUCID", "AIR")]}, lucid) == "AIR"
    assert nhtsa.record_model({"products": [product("9999", "TBD", "TBD"), product("2026", "Lucid", " Air ")]}, lucid) == "AIR"
    assert nhtsa.record_model({"products": [product("2026", "LUCID", "TBD")]}, lucid) is None
    assert nhtsa.record_model({"products": [product("2025", "LUCID", "AIR")]}, lucid) is None  # another model year
    assert nhtsa.record_model({"products": [product("2026", "LUCID", "AIR", kind="Equipment")]}, lucid) is None
    assert nhtsa.record_model({}, lucid) is None and nhtsa.record_model({"products": "AIR"}, lucid) is None


def test_vehicle_lists_combine_both_lists_without_repeats():
    fetch, _ = server({
        "/products/vehicle/models?modelYear=2015&make=FORD&issueType=c": (200, {"results": [{"model": "FLEX"}, {"model": "FLEX"}]}),
        "/products/vehicle/models?modelYear=2015&make=FORD&issueType=r": (400, {"results": []}),
    })
    assert nhtsa.listed_models("2015", "FORD", fetch) == ["FLEX"]


def test_answers_are_kept_for_a_while():
    calls = []

    def fetch(url):
        calls.append(url)
        return (200, b'{"results": []}') if "ok" in url else (503, b"")
    cached = CachedFetch(fetch, seconds=60)
    assert cached("https://example/ok") == cached("https://example/ok") == (200, b'{"results": []}')
    cached("https://example/down"), cached("https://example/down")
    assert calls == ["https://example/ok", "https://example/down", "https://example/down"]  # failures are asked again
