"""Identify watches that are not in the curated catalogue, using Kello.

A free web search cannot do this reliably (it returns unrelated pages), so this uses
the Kello watch database (KELLO_API_KEY), which the market-data code already talks to:

  1. GET /watches?reference_number=... (then ?search=...) to find the watch.
  2. GET /watches/{slug} for details: brand, model, case, movement, prices.
  3. Prices are in USD and converted to euros with USD_TO_EUR.

Kello's response fields are not publicly documented, so fields are read by name from
anywhere in the (possibly nested) response. Run `python kello_probe.py <reference>` with
your key to see the real field names and tighten FIELD_NAMES if needed.

Resolved watches are saved to data/discovered_watches.json, so GET /watches/{id},
the detail page and "My watches" keep working without another lookup. Fields no
source provides are estimates and are listed in `source.estimated_fields`.
"""
import json
import os
import re
import threading
from pathlib import Path

import requests

import market_data
from config import DISCOVERED_WATCHES_PATH

ROOT = Path(__file__).parent
_SAVE_LOCK = threading.Lock()

# Typical service interval (years) and full-service cost (EUR) per brand. Estimates.
BRAND_SERVICE = {
    "rolex": (10, 1000),
    "tudor": (10, 520),
    "omega": (8, 700),
    "patek philippe": (5, 1500),
    "audemars piguet": (5, 1500),
    "vacheron constantin": (5, 1400),
    "a. lange & söhne": (5, 1500),
    "cartier": (6, 650),
    "grand seiko": (4, 600),
    "iwc": (7, 750),
    "jaeger-lecoultre": (7, 800),
    "breitling": (7, 650),
    "panerai": (6, 700),
    "tag heuer": (5, 450),
    "longines": (5, 350),
    "tissot": (5, 250),
    "seiko": (5, 250),
}
MOVEMENT_SERVICE = {"quartz": (5, 120), "spring-drive": (4, 600)}
DEFAULT_SERVICE = (5, 450)
DEFAULT_RETENTION_PCT = 80.0


class ResolutionUnavailable(Exception):
    """The watch could not be resolved; the message says why (shown in logs and data quality)."""


def usd_to_eur_rate():
    try:
        rate = float(os.environ.get("USD_TO_EUR", "").strip())
    except ValueError:
        return None
    return rate if rate > 0 else None


def is_configured():
    return bool(market_data.kello_key())


def alnum(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


# Candidate field names per value, in order of preference (snake_case, after flattening).
FIELD_NAMES = {
    "reference": ("reference_number", "reference", "ref", "refnr", "model_number"),
    "brand": ("brand_name", "brand", "make", "manufacturer", "brand_title"),
    "model": ("model_name", "model", "collection", "family", "line"),
    "name": ("name", "title", "display_name"),
    "case_mm": (
        "case_diameter_mm", "case_diameter", "case_size_mm", "case_size", "diameter_mm", "diameter",
        "specs_case_diameter", "specs_case_size", "specifications_case_diameter", "specifications_case_size",
        "case",  # Kello shows e.g. "43 mm Titanium" as one field
    ),
    "material": (
        "case_material", "case_materials", "case_materials_material", "material", "materials",
        "specs_case_material", "specifications_case_material", "metal",
        "case",
    ),
    "movement": (
        "movement_type", "movement", "caliber_type", "calibre_type", "specs_movement", "specifications_movement",
        "winding", "mechanism", "caliber", "calibre", "movement_name", "caliber_name",
    ),
    "water": (
        "water_resistance_m", "water_resistance", "case_water_resistance", "specs_water_resistance",
        "specifications_water_resistance", "waterproof", "depth_rating",
    ),
    "retail": (
        "retail_price_eur", "retail_price_usd", "retail_price_amount", "retail_price_value", "retail_price",
        "price_retail", "retail", "msrp", "list_price", "rrp",
    ),
    "retail_currency": ("retail_price_currency", "retail_currency", "price_currency", "currency"),
}


def snake(key):
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", str(key)).lower()


def flatten(value, prefix="", out=None):
    """{'case': {'diameterMm': 40}, 'brand': {'name': 'Rolex'}} -> {'case_diameter_mm': 40, 'brand_name': 'Rolex', 'brand': 'Rolex'}."""
    out = {} if out is None else out
    if isinstance(value, dict):
        for key, item in value.items():
            name = snake(key)
            full = f"{prefix}_{name}" if prefix else name
            if isinstance(item, (dict, list)):
                flatten(item, full, out)
                if isinstance(item, dict) and "name" in item and not isinstance(item["name"], (dict, list)):
                    out.setdefault(full, item["name"])  # {'brand': {'name': 'Rolex'}} -> brand
            else:
                out.setdefault(full, item)
    elif isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, (dict, list)):
            flatten(first, prefix, out)
        elif prefix:
            out.setdefault(prefix, ", ".join(str(item) for item in value))
    return out


