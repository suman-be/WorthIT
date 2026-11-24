import subprocess
import sys
from pathlib import Path

import pandas as pd

from generate_sample_data import build_history
from predict import describe_watch, load_catalog

ROOT = Path(__file__).parent


def run_cli(tmp_path, serial, catalog_rows):
    data_path = tmp_path / "history.csv"
    build_history().to_csv(data_path, index=False)
    catalog_path = tmp_path / "catalog.csv"
    pd.DataFrame(catalog_rows).to_csv(catalog_path, index=False)
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "predict.py"),
            "--serial",
            serial,
            "--price",
            "500",
            "--data",
            str(data_path),
            "--serials",
            str(tmp_path / "missing.csv"),
            "--catalog",
            str(catalog_path),
            "--no-web",
            "--predictions",
            str(tmp_path / "predictions.csv"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_load_catalog_returns_entry_for_known_serial():
    catalog = load_catalog(ROOT / "data" / "watch_catalog.csv")
    assert catalog["WATCH-DEMO-001"]["brand"] == "Northfield"
    assert "black dial" in catalog["WATCH-DEMO-001"]["description"]


def test_load_catalog_handles_missing_file(tmp_path):
    assert load_catalog(tmp_path / "missing.csv") == {}


def test_describe_watch_formats_name_and_description():
    entry = {
        "brand": "Northfield",
        "model": "Diver",
        "variant": "42mm Blue",
        "description": "Blue dive watch.",
    }
    assert describe_watch(entry) == ("Northfield Diver 42mm Blue", "Blue dive watch.")
    assert describe_watch({}) is None


def test_cli_prints_description_for_known_serial(tmp_path):
    completed = run_cli(
        tmp_path,
        "ABC-1",
        [
            {
                "serial": "ABC-1",
                "sku": "WATCH-001",
                "brand": "Northfield",
                "model": "Dress",
                "variant": "38mm",
                "description": "Slim automatic dress watch.",
            }
        ],
    )
    assert completed.returncode == 0, completed.stderr
    assert "watch: Northfield Dress 38mm" in completed.stdout
    assert "description: Slim automatic dress watch." in completed.stdout


def test_cli_reports_unknown_serial(tmp_path):
    completed = run_cli(tmp_path, "UNKNOWN-1", [{"serial": "ABC-1", "description": "Other watch."}])
    assert completed.returncode == 0, completed.stderr
    assert "no catalog entry for serial UNKNOWN-1" in completed.stdout
