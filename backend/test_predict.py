import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config import HORIZON_WEEKS
from generate_sample_data import build_history
from predict import estimate_price, long_run_drift, main, parse_price, seasonal_multipliers


def test_seasonal_multipliers_learns_q4_uplift():
    ratios = seasonal_multipliers(build_history())
    assert ratios.size > 0
    assert 1.0 < float(np.median(ratios)) < 1.3


def test_estimate_price_scales_input_and_returns_range():
    predicted, low, high, multiplier, learned = estimate_price(build_history(), 500.0)
    assert learned
    assert low <= predicted <= high
    assert predicted == pytest.approx(500.0 * multiplier)


def test_estimate_price_is_neutral_without_history():
    empty = pd.DataFrame(columns=["week_start", "price"])
    predicted, low, high, multiplier, learned = estimate_price(empty, 250.0)
    assert not learned
    assert multiplier == 1.0
    assert predicted == low == high == 250.0


def test_parse_price_handles_currency_and_rejects_bad_values():
    assert parse_price("$1,250.50") == pytest.approx(1250.5)
    with pytest.raises(ValueError):
        parse_price("-5")
    with pytest.raises(ValueError):
        parse_price("abc")


def test_cli_accepts_serial_and_price(tmp_path):
    data_path = tmp_path / "watch_history.csv"
    build_history().to_csv(data_path, index=False)
    predictions_path = tmp_path / "predictions.csv"
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "predict.py"),
            "--serial",
            "SER-123",
            "--price",
            "500",
            "--data",
            str(data_path),
            "--serials",
            str(tmp_path / "missing.csv"),
            "--predictions",
            str(predictions_path),
        ],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert f"{HORIZON_WEEKS} weeks" in completed.stdout
    assert "SER-123" in completed.stdout
    logged = pd.read_csv(predictions_path)
    assert len(logged) == 1
    assert logged["serial"].iloc[0] == "SER-123"
    assert logged["current_price"].iloc[0] == pytest.approx(500.0)


def test_cli_prompts_for_serial_and_price(tmp_path, monkeypatch, capsys):
    data_path = tmp_path / "watch_history.csv"
    build_history().to_csv(data_path, index=False)
    predictions_path = tmp_path / "predictions.csv"
    answers = iter(["SER-9", "$600"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "predict.py",
            "--data",
            str(data_path),
            "--serials",
            str(tmp_path / "missing.csv"),
            "--predictions",
            str(predictions_path),
        ],
    )
    main()
    output = capsys.readouterr().out
    assert "SER-9" in output
    assert "$600.00" in output
    logged = pd.read_csv(predictions_path)
    assert logged["serial"].iloc[0] == "SER-9"


def test_seasonal_multipliers_ignores_rows_that_are_not_8_weeks_apart():
    # Sparse live history: consecutive rows are years apart, so no real 8-week window exists.
    history = pd.DataFrame(
        {
            "week_start": pd.to_datetime(
                ["2016-10-02", "2017-11-26", "2018-11-25", "2019-11-24", "2020-11-29",
                 "2021-11-28", "2022-11-27", "2023-11-26", "2024-11-24", "2025-11-30"]
            ),
            "price": [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        }
    )
    assert seasonal_multipliers(history).size == 0


def test_seasonal_multipliers_matches_by_date_despite_missing_weeks():
    dates = pd.to_datetime(["2025-10-05", "2025-10-19", "2025-11-30"])
    history = pd.DataFrame({"week_start": dates, "price": [100.0, 105.0, 120.0]})
    ratios = seasonal_multipliers(history)
    assert ratios.tolist() == pytest.approx([1.2])


def test_estimate_price_uses_time_of_year_of_target():
    history = build_history()  # synthetic: +10% level during ISO weeks 40-52
    into_peak, *_ = estimate_price(history, 500.0, target_date="2026-12-06")
    after_peak, *_ = estimate_price(history, 500.0, target_date="2027-01-24")
    assert into_peak > 500.0
    assert after_peak < 500.0


def test_long_run_drift_detects_trend_and_needs_enough_data():
    weeks = pd.date_range("2024-01-07", periods=104, freq="W-SUN")
    rising = pd.DataFrame({"week_start": weeks, "price": 1000.0 * 1.10 ** (np.arange(104) / 52)})
    assert long_run_drift(rising) == pytest.approx(0.10, abs=0.005)
    assert long_run_drift(rising.head(4)) == 0.0
