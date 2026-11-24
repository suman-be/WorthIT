"""Watch catalogue and serial lookups in the shape the WorthIT frontend expects.

Contract (see frontend/src/types/watch.ts and frontend/src/api/schema.ts):
  Watch            {id, brand, model, reference, specs{...}, market{...}, ownership{...}}  (euros)
  SerialLookup     {watch: Watch, check: SerialCheckResult}

The serial check describes one physical watch and is returned separately from
the model data: it must never change the Watch used for the Worth Score.
"""
import copy
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import logging

import market_data
import watch_resolver
from config import SERIAL_REGISTRY_PATH, WATCHES_PATH
from predict import long_run_drift

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
SERIAL_PATTERN = re.compile(r"^[A-Z0-9]{4,20}$")
AUTHENTICITY = {"consistent", "inconsistent", "unverified"}
STOLEN = {"clear", "reported", "unavailable"}


class WatchLookupError(Exception):
    """Raised for user-facing lookup failures; carries an HTTP status and optional field."""

    def __init__(self, status, message, field=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.field = field


def normalise_serial(raw):
    """Same rule as the frontend: drop spaces and dashes, upper-case."""
    return re.sub(r"[\s-]+", "", str(raw or "")).upper()


def load_catalog():
    """Curated catalogue plus watches resolved earlier from a watch database (curated wins)."""
    path = ROOT / WATCHES_PATH
    curated = {watch["id"]: watch for watch in json.loads(path.read_text(encoding="utf-8"))}
    return {**watch_resolver.load_discovered(), **curated}


def usd_to_eur_rate():
    """Optional FX rate for converting USD market data. Unset means: don't convert."""
    raw = os.environ.get("USD_TO_EUR", "").strip()
    try:
        rate = float(raw)
    except ValueError:
        return None
    return rate if rate > 0 else None


def enrich_market(watch):
    """Override catalogue market estimates with data saved by fetch_history.py, when present.

    - popularity_trend <- long-run annual price drift of the saved history (ratio, so currency-free)
    - resale_retention_pct <- saved USD valuation converted to EUR / list price (only with USD_TO_EUR set)
    """
    enriched = copy.deepcopy(watch)
    market = enriched["market"]
    reference = watch["reference"]
    history_file = market_data.history_path(reference)
    if history_file.exists():
        history = pd.read_csv(history_file, parse_dates=["week_start"])
        drift = long_run_drift(history)
        if drift:
            market["popularity_trend"] = round(drift, 3)
    valuation_file = market_data.valuation_path(reference)
    rate = usd_to_eur_rate()
    if valuation_file.exists() and rate and market.get("price"):
        try:
            valuation = json.loads(valuation_file.read_text(encoding="utf-8"))
            used_eur = float(valuation["average_price"]) * rate
            market["resale_retention_pct"] = round(used_eur / float(market["price"]) * 100.0, 1)
        except (KeyError, TypeError, ValueError):
            pass
    return enriched


def get_watch(watch_id):
    watch = load_catalog().get(watch_id)
    if watch is None:
        raise WatchLookupError(404, "We could not find this watch.")
    return enrich_market(watch)


def get_watches(ids=None):
    catalog = load_catalog()
    if ids is None:
        return [enrich_market(watch) for watch in catalog.values()]
    seen = set()
    result = []
    for watch_id in ids:
        if watch_id in catalog and watch_id not in seen:
            seen.add(watch_id)
            result.append(enrich_market(catalog[watch_id]))
    return result


def parse_service_history(raw):
    records = []
    for chunk in str(raw or "").split(";"):
        parts = [part.strip() for part in chunk.split("|")]
        if len(parts) == 3 and all(parts):
            records.append({"date": parts[0], "description": parts[1], "servicedBy": parts[2]})
    return records


def load_registry():
    path = ROOT / SERIAL_REGISTRY_PATH
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str).fillna("")
    return {normalise_serial(row["serial"]): row for row in frame.to_dict("records")}


