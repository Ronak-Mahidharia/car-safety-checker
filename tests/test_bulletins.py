"""Reading NHTSA's file of manufacturer communications, and finding the model years a text names."""
import zipfile

import pytest

from carsafety.bulletins import bulletin, load_index, read_bulletins, stated_years, text_key


def row(nhtsa_id, make="MAZDA", model="CX-5", year="2022", component="ENGINE", kind="Warranty Program/Extension",
        summary="Mazda extends the warranty coverage of the thermostat.", added="20260305"):
    return [nhtsa_id, "", added, "SSP 123", "20260301", "", kind, make, model, year, component, "", "", summary]


def write(path, rows):
    path.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_a_communication_is_built_from_all_of_its_rows(tmp_path):
    rows = [row("1"), row("1", model="CX-30", component="ENGINE AND ENGINE COOLING"), row("1", component="UNKNOWN OR OTHER"),
            row("1", year="9999"), row("2", kind="Over The Air", component="SERVICE BRAKES, HYDRAULIC", summary='"Quoted."')]
    found = read_bulletins(write(tmp_path / "TSBS.txt", rows))
    assert [b.id for b in found] == ["1", "2"]
    one = found[0]
    assert one.vehicles == (("MAZDA", "CX-30", "2022"), ("MAZDA", "CX-5", "2022"), ("MAZDA", "CX-5", "9999"))
    assert one.labels == ("ENGINE",)  # merged into the current name; "unknown" left out
    assert (one.added, one.document, one.issued, one.type) == ("20260305", "SSP 123", "20260301", "Warranty Program/Extension")
    assert found[1].labels == ("SERVICE BRAKES",) and found[1].summary == '"Quoted."'  # quote marks are text, not quoting


def test_the_zip_as_downloaded_reads_the_same(tmp_path):
    text = write(tmp_path / "TSBS_RECEIVED_2025-2026.txt", [row("1"), row("2", make="FORD", model="F-150")])
    with zipfile.ZipFile(tmp_path / "TSBS_RECEIVED_2025-2026.zip", "w") as z:
        z.write(text, text.name)
    assert read_bulletins(tmp_path / "TSBS_RECEIVED_2025-2026.zip") == read_bulletins(text)
    with zipfile.ZipFile(tmp_path / "two.zip", "w") as z:
        z.writestr("a.txt", "")
        z.writestr("b.txt", "")
    with pytest.raises(ValueError, match="one text file"):
        read_bulletins(tmp_path / "two.zip")


def test_a_file_that_doesnt_look_like_nhtsas_is_refused(tmp_path):
    with pytest.raises(ValueError, match="line 2: 13 fields"):
        read_bulletins(write(tmp_path / "short.txt", [row("1"), row("2")[:13]]))
    with pytest.raises(ValueError, match="disagree"):
        bulletin([row("1"), row("1", summary="Another summary.")])
    with pytest.raises(ValueError, match="31 labels"):
        bulletin([row("1", component="FLUX CAPACITOR")])


def test_the_index_finds_communications_by_make_year_and_model(tmp_path):
    old = write(tmp_path / "TSBS_RECEIVED_2020-2024.txt", [row("1", summary="Old copy."), row("3", year="2019")])
    new = write(tmp_path / "TSBS_RECEIVED_2025-2026.txt", [row("1"), row("2", model="CX-30")])
    index = load_index([new, old])
    assert index.files == ("TSBS_RECEIVED_2020-2024.txt", "TSBS_RECEIVED_2025-2026.txt")
    assert index.bulletins["1"].summary.startswith("Mazda extends")  # the later file's copy
    assert index.models[("MAZDA", "2022")] == {"CX-5": ("1",), "CX-30": ("2",)}
    assert index.models[("MAZDA", "2019")] == {"CX-5": ("3",)}


@pytest.mark.parametrize("text, years", [
    ("Some 2021 ES 250 and 2019 – 2021 ES 300h", {2019, 2020, 2021}),
    ("2024-26 CX-90 and 2025-2026 CX-70", {2024, 2025, 2026}),
    ("certain 2024-26 CX-90 vehicles", {2024, 2025, 2026}),  # a short range alone: its last year only from the range
    ("from 2020 through 2022", {2020, 2021, 2022}),
    ("2024MY Tiguan", {2024}),
    ("2019, 2020,2021 models", {2019, 2020, 2021}),
    ("between 1,600 and 2,100 RPM", set()),
    ("at 2000 rpm, or 2000-2500 rpm", set()),
    ("DTC P2024 is set", set()),
    ("part 68412024AA", set()),
    ("produced November 18, 2025 and prior", set()),
    ("built before 11/18/2025", set()),
    ("software version 26.21.2", set()),
])
def test_model_years_named_in_a_text(text, years):
    assert stated_years(text) == years


def test_a_summary_is_the_same_whatever_its_spacing_or_capitals():
    assert text_key("  Flash:  PCM\nUpdates ") == text_key("flash: pcm updates")
