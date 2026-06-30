# Window Frames

Use this reference when the user asks for rolling, moving, cumulative, running,
month-over-month, period-over-period, lag, rank, percentile, or "latest Top N"
analysis.

## Default Rule

Time-series aggregate windows must use an explicit `ROWS` frame. Do not rely on
the database default frame.

The risky pattern is:

```sql
SUM(x) OVER (PARTITION BY code ORDER BY trade_date)
```

The safer cumulative pattern is:

```sql
SUM(x) OVER (
  PARTITION BY code
  ORDER BY trade_date
  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

## Standard Frames

| Scenario | Frame | Required companion output |
|----------|-------|---------------------------|
| Cumulative sum/avg | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | none beyond grain |
| N-period moving average | `ROWS BETWEEN N-1 PRECEDING AND CURRENT ROW` | `window_n` |
| N-period rolling stddev | `ROWS BETWEEN N-1 PRECEDING AND CURRENT ROW` | `window_n` |
| N-period rolling correlation | `ROWS BETWEEN N-1 PRECEDING AND CURRENT ROW` | `window_n` and pairwise non-null filter strategy |
| Previous value | `LAG(x, 1) OVER (...)` | previous value column |
| Cross-section rank | `RANK() OVER (PARTITION BY trade_date ORDER BY metric DESC)` | rank column |

Ranking functions such as `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`, `LAG`,
and `LEAD` do not require a frame. Aggregate window functions such as `SUM`,
`AVG`, `MIN`, `MAX`, `STDDEV`, `COUNT`, and `CORR` do.

## Partition And Order

- Entity time series must use `PARTITION BY code`, `ts_code`, board code/name,
  strategy name, or another entity key.
- Market-level series may omit `PARTITION BY` only when each date has one row.
- Time-series windows must include `ORDER BY date`, `trade_date`, `month`,
  `quarter`, or another temporal column.
- Cross-section ranking should partition by date first, then order by the metric.

## Nested Query Pattern

Use this staged CTE shape for complex windows:

```sql
WITH
base AS (
  SELECT trade_date, code, metric
  FROM Stock.v_kline
),
windowed AS (
  SELECT
    trade_date,
    code,
    metric,
    AVG(metric) OVER (
      PARTITION BY code
      ORDER BY trade_date
      ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS ma20,
    COUNT(metric) OVER (
      PARTITION BY code
      ORDER BY trade_date
      ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS window_n
  FROM base
),
final AS (
  SELECT *
  FROM windowed
  WHERE window_n >= 20
)
SELECT *
FROM final;
```

## Common Blocks

- Do not put `LIMIT` inside `base` before an aggregate, rank, or rolling window
  unless the limit is intentionally selecting a latest slice.
- Do not rank across all historical rows when the question asks for latest Top N;
  filter to each source's latest date first.
- Do not interpret early rolling-window rows unless `window_n` confirms the full
  frame is present.
