"""Build a self-contained HTML dashboard from query results.

This is intentionally modest: one offline HTML file with KPI tiles, an optional
Chart.js chart, and a sortable/filterable table. It complements data-agent's
accuracy guardrails without turning the project into a BI framework.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent))
from db import get_engine  # noqa: E402

DATE_HINTS = ("date", "time", "month", "quarter", "year")
METRIC_HINTS = (
    "amount", "money", "price", "close", "open", "high", "low", "pct", "rate",
    "ratio", "count", "num", "volume", "turnover", "balance", "net", "buy", "sell",
    "yi",
)


def normalize_rows(rows):
    normalized = []
    for row in rows:
        if hasattr(row, "_mapping"):
            normalized.append(dict(row._mapping))
        else:
            normalized.append(dict(row))
    return normalized


def jsonable(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def collect_columns(rows):
    columns = []
    for row in rows:
        for col in row:
            if col not in columns:
                columns.append(col)
    return columns


def is_numeric_column(rows, col):
    values = [row.get(col) for row in rows if row.get(col) is not None]
    return bool(values) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)


def choose_chart(rows, columns):
    if not rows or len(rows) < 2:
        return None
    date_col = next((c for c in columns if any(h in c.lower() for h in DATE_HINTS)), None)
    metric_cols = [c for c in columns if is_numeric_column(rows, c)]
    preferred_metric = next((c for c in metric_cols if any(h in c.lower() for h in METRIC_HINTS)), None)
    metric_col = preferred_metric or (metric_cols[0] if metric_cols else None)
    if date_col and metric_col:
        return {"type": "line", "x": date_col, "y": metric_col}
    label_col = next((c for c in columns if not is_numeric_column(rows, c)), None)
    if label_col and metric_col:
        return {"type": "bar", "x": label_col, "y": metric_col}
    return None


def summarize_kpis(rows, columns):
    kpis = [{"label": "Rows", "value": len(rows)}]
    for col in columns:
        if len(kpis) >= 4:
            break
        if is_numeric_column(rows, col):
            values = [float(row[col]) for row in rows if row.get(col) is not None]
            kpis.append({"label": f"Sum {col}", "value": round(sum(values), 4)})
    return kpis


def slugify(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_").lower() or "dashboard"


def render_dashboard(rows, title="data-agent dashboard", subtitle="", source=""):
    rows = normalize_rows(rows)
    rows = [{k: jsonable(v) for k, v in row.items()} for row in rows]
    columns = collect_columns(rows)
    chart = choose_chart(rows, columns)
    kpis = summarize_kpis(rows, columns)
    title_html = html.escape(title)
    subtitle_html = html.escape(subtitle)
    source_html = html.escape(source)
    data_json = json.dumps(rows, ensure_ascii=False)
    columns_json = json.dumps(columns, ensure_ascii=False)
    chart_json = json.dumps(chart, ensure_ascii=False)
    kpis_json = json.dumps(kpis, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title_html}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1"></script>
  <style>
    :root {{
      --bg: #f7f7f4;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #697586;
      --border: #d9d9d2;
      --accent: #256f8f;
      --accent-2: #b75d36;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .shell {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 18px;
    }}
    h1 {{
      font-size: 24px;
      margin: 0 0 4px;
      letter-spacing: 0;
    }}
    .subtitle, .source {{
      color: var(--muted);
      font-size: 13px;
    }}
    .filter {{
      min-width: 240px;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 9px 10px;
      background: var(--panel);
      color: var(--text);
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }}
    .kpi, .chart-wrap, .table-wrap {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
    }}
    .kpi {{
      padding: 12px;
      min-height: 74px;
    }}
    .kpi-label {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .kpi-value {{
      font-size: 22px;
      font-weight: 650;
    }}
    .chart-wrap {{
      height: 330px;
      padding: 14px;
      margin-bottom: 14px;
    }}
    .table-wrap {{
      overflow: auto;
      max-height: 560px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 8px 10px;
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #eeeeea;
      cursor: pointer;
      user-select: none;
      font-weight: 650;
    }}
    tr:hover td {{ background: #fafaf7; }}
    .empty {{
      padding: 24px;
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      .shell {{ padding: 14px; }}
      header {{ flex-direction: column; }}
      .filter {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <h1>{title_html}</h1>
        <div class="subtitle">{subtitle_html}</div>
        <div class="source">{source_html}</div>
      </div>
      <input id="filter" class="filter" placeholder="Filter rows">
    </header>
    <section id="kpis" class="kpis"></section>
    <section class="chart-wrap"><canvas id="chart"></canvas></section>
    <section id="table" class="table-wrap"></section>
  </main>
  <script>
    const DATA = {data_json};
    const COLUMNS = {columns_json};
    const CHART = {chart_json};
    const KPIS = {kpis_json};
    let filtered = DATA.slice();
    let sortColumn = null;
    let sortDir = 1;

    function fmt(value) {{
      if (value === null || value === undefined) return "";
      if (typeof value === "number") {{
        return Math.abs(value) >= 1000 ? value.toLocaleString(undefined, {{ maximumFractionDigits: 2 }}) : value.toFixed(4).replace(/\\.0+$/, "").replace(/(\\.\\d*?)0+$/, "$1");
      }}
      return String(value);
    }}

    function renderKPIs() {{
      document.getElementById("kpis").innerHTML = KPIS.map(kpi => `
        <div class="kpi">
          <div class="kpi-label">${{kpi.label}}</div>
          <div class="kpi-value">${{fmt(kpi.value)}}</div>
        </div>
      `).join("");
    }}

    function renderTable() {{
      const root = document.getElementById("table");
      if (!COLUMNS.length) {{
        root.innerHTML = '<div class="empty">No rows</div>';
        return;
      }}
      const head = COLUMNS.map(col => `<th data-col="${{col}}">${{col}}${{sortColumn === col ? (sortDir > 0 ? " ↑" : " ↓") : ""}}</th>`).join("");
      const body = filtered.map(row => `<tr>${{COLUMNS.map(col => `<td>${{fmt(row[col])}}</td>`).join("")}}</tr>`).join("");
      root.innerHTML = `<table><thead><tr>${{head}}</tr></thead><tbody>${{body}}</tbody></table>`;
      root.querySelectorAll("th").forEach(th => th.addEventListener("click", () => {{
        const col = th.dataset.col;
        if (sortColumn === col) sortDir *= -1; else {{ sortColumn = col; sortDir = 1; }}
        filtered.sort((a, b) => {{
          const av = a[col], bv = b[col];
          if (av === bv) return 0;
          if (av === null || av === undefined) return 1;
          if (bv === null || bv === undefined) return -1;
          return av > bv ? sortDir : -sortDir;
        }});
        renderTable();
      }}));
    }}

    let chart;
    function renderChart() {{
      const canvas = document.getElementById("chart");
      if (!CHART || !DATA.length) {{
        canvas.parentElement.innerHTML = '<div class="empty">No chartable columns detected</div>';
        return;
      }}
      const points = DATA.slice(0, 200);
      chart = new Chart(canvas, {{
        type: CHART.type,
        data: {{
          labels: points.map(row => row[CHART.x]),
          datasets: [{{
            label: CHART.y,
            data: points.map(row => row[CHART.y]),
            borderColor: "#256f8f",
            backgroundColor: "rgba(37,111,143,0.28)",
            tension: 0.25
          }}]
        }},
        options: {{
          maintainAspectRatio: false,
          responsive: true,
          plugins: {{ legend: {{ display: true }} }},
          scales: {{ x: {{ ticks: {{ maxRotation: 45, minRotation: 0 }} }} }}
        }}
      }});
    }}

    document.getElementById("filter").addEventListener("input", e => {{
      const q = e.target.value.toLowerCase();
      filtered = DATA.filter(row => JSON.stringify(row).toLowerCase().includes(q));
      renderTable();
    }});

    renderKPIs();
    renderChart();
    renderTable();
  </script>
</body>
</html>
"""


def fetch_rows(sql, schema=None):
    with get_engine(schema).connect() as conn:
        return conn.execute(text(sql)).mappings().all()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", help="SQL to execute")
    ap.add_argument("--rows-json", help="JSON array of rows")
    ap.add_argument("--schema", default=None)
    ap.add_argument("--title", default="data-agent dashboard")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.rows_json:
        rows = json.loads(args.rows_json)
    elif args.sql:
        rows = fetch_rows(args.sql, schema=args.schema)
    else:
        raise SystemExit("provide --sql or --rows-json")

    out = Path(args.out or f"{slugify(args.title)}.html")
    rendered = render_dashboard(rows, title=args.title, subtitle=args.subtitle, source=args.source or (args.sql or "rows-json"))
    out.write_text(rendered, encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
