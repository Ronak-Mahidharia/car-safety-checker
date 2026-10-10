"""NHTSA's public API: a vehicle's recalls and owner complaints, read the same way the website reads them.

This follows web/src/lib/nhtsa.ts and web/src/lib/dates.ts, and the tests check both follow the same rules.
What the API does (checked Oct 2, 2026):
  - A vehicle with no records comes back as HTTP 400 with an empty "results" list: no records, not an error.
  - Recall dates are day/month/year ("05/12/2019" for recall 19V865000 is Dec 5, 2019, its RCDATE in
    NHTSA's recall file), while complaint dates are month/day/year.
  - Each complaint record includes a partial VIN. It's dropped here and never kept or returned.
  - A recall lists one component, even when NHTSA's recall file lists several for the campaign.
  - A complaint's components are joined by a comma with no space ("SERVICE BRAKES,AIR BAGS"), while
    names that contain a comma have a space after it ("FUEL SYSTEM, GASOLINE").
  - Searches ignore capitals.
"""
from __future__ import annotations

import gzip
import http.client
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import date
from typing import Callable

from .labels import normalize
from .privacy import scrub

API = "https://api.nhtsa.gov"
# NHTSA's own page for one recall or complaint, with the record and a PDF of it. Links point there,
# because the API's JSON is for programs, not people.
RECORD_PAGE = "https://www.nhtsa.gov/recalls"
USER_AGENT = "car-safety-checker/0.1"
TIMEOUT_SECONDS = 30

# url -> (HTTP status, body). Tests pass their own; the default asks NHTSA's server.
Fetch = Callable[[str], "tuple[int, bytes]"]


class NhtsaError(Exception):
    """NHTSA couldn't be reached, or sent something that couldn't be read."""


def http_get(url: str) -> tuple[int, bytes]:
    """A plain GET to NHTSA's API. Answers with an error status are returned, not raised."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                                                   "Accept-Encoding": "gzip"})
    try:
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                status, body, encoding = response.status, response.read(), response.headers.get("Content-Encoding")
        except urllib.error.HTTPError as error:
            status, body, encoding = error.code, error.read(), error.headers.get("Content-Encoding")
    # http.client.HTTPException covers a reply cut off part way (IncompleteRead), which isn't an OSError
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
        raise NhtsaError("Couldn't reach NHTSA. Check the connection and try again.") from error
    if encoding != "gzip":
        return status, body
    try:
        return status, gzip.decompress(body)
    except (OSError, EOFError, zlib.error) as error:  # a compressed reply that was cut off or damaged
        raise NhtsaError("NHTSA sent a reply that couldn't be read. Try again.") from error


class CachedFetch:
    """Keeps NHTSA's answers for a while, so asking about the same vehicle twice downloads it once."""

    def __init__(self, fetch: Fetch = http_get, seconds: float = 3600, size: int = 64):
        self.fetch, self.seconds, self.size = fetch, seconds, size
        self.kept: dict[str, tuple[float, int, bytes]] = {}
        self.lock = threading.Lock()

    def __call__(self, url: str) -> tuple[int, bytes]:
        now = time.monotonic()
        with self.lock:
            hit = self.kept.get(url)
            if hit and now - hit[0] < self.seconds:
                return hit[1], hit[2]
        status, body = self.fetch(url)
        if status in (200, 400):  # only answers worth keeping
            with self.lock:
                if len(self.kept) >= self.size:
                    del self.kept[min(self.kept, key=lambda k: self.kept[k][0])]
                self.kept[url] = (now, status, body)
        return status, body


def encode(value: str) -> str:
    """The same as JavaScript's encodeURIComponent, so both versions ask for exactly the same URLs."""
    return urllib.parse.quote(value, safe="!'()*")


def query(**params: str) -> str:
    return "&".join(f"{key}={encode(value)}" for key, value in params.items())


def results(path: str, fetch: Fetch = http_get) -> list[dict]:
    """The "results" rows of one API answer. A 400 with no rows means NHTSA has no records."""
    status, body = fetch(f"{API}{path}")
    if status not in (200, 400):
        raise NhtsaError(f"NHTSA's server answered {status}.")
    try:
        data = json.loads(body)
    except ValueError as error:
        raise NhtsaError("NHTSA sent a reply that couldn't be read.") from error
    rows = (data.get("results", data.get("Results")) if isinstance(data, dict) else None)
    if not isinstance(rows, list):
        raise NhtsaError("NHTSA sent a reply that couldn't be read.")
    if status == 400 and rows:
        raise NhtsaError("NHTSA's server answered 400.")
    return [row for row in rows if isinstance(row, dict)]


# ---------- Dates ----------

_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_day_first(value: str) -> str | None:
    """A recall date ("DD/MM/YYYY") as "YYYY-MM-DD", or None if it isn't a real date."""
    m = _DATE.match(value.strip())
    return _iso(int(m[3]), int(m[2]), int(m[1])) if m else None


def parse_month_first(value: str) -> str | None:
    """A complaint date ("MM/DD/YYYY") as "YYYY-MM-DD", or None if it isn't a real date."""
    m = _DATE.match(value.strip())
    return _iso(int(m[3]), int(m[1]), int(m[2])) if m else None


# ---------- Records ----------

