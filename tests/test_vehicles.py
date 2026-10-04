"""Vehicle names: the rules for related names, the recall-file index in web/public/vehicles/, how the
API's list and the index combine, and the search that sorts out which records are the vehicle's own.
The cases mirror web/src/lib/vehicles.test.ts, and web/src/lib/fixtures/names.json holds this code's
answers for the TypeScript to match. Complaint rows are made up; the names are NHTSA's."""
import json
from pathlib import Path

from carsafety.nhtsa import API, NhtsaError, Vehicle
from carsafety.vehicles import (INDEX, closest_recall_names, identify, recall_names, related, related_names, same_name,
                                search, shorter_names, vehicle_models, within, words)

FIXTURE = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "fixtures" / "names.json"


def test_related_names_are_the_same_name_plus_more_words():
    assert related("AIR", "AIR BEV")
    assert related("F-150 SUPERCREW", "F-150")
    assert related("GRAND CHEROKEE", "GRAND CHEROKEE L")
    assert related("CR-V", "CR-V")
    assert related("MUSTANG MACH-E", "MUSTANG MACH E")  # spelled the same apart from punctuation
    assert related("F-150 LIGHTNING BEV", "F-150 (SUPER CREW) LIGHTNING BEV")  # more words in between
    assert not related("MODEL 3", "MODEL Y")
    assert not related("GRAND CHEROKEE", "GRAND WAGONEER")
    assert not related("AIR", "AIRSTREAM")
    assert not related("F-150 HYBRID", "F-150 (SUPER CREW) HEV")


def test_the_chosen_name_comes_first():
    assert related_names("AIR BEV", ["AIR", "AIR BEV", "GRAVITY", "GRAVITY BEV"]) == ["AIR BEV", "AIR"]
    assert related_names("MODEL 3", ["MODEL 3", "MODEL S", "MODEL X", "MODEL Y"]) == ["MODEL 3"]


def test_names_spelled_the_same_apart_from_spaces_and_punctuation_match():
    assert words("F-150 (SUPER CREW) GAS") == ["F150", "SUPER", "CREW", "GAS"]
    assert same_name("MUSTANG MACH-E", "MUSTANG MACH E") and same_name("CR-V", "crv") and same_name("ID.4", "ID 4")
    assert not same_name("MODEL 3", "MODEL Y")
    assert not same_name("", "") and not same_name("-", "")  # a name with no letters or digits matches nothing


def test_more_words_keep_the_order_and_the_first_word():
    assert within("AIR", "AIR BEV") and within("F-150 LIGHTNING BEV", "F-150 (SUPER CREW) LIGHTNING BEV")
    assert not within("AIR BEV", "AIR") and not within("AIR", "AIR")  # not more words
    assert not within("LIGHTNING BEV", "F-150 LIGHTNING BEV")  # another first word
    assert not within("F-150 BEV LIGHTNING", "F-150 LIGHTNING BEV")  # another order


def test_the_most_specific_recall_names_win():
    names = ["F-150", "F-150 LIGHTNING BEV", "MUSTANG", "MUSTANG MACH E"]
    assert closest_recall_names("F-150 (SUPER CREW) LIGHTNING BEV", names) == ["F-150 LIGHTNING BEV"]
    assert closest_recall_names("F-150 (SUPER CREW) HEV", names) == ["F-150"]
    assert closest_recall_names("MUSTANG MACH-E", names) == ["MUSTANG MACH E"]
    assert closest_recall_names("BRONCO", names) == []
    # A name in no list: the one recall-file name that is it with more words beats a shorter one.
    assert closest_recall_names("F-150 LIGHTNING", names) == ["F-150 LIGHTNING BEV"]
    assert closest_recall_names("GRAND CHEROKEE", ["GRAND CHEROKEE L", "GRAND CHEROKEE 4XE"]) == []  # two: no guess


def test_shorter_names_keep_at_least_two_words():
    assert shorter_names("F-150 LIGHTNING BEV") == ["F-150 LIGHTNING"]
    assert shorter_names("SONATA PLUG-IN HYBRID TOURING") == ["SONATA PLUG-IN HYBRID", "SONATA PLUG-IN"]
    assert shorter_names("AIR BEV") == [] and shorter_names("CR-V") == []


def test_the_complaint_records_say_which_model_it_is():
    assert identify("AIR BEV", ["AIR", None, "AIR"]) == ["AIR"]
    assert identify("F-150 (SUPER CREW) LIGHTNING BEV", ["F-150 LIGHTNING BEV", "F-150 HYBRID"]) == ["F-150 LIGHTNING BEV"]
    assert identify("F-150 (SUPER CREW) HEV", ["F-150 HYBRID"]) == ["F-150 HYBRID"]  # no name fits, so the records are trusted
    assert identify("MUSTANG", ["MUSTANG", "MUSTANG MACH E"]) == ["MUSTANG"]
    assert identify("MODEL Y", ["MODEL Y RWD"]) == ["MODEL Y RWD"]
    assert identify("E-CLASS", ["E 450", "E350", "E450", "E 350"]) == ["E 450", "E350"]  # each model once, spellings aside
    assert identify("AIR", []) == ["AIR"]


