import json
import sys
from types import SimpleNamespace

import pytest

import market_data
from fetch_history import main as fetch_main
from market_data import fetch_valuation, fetch_watch_history, save_history, save_valuation, to_weekly_history


def fake_response(payload, status_code=200):
    def raise_for_status():
        if status_code >= 400:
            raise RuntimeError(f"HTTP {status_code}")

    return SimpleNamespace(
        status_code=status_code,
        json=lambda: payload,
        raise_for_status=raise_for_status,
    )


def test_fetch_valuation_uses_optional_key(monkeypatch):
    monkeypatch.setenv("PRICETHATWATCH_API_KEY", "free-key")
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        payload = {
            "market_summary": {
                "average_price": 60000,
                "floor_price": 50000,
                "ceiling_price": 70000,
                "sample_size": 100,
            }
        }
        return fake_response(payload)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    result = fetch_valuation("Rolex", "126505")
    assert result["average_price"] == 60000.0
    assert result["sample_size"] == 100
    assert calls[0][1] == {"brand": "Rolex", "reference": "126505"}
    assert calls[0][2]["X-Api-Key"] == "free-key"


def test_fetch_valuation_works_without_key(monkeypatch):
    monkeypatch.delenv("PRICETHATWATCH_API_KEY", raising=False)
    headers_seen = []

    def fake_get(url, params=None, headers=None, timeout=None):
        headers_seen.append(headers)
        return fake_response({"market_summary": {"average_price": 1, "sample_size": 1}})

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    fetch_valuation("Rolex", "126505")
    assert "X-Api-Key" not in headers_seen[0]


def test_fetch_watch_history_filters_currency_and_builds_weekly(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params))
        payload = {
            "data": {
                "item": "Rolex Daytona",
                "url": "https://nuvinty.com/price-history/rolex-daytona",
                "points": [
                    {"date": "2026-01", "price": 10000, "currency": "USD"},
                    {"date": "2026-01", "price": 8000, "currency": "GBP"},
                    {"date": "2026-02", "price": 11000, "currency": "USD"},
                ],
            }
        }
        return fake_response(payload)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    result = fetch_watch_history("Rolex", "126505", model="Daytona")
    assert calls[0][1] == {"type": "history", "q": "Rolex Daytona"}
    assert result["query"] == "Rolex Daytona"
    assert result["currencies"] == ["GBP", "USD"]
    frame = result["history"]
    assert list(frame.columns) == market_data.HISTORY_COLUMNS
    assert len(frame) == 2
    assert frame["price"].tolist() == [10000, 11000]
    assert frame["sku"].iloc[0] == "126505"


def test_save_helpers_write_files(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    frame = to_weekly_history([("2026-01-04", 100)], "126505")
    path = save_history("126505", frame)
    assert path == tmp_path / "data" / "model_history" / "126505.csv"
    valuation = {"average_price": 100}
    valuation_file = save_valuation("126505", valuation)
    assert json.loads(valuation_file.read_text(encoding="utf-8")) == valuation


def test_kello_get_requires_key(monkeypatch):
    monkeypatch.delenv("KELLO_API_KEY", raising=False)
    with pytest.raises(ValueError, match="KELLO_API_KEY"):
        market_data.kello_get("/watches", None)


def test_fetch_kello_history_builds_weekly_from_detail(monkeypatch):
    monkeypatch.setenv("KELLO_API_KEY", "kello-key")
    headers_seen = []

    def fake_get(url, params=None, headers=None, timeout=None):
        headers_seen.append(headers)
        if url.endswith("/watches"):
            assert params == {"reference_number": "126505", "per_page": 10}
            payload = {
                "data": [
                    {
                        "slug": "rolex-126505",
                        "reference_number": "126505",
                        "name": "Rolex Daytona",
                        "current_market_price": 60000,
                    }
                ]
            }
            return fake_response(payload)
        assert url.endswith("/watches/rolex-126505")
        payload = {
            "data": {
                "priceHistory": [
                    {"date": "2026-01-04", "averageMarketPrice": 50000},
                    {"date": "2026-01-11", "averageMarketPrice": 51000},
                    {"date": "2026-01-18", "averageMarketPrice": 52000},
                ]
            }
        }
        return fake_response(payload)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    result = market_data.fetch_kello_history("Rolex", "126505")
    assert headers_seen[0]["Authorization"] == "Bearer kello-key"
    assert result["provider"] == "Kello"
    assert result["item"] == "Rolex Daytona"
    assert result["current_price"] == 60000.0
    assert result["price_source"] == "Kello watch detail"
    assert result["history"]["price"].tolist() == [50000, 51000, 52000]


def test_extract_price_rows_handles_snake_case():
    rows = market_data.extract_price_rows(
        {"data": {"prices": [{"date": "2026-02-01", "average_market_price": 123}]}}
    )
    assert rows == [("2026-02-01", 123)]


def test_fetch_cli_prints_valuation_and_history(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.delenv("PRICETHATWATCH_API_KEY", raising=False)
    monkeypatch.delenv("KELLO_API_KEY", raising=False)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == market_data.PTW_URL:
            payload = {
                "market_summary": {
                    "average_price": 60000,
                    "floor_price": 50000,
                    "ceiling_price": 70000,
                    "sample_size": 100,
                }
            }
            return fake_response(payload)
        assert url == market_data.NUVINTY_URL
        payload = {
            "data": {
                "item": "Rolex Daytona",
                "url": "https://nuvinty.com/x",
                "points": [{"date": "2026-01", "price": 60000, "currency": "USD"}],
            }
        }
        return fake_response(payload)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fetch_history.py",
            "--brand",
            "Rolex",
            "--ref",
            "126505",
            "--model",
            "Daytona",
            "--provider",
            "nuvinty",
        ],
    )
    fetch_main()
    output = capsys.readouterr().out
    assert "$60,000.00" in output
    assert "saved 1 weekly prices" in output


