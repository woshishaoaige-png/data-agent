import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from profile_table import infer_kind, profile_rows  # noqa: E402


def test_infer_kind_for_common_columns():
    assert infer_kind("trade_date", ["2026-06-26"]) == "temporal"
    assert infer_kind("ts_code", ["000001.SZ"]) == "identifier"
    assert infer_kind("net_amount", [1.0, -2.0]) == "metric"
    assert infer_kind("board_type", ["行业", "概念"]) == "dimension"


def test_profile_rows_detects_duplicate_key_and_sparse_column():
    rows = [
        {"trade_date": "2026-06-26", "ts_code": "000001.SZ", "net_amount": 1.0, "note": None},
        {"trade_date": "2026-06-26", "ts_code": "000001.SZ", "net_amount": 2.0, "note": None},
        {"trade_date": "2026-06-27", "ts_code": "000002.SZ", "net_amount": -1.0, "note": "x"},
    ]
    report = profile_rows(rows, table="Stock.example")
    assert report["row_count"] == 3
    assert report["key_columns"] == ["trade_date", "ts_code"]
    assert report["duplicate_key_count"] == 1
    assert any(flag.startswith("duplicate_key") for flag in report["quality_flags"])
    assert any(flag.startswith("sparse_column:note") for flag in report["quality_flags"])


def test_profile_rows_numeric_stats():
    rows = [
        {"code": "000001", "amount": 0},
        {"code": "000002", "amount": 10},
        {"code": "000003", "amount": -5},
    ]
    report = profile_rows(rows)
    amount = next(col for col in report["columns"] if col["name"] == "amount")
    assert amount["stats"]["min"] == -5
    assert amount["stats"]["max"] == 10
    assert amount["stats"]["zero_count"] == 1
    assert amount["stats"]["negative_count"] == 1


def test_profile_rows_decimal_stats():
    rows = [
        {"code": "000001", "amount": Decimal("1.5")},
        {"code": "000002", "amount": Decimal("2.5")},
    ]
    report = profile_rows(rows)
    amount = next(col for col in report["columns"] if col["name"] == "amount")
    assert amount["kind"] == "metric"
    assert amount["stats"]["avg"] == 2.0
