import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from context_extractor import build_context_draft, select_tables  # noqa: E402


def _catalog():
    return {
        "schemas": {
            "Stock": {
                "stock_moneyflow_snapshot": {
                    "type": "BASE TABLE",
                    "row_count": 2,
                    "coverage": "TINY",
                    "flags": ["SHORT_HISTORY"],
                    "date_col": "trade_date",
                    "date_min": "2026-06-26",
                    "date_max": "2026-06-27",
                    "unit": "万元",
                    "dimensions": {"stock_col": "ts_code"},
                    "columns": [
                        {"name": "trade_date", "key": ""},
                        {"name": "ts_code", "key": ""},
                        {"name": "net_mf_amount", "key": ""},
                    ],
                },
                "v_kline": {
                    "type": "VIEW",
                    "row_count": 1000,
                    "coverage": "OK",
                    "flags": [],
                    "columns": [{"name": "code", "key": ""}],
                },
            }
        }
    }


def test_select_tables_by_pattern():
    selected = select_tables(_catalog(), ["moneyflow"])
    assert [item[1] for item in selected] == ["stock_moneyflow_snapshot"]


def test_build_context_draft_contains_reference_and_eval_drafts(tmp_path):
    path = tmp_path / "catalog.json"
    import json
    path.write_text(json.dumps(_catalog()), encoding="utf-8")
    draft = build_context_draft("moneyflow", ["moneyflow"], catalog_path=path)
    assert draft["table_count"] == 1
    assert "`Stock.stock_moneyflow_snapshot`" in draft["reference_markdown"]
    assert any(item["expected_risk"] == "tiny_source" for item in draft["eval_drafts"])
    assert any(item["expected_risk"] == "short_history_trend" for item in draft["eval_drafts"])
