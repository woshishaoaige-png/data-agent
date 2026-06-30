# Join Map

Use only these joins as safe defaults. Anything else is exploratory.

## Safe Daily Stock Joins

`Stock.v_kline`
- Key: `code`
- Use catalog date column.

`Stock.stock_board_data`
- Key: `stock_code`
- Join: `v_kline.code = stock_board_data.stock_code`
- Caveat: current mapping only; check catalog flags.

`Stock.margin_detail_snapshot`
- Key: `ts_code`
- Join to kline by converting suffix: `v_kline.code = LEFT(margin_detail_snapshot.ts_code, 6)` and `v_kline.date = margin_detail_snapshot.trade_date`.

`Stock.stock_moneyflow_snapshot`
- Key: `ts_code`
- Join to kline by `v_kline.code = LEFT(stock_moneyflow_snapshot.ts_code, 6)` and date equality.
- Caveat: check catalog flags and unit.

`Stock.top_list_snapshot` and `Stock.top_inst_snapshot`
- Key: `ts_code`
- Join between them on `ts_code, trade_date`.
- Join to kline by `LEFT(ts_code, 6)`.

`Stock.hsgt_top10_snapshot`
- Key: `ts_code`
- Join to kline by `LEFT(ts_code, 6)`.

## Board Joins

`Stock.ths_daily_snapshot`
- Board key: `ts_code`

`Stock.ths_moneyflow_snapshot`
- Board key: `ts_code`
- Join: `ths_daily_snapshot.ts_code = ths_moneyflow_snapshot.ts_code`
  and same `trade_date`.

`Stock.ths_board_member`
- Board key: `ts_code`
- Stock constituent key: `con_code`
- Join to board tables by board `ts_code`.
- Join to stocks by `v_kline.code = LEFT(con_code, 6)`.
- Caveat: check catalog flags.

`Stock.dc_moneyflow_snapshot`
- Board key: `ts_code`
- Do not join to THS board code without an explicit mapping.

## Research And Holdings Joins

Research/holding stock tables generally use `ts_code`.
- Join to `v_kline` by `LEFT(ts_code, 6)`.
- Join to `stock_board_data` by `LEFT(ts_code, 6) = stock_board_data.stock_code`.
- Many tables are partial coverage; check catalog first.

## Unsafe Joins

- Do not join DC board codes (`BK....DC`) to THS board codes (`885....TI`) by name unless the user accepts fuzzy matching.
- Do not join quarter tables to daily tables without defining a reporting-date rule.
- Do not join `finance.sentiment_index` to stock rows as if it were stock-level sentiment; it is market-level.
- Do not mix different latest dates without disclosing the mismatch.