def test_the_typescript_fixture_still_has_this_codes_answers():
    # If this fails, the rules changed: run scripts/build_web_fixtures.py so the TypeScript is checked against them.
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for name, expected in fixture["words"]:
        assert words(name) == expected, name
    for a, b, *expected in fixture["pairs"]:
        assert [same_name(a, b), within(a, b), related(a, b)] == expected, (a, b)
    for name, names, expected in fixture["closest"]:
        assert closest_recall_names(name, names) == expected, name
    for chosen, models, expected in fixture["identify"]:
        assert identify(chosen, models) == expected, chosen
    for name, expected in fixture["shorter"]:
        assert shorter_names(name) == expected, name


def test_the_index_has_the_names_nhtsas_list_misses():
    assert {"2026", "2025", "2019"} <= set(json.loads((INDEX / "years.json").read_text()))
    assert {"AIR", "GRAVITY"} <= set(recall_names("2026")["LUCID"])
    assert {"NPR HD", "FTR"} <= set(recall_names("2025")["ISUZU"])
    assert "CR-V" in recall_names("2019")["HONDA"]
    assert recall_names("1850") == {}


def test_both_sources_combine_in_capitals_without_repeats():
    def fetch(url):
        if "make=LUCID" in url and url.startswith(f"{API}/products/vehicle/models"):
            return 200, json.dumps({"results": [{"model": "AIR BEV"}, {"model": "Air Bev"}, {"model": "GRAVITY BEV"}]}).encode()
        return 400, b'{"results": []}'
    assert vehicle_models("2026", "lucid", fetch) == ["AIR", "AIR BEV", "GRAVITY", "GRAVITY BEV"]


def test_the_index_still_works_when_nhtsas_list_cant_be_reached():
    def offline(url):
        raise NhtsaError("Couldn't reach NHTSA.")
    assert {"NPR HD", "FTR"} <= set(vehicle_models("2025", "ISUZU", offline))


# ---------- The search, against a stand-in for NHTSA's server ----------

def nhtsa_server(routes):
    """path -> rows. Anything else gets NHTSA's answer for no records: 400 with no rows."""
    calls = []

    def fetch(url):
        calls.append(url.removeprefix(API))
        rows = routes.get(url.removeprefix(API))
        return (400, b'{"results": []}') if rows is None else (200, json.dumps({"results": rows}).encode())
    return fetch, calls


def path(kind, year, make, model):
    return f"/{kind}/{kind}ByVehicle?{Vehicle(year, make, model).query()}"


def recall(campaign, **flags):
    return {"NHTSACampaignNumber": campaign, "ReportReceivedDate": "06/01/2025", "Component": "ELECTRICAL SYSTEM", "Summary": "Summary.",
            "Consequence": "Risk.", "Remedy": "Fix.", "parkIt": False, "parkOutSide": False, "overTheAirUpdate": False, **flags}


def complaint(odi, year, make, model):
    """A made-up complaint whose record names `model`."""
    return {"odiNumber": odi, "dateComplaintFiled": "09/01/2025", "components": "ELECTRICAL SYSTEM", "summary": "It stopped.",
            "products": [{"type": "Vehicle", "productYear": year, "productMake": make, "productModel": model}]}


MUSTANGS = ["MUSTANG", "MUSTANG GT 500", "MUSTANG MACH E", "MUSTANG MACH-E"]
F150S = ["F-150", "F-150 (REGULAR CAB) GAS", "F-150 (SUPER CAB) GAS", "F-150 (SUPER CREW) GAS", "F-150 (SUPER CREW) HEV",
         "F-150 (SUPER CREW) LIGHTNING BEV", "F-150 LIGHTNING BEV"]


