import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    CATALOG_PATH,
    DATA_PATH,
    HORIZON_WEEKS,
    MAX_ANNUAL_DRIFT,
    PEAK_WEEK_END,
    PEAK_WEEK_START,
    PREDICTIONS_PATH,
    SEASON_WINDOW_WEEKS,
    SERIALS_PATH,
)
from watch_lookup import format_results, lookup_watch
from market_data import history_path

ROOT = Path(__file__).parent


def load_history(path):
    frame = pd.read_csv(path, parse_dates=["week_start"])
    return frame.sort_values("week_start").reset_index(drop=True)


def load_serial_map(path):
    if not Path(path).exists():
        return {}
    frame = pd.read_csv(path, dtype=str)
    if not {"serial", "sku"}.issubset(frame.columns):
        return {}
    return dict(zip(frame["serial"], frame["sku"]))


def load_catalog(path):
    if not Path(path).exists():
        return {}
    frame = pd.read_csv(path, dtype=str).fillna("")
    key = "serial" if "serial" in frame.columns else "identifier" if "identifier" in frame.columns else None
    if key is None:
        return {}
    return {row[key]: row.to_dict() for _, row in frame.iterrows()}


def describe_watch(entry):
    if not entry:
        return None
    name = " ".join(
        str(entry.get(field, "")).strip()
        for field in ("brand", "model", "variant")
        if str(entry.get(field, "")).strip()
    )
    description = str(entry.get("description", "")).strip()
    if not name and not description:
        return None
    return name, description


def parse_price(raw):
    value = float(str(raw).replace(",", "").replace("$", "").strip())
    if not np.isfinite(value) or value <= 0:
        raise ValueError("price must be a positive number")
    return value


def read_inputs(args):
    serial = args.serial or input("watch serial number: ").strip()
    raw_price = args.price if args.price is not None else input("current price: ").strip()
    if not serial:
        raise ValueError("serial number is required")
    return serial, parse_price(raw_price)


def week_distance(a, b):
    diff = abs(int(a) - int(b)) % 52
    return min(diff, 52 - diff)


def target_iso_week(target_date):
    return int(pd.Timestamp(target_date).isocalendar().week)


