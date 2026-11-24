"""Show which fields Kello returns for a reference, and what the resolver makes of them.

    $env:KELLO_API_KEY = "..."; $env:USD_TO_EUR = "0.86"
    python kello_probe.py 126505

Kello's API is not publicly documented. If a value below says "(not found)" while you can
see it in the raw fields, add that field name to FIELD_NAMES in watch_resolver.py.
The API key is never printed.
"""
import json
import sys

import market_data
import watch_resolver


def show(title, payload):
    print(f"\n== {title}")
    for key, value in sorted(watch_resolver.flatten(payload).items()):
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        print(f"  {key:40} {text[:80]}")


def probe_other_endpoints(summary, reference):
    """Kello's /watches/{slug} has no specs or prices; check whether other endpoints do."""
    key = market_data.kello_key()
    slug = summary.get("slug") or summary.get("id")
    watch_id = summary.get("id")
    candidates = [
        (f"/watches/{slug}/specs", None),
        (f"/watches/{slug}/specifications", None),
        (f"/watches/{slug}/prices", None),
        (f"/watches/{slug}/price-history", None),
        (f"/watches/{slug}/market-data", None),
        (f"/watches/{slug}", {"include": "specs,prices,specifications,market_data"}),
        ("/market-data/prices", {"watch_slug": slug}),
        ("/market-data/prices", {"watch_id": watch_id}),
        ("/market-data/prices", {"reference_number": reference}),
        (f"/market-data/watches/{slug}", None),
        ("/prices", {"watch_slug": slug}),
    ]
    results = {}
    print("\n== other endpoints")
    for path, params in candidates:
        label = path + (f"?{params}" if params else "")
        try:
            payload = market_data.kello_get(path, key, params)
            text = json.dumps(payload, ensure_ascii=False)
            print(f"  OK   {label}  ({len(text)} chars)")
            results[label] = payload
        except Exception as exc:
            print(f"  --   {label}  ({str(exc)[:60]})")
            results[label] = f"error: {str(exc)[:200]}"
    return results


def main():
    if len(sys.argv) != 2:
        print("usage: python kello_probe.py <reference>")
        return 2
    reference = sys.argv[1]
    if not market_data.kello_key():
        print("KELLO_API_KEY is not set")
        return 1
    try:
        summary, detail = watch_resolver.fetch_kello(reference)
    except watch_resolver.ResolutionUnavailable as exc:
        print(f"not found: {exc}")
        return 1
    show("search result (raw fields)", summary)
    show("detail (raw fields)", detail)
    extra = probe_other_endpoints(summary, reference)
    raw_file = market_data.ROOT / "data" / f"kello_probe_{market_data.safe_name(reference)}.json"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text(
        json.dumps({"search": summary, "detail": detail, "other_endpoints": extra}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nraw response saved to {raw_file}")
    fields = {**watch_resolver.flatten(summary), **watch_resolver.flatten(detail)}
    print("\n== what the resolver reads")
    for what in watch_resolver.FIELD_NAMES:
        value = watch_resolver.pick(fields, what)
        print(f"  {what:12} {value if value is not None else '(not found)'}")
    print(f"  {'market_usd':12} {market_data.current_kello_price(summary, detail)}")
    try:
        watch = watch_resolver.resolve_reference(reference)
    except watch_resolver.ResolutionUnavailable as exc:
        print(f"\nresolver stopped: {exc}")
        return 1
    print("\n== watch the app will show")
    print(json.dumps(watch, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
