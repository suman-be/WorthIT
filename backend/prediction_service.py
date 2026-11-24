import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import item_lookup
import market_data
from config import (
    CATALOG_PATH,
    HORIZON_WEEKS,
    ITEM_CATALOG_PATH,
    PREDICTIONS_PATH,
    SERIALS_PATH,
)
from predict import (
    estimate_price,
    load_catalog,
    load_history,
    load_serial_map,
    long_run_drift,
    save_prediction,
    target_iso_week,
)

ROOT = Path(__file__).parent
_PREDICTION_LOCK = threading.Lock()
WATCH_CATEGORIES = {"watch", "watches", "timepiece", "timepieces"}
GENERIC_CATEGORIES = {"other", "unknown", "general"}
CATEGORY_WEEKLY_DRIFT = {
    "electronics": -0.004,
    "phones": -0.004,
    "computers": -0.004,
    "cameras": -0.002,
    "sneakers": 0.0,
    "bags": 0.0,
    "jewelry": 0.0,
    "art": 0.001,
    "collectibles": 0.001,
    "coins": 0.001,
    "trading cards": 0.001,
}
DEFAULT_LOG_SPREAD = 0.05


def utc_now():
    return datetime.now(timezone.utc)


def iso_time(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def money(value):
    return round(float(value), 2)


def bounded(value, low, high):
    return float(np.clip(float(value), low, high))


def normalized_category(request):
    return str(request.get("category") or "").strip().lower()


def is_watch_category(category):
    return str(category or "").strip().lower() in WATCH_CATEGORIES


def is_watch_request(request):
    category = normalized_category(request)
    if category and category not in GENERIC_CATEGORIES:
        return is_watch_category(category)
    return bool(request.get("brand") and request.get("reference"))


def item_identifier(request):
    for key in ("identifier", "serial", "reference", "name", "brand"):
        value = request.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return "unknown"


def item_label(request):
    name = request.get("name")
    if name and str(name).strip():
        return str(name).strip()
    parts = [request.get("brand"), request.get("model"), request.get("variant") or request.get("reference")]
    label = " ".join(str(part).strip() for part in parts if part and str(part).strip())
    return label or item_identifier(request)


def normalize_comparables(entries, currency, title, default_score):
    items = []
    for entry in entries or []:
        price = market_data.number_value(
            market_data.first_value(
                entry,
                ("price", "averagePrice", "average_price", "priceUsd", "price_usd", "marketPrice", "market_price"),
            )
        )
        if price is None:
            continue
        sold_at = market_data.first_value(entry, ("soldAt", "sold_at", "listedAt", "listed_at", "date"))
        score = market_data.number_value(
            market_data.first_value(entry, ("similarityScore", "similarity_score"))
        )
        items.append(
            {
                "id": str(market_data.first_value(entry, ("id", "listingId", "listing_id")) or f"sale_{len(items) + 1}"),
                "title": str(
                    market_data.first_value(entry, ("title", "name", "description"))
                    or title
                ),
                "price": money(price),
                "currency": str(
                    market_data.first_value(entry, ("currency",)) or currency
                ).upper(),
                "condition": str(market_data.first_value(entry, ("condition", "grade")) or "unknown"),
                "soldAt": str(sold_at) if sold_at else None,
                "source": str(market_data.first_value(entry, ("source", "marketplace")) or "Marketplace"),
                "similarityScore": int(score) if score is not None else default_score,
                "url": str(market_data.first_value(entry, ("url", "link")) or ""),
            }
        )
    return items


def history_from_request(request):
    rows = []
    for point in request.get("priceHistory") or []:
        date = point.get("date")
        price = market_data.number_value(
            market_data.first_value(point, ("averageValue", "average_value", "price", "minimumValue", "maximumValue"))
        )
        if date is not None and price is not None:
            rows.append((date, price))
    return market_data.to_weekly_history(rows, item_identifier(request))


def comparables_from_request(request, currency, title):
    return normalize_comparables(request.get("comparableSales"), currency, title, 90)


def comparables_from_web(web_result, currency, title):
    return normalize_comparables((web_result or {}).get("items"), currency, title, 70)


def refresh_market_data(request, live=True):
    errors = []
    sources = []
    history = None
    history_source = "local"
    history_currency = None
    live_history = False
    valuation = None
    valuation_source = None
    kello_result = None
    provided_comparables = []
    web_result = None
    url = ""
    identifier = item_identifier(request)
    label = item_label(request)
    currency = (request.get("currency") or "USD").upper()
    brand = request.get("brand")
    reference = request.get("reference")
    model = request.get("model")
    watch = is_watch_request(request)

    if live and watch and brand and reference:
        executor = ThreadPoolExecutor(max_workers=1)
        valuation_future = executor.submit(market_data.fetch_valuation, brand, reference, detailed=True)
        executor.shutdown(wait=False)
        if market_data.kello_key():
            try:
                kello_result = market_data.fetch_kello_history(brand, reference)
                history = kello_result["history"]
                history_source = "Kello"
                history_currency = "USD"
                live_history = True
                sources.append("Kello")
                url = kello_result.get("url") or ""
            except Exception as exc:
                errors.append(f"Kello history unavailable: {exc}")
        else:
            errors.append("KELLO_API_KEY is not set; skipped Kello")
        if history is None:
            try:
                result = market_data.fetch_watch_history(
                    brand, reference, model=model or reference, currency=currency
                )
                if not result["history"].empty:
                    history = result["history"]
                    history_source = "Nuvinty"
                    history_currency = currency
                    live_history = True
                    sources.append("Nuvinty")
                    url = result.get("url") or ""
                else:
                    errors.append("Nuvinty returned no dated history")
            except Exception as exc:
                errors.append(f"Nuvinty history unavailable: {exc}")
        try:
            valuation = valuation_future.result()
            valuation_source = "Price That Watch"
            sources.insert(0, valuation_source)
        except Exception as exc:
            errors.insert(0, f"Price That Watch valuation unavailable: {exc}")
        if valuation is None and kello_result and kello_result.get("current_price"):
            valuation = {
                "average_price": kello_result["current_price"],
                "floor_price": None,
                "ceiling_price": None,
                "sample_size": None,
                "source": "Kello",
                "listings": [],
            }
            valuation_source = "Kello"
            sources.append("Kello valuation")
    else:
        if request.get("priceHistory"):
            history = history_from_request(request)
            if not history.empty:
                history_source = "request price history"
                history_currency = currency
                sources.append("request price history")
        provided_comparables = comparables_from_request(request, currency, label)
        if provided_comparables:
            sources.append("request comparables")
        elif live:
            web_result = item_lookup.lookup_comparables(label, limit=5)
            if web_result.get("error"):
                errors.append(f"web comparables unavailable: {web_result['error']}")
            web_comparables = comparables_from_web(web_result, currency, label)
            if web_comparables:
                sources.append("Web comparables")
                if history is None or history.empty:
                    rows = [
                        (item["soldAt"], item["price"])
                        for item in web_comparables
                        if item.get("soldAt")
                    ]
                    history = market_data.to_weekly_history(rows, identifier)
                    if not history.empty:
                        history_source = "web comparables"
                        history_currency = web_comparables[0]["currency"]
                        live_history = True

    if history is None or history.empty:
        # Only history saved for THIS item (by fetch_history.py) is a valid fallback.
        # The demo dataset (DATA_PATH) is synthetic and must never stand in for a real item.
        candidates = [identifier] + ([reference] if reference and reference != identifier else [])
        local_path = next(
            (
                path
                for path in (ROOT / market_data.MODEL_HISTORY_DIR / f"{market_data.safe_name(c)}.csv" for c in candidates)
                if path.exists()
            ),
            None,
        )
        if local_path is not None:
            history = load_history(local_path)
            history_source = local_path.name
            errors.append(f"live history unavailable; using saved history {history_source}")
        else:
            history = pd.DataFrame(columns=market_data.HISTORY_COLUMNS)
            errors.append("no price history available for this item; forecast is neutral or category-based")
    return {
        "history": history,
        "history_source": history_source,
        "history_currency": history_currency,
        "live_history": live_history,
        "valuation": valuation,
        "valuation_source": valuation_source,
        "sources": sources,
        "errors": errors,
        "provided_comparables": provided_comparables,
        "web_comparables": web_result,
        "url": url,
    }


def scope_history(history, sku):
    if history is None or history.empty:
        return pd.DataFrame(columns=market_data.HISTORY_COLUMNS)
    if "sku" in history.columns:
        scoped = history[history["sku"] == sku]
        if not scoped.empty:
            return scoped.reset_index(drop=True)
    return history.reset_index(drop=True)


def price_trend(history):
    if history is None or history.empty or "price" not in history:
        return 0.0
    prices = pd.to_numeric(history["price"], errors="coerce").dropna()
    if len(prices) < 2:
        return 0.0
    window = min(8, max(1, len(prices) // 2))
    recent = prices.tail(window).mean()
    prior = prices.iloc[:-window].tail(window).mean()
    if prior <= 0:
        return 0.0
    return float((recent / prior - 1.0) * 100.0)


def monthly_points(history):
    if history is None or history.empty or "week_start" not in history:
        return []
    frame = history[["week_start", "price"]].copy()
    frame["week_start"] = pd.to_datetime(frame["week_start"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna(subset=["week_start", "price"])
    if frame.empty:
        return []
    frame["month"] = frame["week_start"].dt.to_period("M").dt.to_timestamp()
    grouped = frame.groupby("month")["price"].agg(["mean", "min", "max"]).sort_index().tail(12)
    return [
        {
            "date": index.strftime("%Y-%m-%d"),
            "averageValue": money(row["mean"]),
            "minimumValue": money(row["min"]),
            "maximumValue": money(row["max"]),
        }
        for index, row in grouped.iterrows()
    ]


def estimate_item_price(history, current_price, category, target_date=None):
    if is_watch_category(category):
        return estimate_price(history, current_price, target_date=target_date)
    weekly = CATEGORY_WEEKLY_DRIFT.get(category, 0.0)
    learned = False
    if history is not None and not history.empty and {"week_start", "price"}.issubset(history.columns):
        frame = history[["week_start", "price"]].copy()
        frame["week_start"] = pd.to_datetime(frame["week_start"], errors="coerce")
        frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
        frame = frame.dropna().sort_values("week_start")
        frame = frame[frame["price"] > 0]
        if len(frame) >= 2:
            span = (frame["week_start"].iloc[-1] - frame["week_start"].iloc[0]).days / 7.0
            first = float(frame["price"].iloc[0])
            last = float(frame["price"].iloc[-1])
            if span >= 4 and first > 0 and last > 0:
                weekly = bounded((last / first) ** (1.0 / span) - 1.0, -0.02, 0.02)
                learned = True
    multiplier = bounded((1.0 + weekly) ** HORIZON_WEEKS, 0.5, 2.0)
    if learned:
        mean = float(frame["price"].mean())
        spread = float(frame["price"].std(ddof=0)) / mean if mean else 0.05
        spread = bounded(spread, 0.05, 0.30)
    else:
        spread = 0.05
    low = bounded(multiplier * (1.0 - spread), 0.25, multiplier)
    high = bounded(multiplier * (1.0 + spread), multiplier, 3.0)
    return (
        current_price * multiplier,
        current_price * low,
        current_price * high,
        multiplier,
        learned,
    )


def annual_drift_for(history, category):
    if is_watch_category(category):
        return long_run_drift(history)
    drift = long_run_drift(history)
    if drift:
        return drift
    weekly = CATEGORY_WEEKLY_DRIFT.get(category, 0.0)
    return float(np.expm1(weekly * 52.0)) if weekly else 0.0


def build_comparables(valuation, request, history, url, provided=None, web=None):
    currency = (valuation or {}).get("currency") or (request.get("currency") or "USD").upper()
    title = item_label(request)
    items = normalize_comparables(provided, currency, title, 90)
    source = "provided"
    listings = (valuation or {}).get("listings") or []
    if not items:
        items = normalize_comparables(listings, currency, title, 85)
        source = "live"
    if not items:
        items = comparables_from_web(web, currency, title)
        source = "web"
    if not items and history is not None and not history.empty:
        source = "derived"
        tail = history.tail(3)
        for _, row in tail.iloc[::-1].iterrows():
            items.append(
                {
                    "id": f"derived_{len(items) + 1}",
                    "title": title,
                    "price": money(row["price"]),
                    "currency": currency,
                    "condition": "unknown",
                    "soldAt": pd.to_datetime(row["week_start"]).date().isoformat(),
                    "source": "derived from price history",
                    "similarityScore": 80,
                    "url": url or "",
                }
            )
    if not items:
        source = "none"
    prices = [item["price"] for item in items if item["currency"] == currency.upper()]
    return {
        "total": len(items),
        "averagePrice": money(np.mean(prices)) if prices else None,
        "medianPrice": money(np.median(prices)) if prices else None,
        "items": items,
        "source": source,
    }


def build_market_analysis(history, valuation, trend, currency, now):
    prices = (
        pd.to_numeric(history["price"], errors="coerce").dropna()
        if history is not None and "price" in history
        else pd.Series(dtype=float)
    )
    competitor = (
        pd.to_numeric(history["competitor_price"], errors="coerce").dropna()
        if history is not None and "competitor_price" in history
        else prices
    )
    sample_size = (valuation or {}).get("sample_size")
    total_listings = int(sample_size) if sample_size else int(len(competitor))
    if trend > 5:
        demand = {"level": "high", "score": int(bounded(60 + trend, 0, 100)), "trend": "increasing"}
    elif trend < -5:
        demand = {"level": "low", "score": int(bounded(60 + trend, 0, 100)), "trend": "decreasing"}
    else:
        demand = {"level": "medium", "score": int(bounded(60 + trend, 0, 100)), "trend": "stable"}
    supply_level = "high" if total_listings > 100 else "medium" if total_listings > 30 else "low"
    direction = "increasing" if trend > 1 else "decreasing" if trend < -1 else "stable"
    return {
        "demand": demand,
        "supply": {
            "level": supply_level,
            "availableListings": total_listings or None,
            "trend": "stable",
        },
        "statistics": {
            "averageSellingPrice": money(prices.mean()) if not prices.empty else None,
            "medianSellingPrice": money(prices.median()) if not prices.empty else None,
            "lowestSellingPrice": money(prices.min()) if not prices.empty else None,
            "highestSellingPrice": money(prices.max()) if not prices.empty else None,
            "averageListingPrice": money(competitor.mean()) if not competitor.empty else None,
            "averageDaysToSell": None,
            "totalListings": total_listings or None,
            "totalCompletedSales": int(sample_size) if sample_size else None,
        },
        "marketTrend": {
            "direction": direction,
            "percentageChange": money(trend),
            "period": "last_8_weeks",
            "description": f"Prices have {direction} over the observed period.",
        },
        "currency": currency,
        "lastUpdated": iso_time(now),
    }


def build_price_factors(request, trend, now):
    condition = request.get("condition") or {}
    grade = str(condition.get("grade") or "unknown").lower()
    condition_score = {"excellent": 20, "like_new": 20, "good": 15, "fair": 0, "poor": -15}.get(grade, 0)
    demand_score = int(bounded(trend * 2, -20, 20))
    release_year = request.get("releaseYear")
    age_score = -min(20, max(0, now.year - int(release_year)) * 5) if release_year else 0
    competition_score = -5 if trend < 0 else 0
    return [
        {
            "factor": "Condition",
            "impact": "positive" if condition_score > 0 else "negative" if condition_score < 0 else "neutral",
            "impactScore": condition_score,
            "description": f"Condition grade '{grade}' adjusts resale value.",
        },
        {
            "factor": "Market demand",
            "impact": "positive" if demand_score > 0 else "negative" if demand_score < 0 else "neutral",
            "impactScore": demand_score,
            "description": f"Observed price trend is {trend:.1f}% over the recent window.",
        },
        {
            "factor": "Age",
            "impact": "negative" if age_score < 0 else "neutral",
            "impactScore": age_score,
            "description": "Older products lose value as newer models become available." if age_score else "Release year unavailable; age impact not estimated.",
        },
        {
            "factor": "Competition",
            "impact": "negative" if competition_score < 0 else "neutral",
            "impactScore": competition_score,
            "description": "Soft recent pricing suggests competitive pressure." if competition_score else "No strong competitive pressure detected.",
        },
    ]


def build_future_predictions(
    base_price,
    predicted,
    low,
    high,
    multiplier,
    learned,
    annual_drift=0.0,
    target_week=None,
    basis="seasonal",
):
    if base_price <= 0:
        base_price = 1.0
    predicted = predicted if predicted > 0 else base_price
    low = low if low > 0 else predicted
    high = high if high > 0 else predicted
    down = max(float(np.log(predicted / low)), DEFAULT_LOG_SPREAD) if learned else DEFAULT_LOG_SPREAD
    up = max(float(np.log(high / predicted)), DEFAULT_LOG_SPREAD) if learned else DEFAULT_LOG_SPREAD
    weekly_drift = float(np.log1p(annual_drift)) / 52.0
    periods = (
        ("8_weeks", HORIZON_WEEKS),
        ("3_months", 13),
        ("6_months", 26),
        ("12_months", 52),
    )
    predictions = []
    for period, weeks in periods:
        if weeks == HORIZON_WEEKS:
            estimate_multiplier = bounded(predicted / base_price, 0.25, 3.0)
            low_bound = bounded(low / base_price, 0.25, estimate_multiplier)
            high_bound = bounded(high / base_price, estimate_multiplier, 3.0)
        else:
            scale = np.sqrt(weeks / HORIZON_WEEKS)
            estimate_multiplier = bounded(np.exp(weekly_drift * weeks), 0.25, 3.0)
            low_bound = bounded(estimate_multiplier * np.exp(-down * scale), 0.25, estimate_multiplier)
            high_bound = bounded(estimate_multiplier * np.exp(up * scale), estimate_multiplier, 3.0)
        estimate = base_price * estimate_multiplier
        predictions.append(
            {
                "period": period,
                "estimatedValue": money(estimate),
                "minimumValue": money(base_price * low_bound),
                "maximumValue": money(base_price * high_bound),
                "changePercentage": money((estimate_multiplier - 1.0) * 100.0),
            }
        )
    season = f"around ISO week {target_week}" if target_week else "in Q4"
    if basis == "trend":
        short = (
            f"The {HORIZON_WEEKS}-week estimate extends the observed price trend "
            f"({multiplier:.3f} over {HORIZON_WEEKS} weeks)."
            if learned
            else f"No reliable history was available, so a category trend assumption ({multiplier:.3f}) was applied."
        )
    else:
        short = (
            f"The {HORIZON_WEEKS}-week estimate uses the median historical {HORIZON_WEEKS}-week price change "
            f"for windows ending {season} ({multiplier:.3f})."
            if learned
            else f"No {HORIZON_WEEKS}-week history was found for this time of year, so a neutral multiplier was applied."
        )
    long = (
        f" Longer horizons follow the long-run trend of {annual_drift * 100:+.1f}% per year "
        "with uncertainty widening over time; they are rough guides, not forecasts."
    )
    return {"predictions": predictions, "explanation": short + long}


def build_recommendation(request, valuation_value, predicted, trend, confidence, factors):
    condition = request.get("condition") or {}
    accessories = condition.get("accessories") or []
    tips = []
    if accessories:
        tips.append("Include original accessories.")
    tips.append("Take clear photos from multiple angles.")
    tips.append("Highlight the item's condition and included extras.")
    action = "sell" if trend < -2 or predicted < valuation_value * 0.98 else "hold"
    reason = (
        "Recent pricing is softening, so selling sooner may avoid further depreciation."
        if action == "sell"
        else "Current demand is stable enough that holding may capture more value."
    )
    if factors and factors[0]["impact"] == "positive":
        tips.append("Emphasize the positive condition factors in the listing.")
    return {
        "action": action,
        "confidenceScore": int(confidence),
        "suggestedListingPrice": money(valuation_value * 1.08),
        "expectedSellingPrice": money(valuation_value),
        "reason": reason,
        "tips": tips,
    }


def build_ai_insights(request, valuation_value, predicted, trend, comps, currency, basis="seasonal"):
    comp_prices = [item["price"] for item in comps.get("items") or [] if item.get("price") is not None]
    low = min(comp_prices) if comp_prices else None
    high = max(comp_prices) if comp_prices else None
    label = item_label(request)
    summary = (
        f"The {label} is estimated at "
        f"{currency} {valuation_value:,.2f}, with an {HORIZON_WEEKS}-week projection of {currency} {predicted:,.2f}."
    )
    basis_text = (
        "The 8-week projection follows the recent market trend."
        if basis == "trend"
        else "The 8-week projection is based on how prices historically moved at the same time of year."
    )
    key_insights = [
        f"Recent comparable prices span {currency} {low:,.2f} to {currency} {high:,.2f}." if low and high else "Limited comparable sales were available.",
        f"Observed price trend is {trend:.1f}% over the recent window.",
        basis_text,
    ]
    risks = [
        "Future valuations are estimates and cannot guarantee actual market prices.",
        "Actual selling prices depend on condition, accessories, and buyer demand.",
    ]
    return {"summary": summary, "keyInsights": key_insights, "risks": risks}


def build_data_quality(refresh, history, comps):
    errors = list(refresh["errors"])
    score = 45
    if refresh["valuation_source"]:
        score += 20
    if refresh["live_history"]:
        score += 20
    score += min(15, len(history) // 10)
    if comps["source"] in {"live", "provided", "web"}:
        score += 5
    score = int(bounded(score, 0, 100))
    level = "high" if score >= 80 else "medium" if score >= 60 else "low"
    sources_used = len({source for source in refresh["sources"] if source})
    sample_size = (refresh["valuation"] or {}).get("sample_size") or 0
    limitations = list(errors)
    limitations.append("Future valuations are estimates and cannot guarantee actual market prices.")
    if comps["source"] in {"derived", "web"}:
        limitations.append("Comparable sales were not verified transactions and may overstate resale value.")
    return {
        "overallScore": score,
        "level": level,
        "sourcesUsed": sources_used,
        "totalDataPoints": int(len(history) + len(comps["items"]) + int(sample_size)),
        "limitations": limitations,
    }


def build_item(request, entry, sku, currency, now):
    condition = request.get("condition") or {}
    purchase = request.get("purchase") or {}
    location = request.get("location") or {}
    identifier = item_identifier(request)
    brand = str(request.get("brand") or "")
    model = request.get("model") or (entry.get("model") if entry else "") or identifier
    variant = request.get("variant") or (entry.get("variant") if entry else "") or identifier
    name = request.get("name") or f"{brand} {model} {variant}".strip() or identifier
    description = (
        request.get("description")
        or (entry.get("description") if entry else "")
        or f"{name}"
    )
    category = request.get("category") or ("Watches" if is_watch_request(request) else "Other")
    specifications = [
        {"name": "Identifier", "value": identifier},
        {"name": "Category", "value": str(category)},
    ]
    for name_key, value in (
        ("Brand", brand),
        ("Model", model),
        ("Variant", variant),
        ("SKU", sku),
    ):
        if value:
            specifications.append({"name": name_key, "value": str(value)})
    if request.get("releaseYear"):
        specifications.append({"name": "Release year", "value": str(request["releaseYear"])})
    return {
        "name": name,
        "category": category,
        "subcategory": request.get("subcategory") or model,
        "brand": brand,
        "model": model,
        "variant": variant,
        "description": description,
        "releaseYear": request.get("releaseYear"),
        "identification": {
            "method": "text",
            "confidenceScore": 95 if entry else 85,
            "isVerified": False,
        },
        "specifications": specifications,
        "condition": {
            "grade": str(condition.get("grade") or "unknown"),
            "description": str(condition.get("description") or ""),
            "issues": list(condition.get("issues") or []),
            "accessories": list(condition.get("accessories") or []),
        },
        "purchase": {
            "purchaseDate": purchase.get("purchaseDate"),
            "originalPrice": money(purchase["originalPrice"]) if purchase.get("originalPrice") else None,
            "currency": purchase.get("currency") or currency,
        },
        "location": {
            "country": location.get("country"),
            "region": location.get("region"),
        },
        "images": list(request.get("images") or []),
    }


def build_prediction_payload(request, live=True):
    now = utc_now()
    created_at = now
    expires_at = now + timedelta(hours=1)
    refresh = refresh_market_data(request, live=live)
    history = refresh["history"]
    identifier = item_identifier(request)
    catalog_path = ROOT / ITEM_CATALOG_PATH
    if not catalog_path.exists():
        catalog_path = ROOT / CATALOG_PATH
    catalog = load_catalog(catalog_path)
    serial_map = load_serial_map(ROOT / SERIALS_PATH)
    entry = catalog.get(identifier)
    sku = serial_map.get(identifier)
    if not sku and entry:
        sku = entry.get("sku")
    sku = sku or identifier
    scoped = scope_history(history, sku)
    prices = pd.to_numeric(scoped["price"], errors="coerce").dropna() if "price" in scoped else pd.Series(dtype=float)
    valuation_data = refresh["valuation"]
    request_currency = (request.get("currency") or "USD").upper()
    currency = "USD" if valuation_data else request_currency
    history_currency = refresh.get("history_currency") or currency
    if history_currency != currency:
        refresh["errors"].append(
            f"price history is in {history_currency} but the valuation is in {currency}; "
            "absolute history prices were not used for the value range"
        )
        prices = pd.Series(dtype=float)
    base_price = valuation_data["average_price"] if valuation_data else float(request["price"])
    floor_price = valuation_data.get("floor_price") if valuation_data else None
    ceiling_price = valuation_data.get("ceiling_price") if valuation_data else None
    if floor_price is None:
        floor_price = prices.min() * 0.95 if not prices.empty else base_price * 0.9
    if ceiling_price is None:
        ceiling_price = prices.max() * 1.05 if not prices.empty else base_price * 1.1
    floor_price = min(float(floor_price), base_price)
    ceiling_price = max(float(ceiling_price), base_price)
    target_date = (now + timedelta(weeks=HORIZON_WEEKS)).date()
    target_week = target_iso_week(target_date)
    category = request.get("category") or ("Watches" if is_watch_request(request) else "Other")
    predicted, low, high, multiplier, learned = estimate_item_price(
        scoped, base_price, category, target_date=target_date
    )
    basis = "seasonal" if is_watch_category(category) else "trend"
    annual_drift = annual_drift_for(scoped, category)
    trend = price_trend(scoped)
    comps = build_comparables(
        valuation_data,
        request,
        scoped,
        refresh.get("url") or "",
        provided=refresh.get("provided_comparables"),
        web=refresh.get("web_comparables"),
    )
    data_quality = build_data_quality(refresh, scoped, comps)
    confidence_score = data_quality["overallScore"]
    confidence_level = data_quality["level"]
    market_analysis = build_market_analysis(scoped, valuation_data, trend, currency, now)
    price_history = {"period": "last_12_months", "dataPoints": monthly_points(scoped)}
    price_factors = build_price_factors(request, trend, now)
    future = build_future_predictions(
        base_price,
        predicted,
        low,
        high,
        multiplier,
        learned,
        annual_drift=annual_drift,
        target_week=target_week,
        basis=basis,
    )
    market_position = (
        "increasing" if predicted > base_price * 1.05 else "decreasing" if predicted < base_price * 0.95 else "fair_value"
    )
    valuation = {
        "estimatedValue": money(base_price),
        "minimumValue": money(floor_price),
        "maximumValue": money(ceiling_price),
        "currency": currency,
        "confidence": {
            "score": confidence_score,
            "level": confidence_level,
            "explanation": "Based on available price history, live market data, and comparable coverage.",
        },
        "valuationType": "resale_market_value",
        "valuationDate": now.date().isoformat(),
        "marketPosition": market_position,
    }
    recommendation = build_recommendation(
        request, valuation["estimatedValue"], predicted, trend, confidence_score, price_factors
    )
    ai_insights = build_ai_insights(
        request, valuation["estimatedValue"], predicted, trend, comps, currency, basis=basis
    )
    with _PREDICTION_LOCK:
        save_prediction(
            ROOT / PREDICTIONS_PATH,
            {
                "timestamp": iso_time(created_at),
                "serial": identifier,
                "sku": sku,
                "current_price": money(base_price),
                "horizon_weeks": HORIZON_WEEKS,
                "predicted_price": money(predicted),
                "low_price": money(low),
                "high_price": money(high),
                "multiplier": round(multiplier, 4),
            },
        )
    return {
        "predictionId": f"pred_{uuid.uuid4().hex[:12]}",
        "status": "completed",
        "createdAt": iso_time(created_at),
        "expiresAt": iso_time(expires_at),
        "currency": currency,
        "item": build_item(request, entry, sku, currency, now),
        "valuation": valuation,
        "marketAnalysis": market_analysis,
        "priceHistory": price_history,
        "comparableSales": comps,
        "priceFactors": price_factors,
        "futureValuation": future,
        "recommendation": recommendation,
        "dataQuality": data_quality,
        "aiInsights": ai_insights,
    }
