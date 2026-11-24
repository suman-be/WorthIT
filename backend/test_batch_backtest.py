import pandas as pd

import batch_backtest
import market_data
from generate_sample_data import build_history


def write_history(reference, frame):
    frame = frame.copy()
    frame["sku"] = reference
    market_data.save_history(reference, frame)


def references():
    return [
        {"brand": "Demo", "reference": "WEEKLY", "model": ""},
        {"brand": "Demo", "reference": "MONTHLY", "model": ""},
        {"brand": "Demo", "reference": "MISSING", "model": ""},
    ]


def setup_histories(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    weekly = build_history()
    write_history("WEEKLY", weekly)
    monthly = weekly.set_index("week_start")["price"].resample("MS").first().reset_index()
    write_history("MONTHLY", monthly)


def test_batch_scores_weekly_data_and_flags_sparse_or_missing(tmp_path, monkeypatch):
    setup_histories(tmp_path, monkeypatch)
    results = batch_backtest.run(references(), fetch=False).set_index("watch")
    weekly = results.loc["Demo WEEKLY"]
    assert weekly["points"] >= batch_backtest.MIN_POINTS
    assert weekly["model_mape"] < weekly["last_price_mape"]
    assert weekly["verdict"] == "model wins"
    assert results.loc["Demo MONTHLY", "verdict"].startswith("too little data")
    assert results.loc["Demo MONTHLY", "median_gap_days"] > batch_backtest.MAX_WEEKLY_GAP_DAYS
    assert results.loc["Demo MISSING", "verdict"] == "no data"
    summary = batch_backtest.overall(results.reset_index())
    assert "Model wins on 1/1" in summary
    assert "Too few references" in summary


def test_batch_interpolate_makes_monthly_data_scorable(tmp_path, monkeypatch):
    setup_histories(tmp_path, monkeypatch)
    results = batch_backtest.run(references()[1:2], fetch=False, interpolate=True)
    row = results.iloc[0]
    assert row["interpolated"]
    assert row["points"] > 0


def test_batch_fetch_reports_provider_errors_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.delenv("KELLO_API_KEY", raising=False)

    def fail(*args, **kwargs):
        raise RuntimeError("HTTP 503")

    monkeypatch.setattr(market_data.requests, "get", fail)
    results = batch_backtest.run(references()[:1], fetch=True)
    assert results.iloc[0]["verdict"] == "no data"
    assert "Nuvinty: HTTP 503" in results.iloc[0]["error"]
