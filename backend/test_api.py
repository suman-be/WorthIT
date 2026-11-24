from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import market_data
import prediction_service
from api import app
from generate_sample_data import build_history
from prediction_service import build_future_predictions

client = TestClient(app)


def fake_response(payload, status_code=200):
    def raise_for_status():
        if status_code >= 400:
            raise RuntimeError(f"HTTP {status_code}")

    return SimpleNamespace(
        status_code=status_code,
        json=lambda: payload,
        raise_for_status=raise_for_status,
    )


def kello_history_payload():
    dates = [
        "2025-10-05",
        "2025-10-12",
        "2025-10-19",
        "2025-10-26",
        "2025-11-02",
        "2025-11-09",
        "2025-11-16",
        "2025-11-23",
        "2025-11-30",
    ]
    prices = [10000, 10125, 10250, 10375, 10500, 10625, 10750, 10875, 11000]
    return {
        "data": {
            "priceHistory": [
                {"date": date, "averageMarketPrice": price}
                for date, price in zip(dates, prices)
            ]
        }
    }


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_predict_validation_rejects_bad_price():
    response = client.post(
        "/predict",
        json={"serial": "126505", "price": 0, "brand": "Rolex", "reference": "126505"},
    )
    assert response.status_code == 422


def test_future_extrapolation_uses_fractional_exponent():
    result = build_future_predictions(1000.0, 1100.0, 990.0, 1210.0, 1.1, True)
    periods = {item["period"]: item for item in result["predictions"]}
    assert list(periods) == ["8_weeks", "3_months", "6_months", "12_months"]
    assert periods["8_weeks"]["estimatedValue"] == pytest.approx(1100.0)
    assert periods["8_weeks"]["changePercentage"] == pytest.approx(10.0)
    # no drift: longer horizons stay flat instead of compounding the seasonal bump
    assert periods["12_months"]["estimatedValue"] == pytest.approx(1000.0)
    for item in result["predictions"]:
        assert item["minimumValue"] <= item["estimatedValue"] <= item["maximumValue"]
    widths = [item["maximumValue"] - item["minimumValue"] for item in result["predictions"][1:]]
    assert widths == sorted(widths)


def test_future_predictions_follow_long_run_drift():
    result = build_future_predictions(1000.0, 1000.0, 950.0, 1050.0, 1.0, True, annual_drift=0.10)
    periods = {item["period"]: item for item in result["predictions"]}
    assert periods["12_months"]["estimatedValue"] == pytest.approx(1100.0, rel=1e-3)
    assert "+10.0% per year" in result["explanation"]


