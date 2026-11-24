import json

import pytest
from fastapi.testclient import TestClient

import market_data
import watch_resolver
from api import app

client = TestClient(app)

NAUTILUS_SEARCH = [
    {"slug": "patek-philippe-nautilus-5711-1a-010", "reference_number": "5711/1A-010",
     "name": "Patek Philippe Nautilus 5711/1A-010", "brand": {"name": "Patek Philippe"},
     "current_market_price": 120000},
    {"slug": "patek-philippe-nautilus-5711-1r-001", "reference_number": "5711/1R-001",
     "name": "Patek Philippe Nautilus 5711/1R-001", "brand": {"name": "Patek Philippe"},
     "current_market_price": 150000},
]
NAUTILUS_DETAIL = {
    "data": {
        "slug": "patek-philippe-nautilus-5711-1a-010",
        "referenceNumber": "5711/1A-010",
        "name": "Patek Philippe Nautilus 5711/1A-010",
        "brand": {"name": "Patek Philippe"},
        "collection": "Nautilus",
        "case": {"diameterMm": 40, "material": "Stainless steel", "waterResistance": "120 m"},
        "movement": {"type": "Self-winding"},
        "retailPriceUsd": 35000,
        "currentMarketPrice": 120000,
    }
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def kello(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_resolver, "ROOT", tmp_path)
    monkeypatch.setenv("KELLO_API_KEY", "test-key")
    monkeypatch.setenv("USD_TO_EUR", "0.9")
    state = {"calls": [], "detail": NAUTILUS_DETAIL}

    def fake_get(url, params=None, headers=None, timeout=None):
        state["calls"].append((url, dict(params or {})))
        assert headers["Authorization"] == "Bearer test-key"
        if url.endswith("/watches"):
            query = str((params or {}).get("reference_number") or (params or {}).get("search") or "").upper()
            hits = [w for w in NAUTILUS_SEARCH if query and query in w["reference_number"].upper()]
            return FakeResponse({"data": hits})
        if "/watches/" in url:
            return FakeResponse(state["detail"])
        raise AssertionError(url)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    return state


def test_unknown_reference_is_resolved_from_kello(kello):
    response = client.post("/serial-lookups", json={"serial": "57111A010"})  # as the frontend sends it
    assert response.status_code == 200
    body = response.json()
    watch = body["watch"]
    assert watch["brand"] == "Patek Philippe"
    assert watch["model"] == "Nautilus"
    assert watch["reference"] == "5711/1A-010"
    assert watch["specs"] == {"movement": "automatic", "case_mm": 40.0, "material": "stainless-steel", "water_resistance_m": 120.0}
    assert watch["market"]["price"] == 31500  # list price 35000 USD * 0.9
    assert watch["market"]["resale_retention_pct"] == pytest.approx(342.9, abs=0.1)
    assert body["check"]["found"] is False
    assert "Kello" in body["check"]["authenticityNote"]


def test_without_list_price_uses_market_price_and_estimated_retention(kello):
    detail = json.loads(json.dumps(NAUTILUS_DETAIL))
    del detail["data"]["retailPriceUsd"]
    kello["detail"] = detail
    watch = client.post("/serial-lookups", json={"serial": "57111A010"}).json()["watch"]
    assert watch["market"]["price"] == 108000
    assert watch["market"]["resale_retention_pct"] == watch_resolver.DEFAULT_RETENTION_PCT


def test_model_name_is_derived_when_kello_has_no_model_field(kello):
    detail = json.loads(json.dumps(NAUTILUS_DETAIL))
    del detail["data"]["collection"]
    kello["detail"] = detail
    watch = client.post("/serial-lookups", json={"serial": "57111A010"}).json()["watch"]
    assert watch["model"] == "Nautilus"


def test_resolved_watch_is_remembered_for_the_detail_page(kello, tmp_path):
    watch_id = client.post("/serial-lookups", json={"serial": "57111A010"}).json()["watch"]["id"]
    saved = json.loads((tmp_path / "data" / "discovered_watches.json").read_text())
    assert saved[0]["id"] == watch_id
    kello["calls"].clear()
    assert client.get(f"/watches/{watch_id}").status_code == 200
    assert client.post("/serial-lookups", json={"serial": "57111A010"}).status_code == 200
    assert kello["calls"] == []  # served from the saved record


def test_never_returns_a_different_watch(kello):
    # "5711" matches two Nautilus references; neither is 5711/1A-011, so nothing may be returned.
    assert client.post("/serial-lookups", json={"serial": "57111A011"}).status_code == 404


def test_no_resolution_without_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(watch_resolver, "ROOT", tmp_path)
    monkeypatch.delenv("KELLO_API_KEY", raising=False)

    def fail(*args, **kwargs):
        raise AssertionError("no network call expected")

    monkeypatch.setattr(market_data.requests, "get", fail)
    assert client.post("/serial-lookups", json={"serial": "57111A010"}).status_code == 404


def test_no_resolution_without_fx_rate(kello, monkeypatch):
    monkeypatch.delenv("USD_TO_EUR", raising=False)
    assert client.post("/serial-lookups", json={"serial": "57111A010"}).status_code == 404


def test_daytona_126505_is_in_the_catalogue_without_any_key(monkeypatch):
    monkeypatch.delenv("KELLO_API_KEY", raising=False)
    body = client.post("/serial-lookups", json={"serial": "126505"}).json()
    assert body["watch"]["id"] == "rolex-cosmograph-daytona-126505"
    assert body["watch"]["specs"]["material"] == "gold"


def test_flatten_reads_nested_camel_case_fields():
    fields = watch_resolver.flatten({"brand": {"name": "Rolex"}, "name": "Daytona", "case": {"diameterMm": 40}})
    assert fields["brand"] == "Rolex"
    assert fields["name"] == "Daytona"  # a nested name never overrides the watch's own name
    assert watch_resolver.pick(fields, "case_mm") == 40


@pytest.mark.parametrize("text, expected", [("100.00 m", 100), ("10 bar", 100), ("5 ATM", 50), ("330 ft", 101)])
def test_parse_water_resistance(text, expected):
    assert watch_resolver.parse_water_resistance(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text, expected",
    [("18 ct Everose gold", "gold"), ("Oystersteel", "stainless-steel"), ("Grade 5 titanium", "titanium"), ("Velvet", None)],
)
def test_parse_material(text, expected):
    assert watch_resolver.parse_material(text) == expected


HUBLOT_SEARCH = [
    {"slug": "hublot-big-bang-431-rxr-2770-rx-vel", "reference_number": "431.RXR.2770.RX.VEL",
     "name": "Big Bang Original Soft Touch All Red 43 mm", "brand": "Hublot", "collection": "Big Bang"},
]
HUBLOT_DETAIL = {
    "data": {
        "slug": "hublot-big-bang-431-rxr-2770-rx-vel",
        "reference_number": "431.RXR.2770.RX.VEL",
        "name": "Big Bang Original Soft Touch All Red 43 mm",
        "brand": "Hublot",
        "collection": "Big Bang",
        "case": "43 mm Titanium",
        "movement": "Hublot caliber HUB1280",
        "retail_price": "€22.799",
        "active_listings": 0,
    }
}


def test_kello_page_shape_without_market_price_uses_euro_list_price(kello, monkeypatch):
    monkeypatch.delenv("USD_TO_EUR", raising=False)  # euro list price needs no conversion
    NAUTILUS_SEARCH.extend(HUBLOT_SEARCH)
    kello["detail"] = HUBLOT_DETAIL
    try:
        response = client.post("/serial-lookups", json={"serial": "431RXR2770RXVEL"})  # as the frontend sends it
    finally:
        del NAUTILUS_SEARCH[-1]
    assert response.status_code == 200
    watch = response.json()["watch"]
    assert watch["brand"] == "Hublot"
    assert watch["model"] == "Big Bang"
    assert watch["specs"]["case_mm"] == 43.0
    assert watch["specs"]["material"] == "titanium"
    assert watch["specs"]["movement"] == "automatic"  # "Hublot caliber HUB1280" has no type: estimated
    assert watch["market"]["price"] == 22799
    assert watch["market"]["resale_retention_pct"] == watch_resolver.DEFAULT_RETENTION_PCT


@pytest.mark.parametrize(
    "value, expected",
    [("€22.799", (22799.0, "EUR")), ("$59,100", (59100.0, "USD")), ("EUR 22 799,00", (22799.0, "EUR")),
     ({"amount": 46150, "currency": "eur"}, (46150.0, "EUR")), (22799, (22799.0, None)), ("", (None, None))],
)
def test_parse_money(value, expected):
    assert watch_resolver.parse_money(value) == expected


# Real shape of Kello's /watches and /watches/{slug} responses (captured with kello_probe.py):
# brand, collection (slug-like name), name and images only - no specs, no prices.
REAL_KELLO_ENTRY = {
    "id": 2721766,
    "slug": "hublot-431-rxr-2770-rx-vel",
    "reference_number": "431.RXR.2770.RX.VEL",
    "name": "Big Bang Original Soft Touch All Red 43 mm",
    "brand": {"id": 74, "slug": "hublot", "name": "Hublot", "country": None},
    "collection": {"id": 301, "slug": "big-bang", "name": "big-bang", "description": None},
    "images": [],
}


def test_real_kello_shape_with_price_from_price_that_watch(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_resolver, "ROOT", tmp_path)
    monkeypatch.setenv("KELLO_API_KEY", "test-key")
    monkeypatch.setenv("USD_TO_EUR", "0.9")

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == market_data.PTW_URL:
            assert params["brand"] == "Hublot"
            return FakeResponse({"market_summary": {"average_price": 20000}})
        if url.endswith("/watches"):
            query = str(params.get("reference_number") or params.get("search") or "").upper()
            hit = query and query in REAL_KELLO_ENTRY["reference_number"].upper()
            return FakeResponse({"data": [REAL_KELLO_ENTRY] if hit else []})
        if "/watches/" in url:
            return FakeResponse({"data": REAL_KELLO_ENTRY})
        raise AssertionError(url)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    response = client.post("/serial-lookups", json={"serial": "431RXR2770RXVEL"})
    assert response.status_code == 200
    watch = response.json()["watch"]
    assert watch["model"] == "Big Bang"
    assert watch["specs"]["case_mm"] == 43.0  # from the name
    assert watch["market"]["price"] == 18000  # 20000 USD * 0.9
    assert "Price That Watch" in response.json()["check"]["authenticityNote"]