def seasonal_multipliers(history, target_week=None, window=SEASON_WINDOW_WEEKS):
    """Historical HORIZON_WEEKS price ratios for windows ending near ``target_week``.

    With ``target_week=None`` the legacy behaviour is kept: all windows ending in
    the Q4 peak (PEAK_WEEK_START..PEAK_WEEK_END).
    """
    ratios = []
    if "week_start" not in history or "price" not in history or history.empty:
        return np.asarray(ratios, dtype=float)
    frame = history[["week_start", "price"]].copy()
    frame["week_start"] = pd.to_datetime(frame["week_start"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna().sort_values("week_start").drop_duplicates("week_start", keep="last")
    if frame.empty:
        return np.asarray(ratios, dtype=float)
    # Look back by calendar time, not by row count: live sources have gaps,
    # so "8 rows back" can silently mean months or years back.
    end_weeks = frame["week_start"].dt.isocalendar().week.astype(int)
    if target_week is None:
        in_season = end_weeks.between(PEAK_WEEK_START, PEAK_WEEK_END)
    else:
        in_season = end_weeks.map(lambda week: week_distance(week, target_week) <= window)
    targets = frame[in_season].copy()
    targets["lookup"] = targets["week_start"] - pd.Timedelta(weeks=HORIZON_WEEKS)
    starts = frame.rename(columns={"week_start": "lookup", "price": "start_price"})
    paired = pd.merge_asof(
        targets.sort_values("lookup"),
        starts,
        on="lookup",
        direction="nearest",
        tolerance=pd.Timedelta(days=3),
    ).dropna(subset=["start_price"])
    paired = paired[(paired["start_price"] > 0) & (paired["price"] > 0)]
    ratios = (paired["price"] / paired["start_price"]).to_numpy(dtype=float)
    return np.clip(ratios, 0.5, 2.0)


def estimate_price(history, current_price, target_date=None):
    """Seasonal HORIZON_WEEKS forecast.

    Pass ``target_date`` (the date the forecast lands on) so the multiplier is
    learned from the same time of year. Without it, the Q4 multiplier is used.
    """
    target_week = target_iso_week(target_date) if target_date is not None else None
    ratios = seasonal_multipliers(history, target_week=target_week)
    if ratios.size == 0:
        return current_price, current_price, current_price, 1.0, False
    multiplier = float(np.median(ratios))
    low_multiplier = float(np.quantile(ratios, 0.1))
    high_multiplier = float(np.quantile(ratios, 0.9))
    return (
        current_price * multiplier,
        current_price * low_multiplier,
        current_price * high_multiplier,
        multiplier,
        True,
    )


def long_run_drift(history, lookback_weeks=104, min_points=6, min_span_weeks=26):
    """Annualised log-linear price drift over the recent history, clipped to a sane range.

    Returns 0.0 when there is too little data to say anything.
    """
    if history is None or history.empty or "week_start" not in history or "price" not in history:
        return 0.0
    frame = history[["week_start", "price"]].copy()
    frame["week_start"] = pd.to_datetime(frame["week_start"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna()
    frame = frame[frame["price"] > 0]
    if frame.empty:
        return 0.0
    cutoff = frame["week_start"].max() - pd.Timedelta(weeks=lookback_weeks)
    frame = frame[frame["week_start"] >= cutoff]
    if len(frame) < min_points:
        return 0.0
    weeks = (frame["week_start"] - frame["week_start"].min()).dt.days.to_numpy(dtype=float) / 7.0
    if weeks.max() < min_span_weeks:
        return 0.0
    slope = np.polyfit(weeks, np.log(frame["price"].to_numpy(dtype=float)), 1)[0]
    annual = float(np.expm1(slope * 52.0))
    return float(np.clip(annual, -MAX_ANNUAL_DRIFT, MAX_ANNUAL_DRIFT))


def save_prediction(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([record]).to_csv(path, mode="a", header=not path.exists(), index=False)


def main():
    parser = argparse.ArgumentParser(description="Predict a watch price from its serial number and current price")
    parser.add_argument("--serial")
    parser.add_argument("--price")
    parser.add_argument("--data", default=str(ROOT / DATA_PATH))
    parser.add_argument("--serials", default=str(ROOT / SERIALS_PATH))
    parser.add_argument("--predictions", default=str(ROOT / PREDICTIONS_PATH))
    parser.add_argument("--catalog", default=str(ROOT / CATALOG_PATH))
    parser.add_argument("--ref")
    parser.add_argument("--no-web", action="store_true")
    parser.add_argument("--info-only", action="store_true")
    parser.add_argument("--history")
    args = parser.parse_args()
    try:
        serial, current_price = read_inputs(args)
    except ValueError as exc:
        print(f"invalid input: {exc}")
        return
    model_path = history_path(args.ref or serial)
    if args.history:
        history = load_history(args.history)
        history_source = Path(args.history).name
    elif model_path.exists():
        history = load_history(model_path)
        history_source = model_path.name
    else:
        history = load_history(args.data)
        history_source = Path(args.data).name
    serial_map = load_serial_map(args.serials)
    catalog = load_catalog(args.catalog)
    entry = catalog.get(serial)
    sku = serial_map.get(serial) or (entry.get("sku") if entry else None)
    if sku is None and not history.empty and "sku" in history.columns:
        sku = str(history["sku"].iloc[0])
    sku = sku or "unknown"
    if (args.history or model_path.exists()) and not history.empty and "sku" in history.columns:
        sku = str(history["sku"].iloc[0])
    if "sku" in history.columns:
        scoped = history[history["sku"] == sku]
        if scoped.empty:
            scoped = history
    else:
        scoped = history
    print(f"serial: {serial} | sku: {sku}")
    details = describe_watch(entry)
    if details:
        name, description = details
        if name:
            print(f"watch: {name}")
        if description:
            print(f"description: {description}")
    else:
        print(f"description: no catalog entry for serial {serial}")
        if not args.no_web:
            for line in format_results(lookup_watch(serial, ref=args.ref)):
                print(line)
    if args.info_only:
        return
    print(f"price history: {history_source}")
    now = datetime.now(timezone.utc)
    target_date = (now + timedelta(weeks=HORIZON_WEEKS)).date()
    predicted, low, high, multiplier, learned = estimate_price(scoped, current_price, target_date=target_date)
    print(f"current price: ${current_price:,.2f}")
    print(
        f"predicted price in {HORIZON_WEEKS} weeks ({target_date}, ISO week {target_iso_week(target_date)}): "
        f"${predicted:,.2f}"
    )
    print(f"range: ${low:,.2f} - ${high:,.2f} | seasonal multiplier: {multiplier:.3f}")
    if not learned:
        print("warning: no history for this time of year; using neutral multiplier")
    save_prediction(
        args.predictions,
        {
            "timestamp": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "serial": serial,
            "sku": sku,
            "current_price": round(current_price, 2),
            "horizon_weeks": HORIZON_WEEKS,
            "predicted_price": round(predicted, 2),
            "low_price": round(low, 2),
            "high_price": round(high, 2),
            "multiplier": round(multiplier, 4),
        },
    )


if __name__ == "__main__":
    main()
