import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    CATALOG_PATH,
    DATA_PATH,
    HORIZON_WEEKS,
    PEAK_WEEK_END,
    PEAK_WEEK_START,
    PREDICTIONS_PATH,
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
    if "serial" not in frame.columns:
        return {}
    return {row["serial"]: row.to_dict() for _, row in frame.iterrows()}


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


def seasonal_multipliers(history):
    ratios = []
    if "week_start" not in history or "price" not in history or history.empty:
        return np.asarray(ratios, dtype=float)
    iso_week = history["week_start"].dt.isocalendar().week
    prices = history["price"].to_numpy(dtype=float)
    for index in range(HORIZON_WEEKS, len(history)):
        week = int(iso_week.iloc[index])
        if not PEAK_WEEK_START <= week <= PEAK_WEEK_END:
            continue
        start_price = prices[index - HORIZON_WEEKS]
        end_price = prices[index]
        if start_price > 0 and end_price > 0:
            ratios.append(end_price / start_price)
    return np.clip(np.asarray(ratios, dtype=float), 0.5, 2.0)


def estimate_price(history, current_price):
    ratios = seasonal_multipliers(history)
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
    predicted, low, high, multiplier, learned = estimate_price(scoped, current_price)
    print(f"current price: ${current_price:,.2f}")
    print(f"predicted price in {HORIZON_WEEKS} weeks (Q4 weeks {PEAK_WEEK_START}-{PEAK_WEEK_END}): ${predicted:,.2f}")
    print(f"range: ${low:,.2f} - ${high:,.2f} | seasonal multiplier: {multiplier:.3f}")
    if not learned:
        print("warning: no Q4 history found; using neutral multiplier")
    save_prediction(
        args.predictions,
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
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