def test_fetch_cli_reports_no_history(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == market_data.PTW_URL:
            return fake_response({"market_summary": {"average_price": 60000, "sample_size": 1}})
        return fake_response({"data": {"item": "", "url": "", "points": []}})

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    monkeypatch.setattr(
        sys,
        "argv",
        ["fetch_history.py", "--brand", "Rolex", "--ref", "126505", "--provider", "nuvinty"],
    )
    fetch_main()
    output = capsys.readouterr().out
    assert "no USD history" in output
    assert "tip: pass --model" in output


def test_fetch_cli_continues_when_valuation_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == market_data.PTW_URL:
            return fake_response({"error": {"message": "quota"}}, status_code=429)
        payload = {
            "data": {
                "item": "Rolex Daytona",
                "url": "https://nuvinty.com/x",
                "points": [{"date": "2026-01", "price": 60000, "currency": "USD"}],
            }
        }
        return fake_response(payload)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fetch_history.py",
            "--brand",
            "Rolex",
            "--ref",
            "126505",
            "--model",
            "Daytona",
            "--provider",
            "nuvinty",
        ],
    )
    fetch_main()
    output = capsys.readouterr().out
    assert "valuation failed" in output
    assert "PRICETHATWATCH_API_KEY" in output
    assert "saved 1 weekly prices" in output


def test_fetch_cli_prefers_kello_when_key_is_set(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.setenv("KELLO_API_KEY", "kello-key")

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == market_data.PTW_URL:
            return fake_response({"error": {"message": "quota"}}, status_code=429)
        if url.endswith("/watches"):
            payload = {
                "data": [
                    {
                        "slug": "rolex-126505",
                        "reference_number": "126505",
                        "name": "Rolex Daytona",
                        "current_market_price": 60000,
                    }
                ]
            }
            return fake_response(payload)
        if url.endswith("/watches/rolex-126505"):
            payload = {
                "data": {
                    "priceHistory": [
                        {"date": "2026-01-04", "averageMarketPrice": 60000},
                        {"date": "2026-01-11", "averageMarketPrice": 61000},
                    ]
                }
            }
            return fake_response(payload)
        raise AssertionError(url)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    monkeypatch.setattr(sys, "argv", ["fetch_history.py", "--brand", "Rolex", "--ref", "126505"])
    fetch_main()
    output = capsys.readouterr().out
    assert "valuation: Rolex 126505 $60,000.00 from Kello" in output
    assert "falling back to Nuvinty" not in output
    assert "history source: Kello watch detail" in output
    assert "saved 2 weekly prices" in output


def test_fetch_cli_falls_back_to_nuvinty_without_kello_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.delenv("KELLO_API_KEY", raising=False)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == market_data.PTW_URL:
            return fake_response({"error": {"message": "quota"}}, status_code=429)
        payload = {
            "data": {
                "item": "Rolex Daytona",
                "url": "https://nuvinty.com/x",
                "points": [{"date": "2026-01", "price": 60000, "currency": "USD"}],
            }
        }
        return fake_response(payload)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    monkeypatch.setattr(sys, "argv", ["fetch_history.py", "--brand", "Rolex", "--ref", "126505"])
    fetch_main()
    output = capsys.readouterr().out
    assert "KELLO_API_KEY is not set; falling back to Nuvinty" in output
    assert "saved 1 weekly prices" in output


def test_predict_uses_saved_model_history(tmp_path, monkeypatch, capsys):
    from generate_sample_data import build_history
    from predict import main as predict_main

    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    frame = build_history()
    frame["sku"] = "126505"
    save_history("126505", frame)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "predict.py",
            "--serial",
            "126505",
            "--price",
            "500",
            "--no-web",
            "--data",
            str(tmp_path / "missing.csv"),
            "--predictions",
            str(tmp_path / "predictions.csv"),
        ],
    )
    predict_main()
    output = capsys.readouterr().out
    assert "price history: 126505.csv" in output
    assert "sku: 126505" in output


def test_find_kello_watch_does_not_fall_back_to_a_different_reference(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return fake_response({"data": [{"slug": "other", "reference_number": "116500LN"}]})

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    with pytest.raises(RuntimeError):
        market_data.find_kello_watch("Rolex", "126505", "key")


def test_market_data_calls_are_cached(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        return fake_response({"market_summary": {"average_price": 60000}})

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    first = fetch_valuation("Rolex", "126505")
    first["average_price"] = 1  # callers mutating results must not poison the cache
    second = fetch_valuation("Rolex", "126505")
    assert len(calls) == 1
    assert second["average_price"] == 60000
