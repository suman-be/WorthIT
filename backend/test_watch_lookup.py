import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from generate_sample_data import build_history
from predict import main
import watch_lookup
from watch_lookup import build_query, format_results, lookup_watch, parse_ddg_url, search_web

DDG_HTML = """
<html><body>
<a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.rolex.com%2Fwatches%2Fdaytona&amp;rut=abc">Rolex Daytona 126505</a>
<td class="result-snippet">Cosmograph Daytona in Everose gold.</td>
<a class="result-link" href="https://watchcharts.com/model/46430">Ref. 126505</a>
<td class="result-snippet">Market price $55,088.</td>
</body></html>
"""

BING_XML = """<?xml version="1.0"?><rss version="2.0"><channel><item><title>Bing Rolex 126505</title><link>https://example.com/rolex</link><description>Bing &lt;b&gt;snippet&lt;/b&gt;.</description></item></channel></rss>"""


def test_build_query_uses_serial_and_optional_ref():
    assert build_query("126505") == "watch 126505"
    assert build_query("126505", ref="126505", brand="Rolex") == "watch Rolex 126505"


def test_parse_ddg_url_decodes_redirect():
    url = parse_ddg_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.rolex.com%2Fwatches%2Fdaytona&rut=abc")
    assert url == "https://www.rolex.com/watches/daytona"


def test_search_web_parses_ddg_results(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == watch_lookup.DDG_LITE_URL
        assert params == {"q": "watch 126505"}
        return SimpleNamespace(text=DDG_HTML)

    monkeypatch.setattr(watch_lookup.requests, "get", fake_get)
    results = search_web("watch 126505", limit=5)
    assert len(results) == 2
    assert results[0].title == "Rolex Daytona 126505"
    assert results[0].url == "https://www.rolex.com/watches/daytona"
    assert results[0].snippet.startswith("Cosmograph Daytona")
    assert results[0].source == "www.rolex.com"


def test_search_web_limits_results(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return SimpleNamespace(text=DDG_HTML)

    monkeypatch.setattr(watch_lookup.requests, "get", fake_get)
    results = search_web("watch 126505", limit=1)
    assert len(results) == 1
    assert results[0].title == "Rolex Daytona 126505"


def test_search_web_falls_back_to_bing_rss(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        if url == watch_lookup.DDG_LITE_URL:
            return SimpleNamespace(text="<html></html>")
        assert url == watch_lookup.BING_RSS_URL
        return SimpleNamespace(text=BING_XML)

    monkeypatch.setattr(watch_lookup.requests, "get", fake_get)
    results = search_web("watch 126505")
    assert len(results) == 1
    assert results[0].title == "Bing Rolex 126505"
    assert results[0].url == "https://example.com/rolex"
    assert "Bing snippet" in results[0].snippet


def test_lookup_watch_reports_network_error(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(watch_lookup, "search_web", fail)
    info = lookup_watch("126505")
    assert info["query"] == "watch 126505"
    assert info["error"] == "boom"
    assert format_results(info)[0].startswith("web lookup failed")


def test_format_results_handles_no_results():
    info = {"query": "watch 000", "results": [], "error": None}
    assert format_results(info) == ['no web results found for "watch 000"']


def test_predict_uses_web_lookup_on_catalog_miss(tmp_path, monkeypatch, capsys):
    data_path = tmp_path / "history.csv"
    build_history().to_csv(data_path, index=False)
    catalog_path = tmp_path / "catalog.csv"
    pd.DataFrame([{"serial": "OTHER", "description": "Other watch."}]).to_csv(catalog_path, index=False)

    def fake_lookup(serial, ref=None):
        return {
            "serial": serial,
            "query": f"watch {serial}",
            "results": [
                {
                    "title": "Rolex Daytona 126505",
                    "url": "https://example.com/rolex",
                    "snippet": "Rose gold chronograph",
                    "source": "example.com",
                }
            ],
            "error": None,
        }

    monkeypatch.setattr("predict.lookup_watch", fake_lookup)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "predict.py",
            "--serial",
            "126505",
            "--price",
            "55000",
            "--data",
            str(data_path),
            "--serials",
            str(tmp_path / "missing.csv"),
            "--catalog",
            str(catalog_path),
            "--predictions",
            str(tmp_path / "predictions.csv"),
            "--info-only",
        ],
    )
    main()
    output = capsys.readouterr().out
    assert "no catalog entry for serial 126505" in output
    assert 'web results for "watch 126505"' in output
    assert "Rolex Daytona 126505" in output
    assert "predicted price" not in output
