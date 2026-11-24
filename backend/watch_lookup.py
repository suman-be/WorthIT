from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
BING_RSS_URL = "https://www.bing.com/search"
USER_AGENT = "Mozilla/5.0"
MAX_SNIPPET_CHARS = 160
TIMEOUT_SECONDS = 10


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


def build_query(serial, ref=None, brand=None):
    token = str(ref or serial).strip()
    parts = ["watch"]
    if brand and str(brand).strip():
        parts.append(str(brand).strip())
    if token:
        parts.append(token)
    return " ".join(parts)


def parse_ddg_url(href):
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.rstrip("/") == "/l":
        targets = parse_qs(parsed.query).get("uddg", [])
        if targets:
            return unquote(targets[0])
    return href


def parse_ddg_results(html, limit):
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select("a.result-link")
    snippets = soup.select("td.result-snippet")
    results = []
    for index, link in enumerate(links[:limit]):
        title = link.get_text(" ", strip=True)
        url = parse_ddg_url(link.get("href", ""))
        snippet = ""
        if index < len(snippets):
            snippet = snippets[index].get_text(" ", strip=True)
        if not title or not url:
            continue
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet[:MAX_SNIPPET_CHARS],
                source=urlparse(url).netloc,
            )
        )
    return results


def parse_bing_rss(xml, limit):
    root = ElementTree.fromstring(xml)
    results = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        description = item.findtext("description") or ""
        snippet = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
        if not title or not url:
            continue
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet[:MAX_SNIPPET_CHARS],
                source=urlparse(url).netloc,
            )
        )
    return results


def search_web(query, limit=5):
    results = []
    try:
        response = requests.get(
            DDG_LITE_URL,
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        results = parse_ddg_results(response.text, limit)
    except requests.RequestException:
        results = []
    if results:
        return results
    try:
        response = requests.get(
            BING_RSS_URL,
            params={"q": query, "format": "rss"},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        return parse_bing_rss(response.text, limit)
    except (requests.RequestException, ElementTree.ParseError):
        return []


def lookup_watch(serial, ref=None, limit=5):
    query = build_query(serial, ref=ref)
    try:
        results = search_web(query, limit=limit)
        error = None
    except Exception as exc:
        results = []
        error = str(exc)
    return {
        "serial": serial,
        "query": query,
        "results": [asdict(result) for result in results],
        "error": error,
    }


def format_results(info):
    query = info.get("query", "")
    if info.get("error"):
        return [f'web lookup failed for "{query}": {info["error"]}']
    results = info.get("results", [])
    if not results:
        return [f'no web results found for "{query}"']
    lines = [f'web results for "{query}":']
    for index, result in enumerate(results, start=1):
        line = f'{index}. {result.get("title", "")}'
        if result.get("snippet"):
            line += f' - {result["snippet"]}'
        line += f' | {result.get("url", "")}'
        lines.append(line)
    return lines