def pick(fields, what):
    for name in FIELD_NAMES[what]:
        value = fields.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


def _entries(payload):
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        for key in ("watches", "results", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return data if isinstance(data, list) else []


def best_match(entries, typed):
    """Exact reference first, then a variant of it (126505 -> 126505-0001), never a looser match."""
    key = alnum(typed)
    refs = [(entry, str(pick(flatten(entry), "reference") or "")) for entry in entries if isinstance(entry, dict)]
    exact = [entry for entry, ref in refs if ref and alnum(ref) == key]
    if exact:
        return exact[0]
    variants = [
        entry for entry, ref in refs
        if ref and (alnum(ref.split("-")[0]) == key or alnum(ref).lstrip("M") == key)
    ]
    return variants[0] if variants else None


def parse_number(text):
    match = re.search(r"\d+(?:[.,]\d+)?", str(text or ""))
    return float(match.group(0).replace(",", ".")) if match else None


def parse_water_resistance(text):
    value = parse_number(text)
    if value is None:
        return None
    lowered = str(text).lower()
    if "bar" in lowered or "atm" in lowered:
        return value * 10
    if "ft" in lowered or "feet" in lowered:
        return round(value * 0.3048)
    return value


def parse_material(text):
    lowered = str(text or "").lower()
    for keyword, material in (
        ("platinum", "platinum"),
        ("ceramic", "ceramic"),
        ("titanium", "titanium"),
        ("bronze", "bronze"),
        ("gold", "gold"),
        ("everose", "gold"),
        ("sedna", "gold"),
        ("steel", "stainless-steel"),
    ):
        if keyword in lowered:
            return material
    return None


def parse_money(value, currency=None):
    """(amount, currency) from 22799, "€22.799", "$59,100", "EUR 22 799,00" or {"amount": ..., "currency": ...}."""
    if isinstance(value, dict):
        amount, _ = parse_money(value.get("amount", value.get("value")), currency)
        return amount, str(value.get("currency") or currency or "").upper() or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (float(value) if value > 0 else None), (str(currency).upper() if currency else None)
    text = str(value or "").strip()
    if not text:
        return None, None
    upper = text.upper()
    if "€" in text or "EUR" in upper:
        currency = "EUR"
    elif "$" in text or "USD" in upper:
        currency = "USD"
    elif "£" in text or "GBP" in upper:
        currency = "GBP"
    digits = re.sub(r"[^0-9.,]", "", text)
    if not digits:
        return None, None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d{1,2})?", digits):  # 22.799 or 22.799,00 (European)
        digits = digits.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+(,\d{1,2})", digits):  # 22799,50
        digits = digits.replace(",", ".")
    else:  # 22,799.00 or 22799
        digits = digits.replace(",", "")
    try:
        amount = float(digits)
    except ValueError:
        return None, None
    return (amount if amount > 0 else None), (str(currency).upper() if currency else None)


def to_eur(amount, currency, rate):
    """EUR stays EUR; USD (or unknown, which Kello prices default to) needs USD_TO_EUR."""
    if amount is None:
        return None
    if currency == "EUR":
        return amount
    if currency in (None, "USD") and rate:
        return amount * rate
    return None


def parse_movement(text):
    lowered = str(text or "").lower()
    if "spring" in lowered:
        return "spring-drive"
    if "quartz" in lowered:
        return "quartz"
    if "manual" in lowered or "hand" in lowered:
        return "manual"
    if "auto" in lowered or "self" in lowered:
        return "automatic"
    return None


def fetch_kello(typed):
    """Search Kello for the reference and return (summary, detail). Never returns a looser match."""
    key = market_data.kello_key()
    if not key:
        raise ResolutionUnavailable("KELLO_API_KEY is not set")
    match = None
    # The frontend strips separators ("5711/1A-010" arrives as "57111A010"), so also try a
    # broader search on the leading characters and compare references without separators.
    compact = alnum(typed)
    leading_digits = re.match(r"\d{3,}", compact)
    broad = [compact[:4]] + ([leading_digits.group(0)] if leading_digits else [])
    queries = [{"reference_number": typed, "per_page": 20}, {"search": typed, "per_page": 20}]
    queries += [{"search": term, "per_page": 50} for term in dict.fromkeys(broad) if term != typed]
    for params in queries:
        try:
            payload = market_data.kello_get("/watches", key, params)
        except Exception:
            continue
        match = best_match(_entries(payload), typed)
        if match is not None:
            break
    if match is None:
        raise ResolutionUnavailable(f"Kello has no watch with reference {typed}")
    detail = {}
    slug_value = match.get("slug") or match.get("id")
    if slug_value:
        try:
            entries = _entries(market_data.kello_get(f"/watches/{slug_value}", key))
            detail = entries[0] if entries and isinstance(entries[0], dict) else {}
        except Exception:
            detail = {}
    return match, detail


