# Holdings And Research

This domain is useful but uneven. Check `catalog.json` before answering.

## Research

`Stock.report_rc_snapshot`
- Catalog owns coverage, flags, date column, and stock key.
- `quarter` is forecast period, not publication date.
- Fields include `org_name`, `author_name`, `op_rt`, `op_pr`, `tp`, `np`, `eps`, `pe`, `roe`, `max_price`, `min_price`.

`Stock.stock_rating_snapshot`
- Catalog owns coverage, flags, date column, and stock key.
- Do not use for market-wide rating distribution.

`Stock.broker_recommend_snapshot`
- Catalog owns coverage, flags, date column, and stock key.

`Stock.analyst_rank_snapshot`
- Catalog owns coverage, flags, and date column.

## Holdings

`Stock.fund_hold_snapshot`
- Catalog owns coverage, flags, date column, and stock key.

`Stock.fund_portfolio_snapshot`
- Catalog owns coverage, flags, date column, and stock key.

`Stock.institution_hold_snapshot`
- Catalog owns coverage, flags, date column, and stock key.

`Stock.holder_number_snapshot`
- Catalog owns coverage, flags, date column, and stock key.
- Do not rank all-market holder counts from this table.

`Stock.top10_holders_snapshot`
- Catalog owns coverage, flags, date column, and stock key.

`Stock.top10_floatholders_snapshot`
- Catalog owns coverage, flags, date column, and stock key.

## Institution Visits

`Stock.jgdy_institution_snapshot`
- Catalog owns coverage, flags, date column, and stock key.
- Use for institution visit/event queries.

## Required Caveat

If catalog marks any table here as sparse, short-history, or stale, state that it
is partial coverage and avoid market-wide conclusions.
