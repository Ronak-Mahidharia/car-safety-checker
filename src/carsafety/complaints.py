"""Read NHTSA's complaint files into one clean table: one row per complaint.

The files are tab-separated, with 51 fields and no header (field list: NHTSA's CMPL.txt).
One complaint appears on several rows, one per component, so rows are grouped by the
complaint number (ODINO). Personal details (the owner's city, state, and partial VIN,
the dealer's details, the vehicle operator's name, and the incident state) are never read.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Iterable

import pandas as pd

from .labels import normalize

# The complaint files the published answer key was built from (downloaded Sept 30, 2026; docs/answer-key.md).
# NHTSA updates these files in place, so a later download usually differs, and a new answer key built from it
# would replace the published test sample. build_answer_key.py checks against these first.
PUBLISHED_SOURCES = {
    "COMPLAINTS_RECEIVED_2015-2019.zip": "d8d95b377ad5e40f014c83030102f5c43b4cd7c0f804d4a66d4b6f4239e94f60",
    "COMPLAINTS_RECEIVED_2020-2024.zip": "e61028e5b509ffcd52f12a6520f0e17084a20bf1c120992e862a79055884a3e6",
    "COMPLAINTS_RECEIVED_2025-2026.zip": "ce30bdc24c6a90a2aabd3333b8fbc189ee23745b874c84ab0fa80e3bf4302fa4",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def changed_sources(raw: Path) -> list[str]:
    """The published answer key's complaint files that are missing from raw/ or differ from the published ones."""
    return [name for name, digest in PUBLISHED_SOURCES.items() if not (raw / name).is_file() or sha256(raw / name) != digest]

FIELDS = (
    "CMPLID ODINO MFR_NAME MAKETXT MODELTXT YEARTXT CRASH FAILDATE FIRE INJURED DEATHS COMPDESC "
    "CITY STATE VIN DATEA LDATE MILES OCCURENCES CDESCR CMPL_TYPE POLICE_RPT_YN PURCH_DT "
    "ORIG_OWNER_YN ANTI_BRAKES_YN CRUISE_CONT_YN NUM_CYLS DRIVE_TRAIN FUEL_SYS FUEL_TYPE "
    "TRANS_TYPE VEH_SPEED DOT TIRE_SIZE LOC_OF_TIRE TIRE_FAIL_TYPE ORIG_EQUIP_YN MANUF_DT "
    "SEAT_TYPE RESTRAINT_TYPE DEALER_NAME DEALER_TEL DEALER_CITY DEALER_STATE DEALER_ZIP "
    "PROD_TYPE REPAIRED_YN MEDICAL_ATTN VEHICLES_TOWED_YN STATE_OF_INCIDENT VEHICLE_OPERATOR"
).split()
assert len(FIELDS) == 51

# The only fields we ever read.
KEEP = ("ODINO", "MAKETXT", "MODELTXT", "YEARTXT", "CRASH", "FIRE", "INJURED", "DEATHS",
        "COMPDESC", "LDATE", "CDESCR", "PROD_TYPE")
# Personal fields. Listed so tests can prove they're never loaded.
PERSONAL = ("CITY", "STATE", "VIN", "DEALER_NAME", "DEALER_TEL", "DEALER_CITY", "DEALER_STATE",
            "DEALER_ZIP", "STATE_OF_INCIDENT", "VEHICLE_OPERATOR")
assert not set(KEEP) & set(PERSONAL)


def read_rows(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Read vehicle complaint rows (product type "V") from one or more NHTSA files."""
    frames = [
        pd.read_csv(path, sep="\t", header=None, names=FIELDS, usecols=list(KEEP), dtype=str,
                    quoting=csv.QUOTE_NONE, keep_default_na=False, encoding="utf-8")
        for path in paths
    ]
    rows = pd.concat(frames, ignore_index=True)
    return rows[rows.PROD_TYPE == "V"].drop(columns="PROD_TYPE")


def to_complaints(rows: pd.DataFrame) -> pd.DataFrame:
    """Group rows into one record per complaint, with its clean set of labels.

    A complaint that lists several vehicles (rare) keeps only its first vehicle, so each
    description is counted once.
    """
    rows = rows.copy()
    lookup = {c: normalize(c) for c in rows.COMPDESC.unique()}
    rows["label"] = rows.COMPDESC.map(lookup)
    first_vehicle = rows.groupby("ODINO", sort=False)[["MAKETXT", "MODELTXT", "YEARTXT"]].transform("first")
    rows = rows[(rows[["MAKETXT", "MODELTXT", "YEARTXT"]] == first_vehicle).all(axis=1)]

    labels = rows.dropna(subset=["label"]).groupby("ODINO", sort=False)["label"].agg(lambda s: sorted(set(s)))
    text = rows.assign(n=rows.CDESCR.str.len()).sort_values("n").groupby("ODINO", sort=False).CDESCR.last()
    first = rows.groupby("ODINO", sort=False).first()
    out = pd.DataFrame({
        "id": first.index,
        "received": first.LDATE.values,
        "make": first.MAKETXT.values,
        "model": first.MODELTXT.values,
        "model_year": first.YEARTXT.values,
        "crash": (first.CRASH == "Y").values,
        "fire": (first.FIRE == "Y").values,
        "injured": pd.to_numeric(first.INJURED, errors="coerce").fillna(0).astype(int).values,
        "deaths": pd.to_numeric(first.DEATHS, errors="coerce").fillna(0).astype(int).values,
    })
    out["text"] = out.id.map(text).fillna("")
    out["labels"] = out.id.map(labels).apply(lambda x: x if isinstance(x, list) else [])
    return out


def split_by_date(complaints: pd.DataFrame, dev_start: str = "20240101", test_start: str = "20250101") -> dict[str, pd.DataFrame]:
    """Train on older complaints, tune on the next year, test on the newest ones."""
    ok = complaints[(complaints.labels.str.len() > 0) & (complaints.text.str.len() >= 20)
                    & complaints.received.str.fullmatch(r"\d{8}")]
    return {
        "train": ok[ok.received < dev_start],
        "dev": ok[(ok.received >= dev_start) & (ok.received < test_start)],
        "test": ok[ok.received >= test_start],
    }
