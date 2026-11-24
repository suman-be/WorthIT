"""Score logged predictions against the prices that actually materialised.

Every call to the API or CLI appends to data/predictions.csv. Once a prediction's
horizon has passed, this script looks up the realised price in the stored history
for that SKU and reports error, bias, range coverage, and how the model compares
with simply assuming the price stays flat.
"""
import argparse
from pathlib import Path

import pandas as pd

from config import DATA_PATH, PREDICTIONS_PATH
from market_data import history_path
from predict import load_history

ROOT = Path(__file__).parent
MATCH_TOLERANCE = pd.Timedelta(days=7)


def load_predictions(path):
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dt.tz_localize(None)
    frame = frame.dropna(subset=["timestamp"])
    frame["target_date"] = frame["timestamp"] + pd.to_timedelta(frame["horizon_weeks"] * 7, unit="D")
    return frame


def history_for(sku, default_history, cache):
    if sku not in cache:
        path = history_path(sku)
        history = load_history(path) if path.exists() else default_history
        if history is not None and "sku" in history.columns and (history["sku"].astype(str) == str(sku)).any():
            history = history[history["sku"].astype(str) == str(sku)]
        cache[sku] = history
    return cache[sku]


def realised_price(history, target_date):
    if history is None or history.empty:
        return None
    gaps = (history["week_start"] - target_date).abs()
    best = gaps.idxmin()
    if gaps.loc[best] > MATCH_TOLERANCE:
        return None
    return float(history.loc[best, "price"])


def evaluate(predictions, default_history, as_of=None):
    as_of = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC").tz_localize(None)
    due = predictions[predictions["target_date"] <= as_of].copy()
    cache = {}
    due["actual"] = [
        realised_price(history_for(str(row.sku), default_history, cache), row.target_date)
        for row in due.itertuples()
    ]
    scored = due.dropna(subset=["actual"]).copy()
    scored["error"] = scored["predicted_price"] - scored["actual"]
    scored["abs_pct_error"] = scored["error"].abs() / scored["actual"]
    scored["flat_abs_pct_error"] = (scored["current_price"] - scored["actual"]).abs() / scored["actual"]
    scored["in_range"] = scored["actual"].between(scored["low_price"], scored["high_price"])
    return {
        "logged": len(predictions),
        "due": len(due),
        "scored": len(scored),
        "pending": len(predictions) - len(due),
        "unmatched": len(due) - len(scored),
        "rows": scored,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--predictions", default=str(ROOT / PREDICTIONS_PATH))
    parser.add_argument("--data", default=str(ROOT / DATA_PATH))
    parser.add_argument("--as-of", help="evaluate as if today were this date (YYYY-MM-DD)")
    args = parser.parse_args()
    if not Path(args.predictions).exists():
        print(f"no predictions logged yet at {args.predictions}")
        return
    default_history = load_history(args.data) if Path(args.data).exists() else None
    result = evaluate(load_predictions(args.predictions), default_history, as_of=args.as_of)
    print(
        f"logged: {result['logged']} | due: {result['due']} | scored: {result['scored']} | "
        f"pending: {result['pending']} | no realised price yet: {result['unmatched']}"
    )
    rows = result["rows"]
    if rows.empty:
        print("nothing to score yet; refresh price history after predictions reach their horizon")
        return
    print(f"model MAPE:          {rows['abs_pct_error'].mean():.2%}")
    print(f"flat-price MAPE:     {rows['flat_abs_pct_error'].mean():.2%}")
    print(f"bias (pred - real):  {rows['error'].mean():+,.2f}")
    print(f"range coverage:      {rows['in_range'].mean():.0%} (low/high is a 10-90% band, so ~80% is healthy)")


if __name__ == "__main__":
    main()