def split_components(value: str) -> list[str]:
    """Split the complaints API's list of components (comma with no space between names)."""
    return re.split(r",(?=\S)", value) if value else []


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else "" if value is None else str(value)


def _count(value: object) -> int:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return int(number) if number == number and abs(number) != float("inf") else 0


@dataclass(frozen=True)
class Vehicle:
    year: str
    make: str
    model: str

    def query(self) -> str:
        return query(make=self.make, model=self.model, modelYear=self.year)


@dataclass(frozen=True)
class Recall:
    campaign: str
    received: str | None  # YYYY-MM-DD
    component: str  # as NHTSA lists it, such as "FUEL SYSTEM, GASOLINE:DELIVERY:FUEL PUMP"
    label: str | None
    summary: str
    consequence: str
    remedy: str
    do_not_drive: bool
    park_outside: bool
    over_the_air: bool
    source: str
    listed_as: str  # the model name it was found under


@dataclass(frozen=True)
class Complaint:
    odi_number: str
    filed: str | None  # YYYY-MM-DD
    components: tuple[str, ...]  # as NHTSA lists them
    labels: tuple[str, ...]
    summary: str  # with emails, phone numbers, and full VINs masked
    crash: bool
    fire: bool
    injuries: int
    deaths: int
    source: str
    listed_as: str  # the model name it was found under
    # The model the record itself names. NHTSA's complaint search takes its vehicle list's names
    # ("AIR BEV"), but each record names the model the way recalls are filed ("AIR"), and a search can
    # return records for another model too (see vehicles.py).
    record_model: str | None = None


def to_recall(row: dict, listed_as: str) -> Recall:
    campaign, component = _text(row.get("NHTSACampaignNumber")), _text(row.get("Component"))
    return Recall(
        campaign=campaign,
        received=parse_day_first(_text(row.get("ReportReceivedDate"))),
        component=component,
        label=normalize(component),
        summary=_text(row.get("Summary")),
        consequence=_text(row.get("Consequence")),
        remedy=_text(row.get("Remedy")),
        do_not_drive=row.get("parkIt") is True,
        park_outside=row.get("parkOutSide") is True,
        over_the_air=row.get("overTheAirUpdate") is True,
        source=f"{RECORD_PAGE}?{query(nhtsaId=campaign)}",
        listed_as=listed_as,
    )


def record_model(row: dict, vehicle: Vehicle) -> str | None:
    """The model a complaint record names for the vehicle searched (same model year and make), if any."""
    for product in row.get("products") or []:
        if not isinstance(product, dict) or product.get("type") != "Vehicle":
            continue
        if _text(product.get("productYear")) == vehicle.year and _text(product.get("productMake")).upper() == vehicle.make:
            model = _text(product.get("productModel")).upper()
            if model and model != "TBD":
                return model
    return None


def to_complaint(row: dict, vehicle: Vehicle) -> Complaint:
    """Only these fields are kept. The partial VIN and everything else in the record are dropped."""
    odi_number = _text(row.get("odiNumber"))
    components = tuple(split_components(_text(row.get("components"))))
    labels = tuple(sorted({label for c in components if (label := normalize(c)) is not None}))
    return Complaint(
        odi_number=odi_number,
        filed=parse_month_first(_text(row.get("dateComplaintFiled"))),
        components=components,
        labels=labels,
        summary=scrub(_text(row.get("summary"))),
        crash=row.get("crash") is True,
        fire=row.get("fire") is True,
        injuries=_count(row.get("numberOfInjuries")),
        deaths=_count(row.get("numberOfDeaths")),
        source=f"{RECORD_PAGE}?{query(nhtsaId=odi_number)}",
        listed_as=vehicle.model,
        record_model=record_model(row, vehicle),
    )


def recalls(vehicle: Vehicle, fetch: Fetch = http_get) -> list[Recall]:
    """The vehicle's recall campaigns, one entry per campaign."""
    found: dict[str, Recall] = {}
    for row in results(f"/recalls/recallsByVehicle?{vehicle.query()}", fetch):
        recall = to_recall(row, vehicle.model)
        if recall.campaign and recall.campaign not in found:
            found[recall.campaign] = recall
    return list(found.values())


def complaints(vehicle: Vehicle, fetch: Fetch = http_get) -> list[Complaint]:
    rows = results(f"/complaints/complaintsByVehicle?{vehicle.query()}", fetch)
    return [c for c in (to_complaint(row, vehicle) for row in rows) if c.odi_number]


# ---------- NHTSA's vehicle lists ----------

def _listed(path: Callable[[str], str], key: str, fetch: Fetch) -> list[str]:
    """Values from both lists (vehicles with complaints, "c", and with recalls, "r"), without repeats."""
    seen: dict[str, None] = {}
    for issue_type in ("c", "r"):
        for row in results(path(issue_type), fetch):
            value = _text(row.get(key))
            if value:
                seen.setdefault(value, None)
    return list(seen)


def listed_models(year: str, make: str, fetch: Fetch = http_get) -> list[str]:
    """Model names on NHTSA's vehicle-list API for a model year and make (it misses some; see vehicles.py)."""
    return _listed(lambda t: f"/products/vehicle/models?{query(modelYear=year, make=make, issueType=t)}", "model", fetch)
