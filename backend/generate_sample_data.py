from pathlib import Path

import numpy as np
import pandas as pd

from config import BASE_PRICE, DATA_PATH, END_DATE, HISTORY_WEEKS, RANDOM_SEED, SKU_ID


def build_history():
    rng = np.random.default_rng(RANDOM_SEED)
    weeks = pd.date_range(end=END_DATE, periods=HISTORY_WEEKS, freq="W-SUN")
    iso_week = weeks.isocalendar().week.to_numpy(dtype=int)
    peak = ((iso_week >= 40) & (iso_week <= 52)).astype(float)
    trend = np.linspace(-0.04, 0.06, HISTORY_WEEKS)
    noise = rng.normal(0.0, 0.012, HISTORY_WEEKS)
    price = BASE_PRICE * (1.0 + trend + 0.10 * peak + noise)
    promo = (rng.random(HISTORY_WEEKS) < 0.12) & (peak == 0)
    price[promo] *= 0.88
    price = np.round(price, 2)
    competitor_price = np.round(price * rng.uniform(0.94, 1.06, HISTORY_WEEKS), 2)
    stock = rng.integers(0, 60, HISTORY_WEEKS)
    low_stock_window = (iso_week >= 45) & (iso_week <= 50)
    stock[low_stock_window] = rng.integers(0, 15, int(low_stock_window.sum()))
    demand = 90 * (1.0 + 0.8 * peak) * (BASE_PRICE / price) + rng.normal(0, 8, HISTORY_WEEKS)
    units_sold = np.clip(np.round(demand), 0, None).astype(int)
    units_sold[stock == 0] = 0
    return pd.DataFrame(
        {
            "week_start": weeks,
            "sku": SKU_ID,
            "price": price,
            "competitor_price": competitor_price,
            "promo_flag": promo.astype(int),
            "stock_units": stock,
            "units_sold": units_sold,
        }
    )


def main():
    path = Path(__file__).parent / DATA_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = build_history()
    frame.to_csv(path, index=False)
    print(f"wrote {len(frame)} weeks to {path}")


if __name__ == "__main__":
    main()
