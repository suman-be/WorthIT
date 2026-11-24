import argparse

from market_data import (
    fetch_kello_history,
    fetch_valuation,
    fetch_watch_history,
    kello_key,
    save_history,
    save_valuation,
)


def main():
    parser = argparse.ArgumentParser(description="Fetch free watch valuation and dated price history")
    parser.add_argument("--brand", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--model")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--provider", choices=("kello", "nuvinty"), default="kello")
    args = parser.parse_args()
    valuation = None
    try:
        valuation = fetch_valuation(args.brand, args.ref)
    except Exception as exc:
        print(f"valuation failed: {exc}")
        print("tip: set PRICETHATWATCH_API_KEY for a free private key by email")
    else:
        sample_size = valuation.get("sample_size")
        suffix = f" from {sample_size} listings" if sample_size else ""
        valuation_file = save_valuation(args.ref, valuation)
        print(
            f"valuation: {valuation['brand']} {valuation['reference']} "
            f"${valuation['average_price']:,.2f}{suffix}"
        )
        if valuation.get("floor_price") is not None and valuation.get("ceiling_price") is not None:
            print(f"range: ${valuation['floor_price']:,.2f} - ${valuation['ceiling_price']:,.2f}")
        print(f"saved valuation: {valuation_file}")
    result = None
    if args.provider == "kello":
        if kello_key():
            try:
                result = fetch_kello_history(args.brand, args.ref)
            except Exception as exc:
                print(f"Kello failed: {exc}")
        else:
            print("KELLO_API_KEY is not set; falling back to Nuvinty")
        if result is None:
            try:
                result = fetch_watch_history(args.brand, args.ref, model=args.model, currency=args.currency)
            except Exception as exc:
                print(f"Nuvinty failed: {exc}")
                return
    else:
        try:
            result = fetch_watch_history(args.brand, args.ref, model=args.model, currency=args.currency)
        except Exception as exc:
            print(f"Nuvinty failed: {exc}")
            return
    frame = result["history"]
    if frame.empty:
        print(f"no {args.currency} history for query '{result['query']}'")
        if result["currencies"]:
            print(f"available currencies: {', '.join(result['currencies'])}")
        print("tip: pass --model like 'rolex daytona'")
        return
    path = save_history(args.ref, frame)
    if valuation is None and result.get("current_price"):
        valuation = {
            "brand": args.brand,
            "reference": args.ref,
            "average_price": result["current_price"],
            "floor_price": None,
            "ceiling_price": None,
            "sample_size": None,
            "source": "Kello",
        }
        valuation_file = save_valuation(args.ref, valuation)
        print(f"valuation: {args.brand} {args.ref} ${result['current_price']:,.2f} from Kello")
        print(f"saved valuation: {valuation_file}")
    print(f"history source: {result.get('price_source', 'Nuvinty')}")
    print(f"history: {result['item']} ({result['url']})")
    print(f"saved {len(frame)} weekly prices to {path}")
    print(f"latest: ${frame['price'].iloc[-1]:,.2f} on {frame['week_start'].iloc[-1].date()}")


if __name__ == "__main__":
    main()
