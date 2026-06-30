# Daily Joinable

Use this for stock-level daily or near-daily questions.

## Primary Source

`Stock.v_kline`
- Catalog owns coverage, date column, and stock key.
- Use for price, return, volume, turnover, and amount.
- It covers all kline shards through one view.

## Current Stock Metadata

`Stock.stock_board_data`
- Catalog owns coverage, flags, date column, and stock key.
- Use for current sector/concept/region mapping only.

## Stock Money Flow

`Stock.stock_moneyflow_snapshot`
- Catalog owns coverage, flags, date column, stock key, and unit.
- Use for recent stock-level small/medium/large/extra-large order flow.
- Do not use for long trends.

## Margin Detail

`Stock.margin_detail_snapshot`
- Catalog owns coverage, date column, stock key, and unit.
- Fields: `rzye`, `rqye`, `rzmre`, `rqyl`, `rzche`, `rqchl`, `rqmcl`, `rzrqye`.

## Top List

`Stock.top_list_snapshot`
- Catalog owns coverage, date column, stock key, and unit.

`Stock.top_inst_snapshot`
- Catalog owns coverage, date column, and stock key.
- `side`: 1 buy, 2 sell.

## Query Pattern

For latest stock-level joins:

```sql
WITH latest_k AS (
  SELECT MAX(`date`) AS d FROM Stock.v_kline
),
latest_flow AS (
  SELECT MAX(trade_date) AS d FROM Stock.stock_moneyflow_snapshot
)
SELECT ...
```

Always check date overlap before joining.
