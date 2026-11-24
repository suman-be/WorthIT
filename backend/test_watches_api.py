"""Contract tests: responses must pass the frontend's validators in frontend/src/api/schema.ts."""
import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import market_data
from api import app

client = TestClient(app)

MOVEMENTS = {"automatic", "manual", "quartz", "spring-drive"}
MATERIALS = {"stainless-steel", "titanium", "ceramic", "bronze", "gold", "platinum"}
AUTHENTICITY = {"consistent", "inconsistent", "unverified"}
STOLEN = {"clear", "reported", "unavailable"}
FRONTEND_ORIGIN = "http://localhost:5173"


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def assert_watch(watch):
    """Mirror of parseWatch() in schema.ts."""
    for key in ("id", "brand", "model", "reference"):
        assert isinstance(watch[key], str)
    specs, market, ownership = watch["specs"], watch["market"], watch["ownership"]
    assert specs["movement"] in MOVEMENTS
    assert specs["material"] in MATERIALS
    assert is_number(specs["case_mm"]) and is_number(specs["water_resistance_m"])
    for key in ("price", "resale_retention_pct", "popularity_trend"):
        assert is_number(market[key])
    for key in ("service_interval_years", "service_cost"):
        assert is_number(ownership[key])


def assert_check(check):
    """Mirror of parseSerialCheck() in schema.ts."""
    assert isinstance(check["serial"], str)
    assert isinstance(check["found"], bool)
    assert check["productionYear"] is None or is_number(check["productionYear"])
    assert check["productionBatch"] is None or isinstance(check["productionBatch"], str)
    assert check["authenticity"] in AUTHENTICITY
    assert isinstance(check["authenticityNote"], str)
    assert isinstance(check["serviceHistory"], list)
    for record in check["serviceHistory"]:
        assert all(isinstance(record[key], str) for key in ("date", "description", "servicedBy"))
    assert check["stolenCheck"] in STOLEN
    assert isinstance(check["checkedAt"], str)


def test_get_watch_matches_frontend_schema():
    response = client.get("/watches/rolex-submariner-124060")
    assert response.status_code == 200
    assert_watch(response.json())


def test_get_watch_unknown_returns_404_in_frontend_error_format():
    response = client.get("/watches/does-not-exist")
    assert response.status_code == 404
    assert isinstance(response.json()["error"]["message"], str)


def test_get_watches_by_ids_keeps_order_and_skips_unknown():
    response = client.get("/watches?ids=grand-seiko-sbga211,nope,rolex-submariner-124060")
    assert response.status_code == 200
    body = response.json()
    assert [watch["id"] for watch in body] == ["grand-seiko-sbga211", "rolex-submariner-124060"]
    for watch in body:
        assert_watch(watch)


def test_get_watches_without_ids_returns_catalogue():
    body = client.get("/watches").json()
    assert len(body) >= 6
    for watch in body:
        assert_watch(watch)


def test_serial_lookup_normalises_and_matches_schema():
    response = client.post("/serial-lookups", json={"serial": "om55-12903"})
    assert response.status_code == 200
    body = response.json()
    assert_watch(body["watch"])
    assert_check(body["check"])
    assert body["check"]["serial"] == "OM5512903"
    assert body["check"]["serviceHistory"]


def test_serial_never_changes_the_scored_watch():
    looked_up = client.post("/serial-lookups", json={"serial": "TD58A2099"}).json()
    plain = client.get("/watches/tudor-black-bay-58-m79030n").json()
    assert looked_up["watch"] == plain
    assert looked_up["check"]["stolenCheck"] == "reported"


def test_serial_lookup_unknown_is_404():
    response = client.post("/serial-lookups", json={"serial": "00004417"})
    assert response.status_code == 404
    assert "serial" in response.json()["error"]["message"]


@pytest.mark.parametrize("serial", ["", "AB", "ABC$123", "A" * 21])
def test_serial_lookup_invalid_is_422_with_field(serial):
    response = client.post("/serial-lookups", json={"serial": serial})
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "serial"


