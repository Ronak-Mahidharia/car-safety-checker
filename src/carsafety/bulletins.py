"""Manufacturers' communications to their dealers, as NHTSA publishes them: service bulletins, warranty extensions,
service campaigns, over-the-air updates, and more.

NHTSA's files (https://static.nhtsa.gov/odi/ffdd/tsbs/, one per span of years NHTSA received them in; the fields are
described in TSBS.txt there) are tab-separated, with one row per communication and value of every field that has
several (vehicle, model year, component), and 14 fields. The ones used here:
    0 NHTSA ID Number           2 Date Added to File (YYYYMMDD)   3 TSB/Document ID (the maker's own number)
    4 Mfr Communication Date    6 Communication Type              7 Make   8 Model   9 Model Year (9999 if unknown)
    10 NHTSA Components         13 Summary (at most 4,000 characters)
They are manufacturers' documents, with no personal details.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .labels import LABELS, normalize

FILE = "TSBS_RECEIVED_2025-2026.zip"
# The download the published answer key (data/bulletins/key.jsonl) was built from. NHTSA updates its files in place.
PUBLISHED_SOURCES = {FILE: "3002a198debb0f6c91268cdee7e2d940084548514b845462d1dc3fb14a5296ed"}
TYPES = ("Service Bulletin/Repair Instructions", "Service Campaign", "Warranty Program/Extension", "Over The Air",
         "Emissions", "Other")
WARRANTY = "Warranty Program/Extension"
OVER_THE_AIR = "Over The Air"
FIELDS = 14

# A model year in the text: 1950 to 2049, not inside a longer number or a code such as the trouble code P2024
# ("2024MY" counts), not a measurement ("2000 RPM", "2000-2500 rpm"), and not a date ("11/18/2025", "November 18,
# 2025"). A range ("2019 - 2021", "2024-26", "2020 through 2022") counts every year in it.
_YEAR = r"(?<![A-Za-z0-9./])(19[5-9]\d|20[0-4]\d)"
_TO = r"\s*(?:-|–|—|to|through|thru)\s*"
_UNITS = r"(?!\s*(?:rpm|psi|kpa|bar\b|nm\b|n·m|km|mi\b|miles|lbs?\b|ft\b|volts?\b|v\b|hz\b|ms\b|kg\b|cc\b|ml\b|mm\b|°|%))"
_RANGE = re.compile(_YEAR + _TO + r"(?:(19[5-9]\d|20[0-4]\d)|(\d\d))(?!\d)" + _UNITS, re.I)
_SINGLE = re.compile(_YEAR + r"(?!\d)(?!" + _TO + r"\d)" + _UNITS, re.I)
_DATE = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s*$", re.I)


@dataclass(frozen=True)
class Bulletin:
    id: str
    added: str  # when NHTSA added it to the file, YYYYMMDD
    document: str  # the maker's own number for it
    issued: str  # the maker's date, YYYYMMDD
    type: str
    vehicles: tuple[tuple[str, str, str], ...]  # (make, model, model year), sorted
    labels: tuple[str, ...]  # NHTSA's components as the 31 labels, unknown left out
    summary: str


def read_bulletins(path: str | Path) -> list[Bulletin]:
    """Every communication in one of NHTSA's files (the zip as downloaded, or its text file), each built from all of
    its rows, in the file's order."""
    path = Path(path)
    rows: dict[str, list[list[str]]] = {}
    with _open(path) as f:
        for number, row in enumerate(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE), 1):
            if len(row) != FIELDS:
                raise ValueError(f"{path.name}, line {number}: {len(row)} fields, not {FIELDS}")
            rows.setdefault(row[0], []).append(row)
    return [bulletin(group) for group in rows.values()]


@contextmanager
def _open(path: Path):
    if path.suffix != ".zip":
        with path.open(encoding="utf-8", newline="") as f:
            yield f
        return
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".txt")]
        if len(names) != 1:
            raise ValueError(f"{path.name} should hold one text file, not {len(names)}")
        with archive.open(names[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8", newline="") as f:
            yield f


def bulletin(rows: list[list[str]]) -> Bulletin:
    """One communication from its rows, which must agree on everything but the vehicle and the component."""
    first = rows[0]
    for row in rows:
        if [row[i] for i in (2, 3, 4, 6, 13)] != [first[i] for i in (2, 3, 4, 6, 13)]:
            raise ValueError(f"NHTSA ID {first[0]}: its rows disagree on the date, number, type, or summary")
    labels = {label for row in rows if (label := normalize(row[10])) is not None}
    if labels - set(LABELS):
        raise ValueError(f"NHTSA ID {first[0]}: components that aren't one of the 31 labels: {sorted(labels - set(LABELS))}")
    return Bulletin(id=first[0], added=first[2], document=first[3].strip(), issued=first[4], type=first[6],
                    vehicles=tuple(sorted({(r[7].strip().upper(), r[8].strip().upper(), r[9].strip()) for r in rows})),
                    labels=tuple(sorted(labels)), summary=first[13].strip())


def stated_years(text: str) -> set[int]:
    """The model years a text names, counting every year in a range."""
    years: set[int] = set()
    for match in _RANGE.finditer(text):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start // 100 * 100 + int(match.group(3))
        if start <= end <= start + 20:
            years.update(range(start, end + 1))
    years.update(int(match.group(1)) for match in _SINGLE.finditer(text)
                 if not _DATE.search(text[max(0, match.start() - 20):match.start()]))
    return years


def text_key(text: str) -> str:
    """The same summary, whatever its spacing or capitals."""
    return " ".join(text.lower().split())


@dataclass(frozen=True)
class Index:
    files: tuple[str, ...]
    bulletins: dict[str, Bulletin]
    models: dict[tuple[str, str], dict[str, tuple[str, ...]]]  # (make, model year) -> model -> NHTSA IDs


def load_index(paths) -> Index:
    """Every communication in NHTSA's files, by make, model year, and model. An ID in two files keeps the later file's."""
    bulletins: dict[str, Bulletin] = {}
    paths = sorted(Path(p) for p in paths)
    for path in paths:
        bulletins.update((b.id, b) for b in read_bulletins(path))
    models: dict[tuple[str, str], dict[str, list[str]]] = {}
    for b in bulletins.values():
        for make, model, year in b.vehicles:
            models.setdefault((make, year), {}).setdefault(model, []).append(b.id)
    return Index(tuple(p.name for p in paths), bulletins,
                 {key: {model: tuple(ids) for model, ids in names.items()} for key, names in models.items()})
