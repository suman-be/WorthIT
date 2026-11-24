import pandas as pd

from config import HORIZON_WEEKS


def last_price(history):
    return float(history["price"].iloc[-1])


def same_week_last_year(history, target_week):
    target_iso_week = target_week.isocalendar().week
    matches = history[history["week_start"].dt.isocalendar().week == target_iso_week]
    matches = matches[matches["week_start"] < target_week]
    if matches.empty:
        return last_price(history)
    return float(matches["price"].iloc[-1])


def seasonal_ratio(history, target_week):
    fallback = last_price(history)
    target_iso_week = target_week.isocalendar().week
    matches = history[history["week_start"].dt.isocalendar().week == target_iso_week]
    matches = matches[matches["week_start"] < target_week]
    if matches.empty:
        return fallback
    anchor = matches.iloc[-1]
    prior = history[history["week_start"] <= anchor["week_start"] - pd.Timedelta(weeks=HORIZON_WEEKS)]
    if prior.empty:
        return fallback
    start_price = float(prior["price"].iloc[-1])
    if start_price <= 0:
        return fallback
    ratio = float(anchor["price"]) / start_price
    ratio = min(max(ratio, 0.8), 1.3)
    return fallback * ratio


BASELINES = {
    "last_price": lambda history, target_week: last_price(history),
    "same_week_last_year": lambda history, target_week: same_week_last_year(history, target_week),
    "seasonal_ratio": lambda history, target_week: seasonal_ratio(history, target_week),
}
