import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest import MODELS, run_backtest, summarize
from baseline import BASELINES, last_price, same_week_last_year, seasonal_ratio
from config import PEAK_WEEK_END, PEAK_WEEK_START
from generate_sample_data import build_history


def make_history(prices=None, weeks=104, end="2026-01-04"):
    dates = pd.date_range(end=end, periods=weeks, freq="W-SUN")
    values = np.linspace(100.0, 120.0, weeks) if prices is None else np.asarray(prices, dtype=float)
    return pd.DataFrame({"week_start": dates, "price": values, "units_sold": np.ones(weeks, dtype=int)})


def matching_target(anchor, weeks_ahead=52):
    target = anchor + pd.Timedelta(weeks=weeks_ahead)
    while target.isocalendar().week != anchor.isocalendar().week:
        target += pd.Timedelta(weeks=1)
    return target


def test_last_price_uses_latest_row():
    history = make_history([100.0, 110.0, 120.0], weeks=3)
    assert last_price(history) == pytest.approx(120.0)


def test_same_week_last_year_uses_matching_prior_week():
    history = make_history()
    anchor = history["week_start"].iloc[-1]
    target = matching_target(anchor)
    assert same_week_last_year(history, target) == pytest.approx(float(history["price"].iloc[-1]))


def test_same_week_last_year_falls_back_without_history():
    history = make_history(weeks=2, prices=[100.0, 101.0])
    target = pd.Timestamp("2030-01-06")
    assert same_week_last_year(history, target) == pytest.approx(101.0)


def test_seasonal_ratio_applies_prior_year_uplift():
    dates = pd.date_range("2025-01-05", periods=30, freq="W-SUN")
    prices = np.full(30, 100.0)
    prices[20] = 110.0
    history = pd.DataFrame({"week_start": dates, "price": prices, "units_sold": np.ones(30, dtype=int)})
    target = matching_target(dates[20])
    assert seasonal_ratio(history, target) == pytest.approx(110.0)


def test_backtest_filters_to_peak_weeks_and_scores_all_baselines():
    results = run_backtest(build_history())
    assert not results.empty
    assert set(results["model"]) == set(MODELS)
    assert set(BASELINES) <= set(MODELS)
    target_weeks = pd.to_datetime(results["target"]).dt.isocalendar().week.astype(int)
    assert target_weeks.between(PEAK_WEEK_START, PEAK_WEEK_END).all()
    summary = summarize(results)
    assert {"n", "mae", "mape", "bias"}.issubset(summary.columns)
    assert summary["mae"].notna().all()


def test_backtest_cli_prints_summary(tmp_path):
    data_path = tmp_path / "watch_history.csv"
    build_history().to_csv(data_path, index=False)
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "backtest.py"), "--data", str(data_path)],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Q4 forecast points" in completed.stdout
    assert "last_price" in completed.stdout


def test_seasonal_model_beats_q4_only_model_across_the_year():
    summary = summarize(run_backtest(build_history(), all_weeks=True))
    assert summary.loc["seasonal_model", "mae"] < summary.loc["q4_only_model", "mae"]


def test_backtest_skips_origins_without_a_price_8_weeks_later():
    history = build_history()
    gappy = history.drop(index=range(100, 140)).reset_index(drop=True)
    results = run_backtest(gappy, all_weeks=True)
    gaps = (pd.to_datetime(results["target"]) - pd.to_datetime(results["origin"])).dt.days
    assert not results.empty
    assert gaps.between(53, 59).all()
