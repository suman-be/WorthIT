import os
import time

import pandas as pd

import market_data
import refresh_histories

WATCH = {"id": "w1", "brand": "Rolex", "model": "Submariner", "reference": "124060"}


def frame(price=11000.0, date="2026-10-04"):
    return pd.DataFrame(
        {
            "week_start": [pd.Timestamp(date)],
            "sku": "124060",
            "price": [price],
            "competitor_price": [price],
            "promo_flag": [0],
            "stock_units": [0],
            "units_sold": [0],
        }
    )


def setup(tmp_path, monkeypatch, result=None, error=None):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.delenv("KELLO_API_KEY", raising=False)
    monkeypatch.setattr(refresh_histories, "catalogue", lambda: [WATCH])
    monkeypatch.setattr(refresh_histories, "PAUSE_SECONDS", 0)
    calls = []

    def fake_fetch(brand, reference, model=None, currency="USD"):
        calls.append((brand, reference, model))
        if error:
            raise error
        return result

    monkeypatch.setattr(market_data, "fetch_watch_history", fake_fetch)
    return calls


def nuvinty(history):
    return {"history": history, "url": "https://nuvinty.com/x", "item": "x", "query": "x", "currencies": ["USD"]}


def test_refresh_saves_history_and_marks_it_as_list_prices(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, nuvinty(frame()))
    outcomes = refresh_histories.main([])
    assert outcomes["w1"].startswith("saved 1 prices")
    assert market_data.load_saved_history("124060")[0]["price"].iloc[0] == 11000.0
    assert market_data.load_history_source("124060") == {
        "provider": "Nuvinty",
        "kind": "list",
        "url": "https://nuvinty.com/x",
    }


def test_recent_histories_are_skipped_and_old_ones_are_refreshed(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch, nuvinty(frame(12000.0)))
    market_data.save_history("124060", frame(10000.0))
    assert refresh_histories.main([])["w1"] == "skipped (recent)"
    assert calls == []

    path = market_data.history_path("124060")
    old = time.time() - 10 * 86400
    os.utime(path, (old, old))
    assert refresh_histories.main([])["w1"].startswith("saved")
    assert len(calls) == 1
    assert market_data.load_saved_history("124060")[0]["price"].iloc[0] == 12000.0


def test_force_refreshes_a_recent_history(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch, nuvinty(frame(12000.0)))
    market_data.save_history("124060", frame(10000.0))
    refresh_histories.main(["--force"])
    assert len(calls) == 1


def test_a_failed_fetch_keeps_the_old_history(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, error=RuntimeError("offline"))
    market_data.save_history("124060", frame(10000.0))
    outcome = refresh_histories.main(["--force"])["w1"]
    assert outcome.startswith("failed, kept the old history")
    assert market_data.load_saved_history("124060")[0]["price"].iloc[0] == 10000.0


def test_an_empty_result_never_replaces_a_saved_history(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, nuvinty(frame().iloc[0:0]))
    market_data.save_history("124060", frame(10000.0))
    assert refresh_histories.main(["--force"])["w1"] == "no data found, kept the old history"
    assert market_data.load_saved_history("124060")[0]["price"].iloc[0] == 10000.0


def test_kello_history_is_saved_as_market_prices(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch, nuvinty(frame()))
    monkeypatch.setenv("KELLO_API_KEY", "test-key")
    kello = {"history": frame(15000.0), "url": "https://kellowatch.com/x", "provider": "Kello"}
    monkeypatch.setattr(market_data, "fetch_kello_history", lambda brand, reference: kello)
    refresh_histories.main([])
    assert calls == []
    assert market_data.load_history_source("124060")["kind"] == "market"


def test_kello_without_data_falls_back_to_list_prices(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, nuvinty(frame()))
    monkeypatch.setenv("KELLO_API_KEY", "test-key")

    def broken(brand, reference):
        raise RuntimeError("Kello returned no dated prices")

    monkeypatch.setattr(market_data, "fetch_kello_history", broken)
    refresh_histories.main([])
    assert market_data.load_history_source("124060")["kind"] == "list"
