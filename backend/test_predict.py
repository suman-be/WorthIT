import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config import HORIZON_WEEKS
from generate_sample_data import build_history
from predict import estimate_price, main, parse_price, seasonal_multipliers


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
