"""Refresh the saved price history of every catalogue watch.

Safe to run on a schedule: a history that is still recent is skipped, and a failed or empty
fetch never replaces a history that was saved earlier.

    python refresh_histories.py              # refresh histories older than 7 days
    python refresh_histories.py --force      # refresh all of them
"""

import argparse
import json
import time
from datetime import datetime, timezone

import market_data
from config import WATCHES_PATH

DEFAULT_MAX_AGE_DAYS = 7
PAUSE_SECONDS = 2


def catalogue():
    path = market_data.ROOT / WATCHES_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def age_days(path, now):
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (now - modified).total_seconds() / 86400


def fetch(watch):
    """Kello (resale prices) when a key is set and it has data, otherwise Nuvinty (brand list prices)."""
    if market_data.kello_key():
        try:
            result = market_data.fetch_kello_history(watch["brand"], watch["reference"])
            if not result["history"].empty:
                return result, "market"
        except Exception as exc:
            print(f"  Kello failed: {exc}")
    result = market_data.fetch_watch_history(watch["brand"], watch["reference"], model=watch.get("model"))
    return result, "list"


def refresh(watch, now, max_age_days, force):
    reference = watch["reference"]
    existing = market_data.history_path(reference)
    if existing.exists() and not force and age_days(existing, now) < max_age_days:
        return "skipped (recent)"
    try:
        result, kind = fetch(watch)
    except Exception as exc:
        return f"failed, kept the old history ({exc})"
    frame = result["history"]
    if frame.empty:
        return "no data found, kept the old history" if existing.exists() else "no data found"
    market_data.save_history(reference, frame)
    provider = result.get("provider", "Nuvinty")
    market_data.save_history_source(reference, provider, kind, result.get("url", ""))
    return f"saved {len(frame)} prices, latest {frame['week_start'].iloc[-1].date()} ({provider}, {kind})"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Refresh saved price histories for the catalogue")
    parser.add_argument("--force", action="store_true", help="refresh even recent histories")
    parser.add_argument("--max-age-days", type=float, default=DEFAULT_MAX_AGE_DAYS)
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    outcomes = {}
    for index, watch in enumerate(catalogue()):
        if index:
            time.sleep(PAUSE_SECONDS)
        outcome = refresh(watch, now, args.max_age_days, args.force)
        outcomes[watch["id"]] = outcome
        print(f"{watch['id']}: {outcome}")
    return outcomes


if __name__ == "__main__":
    main()
