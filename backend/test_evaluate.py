import pandas as pd
import pytest

from evaluate_predictions import evaluate, load_predictions


def test_evaluate_scores_due_predictions_against_realised_history(tmp_path):
    path = tmp_path / "predictions.csv"
    pd.DataFrame(
        [
            {"timestamp": "2026-01-04T10:00:00Z", "serial": "A", "sku": "S1", "current_price": 100.0,
             "horizon_weeks": 8, "predicted_price": 110.0, "low_price": 95.0, "high_price": 115.0, "multiplier": 1.1},
            {"timestamp": "2026-12-01T10:00:00Z", "serial": "B", "sku": "S1", "current_price": 100.0,
             "horizon_weeks": 8, "predicted_price": 105.0, "low_price": 95.0, "high_price": 115.0, "multiplier": 1.05},
        ]
    ).to_csv(path, index=False)
    history = pd.DataFrame(
        {"week_start": pd.to_datetime(["2026-03-01"]), "sku": ["S1"], "price": [120.0]}
    )
    result = evaluate(load_predictions(path), history, as_of="2026-06-01")
    assert result["scored"] == 1
    assert result["pending"] == 1
    row = result["rows"].iloc[0]
    assert row["actual"] == 120.0
    assert row["abs_pct_error"] == pytest.approx(10 / 120)
    assert row["flat_abs_pct_error"] == pytest.approx(20 / 120)
    assert not row["in_range"]
