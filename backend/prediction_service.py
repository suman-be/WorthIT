import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import market_data
from config import CATALOG_PATH, DATA_PATH, HORIZON_WEEKS, PREDICTIONS_PATH, SERIALS_PATH
from predict import (
    estimate_price,
    load_catalog,
    load_history,
    load_serial_map,
    save_prediction,
)

ROOT = Path(__file__).parent
_PREDICTION_LOCK = threading.Lock()


def utc_now():
    return datetime.now(timezone.utc)


def iso_time(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def money(value):
    return round(float(value), 2)


def bounded(value, low, high):
    return float(np.clip(float(value), low, high))


def refresh_market_data(request, live=True):
    errors = []
    sources = []
    history = None
    history_source = "local"
    live_history = False
    valuation = None
    valuation_source = None
    kello_result = None
    brand = request["brand"]
    reference = request["reference"]
    model = request.get("model")
    currency = request.get("currency") or "USD"
    if live:
        try:
            valuation = market_data.fetch_valuation(brand, reference, detailed=True)
            valuation_source = "Price That Watch"
            sources.append(valuation_source)
        except Exception as exc:
            errors.append(f"Price That Watch valuation unavailable: {exc}")
        if market_data.kello_key():
            try:
                kello_result = market_data.fetch_kello_history(brand, reference)
                history = kello_result["history"]
                history_source = "Kello"
                live_history = True
                sources.append("Kello")
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
                    live_history = True
                    sources.append("Nuvinty")
                else:
                    errors.append("Nuvinty returned no dated history")
            except Exception as exc:
                errors.append(f"Nuvinty history unavailable: {exc}")
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
    if history is None or history.empty:
        local_path = ROOT / market_data.MODEL_HISTORY_DIR / f"{market_data.safe_name(reference)}.csv"
        if not local_path.exists():
            local_path = ROOT / DATA_PATH
        history = load_history(local_path)
        history_source = local_path.name
        errors.append(f"live history unavailable; using local {history_source}")
    return {
        "history": history,
        "history_source": history_source,
        "live_history": live_history,
        "valuation": valuation,
        "valuation_source": valuation_source,
        "sources": sources,
        "errors": errors,
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


def build_comparables(valuation, request, history, url):
    items = []
    listings = (valuation or {}).get("listings") or []
    currency = (valuation or {}).get("currency") or request.get("currency") or "USD"
    for entry in listings[:5]:
        price = market_data.number_value(
            market_data.first_value(
                entry,
                ("price", "price_usd", "priceUsd", "askingPrice", "asking_price", "marketPrice", "market_price"),
            )
        )
        if price is None:
            continue
        sold_at = market_data.first_value(entry, ("soldAt", "sold_at", "listedAt", "listed_at", "date"))
        items.append(
            {
                "id": str(market_data.first_value(entry, ("id", "listingId", "listing_id")) or f"sale_{len(items) + 1}"),
                "title": str(
                    market_data.first_value(entry, ("title", "name", "description"))
                    or f"{request['brand']} {request.get('model') or request['reference']}"
                ),
                "price": money(price),
                "currency": str(
                    market_data.first_value(entry, ("currency",)) or currency
                ).upper(),
                "condition": str(market_data.first_value(entry, ("condition", "grade")) or "unknown"),
                "soldAt": str(sold_at) if sold_at else None,
                "source": str(market_data.first_value(entry, ("source", "marketplace")) or "Marketplace"),
                "similarityScore": int(
                    market_data.number_value(
                        market_data.first_value(entry, ("similarityScore", "similarity_score"))
                    )
                    or 85
                ),
                "url": str(market_data.first_value(entry, ("url", "link")) or ""),
            }
        )
    source = "live"
    if not items and history is not None and not history.empty:
        source = "derived"
        tail = history.tail(3)
        for _, row in tail.iloc[::-1].iterrows():
            items.append(
                {
                    "id": f"derived_{len(items) + 1}",
                    "title": f"{request['brand']} {request.get('model') or request['reference']}",
                    "price": money(row["price"]),
                    "currency": currency,
                    "condition": "unknown",
                    "soldAt": pd.to_datetime(row["week_start"]).date().isoformat(),
                    "source": "derived from price history",
                    "similarityScore": 80,
                    "url": url or "",
                }
            )
    prices = [item["price"] for item in items]
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


def build_future_predictions(base_price, predicted, low, high, multiplier, learned):
    if base_price <= 0:
        base_price = 1.0
    base_multiplier = predicted / base_price
    low_multiplier = low / base_price
    high_multiplier = high / base_price
    periods = (
        ("8_weeks", HORIZON_WEEKS),
        ("3_months", 13),
        ("6_months", 26),
        ("12_months", 52),
    )
    predictions = []
    for period, weeks in periods:
        exponent = weeks / HORIZON_WEEKS
        estimate_multiplier = bounded(base_multiplier**exponent, 0.25, 3.0)
        low_bound = bounded(low_multiplier**exponent, 0.25, estimate_multiplier)
        high_bound = bounded(high_multiplier**exponent, estimate_multiplier, 3.0)
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
    explanation = (
        f"Based on the median historical {HORIZON_WEEKS}-week Q4 multiplier of {multiplier:.3f}, "
        "extrapolated to longer horizons; longer-term estimates are less reliable."
        if learned
        else "No comparable Q4 history was found, so a neutral multiplier was applied."
    )
    return {"predictions": predictions, "explanation": explanation}


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


def build_ai_insights(request, valuation_value, predicted, trend, comps, currency):
    low = comps.get("items", [{}])[0].get("price") if comps.get("items") else None
    high = comps.get("items", [{}])[-1].get("price") if comps.get("items") else None
    summary = (
        f"The {request['brand']} {request.get('model') or request['reference']} is estimated at "
        f"{currency} {valuation_value:,.2f}, with an {HORIZON_WEEKS}-week projection of {currency} {predicted:,.2f}."
    )
    key_insights = [
        f"Recent comparable prices span {currency} {low:,.2f} to {currency} {high:,.2f}." if low and high else "Limited comparable sales were available.",
        f"Observed price trend is {trend:.1f}% over the recent window.",
        f"The model applies a seasonal multiplier over an {HORIZON_WEEKS}-week Q4 horizon.",
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
    if comps["source"] == "live":
        score += 5
    score = int(bounded(score, 0, 100))
    level = "high" if score >= 80 else "medium" if score >= 60 else "low"
    sources_used = len({source for source in refresh["sources"] if source})
    sample_size = (refresh["valuation"] or {}).get("sample_size") or 0
    limitations = list(errors)
    limitations.append("Future valuations are estimates and cannot guarantee actual market prices.")
    if comps["source"] == "derived":
        limitations.append("Comparable sales were derived from price history rather than observed transactions.")
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
    brand = request["brand"]
    model = request.get("model") or (entry.get("model") if entry else "") or request["reference"]
    variant = request.get("variant") or (entry.get("variant") if entry else "") or request["reference"]
    name = request.get("name") or f"{brand} {model} {variant}".strip()
    description = (
        request.get("description")
        or (entry.get("description") if entry else "")
        or f"{brand} {model}, reference {request['reference']}"
    )
    specifications = [
        {"name": "Reference", "value": request["reference"]},
        {"name": "Brand", "value": brand},
        {"name": "Model", "value": model},
        {"name": "Variant", "value": variant},
        {"name": "SKU", "value": sku},
    ]
    if request.get("releaseYear"):
        specifications.append({"name": "Release year", "value": str(request["releaseYear"])})
    return {
        "name": name,
        "category": request.get("category") or "Watches",
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
    catalog = load_catalog(ROOT / CATALOG_PATH)
    serial_map = load_serial_map(ROOT / SERIALS_PATH)
    entry = catalog.get(request["serial"])
    sku = (
        serial_map.get(request["serial"])
        or (entry.get("sku") if entry else None)
        or request["reference"]
        or "unknown"
    )
    scoped = scope_history(history, sku)
    prices = pd.to_numeric(scoped["price"], errors="coerce").dropna() if "price" in scoped else pd.Series(dtype=float)
    valuation_data = refresh["valuation"]
    currency = "USD" if refresh["valuation_source"] or refresh["live_history"] else request.get("currency") or "USD"
    base_price = valuation_data["average_price"] if valuation_data else request["price"]
    floor_price = valuation_data.get("floor_price") if valuation_data else None
    ceiling_price = valuation_data.get("ceiling_price") if valuation_data else None
    if floor_price is None:
        floor_price = prices.min() * 0.95 if not prices.empty else base_price * 0.9
    if ceiling_price is None:
        ceiling_price = prices.max() * 1.05 if not prices.empty else base_price * 1.1
    predicted, low, high, multiplier, learned = estimate_price(scoped, base_price)
    trend = price_trend(scoped)
    url = ""
    if refresh["live_history"] and refresh["history_source"] == "Kello":
        url = f"https://kellowatch.com/watches/{request['reference']}"
    comps = build_comparables(valuation_data, request, scoped, url)
    data_quality = build_data_quality(refresh, scoped, comps)
    confidence_score = data_quality["overallScore"]
    confidence_level = data_quality["level"]
    market_analysis = build_market_analysis(scoped, valuation_data, trend, currency, now)
    price_history = {"period": "last_12_months", "dataPoints": monthly_points(scoped)}
    price_factors = build_price_factors(request, trend, now)
    future = build_future_predictions(base_price, predicted, low, high, multiplier, learned)
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
        request, valuation["estimatedValue"], predicted, trend, comps, currency
    )
    with _PREDICTION_LOCK:
        save_prediction(
            ROOT / PREDICTIONS_PATH,
            {
                "timestamp": iso_time(created_at),
                "serial": request["serial"],
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
