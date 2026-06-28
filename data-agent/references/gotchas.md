# Gotchas

Read this before writing SQL.

## Hard Blocks

- Do not query `kline_000` ... `kline_920`; use `Stock.v_kline`.
- Do not rank or compare "全市场" with a `SINGLE_STOCK` table.
- Do not describe trends from a table with `SHORT_HISTORY`.
- Do not call stale data "today" when `flags` contains `STALE_CURRENT`.
- Do not compare money columns until units are normalized.

## Unit Traps

Normalize money to `亿元` for cross-source reporting:

- `Stock.hsgt_moneyflow_snapshot`: `万元`; divide by `10000` for `亿元`.
- `Stock.stock_moneyflow_snapshot`: `万元`; divide by `10000` for `亿元`.
- `Stock.dc_moneyflow_snapshot`: `元`; divide by `100000000` for `亿元`.
- `Stock.dc_moneyflow_mkt_snapshot`: `元`; divide by `100000000` for `亿元`.
- `Stock.ths_moneyflow_snapshot`: `元`; divide by `100000000` for `亿元`.
- `Stock.margin_*`, `Stock.top_list_snapshot`, `Stock.hsgt_top10_snapshot`: `元`.

## Date Traps

- `trade_date`, `date`, `publish_time`, `report_date`, `visit_date`, `ann_date`, `end_date` are not interchangeable.
- `report_rc_snapshot.quarter` is forecast period, not publication date. Use `report_date` for publication timing.
- `fund_*` and `institution_hold_snapshot` use quarter-like periods. They are cross-sections, not daily series.
- `stock_board_data.as_of_date` currently has one day only. Use it for current mapping, not history.
- `ths_board_member` currently has only two trade dates. Use it for member lookup, not long-term board-member changes.

## Key Traps

- `Stock.v_kline.code` is six-digit stock code without exchange suffix.
- Most Tushare snapshot stock tables use `ts_code` with suffix.
- `stock_board_data.stock_code` is the six-digit join key to `v_kline.code`.
- `ths_board_member.ts_code` is board code; `ths_board_member.con_code` is constituent stock code.
- `dc_moneyflow_snapshot.ts_code` is DC board code, not stock code.

## Snapshot Traps

- For "latest/current", use each table's `MAX(date_col)` separately.
- When joining daily tables, pre-check that both tables have overlapping dates.
- If latest dates differ, state the mismatch rather than silently joining stale with fresh data.

## Interpretation Traps

- `TINY` market-wide sources can answer "what is in this table", but not robust market conclusions.
- `SINGLE_STOCK` holder/rating tables are examples or partial coverage, not the market.
- Sentiment tables live in `finance`, not `Stock`, and are `TINY`; disclose coverage.

## User-Facing Glossary

- THS: 同花顺口径; DC: 东方财富口径. Their board codes are not directly joinable.
- 行业/概念/地域: board categories; ask or filter explicitly when ranking boards.
- 北向资金: 沪股通 + 深股通. 南向资金 points to 港股通 flows/holdings.
- 主力资金: large/extra-large order flow; source can be stock, board, or market-level, so clarify scope.
- 龙虎榜机构净买入: institution/seat buy minus sell from top-list institution details.
- 融资融券: leverage data. 注意口径区分：问"融资融券余额/两融余额"用 `rzrqye`（融资+融券总额）；问"融资余额"才用 `rzye`；`rzmre` 是融资买入额、`rqye` 是融券余额。不要把 `rzye` 当作"融资融券余额"回答。
- Sparse table: explain as "本地库样本很少/覆盖不全", not as an internal label only.
