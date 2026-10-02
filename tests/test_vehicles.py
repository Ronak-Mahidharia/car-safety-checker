"""Vehicle names: the related-name rule, the recall-file index in web/public/vehicles/, and how the
API's list and the index combine. The cases mirror web/src/lib/vehicles.test.ts."""
import json

from carsafety.nhtsa import API, NhtsaError
from carsafety.vehicles import INDEX, recall_names, related, related_names, vehicle_models


def test_related_names_are_the_same_name_plus_more_words():
    assert related("AIR", "AIR BEV")
    assert related("F-150 SUPERCREW", "F-150")
    assert related("GRAND CHEROKEE", "GRAND CHEROKEE L")
    assert related("CR-V", "CR-V")
    assert not related("MODEL 3", "MODEL Y")
    assert not related("GRAND CHEROKEE", "GRAND WAGONEER")
    assert not related("AIR", "AIRSTREAM")


def test_the_chosen_name_comes_first():
    assert related_names("AIR BEV", ["AIR", "AIR BEV", "GRAVITY", "GRAVITY BEV"]) == ["AIR BEV", "AIR"]
    assert related_names("MODEL 3", ["MODEL 3", "MODEL S", "MODEL X", "MODEL Y"]) == ["MODEL 3"]


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
