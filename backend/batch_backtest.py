"""Fetch price history for a list of references and backtest the model on each.

This answers the proof-of-concept question: does the seasonal model beat
"the price stays where it is" on real watch prices, not just on sample data?

    python batch_backtest.py                      # fetch + backtest data/references.csv
    python batch_backtest.py --skip-fetch         # reuse data/model_history/*.csv
    python batch_backtest.py --interpolate        # fill short gaps in sparse (e.g. monthly) data
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import market_data
from backtest import run_backtest, summarize
from config import HORIZON_WEEKS, MIN_HISTORY_WEEKS

ROOT = Path(__file__).parent
REFERENCES_PATH = "data/references.csv"
RESULTS_PATH = "data/batch_backtest.csv"
MIN_POINTS = 20          # fewer scored forecasts than this is noise, not evidence
MIN_REFERENCES = 3       # fewer judged references than this is an anecdote, not a conclusion
WIN_MARGIN = 0.9         # model must cut last_price's error by at least 10% to count as a win
MAX_WEEKLY_GAP_DAYS = 10 # median gap above this means the data is not really weekly
INTERPOLATE_LIMIT_WEEKS = 6


def load_references(path):
    frame = pd.read_csv(path, dtype=str).fillna("")
    missing = {"brand", "reference"} - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")
    return frame.to_dict("records")


def fetch_reference(ref, provider, currency):
    """Fetch and save history for one reference. Returns (source, error)."""
    brand, reference, model = ref["brand"], ref["reference"], ref.get("model") or None
    errors = []
    if provider in ("auto", "kello"):
        if market_data.kello_key():
            try:
                result = market_data.fetch_kello_history(brand, reference)
                market_data.save_history(reference, result["history"])
                return "Kello", None
            except Exception as exc:
                errors.append(f"Kello: {exc}")
        elif provider == "kello":
            return None, "KELLO_API_KEY is not set"
    if provider in ("auto", "nuvinty"):
        try:
            result = market_data.fetch_watch_history(brand, reference, model=model, currency=currency)
            if result["history"].empty:
                errors.append(f"Nuvinty: no {currency} history for '{result['query']}'")
            else:
                market_data.save_history(reference, result["history"])
                return "Nuvinty", None
        except Exception as exc:
            errors.append(f"Nuvinty: {exc}")
    return None, "; ".join(errors) or "no provider succeeded"


def load_reference_history(reference):
    path = market_data.history_path(reference)
    if not path.exists():
        return None
    frame = pd.read_csv(path, parse_dates=["week_start"])
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna(subset=["week_start", "price"])
    return frame.sort_values("week_start").drop_duplicates("week_start", keep="last").reset_index(drop=True)


def describe_history(frame):
    if frame is None or frame.empty:
        return {"rows": 0, "span_weeks": 0, "median_gap_days": None}
    gaps = frame["week_start"].diff().dt.days.dropna()
    return {
        "rows": len(frame),
        "span_weeks": int((frame["week_start"].iloc[-1] - frame["week_start"].iloc[0]).days // 7),
        "median_gap_days": float(gaps.median()) if not gaps.empty else None,
    }


def interpolate_weekly(frame, limit_weeks=INTERPOLATE_LIMIT_WEEKS):
    """Put sparse history on a weekly grid, filling gaps of at most ``limit_weeks``.

    Interpolated weeks are smoother than reality, so results on interpolated data
    flatter every model; treat them as indicative only.
    """
    weekly = frame.set_index("week_start")["price"].resample("W-SUN").mean()
    weekly = weekly.interpolate(method="time", limit=limit_weeks, limit_area="inside").dropna()
    out = weekly.reset_index()
    out["sku"] = frame["sku"].iloc[0] if "sku" in frame.columns and not frame.empty else ""
    return out


def verdict(row):
    if row["points"] < MIN_POINTS:
        return "too little data"
    if row["model_mape"] < row["last_price_mape"] * WIN_MARGIN:
        return "model wins"
    if row["model_mape"] <= row["last_price_mape"]:
        return "marginal"
    return "no edge"


def evaluate_reference(frame):
    results = run_backtest(frame, all_weeks=True)
    if results.empty:
        return None
    summary = summarize(results)
    return {
        "points": int(summary.loc["seasonal_model", "n"]),
        "model_mape": float(summary.loc["seasonal_model", "mape"]),
        "model_bias_pct": float(
            (results.loc[results["model"] == "seasonal_model", "error"]
             / results.loc[results["model"] == "seasonal_model", "actual"]).mean()
        ),
        "last_price_mape": float(summary.loc["last_price", "mape"]),
        "q4_only_mape": float(summary.loc["q4_only_model", "mape"]),
    }


def run(references, fetch=True, provider="auto", currency="USD", interpolate=False):
    rows = []
    for ref in references:
        reference = ref["reference"]
        label = f"{ref['brand']} {reference}"
        row = {"watch": label, "source": "saved", "error": ""}
        if fetch:
            source, error = fetch_reference(ref, provider, currency)
            row["source"] = source or "saved"
            row["error"] = error or ""
        frame = load_reference_history(reference)
        row.update(describe_history(frame))
        if frame is None or frame.empty:
            row.update(verdict="no data", points=0)
            rows.append(row)
            continue
        sparse = row["median_gap_days"] is not None and row["median_gap_days"] > MAX_WEEKLY_GAP_DAYS
        row["interpolated"] = bool(interpolate and sparse)
        if row["interpolated"]:
            frame = interpolate_weekly(frame)
        scores = evaluate_reference(frame)
        if scores is None:
            reason = "not weekly data" if sparse and not interpolate else f"needs >{MIN_HISTORY_WEEKS} weeks + {HORIZON_WEEKS}w ahead"
            row.update(verdict=f"too little data ({reason})", points=0)
        else:
            row.update(scores)
            row["verdict"] = verdict(row)
        rows.append(row)
    return pd.DataFrame(rows)


def format_table(results):
    columns = ["watch", "rows", "span_weeks", "median_gap_days", "points",
               "model_mape", "last_price_mape", "q4_only_mape", "verdict"]
    view = results.reindex(columns=columns).copy()
    for column in ("model_mape", "last_price_mape", "q4_only_mape"):
        view[column] = view[column].map(lambda v: f"{v:.1%}" if pd.notna(v) else "-")
    view["median_gap_days"] = view["median_gap_days"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "-")
    view["points"] = view["points"].fillna(0).astype(int)
    return view.to_string(index=False)


def overall(results):
    scored = results[results["verdict"].isin(["model wins", "marginal", "no edge"])]
    if scored.empty:
        return "No reference had enough weekly history to judge the model. Get denser data first."
    wins = int((scored["verdict"] == "model wins").sum())
    model = scored["model_mape"].mean()
    flat = scored["last_price_mape"].mean()
    line = f"Model wins on {wins}/{len(scored)} references | avg MAPE model {model:.1%} vs last_price {flat:.1%}."
    if len(scored) < MIN_REFERENCES:
        return line + f" Too few references to conclude anything (need {MIN_REFERENCES}+ with enough data)."
    if wins >= int(np.ceil(len(scored) * 0.6)):
        return line + " The seasonal signal looks real: worth building on."
    return line + " No consistent seasonal edge: consider pivoting to per-watch valuation."


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refs", default=str(ROOT / REFERENCES_PATH))
    parser.add_argument("--skip-fetch", action="store_true", help="use histories already in data/model_history")
    parser.add_argument("--provider", choices=("auto", "kello", "nuvinty"), default="auto")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--interpolate", action="store_true", help="fill gaps up to 6 weeks in sparse data")
    parser.add_argument("--out", default=str(ROOT / RESULTS_PATH))
    args = parser.parse_args()
    references = load_references(args.refs)
    print(f"backtesting {len(references)} references | horizon {HORIZON_WEEKS}w | "
          f"needs {MIN_HISTORY_WEEKS}+ weeks of weekly history each")
    results = run(references, fetch=not args.skip_fetch, provider=args.provider,
                  currency=args.currency, interpolate=args.interpolate)
    print(format_table(results))
    for row in results.itertuples():
        if getattr(row, "error", ""):
            print(f"  {row.watch}: {row.error}")
    if "interpolated" in results and results["interpolated"].eq(True).any():
        print("note: interpolated histories are smoother than reality; treat their scores as indicative.")
    print(overall(results))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.out, index=False)
    print(f"saved: {args.out}")


if __name__ == "__main__":
    main()
