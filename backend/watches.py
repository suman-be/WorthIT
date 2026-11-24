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
from config import HORIZON_WEEKS, SERIAL_REGISTRY_PATH, WATCHES_PATH
from prediction_service import build_future_predictions
from predict import estimate_price, long_run_drift, target_iso_week

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


FORECAST_WEEKS = {"8_weeks": 8, "3_months": 13, "6_months": 26, "12_months": 52}
# A forecast starts from the last saved price. If that is older than this, it would describe the past.
FORECAST_MAX_STALENESS_DAYS = 120


def build_forecast(history, factor, now):
    """Read-only forecast from saved history, using the same model as /predict. None when it cannot say anything.

    Unlike /predict this makes no network calls and writes nothing, so it is safe to run on every page view.
    """
    frame = history[["week_start", "price"]].dropna().sort_values("week_start").drop_duplicates("week_start", keep="last")
    if len(frame) < 2:
        return None
    last_date = frame["week_start"].iloc[-1]
    if (now - last_date.to_pydatetime().replace(tzinfo=timezone.utc)).days > FORECAST_MAX_STALENESS_DAYS:
        return None
    base = float(frame["price"].iloc[-1])
    target_date = (last_date + pd.Timedelta(weeks=HORIZON_WEEKS)).date()
    predicted, low, high, multiplier, learned = estimate_price(frame, base, target_date=target_date)
    annual_drift = long_run_drift(frame)
    if not learned and not annual_drift:
        return None
    future = build_future_predictions(
        base,
        predicted,
        low,
        high,
        multiplier,
        learned,
        annual_drift=annual_drift,
        target_week=target_iso_week(target_date),
    )
    points = [
        {
            "date": (last_date + pd.Timedelta(weeks=FORECAST_WEEKS[entry["period"]])).strftime("%Y-%m-%d"),
            "price": round(entry["estimatedValue"] * factor, 2),
            "low": round(entry["minimumValue"] * factor, 2),
            "high": round(entry["maximumValue"] * factor, 2),
        }
        for entry in future["predictions"]
    ]
    return {"explanation": future["explanation"], "points": points}


LIST_OUTLOOK_WEEKS = {"12_months": 52, "24_months": 104}
LIST_OUTLOOK_MIN_SPAN_DAYS = 730
LIST_OUTLOOK_MAX_STALENESS_DAYS = 366
LIST_OUTLOOK_MAX_GROWTH = 0.20


def build_list_outlook(history, factor, now):
    """Where a brand's list price ends up if it keeps rising at its average pace. None when it cannot say.

    List prices move in announced steps, so this is not a resale forecast. The low end is "no rise"
    (brands rarely cut list prices), the estimate keeps the average yearly rise, and the high end
    doubles it. Needs two prices at least two years apart and a last price no older than a year.
    """
    frame = history[["week_start", "price"]].dropna().sort_values("week_start")
    if len(frame) < 2:
        return None
    first_date, last_date = frame["week_start"].iloc[0], frame["week_start"].iloc[-1]
    span_days = (last_date - first_date).days
    if span_days < LIST_OUTLOOK_MIN_SPAN_DAYS:
        return None
    if (now - last_date.to_pydatetime().replace(tzinfo=timezone.utc)).days > LIST_OUTLOOK_MAX_STALENESS_DAYS:
        return None
    first, last = float(frame["price"].iloc[0]), float(frame["price"].iloc[-1])
    growth = (last / first) ** (365.25 / span_days) - 1
    if growth <= 0:
        return None
    growth = min(growth, LIST_OUTLOOK_MAX_GROWTH)
    points = []
    for weeks in LIST_OUTLOOK_WEEKS.values():
        years = weeks / 52
        points.append(
            {
                "date": (last_date + pd.Timedelta(weeks=weeks)).strftime("%Y-%m-%d"),
                "price": round(last * (1 + growth) ** years * factor, 2),
                "low": round(last * factor, 2),
                "high": round(last * (1 + 2 * growth) ** years * factor, 2),
            }
        )
    return {
        "explanation": (
            f"This is a list price outlook, not a resale forecast. It assumes the brand keeps raising its list "
            f"price by about {growth * 100:.1f}% a year, as it did between {first_date.year} and {last_date.year}. "
            "The low end is no rise and the high end is twice that pace. Brands change list prices in steps, "
            "so the real path will be uneven."
        ),
        "points": points,
    }


def get_price_history(watch_id, now=None):
    """Saved market price history for a watch, one point per month (the last saved week of each month).

    Saved histories are in USD. They are converted to EUR when USD_TO_EUR is set, otherwise
    returned as USD so the frontend can label the currency honestly. No saved history gives an
    empty list and no forecast: nothing is invented.
    """
    watch = load_catalog().get(watch_id)
    if watch is None:
        raise WatchLookupError(404, "We could not find this watch.")
    rate = usd_to_eur_rate()
    history_file = market_data.history_path(watch["reference"])
    origin = market_data.load_history_source(watch["reference"])
    result = {
        "watchId": watch_id,
        "currency": "EUR" if rate else "USD",
        "source": origin["kind"],
        "sourceName": origin["provider"] or None,
        "sourceUrl": origin["url"] or None,
        "points": [],
        "forecast": None,
    }
    if not history_file.exists():
        return result
    history = pd.read_csv(history_file, parse_dates=["week_start"])
    history = history[history["price"] > 0].sort_values("week_start")
    monthly = history.groupby(history["week_start"].dt.to_period("M")).last()
    factor = rate or 1.0
    result["points"] = [
        {"date": row["week_start"].strftime("%Y-%m-%d"), "price": round(float(row["price"]) * factor, 2)}
        for _, row in monthly.iterrows()
    ]
    now = now or datetime.now(timezone.utc)
    # List prices move in announced steps, not with the resale market, so the resale model is not used on them.
    builder = build_forecast if origin["kind"] == "market" else build_list_outlook
    result["forecast"] = builder(history, factor, now)
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
