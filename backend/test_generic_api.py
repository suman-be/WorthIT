from fastapi.testclient import TestClient

import item_lookup
import market_data
import prediction_service
from api import app
from item_lookup import parse_price

client = TestClient(app)


def failing_get(*args, **kwargs):
    raise AssertionError("network must not be called in this test")


def test_parse_price_requires_currency_marker():
    assert parse_price("MacBook Pro $1,899 used") == 1899.0
    assert parse_price("Prix €1.899") == 1899.0
    assert parse_price("Model M4 14 inch 126505") is None


def test_predict_accepts_non_watch_item_with_inline_market_data(tmp_path, monkeypatch):
    monkeypatch.setattr(prediction_service, "ROOT", tmp_path)
    monkeypatch.setattr(market_data.requests, "get", failing_get)
    response = client.post(
        "/predict",
        json={
            "identifier": "MBP-M4-14",
            "name": "MacBook Pro 14 M4",
            "category": "Electronics",
            "price": 1999,
            "currency": "USD",
            "releaseYear": 2025,
            "condition": {"grade": "like_new"},
            "priceHistory": [
                {"date": "2025-01-15", "averageValue": 2400},
                {"date": "2025-03-15", "averageValue": 2280},
                {"date": "2025-05-15", "averageValue": 2150},
                {"date": "2025-07-15", "averageValue": 2020},
                {"date": "2025-09-15", "averageValue": 1875},
                {"date": "2025-11-15", "averageValue": 1750},
            ],
            "comparableSales": [
                {
                    "id": "sale_1",
                    "title": "MacBook Pro 14 M4",
                    "price": 1850,
                    "currency": "USD",
                    "condition": "good",
                    "soldAt": "2026-10-01",
                    "source": "Marketplace",
                    "similarityScore": 95,
                },
                {
                    "id": "sale_2",
                    "title": "MacBook Pro 14 M4",
                    "price": 1925,
                    "currency": "USD",
                    "condition": "like_new",
                    "soldAt": "2026-10-20",
                    "source": "Reseller",
                    "similarityScore": 92,
                },
            ],
            "live": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["item"]["category"] == "Electronics"
    assert body["item"]["name"] == "MacBook Pro 14 M4"
    assert body["valuation"]["estimatedValue"] == 1999.0
    assert body["comparableSales"]["source"] == "provided"
    assert body["comparableSales"]["total"] == 2
    assert body["priceHistory"]["dataPoints"]
    future = {item["period"]: item for item in body["futureValuation"]["predictions"]}
    assert future["8_weeks"]["estimatedValue"] < 1999.0
    assert future["12_months"]["estimatedValue"] < future["8_weeks"]["estimatedValue"]
    assert "observed price trend" in body["futureValuation"]["explanation"]


def test_predict_uses_web_comparables_for_generic_items(tmp_path, monkeypatch):
    monkeypatch.setattr(prediction_service, "ROOT", tmp_path)
    monkeypatch.setattr(market_data.requests, "get", failing_get)
    monkeypatch.setattr(
        item_lookup,
        "lookup_comparables",
        lambda name, limit=5: {
            "query": f'"{name}" sold price',
            "error": None,
            "items": [
                {
                    "id": "web_1",
                    "title": "MacBook Pro 14 M4 sold",
                    "price": 1900,
                    "currency": "USD",
                    "condition": "unknown",
                    "soldAt": "2026-10-05",
                    "source": "example.com",
                    "similarityScore": 70,
                    "url": "https://example.com/sale/1",
                },
                {
                    "id": "web_2",
                    "title": "MacBook Pro 14 M4 sold",
                    "price": 1950,
                    "currency": "USD",
                    "condition": "unknown",
                    "soldAt": "2026-10-12",
                    "source": "example.com",
                    "similarityScore": 70,
                    "url": "https://example.com/sale/2",
                },
            ],
        },
    )
    response = client.post(
        "/predict",
        json={
            "identifier": "MBP-M4-14",
            "name": "MacBook Pro 14 M4",
            "category": "Electronics",
            "price": 1999,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["item"]["category"] == "Electronics"
    assert body["comparableSales"]["source"] == "web"
    assert body["comparableSales"]["total"] == 2
    assert body["priceHistory"]["dataPoints"]
    assert any(
        "not verified transactions" in item
        for item in body["dataQuality"]["limitations"]
    )


def test_predict_requires_some_item_identity():
    response = client.post("/predict", json={"price": 100, "category": "Collectibles"})
    assert response.status_code == 422
