from carsafety.labels import normalize, normalize_all


def test_keeps_the_top_level_part():
    assert normalize("SERVICE BRAKES:DISC BRAKE:CALIPER") == "SERVICE BRAKES"
    assert normalize("AIR BAGS") == "AIR BAGS"


def test_merges_old_names_into_current_ones():
    assert normalize("ENGINE AND ENGINE COOLING:ENGINE:GASOLINE") == "ENGINE"
    assert normalize("SERVICE BRAKES, HYDRAULIC:FOUNDATION COMPONENTS") == "SERVICE BRAKES"
    assert normalize("FUEL SYSTEM, GASOLINE:DELIVERY") == "FUEL/PROPULSION SYSTEM"
    assert normalize("VISIBILITY:WINDSHIELD") == "VISIBILITY/WIPER"
    assert normalize("Chest Clip, Buckle, Harness") == "CHILD SEAT"  # case-insensitive


def test_unknown_values_are_not_labels():
    for value in ["UNKNOWN OR OTHER", "Other/Unknown", "Other/I am not sure", "NONE", "", "  "]:
        assert normalize(value) is None


def test_normalize_all_dedupes_sorts_and_drops_unknown():
    rows = ["POWER TRAIN:AUTOMATIC TRANSMISSION", "UNKNOWN OR OTHER", "ENGINE", "ENGINE AND ENGINE COOLING"]
    assert normalize_all(rows) == ("ENGINE", "POWER TRAIN")
    assert normalize_all(["UNKNOWN OR OTHER"]) == ()
