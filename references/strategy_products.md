# Strategy Products

Use this for generated pools, strategy hits, and signal products.

## Strategy Selection Results

`Stock.daily_selection_results`
- Catalog owns coverage, flags, date column, and stock key.
- Use for historical selected stocks and strategy labels.
- Check actual columns before filtering a strategy name.

## Violent K Signals

`Stock.violent_k_signals`
- Catalog owns coverage, flags, date column, and stock key.
- Use as a latest signal snapshot, not a long trend.

## ETF Pool

`Stock.etf_pool`
- Catalog owns coverage, flags, date column, and stock key.

## Stock Pool

`Stock.stock_pool_base`
- Catalog owns coverage, flags, date column, freshness column, and stock key.
- Use freshness metadata before declaring pool freshness.

`Stock.tmp_pool_mv`
- Catalog owns coverage and row count. Do not use for analysis if catalog says it is empty.

## Naming

Use neutral names such as "BBI-KDJ quantitative strategy" or "violent K signal".
Avoid informal strategy nicknames in user-facing answers.