def test_the_mach_e_gets_its_own_recalls_not_the_gasoline_mustangs():
    # 2022 Ford (checked Oct 3, 2026): Mach-E complaints are found under MUSTANG MACH-E and name MUSTANG MACH E,
    # the name its recalls are filed under. MUSTANG is the gasoline car.
    fetch, _ = nhtsa_server({
        path("complaints", "2022", "FORD", "MUSTANG MACH-E"): [complaint(1, "2022", "FORD", "MUSTANG MACH E"),
                                                               complaint(2, "2022", "FORD", "MUSTANG MACH E")],
        path("recalls", "2022", "FORD", "MUSTANG MACH E"): [recall("22V412000")],
        path("complaints", "2022", "FORD", "MUSTANG"): [complaint(3, "2022", "FORD", "MUSTANG")],
        path("recalls", "2022", "FORD", "MUSTANG"): [recall("22V083000")],
    })
    found = search(Vehicle("2022", "FORD", "MUSTANG MACH-E"), MUSTANGS, ["MUSTANG", "MUSTANG MACH E"], fetch)
    assert found.models == ["MUSTANG MACH E"]
    assert [(r.campaign, r.listed_as) for r in found.recalls] == [("22V412000", "MUSTANG MACH E")]
    assert [(r.campaign, r.listed_as) for r in found.related_recalls] == [("22V083000", "MUSTANG")]
    assert [c.odi_number for c in found.complaints] == ["1", "2"] and found.left_out == {}
    # The other way round, the gasoline Mustang doesn't get the Mach-E's recalls or complaints either.
    found = search(Vehicle("2022", "FORD", "MUSTANG"), MUSTANGS, ["MUSTANG", "MUSTANG MACH E"], fetch)
    assert [r.campaign for r in found.recalls] == ["22V083000"] and [r.campaign for r in found.related_recalls] == ["22V412000"]
    assert [c.odi_number for c in found.complaints] == ["3"]


def test_another_models_complaints_in_a_search_are_left_out():
    # 2023 Ford (checked Oct 3, 2026): the "F-150 (SUPER CREW) LIGHTNING BEV" search returns Lightning complaints and
    # F-150 HYBRID complaints. Lightning recalls are filed under F-150 LIGHTNING BEV; F-150 is the gasoline truck.
    lightning = "F-150 (SUPER CREW) LIGHTNING BEV"
    fetch, _ = nhtsa_server({
        path("complaints", "2023", "FORD", lightning): [complaint(1, "2023", "FORD", "F-150 LIGHTNING BEV"),
                                                         complaint(2, "2023", "FORD", "F-150 HYBRID"),
                                                         complaint(3, "2023", "FORD", "F-150 LIGHTNING BEV")],
        path("recalls", "2023", "FORD", "F-150 LIGHTNING BEV"): [recall("23V900001")],
        path("recalls", "2023", "FORD", "F-150"): [recall("23V900002")],
    })
    found = search(Vehicle("2023", "FORD", lightning), F150S, ["F-150", "F-150 LIGHTNING BEV"], fetch)
    assert found.names == [lightning, "F-150", "F-150 LIGHTNING BEV", "F-150 LIGHTNING"]  # the last, a shorter version
    assert found.models == ["F-150 LIGHTNING BEV"]
    assert [r.campaign for r in found.recalls] == ["23V900001"] and [r.campaign for r in found.related_recalls] == ["23V900002"]
    assert [c.odi_number for c in found.complaints] == ["1", "3"] and found.left_out == {"F-150 HYBRID": 1}


def test_versions_of_the_model_in_its_own_search_count():
    # The 2015 "FUSION HEV" search returns FUSION, FUSION HYBRID, and FUSION ENERGI complaints (checked Oct 3, 2026).
    # FUSION is within the name, so it's the model; the versions with more words are kept. A complaint about the
    # same versions found only under another name is not.
    fetch, _ = nhtsa_server({
        path("complaints", "2015", "FORD", "FUSION HEV"): [complaint(1, "2015", "FORD", "FUSION"), complaint(2, "2015", "FORD", "FUSION HYBRID"),
                                                          complaint(3, "2015", "FORD", "FUSION ENERGI"), complaint(4, "2015", "FORD", "ESCAPE")],
        path("complaints", "2015", "FORD", "FUSION"): [complaint(5, "2015", "FORD", "FUSION HYBRID")],
    })
    found = search(Vehicle("2015", "FORD", "FUSION HEV"), ["FUSION", "FUSION HEV"], ["FUSION", "FUSION ENERGI", "FUSION HYBRID"], fetch)
    assert found.models == ["FUSION"]
    assert [c.odi_number for c in found.complaints] == ["1", "2", "3"] and found.left_out == {"ESCAPE": 1}


def test_the_records_can_point_to_a_name_no_list_relates():
    # The 2023 "F-150 (SUPER CREW) HEV" complaints name the F-150 HYBRID, which has no recalls of its own; its
    # recalls are filed under F-150, the closest recall-file name (checked Oct 3, 2026).
    hev = "F-150 (SUPER CREW) HEV"
    fetch, calls = nhtsa_server({
        path("complaints", "2023", "FORD", hev): [complaint(1, "2023", "FORD", "F-150 HYBRID")],
        path("recalls", "2023", "FORD", "F-150"): [recall("23V900002")],
    })
    found = search(Vehicle("2023", "FORD", hev), F150S, ["F-150", "F-150 LIGHTNING BEV"], fetch)
    assert found.models == ["F-150 HYBRID"]
    assert path("recalls", "2023", "FORD", "F-150 HYBRID") in calls  # searched because the records name it
    assert [(r.campaign, r.listed_as) for r in found.recalls] == [("23V900002", "F-150")] and found.related_recalls == []
    assert [c.odi_number for c in found.complaints] == ["1"]