def test_predict_returns_rich_response_with_mocked_live_apis(tmp_path, monkeypatch):
    monkeypatch.setattr(prediction_service, "ROOT", tmp_path)
    # forecast made early October so it lands in the same weeks as the mocked history
    monkeypatch.setattr(
        prediction_service, "utc_now", lambda: datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    )
    monkeypatch.setenv("KELLO_API_KEY", "kello-key")
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        if url == market_data.PTW_URL:
            assert params["detailed"] == "true"
            payload = {
                "market_summary": {
                    "average_price": 60000,
                    "floor_price": 50000,
                    "ceiling_price": 70000,
                    "sample_size": 120,
                },
                "listings": [
                    {
                        "id": "sale_1",
                        "title": "Rolex Daytona 126505",
                        "price": 61000,
                        "currency": "USD",
                        "condition": "good",
                        "soldAt": "2026-11-15",
                        "source": "Marketplace",
                        "similarityScore": 96,
                        "url": "https://example.com/listing/1",
                    }
                ],
            }
            return fake_response(payload)
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
            return fake_response(kello_history_payload())
        raise AssertionError(url)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    response = client.post(
        "/predict",
        json={
            "serial": "126505",
            "price": 60000,
            "brand": "Rolex",
            "reference": "126505",
            "model": "Daytona",
            "variant": "126505",
            "currency": "USD",
            "condition": {"grade": "good", "description": "Minor wear"},
            "purchase": {"originalPrice": 55000, "purchaseDate": "2024-12-01", "currency": "USD"},
            "location": {"country": "BE", "region": "Flanders"},
            "images": [{"url": "https://example.com/watch.jpg", "type": "front"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert {
        "predictionId",
        "status",
        "createdAt",
        "expiresAt",
        "currency",
        "item",
        "valuation",
        "marketAnalysis",
        "priceHistory",
        "comparableSales",
        "priceFactors",
        "futureValuation",
        "recommendation",
        "dataQuality",
        "aiInsights",
    }.issubset(body)
    assert body["status"] == "completed"
    assert body["valuation"]["estimatedValue"] == pytest.approx(60000.0)
    assert body["marketAnalysis"]["statistics"]["totalListings"] == 120
    assert body["priceHistory"]["dataPoints"]
    assert body["comparableSales"]["total"] == 1
    future = body["futureValuation"]["predictions"]
    assert len(future) == 4
    assert future[0]["period"] == "8_weeks"
    assert future[0]["changePercentage"] == pytest.approx(10.0)
    assert any(call[0] == market_data.PTW_URL for call in calls)
    assert any(url.endswith("/watches/rolex-126505") for url, _, _ in calls)


def test_predict_falls_back_to_saved_history_for_the_same_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(prediction_service, "ROOT", tmp_path)
    monkeypatch.delenv("KELLO_API_KEY", raising=False)
    monkeypatch.delenv("PRICETHATWATCH_API_KEY", raising=False)
    data_path = tmp_path / "data" / "model_history" / "126505.csv"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    build_history().to_csv(data_path, index=False)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == market_data.PTW_URL:
            return fake_response({"error": {"message": "rate limited"}}, status_code=429)
        return fake_response({"error": {"message": "not found"}}, status_code=404)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    response = client.post(
        "/predict",
        json={
            "serial": "126505",
            "price": 500,
            "brand": "Rolex",
            "reference": "126505",
            "model": "Daytona",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valuation"]["estimatedValue"] == pytest.approx(500.0)
    assert any("saved history 126505.csv" in item for item in body["dataQuality"]["limitations"])
    assert body["futureValuation"]["predictions"]


def test_predict_respects_live_false(tmp_path, monkeypatch):
    monkeypatch.setattr(prediction_service, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    build_history().to_csv(tmp_path / "data" / "watch_history.csv", index=False)

    calls = []

    def fail_get(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("network must not be called when live is false")

    monkeypatch.setattr(market_data.requests, "get", fail_get)
    response = client.post(
        "/predict",
        json={"serial": "X1", "price": 500, "brand": "Rolex", "reference": "126505", "live": False},
    )
    assert response.status_code == 200
    assert calls == []


def test_predict_hides_internal_errors(monkeypatch):
    def boom(request, live=True):
        raise RuntimeError("secret internal path /etc/foo")

    monkeypatch.setattr("api.build_prediction_payload", boom)
    response = client.post(
        "/predict",
        json={"serial": "X1", "price": 500, "brand": "Rolex", "reference": "126505"},
    )
    assert response.status_code == 500
    assert "secret" not in response.text


def test_predict_never_uses_demo_dataset_for_a_real_item(tmp_path, monkeypatch):
    monkeypatch.setattr(prediction_service, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    build_history().to_csv(tmp_path / "data" / "watch_history.csv", index=False)  # synthetic ~$450 demo
    response = client.post(
        "/predict",
        json={"price": 60000, "brand": "Rolex", "reference": "126500LN", "live": False},
    )
    assert response.status_code == 200
    body = response.json()
    valuation = body["valuation"]
    assert valuation["minimumValue"] <= valuation["estimatedValue"] <= valuation["maximumValue"]
    assert valuation["minimumValue"] > 10000
    assert body["priceHistory"]["dataPoints"] == []
    assert body["comparableSales"]["source"] == "none"
    assert body["futureValuation"]["predictions"][0]["estimatedValue"] == pytest.approx(60000.0)
