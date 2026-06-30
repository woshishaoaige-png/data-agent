# Statistical SQL

Use this reference when the user asks for correlation, regression, volatility,
dispersion, standard deviation, covariance, or "relationship between" two
metrics.

## Required Shape

Statistical SQL must expose the sample behind the statistic. A result that only
returns `corr` or `slope` is not trustworthy enough for an answer.

Minimum required output:

- `n`: pairwise non-null sample size used by the statistic.
- statistic column: `corr`, `stddev`, `regr_slope`, `regr_intercept`, or a
  clearly named equivalent.
- range columns for interpreted metrics when practical: `x_min`, `x_max`,
  `y_min`, `y_max`.

Filter pairwise nulls before correlation or regression:

```sql
WHERE x IS NOT NULL
  AND y IS NOT NULL
```

For single-metric dispersion, filter the metric itself:

```sql
WHERE metric IS NOT NULL
```

## Minimum Sample

- Correlation and regression require `n >= 20` by default.
- Standard deviation requires `n >= 3` by default.
- If a business question needs a smaller sample, the answer must explicitly
  disclose the sample size and avoid strong language.

## Function Policy

Prefer dialect helpers from `tools/dialects.py` when generating statistical
expressions. Do not hand-write dialect-specific fallback formulas in ad hoc SQL.

| Concept | Canonical alias | Notes |
|---------|-----------------|-------|
| Correlation | `corr` | Must be within `[-1, 1]`. |
| Standard deviation | `stddev` | Must be non-negative. Prefer sample stddev. |
| Regression slope | `regr_slope` | Interpret only with `n` and metric ranges. |
| Regression intercept | `regr_intercept` | Interpret only with `n` and metric ranges. |

## CTE Pattern

Use a staged CTE for non-trivial statistics:

```sql
WITH
base AS (
  SELECT
    trade_date,
    code,
    metric_x AS x,
    metric_y AS y
  FROM Stock.some_view
  WHERE trade_date >= '2026-01-01'
),
sample AS (
  SELECT *
  FROM base
  WHERE x IS NOT NULL
    AND y IS NOT NULL
),
stats AS (
  SELECT
    COUNT(*) AS n,
    CORR(x, y) AS corr,
    MIN(x) AS x_min,
    MAX(x) AS x_max,
    MIN(y) AS y_min,
    MAX(y) AS y_max
  FROM sample
)
SELECT *
FROM stats;
```

## Common Blocks

- Do not compare money metrics from mixed units until they are normalized.
- Do not compute a statistic from a single-stock-only source and describe it as
  a market-wide relationship.
- Do not use sparse or all-null metric columns; profile unfamiliar tables first.
- Do not rank by correlation or regression output unless every group exposes
  its own `n` and the query filters to the minimum sample.
