import re
from urllib.parse import urlparse

from watch_lookup import search_web

PRICE_RE = re.compile(
    r"(?P<symbol>[$€£])?\s*(?P<value>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{1,3}(?:\.\d{3})+|\d+(?:\.\d{1,2})?)\s*(?P<code>USD|EUR|GBP)?",
    re.IGNORECASE,
)


def parse_price(text):
    for match in PRICE_RE.finditer(text or ""):
        if not match.group("symbol") and not match.group("code"):
            continue
        raw = match.group("value")
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
            raw = raw.replace(".", "")
        value = float(raw.replace(",", ""))
        if 10 <= value <= 10_000_000:
            return value
    return None


def parse_currency(text, default="USD"):
    upper = (text or "").upper()
    if "€" in upper or "EUR" in upper:
        return "EUR"
    if "£" in upper or "GBP" in upper:
        return "GBP"
    if "$" in upper or "USD" in upper:
        return "USD"
    return default


def lookup_comparables(name, limit=5):
    query = f'"{name}" sold price'
    try:
        results = search_web(query, limit=limit)
        error = None
    except Exception as exc:
        results = []
        error = str(exc)
    items = []
    seen = set()
    for result in results:
        text = f"{result.title} {result.snippet}"
        price = parse_price(text)
        if price is None or result.url in seen:
            continue
        seen.add(result.url)
        items.append(
            {
                "id": f"web_{len(items) + 1}",
                "title": result.title,
                "price": price,
                "currency": parse_currency(text),
                "condition": "unknown",
                "soldAt": None,
                "source": urlparse(result.url).netloc or "Web",
                "similarityScore": 70,
                "url": result.url,
            }
        )
    return {"query": query, "items": items, "error": error}