def test_cors_preflight_allows_frontend_with_credentials():
    response = client.options(
        "/serial-lookups",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_unknown_origin():
    response = client.get("/watches", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_market_data_is_enriched_from_saved_history_and_valuation(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.setenv("USD_TO_EUR", "0.9")
    weeks = pd.date_range("2024-01-07", periods=104, freq="W-SUN")
    history = pd.DataFrame(
        {"week_start": weeks, "sku": "124060", "price": [10000 * 1.10 ** (i / 52) for i in range(104)]}
    )
    market_data.save_history("124060", history)
    market_data.save_valuation("124060", {"average_price": 12000})
    market = client.get("/watches/rolex-submariner-124060").json()["market"]
    assert market["popularity_trend"] == pytest.approx(0.10, abs=0.005)
    assert market["resale_retention_pct"] == pytest.approx(12000 * 0.9 / 9550 * 100, abs=0.1)


def test_market_data_keeps_catalogue_values_without_fx_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.delenv("USD_TO_EUR", raising=False)
    market_data.save_valuation("124060", {"average_price": 12000})
    assert client.get("/watches/rolex-submariner-124060").json()["market"]["resale_retention_pct"] == 115


def test_price_history_is_monthly_and_converted_with_fx_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.setenv("USD_TO_EUR", "0.5")
    weeks = pd.date_range("2024-01-07", periods=12, freq="W-SUN")
    market_data.save_history("124060", pd.DataFrame({"week_start": weeks, "sku": "124060", "price": [10000.0] * 12}))
    body = client.get("/watches/rolex-submariner-124060/price-history").json()
    assert body["currency"] == "EUR" and body["source"] == "market"
    assert [p["date"][:7] for p in body["points"]] == ["2024-01", "2024-02", "2024-03"]
    assert all(p["price"] == 5000 for p in body["points"])


def test_price_history_without_saved_data_is_empty_and_keeps_usd_without_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.delenv("USD_TO_EUR", raising=False)
    body = client.get("/watches/rolex-submariner-124060/price-history").json()
    assert body == {
        "watchId": "rolex-submariner-124060",
        "currency": "USD",
        "source": "market",
        "sourceName": None,
        "sourceUrl": None,
        "points": [],
        "forecast": None,
    }


def recent_history(growth, weeks=104, end=None):
    end = end or pd.Timestamp.now().normalize()
    dates = pd.date_range(end=end, periods=weeks, freq="W-SUN")
    prices = [10000 * (1 + growth) ** (i / 52) for i in range(weeks)]
    return pd.DataFrame({"week_start": dates, "sku": "124060", "price": prices})


def test_price_history_includes_a_read_only_forecast_with_a_range(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.setenv("USD_TO_EUR", "0.5")
    history = recent_history(0.10)
    market_data.save_history("124060", history)
    before = set(tmp_path.rglob("*"))
    forecast = client.get("/watches/rolex-submariner-124060/price-history").json()["forecast"]
    assert set(tmp_path.rglob("*")) == before  # nothing written
    assert [p["date"] > history["week_start"].iloc[-1].strftime("%Y-%m-%d") for p in forecast["points"]] == [True] * 4
    assert [p["date"] for p in forecast["points"]] == sorted(p["date"] for p in forecast["points"])
    last_price = history["price"].iloc[-1] * 0.5
    for point in forecast["points"]:
        assert point["low"] <= point["price"] <= point["high"]
    # A rising history gives a rising 12-month estimate, and the range widens with the horizon.
    assert forecast["points"][-1]["price"] > last_price
    widths = [p["high"] - p["low"] for p in forecast["points"][1:]]
    assert widths == sorted(widths)
    assert isinstance(forecast["explanation"], str)


def test_price_history_has_no_forecast_when_saved_history_is_out_of_date(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    old_end = pd.Timestamp.now().normalize() - pd.Timedelta(days=400)
    market_data.save_history("124060", recent_history(0.10, end=old_end))
    body = client.get("/watches/rolex-submariner-124060/price-history").json()
    assert body["points"]
    assert body["forecast"] is None


def test_price_history_has_no_forecast_when_history_is_too_thin(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    market_data.save_history("124060", recent_history(0.10, weeks=4))
    assert client.get("/watches/rolex-submariner-124060/price-history").json()["forecast"] is None


def test_price_history_from_list_prices_is_labelled(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    market_data.save_history("124060", recent_history(0.10))
    market_data.save_history_source("124060", "Nuvinty", "list", "https://nuvinty.com/x")
    body = client.get("/watches/rolex-submariner-124060/price-history").json()
    assert body["source"] == "list"
    assert body["sourceName"] == "Nuvinty"
    assert body["sourceUrl"] == "https://nuvinty.com/x"
    assert body["points"]


def list_history(prices, end=None):
    end = end or pd.Timestamp.now().normalize()
    years = len(prices) - 1
    dates = [end - pd.DateOffset(years=years - i) for i in range(len(prices))]
    return pd.DataFrame({"week_start": dates, "sku": "124060", "price": prices})


def save_list_history(tmp_path, monkeypatch, frame):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    monkeypatch.setenv("USD_TO_EUR", "0.5")
    market_data.save_history("124060", frame)
    market_data.save_history_source("124060", "Nuvinty", "list", "https://nuvinty.com/x")
    return client.get("/watches/rolex-submariner-124060/price-history").json()


def test_list_price_outlook_keeps_the_average_rise_with_no_rise_as_the_floor(tmp_path, monkeypatch):
    body = save_list_history(tmp_path, monkeypatch, list_history([8000.0, 9000.0, 10000.0]))
    outlook = body["forecast"]
    assert body["source"] == "list"
    assert "not a resale forecast" in outlook["explanation"]
    last = 10000.0 * 0.5
    first, second = outlook["points"]
    assert second["date"] > first["date"] > body["points"][-1]["date"]
    for point in outlook["points"]:
        assert point["low"] == last  # list prices are not expected to fall
        assert point["low"] < point["price"] < point["high"]
    assert second["price"] > first["price"]
    assert first["price"] == pytest.approx(last * ((10000 / 8000) ** 0.5), rel=0.01)


def test_list_price_outlook_caps_the_assumed_yearly_rise(tmp_path, monkeypatch):
    body = save_list_history(tmp_path, monkeypatch, list_history([1000.0, 5000.0, 25000.0]))
    first = body["forecast"]["points"][0]
    assert first["price"] <= 25000.0 * 0.5 * 1.2 + 1


def test_list_price_outlook_needs_two_years_a_rise_and_a_recent_price(tmp_path, monkeypatch):
    short = pd.DataFrame(
        {
            "week_start": [pd.Timestamp.now().normalize() - pd.DateOffset(months=6), pd.Timestamp.now().normalize()],
            "sku": "124060",
            "price": [9000.0, 10000.0],
        }
    )
    assert save_list_history(tmp_path, monkeypatch, short)["forecast"] is None
    assert save_list_history(tmp_path, monkeypatch, list_history([10000.0, 10000.0, 10000.0]))["forecast"] is None
    assert save_list_history(tmp_path, monkeypatch, list_history([11000.0, 10500.0, 10000.0]))["forecast"] is None
    old_end = pd.Timestamp.now().normalize() - pd.DateOffset(years=2)
    assert save_list_history(tmp_path, monkeypatch, list_history([8000.0, 9000.0, 10000.0], end=old_end))["forecast"] is None


def test_history_source_defaults_to_market_when_missing_or_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "ROOT", tmp_path)
    assert market_data.load_history_source("124060")["kind"] == "market"
    market_data.source_path("124060").parent.mkdir(parents=True, exist_ok=True)
    market_data.source_path("124060").write_text("{not json", encoding="utf-8")
    assert market_data.load_history_source("124060") == {"provider": "", "kind": "market", "url": ""}
    market_data.source_path("124060").write_text('{"kind": "surprise"}', encoding="utf-8")
    assert market_data.load_history_source("124060")["kind"] == "market"


def test_price_history_unknown_watch_is_404():
    response = client.get("/watches/does-not-exist/price-history")
    assert response.status_code == 404
    assert isinstance(response.json()["error"]["message"], str)


def test_predict_validation_errors_use_frontend_format():
    response = client.post("/predict", json={"price": 0, "brand": "Rolex", "reference": "126505"})
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "price"


@pytest.mark.parametrize(
    "entered, watch_id",
    [
        ("124060", "rolex-submariner-124060"),
        ("310.30.42.50.01.001", "omega-speedmaster-310-30-42-50-01-001"),
        ("31030425001001", "omega-speedmaster-310-30-42-50-01-001"),
        ("M79030N-0001", "tudor-black-bay-58-m79030n"),
        ("m79030n", "tudor-black-bay-58-m79030n"),
        ("79030N", "tudor-black-bay-58-m79030n"),
        ("sbga 211", "grand-seiko-sbga211"),
    ],
)
def test_lookup_falls_back_to_reference_number(entered, watch_id):
    response = client.post("/serial-lookups", json={"serial": entered})
    assert response.status_code == 200
    body = response.json()
    assert body["watch"]["id"] == watch_id
    assert body["watch"] == client.get(f"/watches/{watch_id}").json()
    check = body["check"]
    assert_check(check)
    assert check["found"] is False
    assert check["authenticity"] == "unverified"
    assert check["stolenCheck"] == "unavailable"
    assert check["productionYear"] is None
    assert check["serviceHistory"] == []
    assert "reference number" in check["authenticityNote"]


def test_registry_serial_takes_precedence_over_reference():
    check = client.post("/serial-lookups", json={"serial": "OM5512903"}).json()["check"]
    assert check["found"] is True
    assert check["serviceHistory"]


def test_unknown_input_with_symbols_is_still_422():
    response = client.post("/serial-lookups", json={"serial": "999.999.999"})
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "serial"
