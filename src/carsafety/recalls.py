"""Look up NHTSA's official recalls for a vehicle and component.

Reads NHTSA's recalls file (FLAT_RCL_POST_2010.txt: 29 tab-separated fields, no header; the
field list is NHTSA's RCL.txt). One recall campaign appears on several rows, one per vehicle
and component. Matching is by make, model, and model year, plus the clean top-level component
label, so it is only as good as the component identification the evaluation measures.
Recalls with a "Do Not Drive" or "Park Outside" advisory are listed first.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from .labels import normalize

FIELDS = (
    "RECORD_ID CAMPNO MAKETXT MODELTXT YEARTXT MFGCAMPNO COMPNAME MFGNAME BGMAN ENDMAN RCLTYPECD "
    "POTAFF ODATE INFLUENCED_BY MFGTXT RCDATE DATEA RPNO FMVSS DESC_DEFECT CONEQUENCE_DEFECT "
    "CORRECTIVE_ACTION NOTES RCL_CMPT_ID MFR_COMP_NAME MFR_COMP_DESC MFR_COMP_PTNO DO_NOT_DRIVE PARK_OUTSIDE"
).split()
assert len(FIELDS) == 29
KEEP = ("CAMPNO", "MAKETXT", "MODELTXT", "YEARTXT", "COMPNAME", "RCLTYPECD", "POTAFF", "RCDATE",
        "DESC_DEFECT", "CONEQUENCE_DEFECT", "CORRECTIVE_ACTION", "DO_NOT_DRIVE", "PARK_OUTSIDE")
API = "https://api.nhtsa.gov/recalls/campaignNumber?campaignNumber="


def read_recalls(path: str | Path) -> pd.DataFrame:
    """Vehicle recall rows (type "V"), each with its clean component label."""
    rows = pd.read_csv(path, sep="\t", header=None, names=FIELDS, usecols=list(KEEP), dtype=str,
                       quoting=csv.QUOTE_NONE, keep_default_na=False, encoding="utf-8")
    rows = rows[rows.RCLTYPECD == "V"].copy()
    lookup = {c: normalize(c) for c in rows.COMPNAME.unique()}
    rows["label"] = rows.COMPNAME.map(lookup)
    for column in ("MAKETXT", "MODELTXT", "YEARTXT"):
        rows[column] = rows[column].str.strip().str.upper()
    return rows


def find(recalls: pd.DataFrame, make: str, model: str, model_year: str, labels=None) -> list[dict]:
    """Recall campaigns for one vehicle, optionally only those for the given component labels."""
    match = recalls[(recalls.MAKETXT == make.strip().upper()) & (recalls.MODELTXT == model.strip().upper())
                    & (recalls.YEARTXT == str(model_year).strip())]
    if labels is not None:
        match = match[match.label.isin(set(labels))]
    campaigns = []
    for campaign, rows in match.groupby("CAMPNO", sort=False):
        first = rows.iloc[0]
        campaigns.append({
            "campaign": campaign,
            "components": sorted(rows.COMPNAME.unique()),
            "labels": sorted(set(rows.label.dropna())),
            "received": first.RCDATE,
            "do_not_drive": bool((rows.DO_NOT_DRIVE.str.upper() == "YES").any()),
            "park_outside": bool((rows.PARK_OUTSIDE.str.upper() == "YES").any()),
            "summary": first.DESC_DEFECT,
            "consequence": first.CONEQUENCE_DEFECT,
            "remedy": first.CORRECTIVE_ACTION,
            "source": API + campaign,
        })
    campaigns.sort(key=lambda c: c["received"], reverse=True)  # newest first
    campaigns.sort(key=lambda c: not (c["do_not_drive"] or c["park_outside"]))  # then advisories first (stable)
    return campaigns


def agreement(true_labels: list, predicted_labels: list, campaigns_per_complaint: list[list[dict]]) -> dict:
    """End to end: do the predicted components bring up the recalls the true components would?

    For each complaint, the "right" recalls are its vehicle's campaigns for its true components.
    precision: of the recalls the prediction brings up, the share that are right
    recall: of the right recalls, the share the prediction brings up
    """
    hits = shown = right = with_recalls = 0
    for truth, predicted, campaigns in zip(true_labels, predicted_labels, campaigns_per_complaint):
        right_set = {c["campaign"] for c in campaigns if set(c["labels"]) & set(truth)}
        shown_set = {c["campaign"] for c in campaigns if set(c["labels"]) & set(predicted)}
        hits += len(right_set & shown_set)
        shown += len(shown_set)
        right += len(right_set)
        with_recalls += bool(right_set)
    return {"precision": hits / shown if shown else 0.0, "recall": hits / right if right else 0.0,
            "complaints_with_matching_recalls": with_recalls}
