import argparse
from pathlib import Path

import pandas as pd

from baseline import BASELINES
from predict import estimate_price
from config import DATA_PATH, HORIZON_WEEKS, MIN_HISTORY_WEEKS, PEAK_WEEK_END, PEAK_WEEK_START


def seasonal_model(history, target_week):
    current = float(history["price"].iloc[-1])
    return estimate_price(history, current, target_date=target_week)[0]


def q4_only_model(history, target_week):
    """Previous behaviour: always apply the Q4 multiplier, whatever the target date."""
    current = float(history["price"].iloc[-1])
    return estimate_price(history, current)[0]


MODELS = {**BASELINES, "seasonal_model": seasonal_model, "q4_only_model": q4_only_model}


def load_history(path):
    frame = pd.read_csv(path, parse_dates=["week_start"])
    return frame.sort_values("week_start").reset_index(drop=True)


MATCH_TOLERANCE = pd.Timedelta(days=3)


def find_target(frame, target_date):
    """Row whose week_start is within MATCH_TOLERANCE of target_date, or None."""
    position = frame["week_start"].searchsorted(target_date)
    best = None
    for index in (position - 1, position):
        if 0 <= index < len(frame):
            gap = abs(frame["week_start"].iloc[index] - target_date)
            if gap <= MATCH_TOLERANCE and (best is None or gap < best[0]):
                best = (gap, index)
    return None if best is None else frame.iloc[best[1]]


def run_backtest(frame, all_weeks=False, models=None):
    """Walk-forward backtest that matches targets by date, not by row position.

    Real histories have gaps, so "HORIZON_WEEKS rows later" is not "HORIZON_WEEKS
    weeks later". Origins with no observed price HORIZON_WEEKS weeks ahead are skipped.
    """
    models = models or MODELS
    rows = []
    if frame.empty:
        return pd.DataFrame(rows)
    first_date = frame["week_start"].iloc[0]
    min_history = pd.Timedelta(weeks=MIN_HISTORY_WEEKS)
    for origin in range(len(frame)):
        origin_date = frame["week_start"].iloc[origin]
        if origin_date - first_date < min_history:
            continue
        target = find_target(frame, origin_date + pd.Timedelta(weeks=HORIZON_WEEKS))
        if target is None:
            continue
        iso_week = int(target["week_start"].isocalendar().week)
        if not all_weeks and not PEAK_WEEK_START <= iso_week <= PEAK_WEEK_END:
            continue
        history = frame.iloc[: origin + 1]
        actual = float(target["price"])
        for name, predict in models.items():
            predicted = float(predict(history, target["week_start"]))
            rows.append(
                {
                    "model": name,
                    "origin": origin_date.date(),
                    "target": target["week_start"].date(),
                    "actual": actual,
                    "predicted": predicted,
                    "error": predicted - actual,
                    "abs_error": abs(predicted - actual),
                    "abs_pct_error": abs(predicted - actual) / actual if actual else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def summarize(results):
    summary = results.groupby("model").agg(
        n=("error", "size"),
        mae=("abs_error", "mean"),
        mape=("abs_pct_error", "mean"),
        bias=("error", "mean"),
    )
    return summary.sort_values("mae")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(Path(__file__).parent / DATA_PATH))
    parser.add_argument("--all-weeks", action="store_true", help="score every target week, not only Q4")
    args = parser.parse_args()
    frame = load_history(args.data)
    results = run_backtest(frame, all_weeks=args.all_weeks)
    scope = "all-week" if args.all_weeks else "Q4"
    if results.empty:
        print(f"no {scope} backtest windows available; extend history or lower MIN_HISTORY_WEEKS")
        return
    points = results["model"].size // results["model"].nunique()
    print(f"weeks loaded: {len(frame)} | {scope} forecast points: {points} | horizon: {HORIZON_WEEKS}w")
    print(summarize(results).round(4).to_string())


if __name__ == "__main__":
    main()
