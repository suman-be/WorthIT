import copy
import functools
import json
import os
import threading
import time
from pathlib import Path

import pandas as pd
import requests

from config import MODEL_HISTORY_DIR

PTW_URL = "https://pricethat.watch/api/v1/valuation"
NUVINTY_URL = "https://nuvinty.com/api/v1/prices"
KELLO_URL = "https://kellowatch.com/api/v1"
ROOT = Path(__file__).parent
TIMEOUT_SECONDS = 20
USER_AGENT = "Mozilla/5.0"
HISTORY_COLUMNS = [
    "week_start",
    "sku",
    "price",
    "competitor_price",
    "promo_flag",
    "stock_units",
    "units_sold",
]


CACHE_TTL_SECONDS = int(os.environ.get("MARKET_DATA_CACHE_TTL", "3600"))
_CACHE = {}
_CACHE_LOCK = threading.Lock()


def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()


def cached(func):
    """Cache successful results per arguments for CACHE_TTL_SECONDS (failures are not cached).

    External sources are slow and rate limited, and a valuation is valid for an
    hour anyway (see expiresAt in the API response).
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        key = (func.__name__, args, tuple(sorted(kwargs.items())))
        now = time.monotonic()
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit and now - hit[0] < CACHE_TTL_SECONDS:
                return copy.deepcopy(hit[1])
        result = func(*args, **kwargs)
        with _CACHE_LOCK:
            _CACHE[key] = (now, result)
        return copy.deepcopy(result)

    return wrapper


def api_key():
    return os.environ.get("PRICETHATWATCH_API_KEY", "").strip()


@cached
def fetch_valuation(brand, reference, key=None, detailed=False):
    headers = {"User-Agent": USER_AGENT}
    key = key or api_key()
    if key:
        headers["X-Api-Key"] = key
    params = {"brand": brand, "reference": reference}
    if detailed:
        params["detailed"] = "true"
    response = requests.get(
        PTW_URL,
        params=params,
        headers=headers,
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    summary = payload.get("market_summary") or {}
    price = summary.get("average_price")
    if price is None:
        raise RuntimeError("no valuation returned by Price That Watch")
    return {
        "brand": brand,
        "reference": reference,
        "average_price": float(price),
        "floor_price": summary.get("floor_price"),
        "ceiling_price": summary.get("ceiling_price"),
        "sample_size": summary.get("sample_size"),
        "source": "Price That Watch",
        "listings": payload.get("listings") or [],
    }


def kello_key():
    return os.environ.get("KELLO_API_KEY", "").strip()


def kello_get(path, key, params=None):
    if not key:
        raise ValueError("KELLO_API_KEY is not set")
    response = requests.get(
        f"{KELLO_URL}{path}",
        params=params,
        headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {key}"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def first_value(mapping, keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def number_value(value):
    if isinstance(value, dict):
        for key in ("amount", "usd", "value", "price"):
            if key in value:
                return number_value(value[key])
        return None
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def extract_price_rows(payload):
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        for key in (
            "price_history",
            "priceHistory",
            "prices",
            "priceHistories",
            "market_prices",
            "marketPrices",
            "history",
        ):
            if key in data:
                data = data[key]
                break
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        date = first_value(
            item,
            ("date", "recorded_at", "recordedAt", "observed_at", "observedAt", "as_of", "asOf", "week_start", "weekStart"),
        )
        raw_price = first_value(
            item,
            (
                "averageMarketPrice",
                "average_market_price",
                "priceUsd",
                "price_usd",
                "marketPriceUsd",
                "market_price_usd",
                "currentMarketPrice",
                "current_market_price",
                "price",
                "value",
            ),
        )
        price = number_value(raw_price)
        if date is not None and price is not None:
            rows.append((date, price))
    return rows


def find_kello_watch(brand, reference, key):
    queries = (
        {"reference_number": reference, "per_page": 10},
        {"search": reference, "per_page": 10},
        {"search": f"{brand} {reference}", "per_page": 10},
    )
    last_error = None
    for params in queries:
        try:
            payload = kello_get("/watches", key, params)
        except Exception as exc:
            last_error = exc
            continue
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ref = first_value(entry, ("reference_number", "referenceNumber", "reference", "ref"))
            if ref and str(ref).strip().upper() == str(reference).strip().upper():
                return entry
    if last_error is not None:
        raise RuntimeError(str(last_error))
    raise RuntimeError(f"Kello has no watch for {brand} {reference}")


def current_kello_price(watch, detail=None):
    for payload in (detail, watch):
        data = payload.get("data", payload) if isinstance(payload, dict) else None
        if isinstance(data, dict):
            price = number_value(
                first_value(
                    data,
                    ("currentMarketPrice", "current_market_price", "averageMarketPrice", "average_market_price", "priceUsd", "price_usd"),
                )
            )
            if price is not None:
                return price
    return None


@cached
def fetch_kello_history(brand, reference, key=None):
    key = key or kello_key()
    watch = find_kello_watch(brand, reference, key)
    slug = first_value(watch, ("slug", "id"))
    if not slug:
        raise RuntimeError("Kello watch has no slug")
    name = first_value(watch, ("name", "title")) or f"{brand} {reference}"
    detail = None
    rows = []
    price_source = "Kello watch detail"
    try:
        detail = kello_get(f"/watches/{slug}", key)
        rows = extract_price_rows(detail)
    except Exception:
        pass
    if not rows:
        for params in ({"watch_slug": slug}, {"slug": slug}, {"reference_number": reference}):
            try:
                payload = kello_get("/market-data/prices", key, params)
            except Exception:
                continue
            rows = extract_price_rows(payload)
            if rows:
                price_source = "Kello price history"
                break
    if not rows:
        raise RuntimeError("Kello returned no dated prices")
    frame = to_weekly_history(rows, reference)
    if frame.empty:
        raise RuntimeError("Kello returned no usable dated prices")
    return {
        "query": f"{brand} {reference}",
        "item": name,
        "url": f"https://kellowatch.com/watches/{slug}",
        "currencies": ["USD"],
        "history": frame,
        "current_price": current_kello_price(watch, detail),
        "price_source": price_source,
        "provider": "Kello",
    }


def to_weekly_history(rows, sku):
    frame = pd.DataFrame(rows, columns=["date", "price"])
    if frame.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna(subset=["date", "price"])
    frame = frame[frame["price"] > 0].sort_values("date")
    if frame.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    weekly = frame.set_index("date")["price"].resample("W-SUN").last().dropna().reset_index()
    weekly = weekly.rename(columns={"date": "week_start"})
    weekly["sku"] = str(sku)
    weekly["competitor_price"] = weekly["price"]
    weekly["promo_flag"] = 0
    weekly["stock_units"] = 0
    weekly["units_sold"] = 0
    return weekly[HISTORY_COLUMNS]


@cached
def fetch_watch_history(brand, reference, model=None, currency="USD"):
    query = " ".join(
        part.strip() for part in (brand, model) if part and str(part).strip()
    )
    if not query:
        query = str(reference)
    response = requests.get(
        NUVINTY_URL,
        params={"type": "history", "q": query},
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or {}
    rows = []
    currencies = set()
    for point in data.get("points") or []:
        point_currency = str(point.get("currency") or "").upper()
        if point_currency:
            currencies.add(point_currency)
        if point_currency != currency.upper():
            continue
        date = point.get("date")
        price = point.get("price")
        if date is not None and price is not None:
            rows.append((date, price))
    return {
        "query": query,
        "item": data.get("item", ""),
        "url": data.get("url", ""),
        "currencies": sorted(currencies),
        "history": to_weekly_history(rows, reference),
    }


def safe_name(value):
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in str(value))


def history_path(reference):
    return ROOT / MODEL_HISTORY_DIR / f"{safe_name(reference)}.csv"


def valuation_path(reference):
    return ROOT / MODEL_HISTORY_DIR / f"{safe_name(reference)}.valuation.json"


def save_history(reference, frame):
    path = history_path(reference)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def save_valuation(reference, valuation):
    path = valuation_path(reference)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(valuation, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_saved_history(reference):
    path = history_path(reference)
    if not path.exists():
        return None, None
    return pd.read_csv(path, parse_dates=["week_start"]), path