def test_a_name_in_no_list_takes_the_recall_name_it_shortens_not_a_shorter_one():
    # "F-150 LIGHTNING" is in neither NHTSA's vehicle list nor its recall file, and has no complaints. NHTSA's API
    # files two Lightning recalls under it, and the rest under F-150 LIGHTNING BEV (checked Oct 3, 2026). F-150 is
    # the gasoline truck. The campaigns here are made up.
    fetch, _ = nhtsa_server({
        path("recalls", "2023", "FORD", "F-150 LIGHTNING"): [recall("23V900003")],
        path("recalls", "2023", "FORD", "F-150 LIGHTNING BEV"): [recall("23V900001")],
        path("recalls", "2023", "FORD", "F-150"): [recall("23V900002")],
    })
    found = search(Vehicle("2023", "FORD", "F-150 LIGHTNING"), F150S, ["F-150", "F-150 LIGHTNING BEV"], fetch)
    assert [(r.campaign, r.listed_as) for r in found.recalls] == [("23V900003", "F-150 LIGHTNING"), ("23V900001", "F-150 LIGHTNING BEV")]
    assert [(r.campaign, r.listed_as) for r in found.related_recalls] == [("23V900002", "F-150")]


def test_recalls_under_a_shorter_version_of_the_name_are_listed_apart():
    # Picking the trim, the two recalls under "F-150 LIGHTNING" are found through the shorter name and kept apart.
    lightning = "F-150 (SUPER CREW) LIGHTNING BEV"
    fetch, calls = nhtsa_server({
        path("complaints", "2023", "FORD", lightning): [complaint(1, "2023", "FORD", "F-150 LIGHTNING BEV")],
        path("recalls", "2023", "FORD", "F-150 LIGHTNING BEV"): [recall("23V900001")],
        path("recalls", "2023", "FORD", "F-150 LIGHTNING"): [recall("23V900003")],
    })
    found = search(Vehicle("2023", "FORD", lightning), F150S, ["F-150", "F-150 LIGHTNING BEV"], fetch)
    assert path("recalls", "2023", "FORD", "F-150 LIGHTNING") in calls
    assert [r.campaign for r in found.recalls] == ["23V900001"]
    assert [(r.campaign, r.listed_as) for r in found.related_recalls] == [("23V900003", "F-150 LIGHTNING")]


def test_a_recall_file_name_finds_complaints_filed_under_the_lists_name():
    # The picker also offers the recall file's names. For the 2026 Lucid AIR, complaints are found under the
    # vehicle list's AIR BEV and name AIR (checked Oct 3, 2026).
    fetch, _ = nhtsa_server({
        path("complaints", "2026", "LUCID", "AIR BEV"): [complaint(1, "2026", "LUCID", "AIR")],
        path("recalls", "2026", "LUCID", "AIR"): [recall("26V540000", parkOutSide=True)],
    })
    found = search(Vehicle("2026", "LUCID", "AIR"), ["AIR", "AIR BEV", "GRAVITY", "GRAVITY BEV"], ["AIR", "GRAVITY"], fetch)
    assert found.models == ["AIR"]
    assert [(r.campaign, r.park_outside) for r in found.recalls] == [("26V540000", True)]
    assert [(c.odi_number, c.listed_as) for c in found.complaints] == [("1", "AIR BEV")]


def test_every_spelling_the_records_use_is_searched():
    # 2020 Mercedes-Benz (checked Oct 3, 2026): E-CLASS complaint records name both "E 450" and "E450", and NHTSA's
    # API files recall 20V228000 under "E450" only. The made-up campaign stands in for it.
    fetch, calls = nhtsa_server({
        path("complaints", "2020", "MERCEDES-BENZ", "E-CLASS"): [complaint(1, "2020", "MERCEDES-BENZ", "E 450"),
                                                                 complaint(2, "2020", "MERCEDES-BENZ", "E450")],
        path("recalls", "2020", "MERCEDES-BENZ", "E450"): [recall("20V900001")],
    })
    found = search(Vehicle("2020", "MERCEDES-BENZ", "E-CLASS"), ["E-CLASS"], ["E 450"], fetch)
    assert found.models == ["E 450"]  # shown once
    assert path("recalls", "2020", "MERCEDES-BENZ", "E450") in calls
    assert [(r.campaign, r.listed_as) for r in found.recalls] == [("20V900001", "E450")]
    assert [c.odi_number for c in found.complaints] == ["1", "2"]
