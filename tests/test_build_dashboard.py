import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_dashboard import choose_chart, render_dashboard, summarize_kpis  # noqa: E402


def test_choose_chart_prefers_time_series():
    rows = [
        {"trade_date": "2026-06-26", "net_yi": 1.2, "name": "A"},
        {"trade_date": "2026-06-27", "net_yi": 1.5, "name": "A"},
    ]
    chart = choose_chart(rows, ["trade_date", "net_yi", "name"])
    assert chart == {"type": "line", "x": "trade_date", "y": "net_yi"}


def test_summarize_kpis_includes_rows_and_numeric_sum():
    rows = [{"name": "A", "net_yi": 1.2}, {"name": "B", "net_yi": 2.3}]
    kpis = summarize_kpis(rows, ["name", "net_yi"])
    assert kpis[0] == {"label": "Rows", "value": 2}
    assert kpis[1] == {"label": "Sum net_yi", "value": 3.5}


def test_render_dashboard_contains_embedded_data_and_controls():
    html = render_dashboard(
        [{"trade_date": "2026-06-26", "net_yi": 1.2}],
        title="资金流",
        subtitle="测试",
        source="unit-test",
    )
    assert "<!DOCTYPE html>" in html
    assert "资金流" in html
    assert "Chart.js" not in html  # no visible explanatory text
    assert "const DATA =" in html
    assert "2026-06-26" in html
    assert "Filter rows" in html
