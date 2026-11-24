import argparse
from pathlib import Path

import pandas as pd

from baseline import BASELINES
from config import DATA_PATH, HORIZON_WEEKS, MIN_HISTORY_WEEKS, PEAK_WEEK_END, PEAK_WEEK_START


def load_history(path):
    frame = pd.read_csv(path, parse_dates=["week_start"])
    return frame.sort_values("week_start").reset_index(drop=True)


def run_backtest(frame):
    rows = []
    for origin in range(MIN_HISTORY_WEEKS, len(frame) - HORIZON_WEEKS):
        history = frame.iloc[: origin + 1]
        target = frame.iloc[origin + HORIZON_WEEKS]
        iso_week = int(target["week_start"].isocalendar().week)
        if not PEAK_WEEK_START <= iso_week <= PEAK_WEEK_END:
            continue
        actual = float(target["price"])
        for name, predict in BASELINES.items():
            predicted = float(predict(history, target["week_start"]))
            rows.append(
                {
                    "model": name,
                    "origin": history["week_start"].iloc[-1].date(),
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
    args = parser.parse_args()
    frame = load_history(args.data)
    results = run_backtest(frame)
    if results.empty:
        print("no Q4 backtest windows available; extend history or lower MIN_HISTORY_WEEKS")
        return
    points = results["model"].size // len(BASELINES)
    print(f"weeks loaded: {len(frame)} | Q4 forecast points: {points} | horizon: {HORIZON_WEEKS}w")
    print(summarize(results).round(4).to_string())


if __name__ == "__main__":
    main()