def alnum(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def reference_keys(reference):
    """Forms a user may type for a reference: '310.30.42.50.01.001' -> '31030425001001',
    'M79030N-0001' -> 'M79030N0001', 'M79030N', '79030N'."""
    keys = {alnum(reference), alnum(str(reference).split("-")[0])}
    keys |= {key[1:] for key in list(keys) if re.match(r"^M\d", key)}
    return {key for key in keys if len(key) >= 4}


def find_by_reference(text, catalog):
    key = alnum(text)
    if len(key) < 4:
        return None
    for watch in catalog.values():
        if key in reference_keys(watch["reference"]):
            return watch
    return None


def resolve_unknown_reference(typed):
    """Look the reference up in the configured watch database and remember it. None if not possible."""
    if not watch_resolver.is_configured() or len(alnum(typed)) < 4:
        return None
    try:
        watch = watch_resolver.resolve_reference(typed)
    except watch_resolver.ResolutionUnavailable as exc:
        logger.info("could not resolve reference %s: %s", typed, exc)
        return None
    except Exception:
        logger.exception("watch database lookup failed for %s", typed)
        return None
    watch_resolver.save_discovered(watch)
    return watch


def reference_check(entered, watch, now):
    note = (
        f"Matched on reference number {watch['reference']}. This specific watch is not in our records, "
        "so its production year, authenticity and service history are unknown."
    )
    source = watch.get("source")
    if source:
        note += (
            f" Model data from {source['specs']}; price from {source['price']}. "
            "Retention, popularity and service figures are estimates."
        )
    return {
        "serial": entered,
        "found": False,
        "productionYear": None,
        "productionBatch": None,
        "authenticity": "unverified",
        "authenticityNote": note,
        "serviceHistory": [],
        "stolenCheck": "unavailable",
        "checkedAt": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def lookup_serial(raw_serial, now=None):
    """Identify a watch from a serial number, or from its reference number as a fallback.

    Real serials only resolve through the registry. When the input matches a catalogue
    reference instead, the model is returned with an honest "not in our records" check,
    so the Worth Score still works.
    """
    now = now or datetime.now(timezone.utc)
    serial = normalise_serial(raw_serial)
    if not serial:
        raise WatchLookupError(422, "Enter the serial number.", field="serial")
    catalog = load_catalog()
    if not SERIAL_PATTERN.match(serial):
        watch = find_by_reference(raw_serial, catalog) or resolve_unknown_reference(alnum(raw_serial))
        if watch is not None:
            return {"watch": enrich_market(watch), "check": reference_check(alnum(raw_serial), watch, now)}
        raise WatchLookupError(
            422,
            "Serial number must be 4 to 20 letters or numbers, with no symbols.",
            field="serial",
        )
    row = load_registry().get(serial)
    if row is None:
        watch = find_by_reference(serial, catalog) or resolve_unknown_reference(serial)
        if watch is not None:
            return {"watch": enrich_market(watch), "check": reference_check(serial, watch, now)}
        raise WatchLookupError(404, "No watch matches this serial or reference number.")
    watch = catalog.get(row["watch_id"])
    if watch is None:
        raise WatchLookupError(404, "No watch in our records matches this serial number.")
    authenticity = row.get("authenticity") if row.get("authenticity") in AUTHENTICITY else "unverified"
    stolen = row.get("stolen_status") if row.get("stolen_status") in STOLEN else "unavailable"
    demo = row.get("source", "") == "demo"
    if authenticity == "unverified":
        note = "Not verified against the manufacturer's records."
    elif authenticity == "consistent":
        note = "The serial number format and production date match this model."
    else:
        note = "The serial number does not match this model's known production records."
    if demo:
        note = f"Demo record. {note}"
    year = row.get("production_year", "")
    check = {
        "serial": serial,
        "found": True,
        "productionYear": int(year) if str(year).isdigit() else None,
        "productionBatch": row.get("production_batch") or None,
        "authenticity": authenticity,
        "authenticityNote": note,
        "serviceHistory": parse_service_history(row.get("service_history")),
        "stolenCheck": stolen,
        "checkedAt": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    # The model data is identical to GET /watches/{id}: the serial never alters it.
    return {"watch": enrich_market(watch), "check": check}