def resolve_reference(typed):
    """Build a frontend Watch for a reference that is not in the catalogue, or raise ResolutionUnavailable."""
    summary, detail = fetch_kello(typed)
    fields = {**flatten(summary), **flatten(detail)}  # detail wins
    brand = str(pick(fields, "brand") or "").strip()
    name = str(pick(fields, "name") or "").strip()
    reference = str(pick(fields, "reference") or typed).strip()
    if not brand:
        raise ResolutionUnavailable("Kello record has no brand")
    model = str(pick(fields, "model") or "").strip()
    if model and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", model):
        model = model.replace("-", " ").title()  # Kello collection names are slugs: "big-bang" -> "Big Bang"
    if not model:
        # "Rolex Cosmograph Daytona 126505" -> "Cosmograph Daytona"
        model = re.sub(re.escape(brand), "", name, flags=re.IGNORECASE)
        model = re.sub(re.escape(reference), "", model, flags=re.IGNORECASE)
        model = re.sub(r"\s+", " ", model).strip(" -|,") or reference
    estimated = []

    def or_default(value, default, field):
        if value is None:
            estimated.append(field)
            return default
        return value

    # Kello's API has no spec fields (only brand, collection and name), so the name is the fallback:
    # "Big Bang Original Soft Touch All Red 43 mm" -> 43 mm.
    name_mm = re.search(r"(\d{2}(?:[.,]\d)?)\s*mm\b", name, flags=re.IGNORECASE)
    movement = or_default(
        parse_movement(pick(fields, "movement")) or parse_movement(name), "automatic", "specs.movement"
    )
    case_mm = or_default(
        parse_number(pick(fields, "case_mm")) or (parse_number(name_mm.group(1)) if name_mm else None),
        40.0,
        "specs.case_mm",
    )
    material = or_default(
        parse_material(pick(fields, "material")) or parse_material(name), "stainless-steel", "specs.material"
    )
    water = or_default(parse_water_resistance(pick(fields, "water")), 50.0, "specs.water_resistance_m")

    rate = usd_to_eur_rate()
    market_usd = market_data.current_kello_price(summary, detail)  # Kello market prices are in USD
    market_source = "Kello"
    if market_usd is None:
        # Kello's watch endpoints carry no prices; ask Price That Watch, which the app already uses.
        try:
            market_usd = float(market_data.fetch_valuation(brand, reference)["average_price"])
            market_source = "Price That Watch"
        except Exception:
            market_usd = None
    market_eur = to_eur(market_usd, "USD", rate)
    retail_amount, retail_currency = parse_money(pick(fields, "retail"), pick(fields, "retail_currency"))
    retail_eur = to_eur(retail_amount, retail_currency, rate)
    if retail_eur:
        price_eur = round(retail_eur)
        price_source = "Kello list price" + ("" if retail_currency == "EUR" else " (USD, converted)")
        if market_eur:
            retention = round(market_eur / retail_eur * 100.0, 1)
        else:
            # No second-hand price (e.g. no active listings): retention is an estimate.
            retention = or_default(None, DEFAULT_RETENTION_PCT, "market.resale_retention_pct")
    elif market_eur:
        price_eur = round(market_eur)
        price_source = f"{market_source} market price (USD, converted)"
        retention = or_default(None, DEFAULT_RETENTION_PCT, "market.resale_retention_pct")
    else:
        missing_rate = rate is None and (market_usd or (retail_amount and retail_currency != "EUR"))
        reason = "USD_TO_EUR is not set" if missing_rate else "neither Kello nor Price That Watch has a price"
        raise ResolutionUnavailable(f"no euro price for {brand} {reference}: {reason}")

    interval, cost = BRAND_SERVICE.get(brand.lower(), MOVEMENT_SERVICE.get(movement, DEFAULT_SERVICE))
    estimated += ["market.popularity_trend", "ownership"]
    return {
        "id": slug(f"{brand}-{model}-{reference}"),
        "brand": brand,
        "model": model,
        "reference": reference,
        "specs": {"movement": movement, "case_mm": case_mm, "material": material, "water_resistance_m": water},
        "market": {"price": price_eur, "resale_retention_pct": retention, "popularity_trend": 0.0},
        "ownership": {"service_interval_years": interval, "service_cost": cost},
        "source": {"specs": "Kello", "price": price_source, "estimated_fields": estimated},
    }


def discovered_path():
    return ROOT / DISCOVERED_WATCHES_PATH


def load_discovered():
    path = discovered_path()
    if not path.exists():
        return {}
    try:
        return {watch["id"]: watch for watch in json.loads(path.read_text(encoding="utf-8"))}
    except (ValueError, KeyError, TypeError):
        return {}


def save_discovered(watch):
    with _SAVE_LOCK:
        known = load_discovered()
        known[watch["id"]] = watch
        path = discovered_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(list(known.values()), indent=2) + "\n", encoding="utf-8")
