# Market Snapshot

Use this for market, board, money flow, northbound/southbound, margin summary,
and sentiment snapshot questions.

## Board行情

`Stock.ths_daily_snapshot`
- Catalog owns coverage, flags, date column, and board key.
- Fields include `board_type`, `board_type_name`, `open`, `high`, `low`, `close`, `pct_change`, `total_mv`, `float_mv`.

`Stock.ths_board_member`
- Catalog owns coverage, flags, date column, board key, and constituent stock key.
- Use for recent board constituents, not historical member-change trends.

## Board Money Flow

`Stock.ths_moneyflow_snapshot`
- Catalog owns coverage, flags, date column, board key, and unit.

`Stock.dc_moneyflow_snapshot`
- Catalog owns coverage, flags, date column, board key, and unit.
- `content_type` separates industry/concept/region.
- Do not join DC board codes to THS board codes without mapping.

## Market Money Flow

`Stock.dc_moneyflow_mkt_snapshot`
- Catalog owns coverage, flags, date column, and unit.
- Use for reporting the available market-flow series with sample-size caveat.

## Northbound / Southbound

`Stock.hsgt_moneyflow_snapshot`
- Catalog owns coverage, flags, date column, and unit.
- Fields: `hgt`, `sgt`, `north_money`, `south_money`, `ggt_ss`, `ggt_sz`.

`Stock.hk_hold_northbound_snapshot`
- Catalog owns coverage, flags, date column, and stock key.

`Stock.hsgt_top10_snapshot`
- Catalog owns coverage, flags, date column, stock key, and unit.

`Stock.southbound_hold_snapshot`
- Catalog owns coverage, flags, date column, and stock key.

## Sentiment

`finance.sentiment_index`
- Catalog owns coverage, flags, and date column.
- Market-level sentiment, not stock-level.

`finance.sentiment_nlp_source`
- Catalog owns coverage, flags, and date column.
- NLP source aggregation.

## Margin Summary

`Stock.margin_summary_snapshot`
- Catalog owns coverage, flags, date column, and unit.
- Use with sample-size disclosure.
