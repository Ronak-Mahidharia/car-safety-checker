"""Tests for reading and grouping NHTSA complaint rows. All data here is made up."""
from carsafety.complaints import FIELDS, PERSONAL, read_rows, split_by_date, to_complaints


def write_rows(path, rows):
    lines = []
    for row in rows:
        values = {name: "" for name in FIELDS}
        values.update(row)
        lines.append("\t".join(values[name] for name in FIELDS))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Unmistakable markers, so a match can only mean a personal field leaked.
PERSONAL_VALUES = {"CITY": "CITYXQZ", "STATE": "QQ", "VIN": "VINXQZ00000", "DEALER_NAME": "DEALERXQZ",
                   "DEALER_TEL": "TELXQZ", "VEHICLE_OPERATOR": "OPERATORXQZ"}
ROWS = [
    # one complaint, two components, so two rows
    {"ODINO": "100", "MAKETXT": "HONDA", "MODELTXT": "CR-V", "YEARTXT": "2019", "COMPDESC": "ENGINE",
     "LDATE": "20250105", "CDESCR": "THE ENGINE STALLED ON THE HIGHWAY AT 60 MPH.", "PROD_TYPE": "V", **PERSONAL_VALUES},
    {"ODINO": "100", "MAKETXT": "HONDA", "MODELTXT": "CR-V", "YEARTXT": "2019", "COMPDESC": "POWER TRAIN:AUTOMATIC TRANSMISSION",
     "LDATE": "20250105", "CDESCR": "THE ENGINE STALLED ON THE HIGHWAY AT 60 MPH.", "PROD_TYPE": "V", **PERSONAL_VALUES},
    # the owner didn't know the component, so it can't be scored
    {"ODINO": "101", "MAKETXT": "TOYOTA", "MODELTXT": "CAMRY", "YEARTXT": "2020", "COMPDESC": "UNKNOWN OR OTHER",
     "LDATE": "20230310", "CDESCR": "SOMETHING IS WRONG WITH THE CAR BUT I DO NOT KNOW WHAT.", "PROD_TYPE": "V"},
    # an old category name, plus a crash with one injury
    {"ODINO": "102", "MAKETXT": "FORD", "MODELTXT": "F-150", "YEARTXT": "2018", "COMPDESC": "SERVICE BRAKES, HYDRAULIC:FOUNDATION COMPONENTS",
     "LDATE": "20240620", "CDESCR": "THE BRAKES FAILED WHILE STOPPING AT A RED LIGHT.", "PROD_TYPE": "V", "CRASH": "Y", "INJURED": "1"},
    # a tire complaint, not a vehicle
    {"ODINO": "103", "MAKETXT": "EXAMPLE TIRE", "MODELTXT": "ALL SEASON", "YEARTXT": "9999", "COMPDESC": "TIRES",
     "LDATE": "20250201", "CDESCR": "THE TREAD SEPARATED FROM THE TIRE ON THE HIGHWAY.", "PROD_TYPE": "T"},
    # one complaint listing two vehicles: only the first is kept
    {"ODINO": "104", "MAKETXT": "CHEVROLET", "MODELTXT": "MALIBU", "YEARTXT": "2017", "COMPDESC": "AIR BAGS",
     "LDATE": "20250310", "CDESCR": "THE AIR BAG WARNING LIGHT STAYS ON IN BOTH OF MY CARS.", "PROD_TYPE": "V"},
    {"ODINO": "104", "MAKETXT": "CHEVROLET", "MODELTXT": "IMPALA", "YEARTXT": "2016", "COMPDESC": "AIR BAGS",
     "LDATE": "20250310", "CDESCR": "THE AIR BAG WARNING LIGHT STAYS ON IN BOTH OF MY CARS.", "PROD_TYPE": "V"},
]


def load(tmp_path):
    path = tmp_path / "complaints.txt"
    write_rows(path, ROWS)
    return read_rows([path])


def test_personal_fields_are_never_loaded(tmp_path):
    rows = load(tmp_path)
    assert not set(PERSONAL) & set(rows.columns)
    flat = " ".join(rows.astype(str).to_numpy().ravel())
    for value in PERSONAL_VALUES.values():
        assert value not in flat


def test_only_vehicle_complaints_are_kept(tmp_path):
    assert "103" not in set(load(tmp_path).ODINO)


def test_rows_group_into_complaints_with_clean_labels(tmp_path):
    complaints = to_complaints(load(tmp_path)).set_index("id")
    assert complaints.loc["100", "labels"] == ["ENGINE", "POWER TRAIN"]
    assert complaints.loc["101", "labels"] == []
    assert complaints.loc["102", "labels"] == ["SERVICE BRAKES"]
    assert bool(complaints.loc["102", "crash"]) and complaints.loc["102", "injured"] == 1
    assert complaints.loc["104", "model"] == "MALIBU"
    assert len(complaints) == 4


def test_split_by_date_and_drop_unscorable(tmp_path):
    splits = split_by_date(to_complaints(load(tmp_path)))
    assert set(splits["test"].id) == {"100", "104"}
    assert set(splits["dev"].id) == {"102"}
    assert set(splits["train"].id) == set()  # 101 has no known component
