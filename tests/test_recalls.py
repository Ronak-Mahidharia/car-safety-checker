"""Tests for the recall lookup. All data here is made up."""
import pytest

from carsafety.recalls import FIELDS, agreement, find, read_recalls

ROWS = [
    # campaign 1: two components on one vehicle, with a Do Not Drive advisory
    {"CAMPNO": "26V001000", "MAKETXT": "EXAMPLE", "MODELTXT": "SEDAN", "YEARTXT": "2020", "COMPNAME": "AIR BAGS:FRONTAL",
     "RCLTYPECD": "V", "RCDATE": "20260105", "DESC_DEFECT": "THE AIR BAG MAY RUPTURE.", "DO_NOT_DRIVE": "Yes", "PARK_OUTSIDE": "No"},
    {"CAMPNO": "26V001000", "MAKETXT": "EXAMPLE", "MODELTXT": "SEDAN", "YEARTXT": "2020", "COMPNAME": "ELECTRICAL SYSTEM:WIRING",
     "RCLTYPECD": "V", "RCDATE": "20260105", "DESC_DEFECT": "THE AIR BAG MAY RUPTURE.", "DO_NOT_DRIVE": "Yes", "PARK_OUTSIDE": "No"},
    # campaign 2: newer, no advisory, old category name
    {"CAMPNO": "26V002000", "MAKETXT": "EXAMPLE", "MODELTXT": "SEDAN", "YEARTXT": "2020", "COMPNAME": "ENGINE AND ENGINE COOLING:ENGINE",
     "RCLTYPECD": "V", "RCDATE": "20260301", "DESC_DEFECT": "THE ENGINE MAY STALL.", "DO_NOT_DRIVE": "No", "PARK_OUTSIDE": "No"},
    # a different model year: never matched
    {"CAMPNO": "26V003000", "MAKETXT": "EXAMPLE", "MODELTXT": "SEDAN", "YEARTXT": "2021", "COMPNAME": "STEERING",
     "RCLTYPECD": "V", "RCDATE": "20260401", "DESC_DEFECT": "STEERING MAY BIND.", "DO_NOT_DRIVE": "No", "PARK_OUTSIDE": "No"},
    # a tire recall: not a vehicle recall
    {"CAMPNO": "26T004000", "MAKETXT": "EXAMPLE TIRE", "MODELTXT": "ALL SEASON", "YEARTXT": "2020", "COMPNAME": "TIRES",
     "RCLTYPECD": "T", "RCDATE": "20260501", "DESC_DEFECT": "TREAD MAY SEPARATE.", "DO_NOT_DRIVE": "No", "PARK_OUTSIDE": "No"},
]


def recalls(tmp_path):
    path = tmp_path / "recalls.txt"
    lines = []
    for row in ROWS:
        values = {name: "" for name in FIELDS}
        values.update(row)
        lines.append("\t".join(values[name] for name in FIELDS))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return read_recalls(path)


def test_only_vehicle_recalls_are_read_and_labels_are_clean(tmp_path):
    table = recalls(tmp_path)
    assert "26T004000" not in set(table.CAMPNO)
    assert set(table.label) == {"AIR BAGS", "ELECTRICAL SYSTEM", "ENGINE", "STEERING"}


def test_finds_one_vehicles_campaigns_case_insensitively_with_advisories_first(tmp_path):
    found = find(recalls(tmp_path), "example", "sedan", "2020")
    assert [c["campaign"] for c in found] == ["26V001000", "26V002000"]  # advisory first, even though it's older
    assert found[0]["do_not_drive"] is True and found[0]["labels"] == ["AIR BAGS", "ELECTRICAL SYSTEM"]
    assert found[0]["source"].endswith("campaignNumber=26V001000")


def test_agreement_compares_shown_recalls_with_the_right_ones():
    campaigns = [[{"campaign": "A", "labels": ["AIR BAGS"]}, {"campaign": "B", "labels": ["ENGINE"]}],
                 [{"campaign": "C", "labels": ["STEERING"]}]]
    truth = [["AIR BAGS"], ["SEATS"]]  # the second complaint has no matching recall
    predicted = [{"AIR BAGS", "ENGINE"}, {"STEERING"}]
    result = agreement(truth, predicted, campaigns)
    # right recalls: {A}; shown: {A, B} and {C}; so 1 of 1 right found, 1 of 3 shown is right
    assert result["recall"] == 1.0
    assert result["precision"] == pytest.approx(1 / 3)
    assert result["complaints_with_matching_recalls"] == 1


def test_filters_by_component_label(tmp_path):
    found = find(recalls(tmp_path), "EXAMPLE", "SEDAN", "2020", labels={"ENGINE"})
    assert [c["campaign"] for c in found] == ["26V002000"]
    assert find(recalls(tmp_path), "EXAMPLE", "SEDAN", "2020", labels={"TIRES"}) == []
