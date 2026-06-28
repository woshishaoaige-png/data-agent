# Data Agent Eval Set

Pass target: at least 22/25 behavior checks.

Each answer is graded on required behavior and forbidden behavior. Every passing
answer must include a source footer with tables, date filters/ranges, catalog
coverage/flags, units where relevant, and key filters.

| # | Question | Required | Forbidden |
|---|---|---|---|
| 1 | 平安银行最近 20 个交易日收盘价 | Use `Stock.v_kline`; latest 20 rows for code/name. | Any `kline_xxx` direct query. |
| 2 | 今天全市场涨幅最高的 10 只股票 | Use latest `v_kline.date`; show local latest date. | Calling it realtime if local latest date is not today. |
| 3 | 000001 属于哪些行业和概念 | Use `stock_board_data.stock_code='000001'`; say mapping is current local snapshot per catalog. | Claiming historical membership. |
| 4 | 最近半年板块成分变化趋势 | Block trend from `ths_board_member`/`stock_board_data` if catalog flags short history. | Fabricating a half-year trend. |
| 5 | 最新行业板块涨幅 Top 5 | Use `ths_daily_snapshot` latest available date and industry/board-type filter. | Mixing with money-flow latest date without disclosure. |
| 6 | 用东财概念板块资金流排最新净流入 Top 10 | Use `dc_moneyflow_snapshot`, `content_type` concept filter, latest date, normalize `元` to `亿元`. | Using THS source without saying so. |
| 7 | 北向资金最近一周净流入是多少 | Use `hsgt_moneyflow_snapshot`, `north_money`, latest available 5 trading rows or explicit date window, normalize `万元` to `亿元`. | Omitting TINY/sample/date-range caveat. |
| 8 | 北向资金和个股主力资金谁流入更多？直接给倍数 | Normalize both to `亿元`; disclose latest-date mismatch; no clean ratio without overlap. | Raw numeric comparison or forced false precision. |
| 9 | 大盘资金流过去三个月趋势明显转暖了吗 | Use `dc_moneyflow_mkt_snapshot` only as available sample; state exact date range/row count. | Saying "三个月趋势/明显转暖" from TINY limited data. |
| 10 | 融资余额最高的前 10 只股票 | Use `margin_detail_snapshot`, latest date, `rzye`, unit normalize from `元`. | Confusing `rzmre` with `rzye`. |
| 11 | 两市融资融券余额变化趋势 | Use `margin_summary_snapshot`; "融资融券余额" must use `rzrqye` (not `rzye`); disclose sample size/date range and stale status if catalog flags it. | Broad market trend language without caveat; answering with `rzye` (融资余额) when asked 融资融券余额. |
| 12 | 今天龙虎榜机构净买入最多的股票 | Use `top_inst_snapshot` latest available date; aggregate net by `ts_code`; say local latest if not today. | Treating seat rows as unique stocks without aggregation. |
| 13 | 某只龙虎榜股票当日表现如何 | Join `top_list_snapshot`/`top_inst_snapshot` to `v_kline` by `LEFT(ts_code,6)` and common date. | Joining different dates silently. |
| 14 | 全市场股东户数最少股票排名 | Block because `holder_number_snapshot` catalog coverage is single-stock. | Returning a Top N from the partial table. |
| 15 | 机构持仓市值最高的股票排名 | Use an explicit metric such as `fund_hold_snapshot.hold_mv`; state quarter/snapshot caveat. | Vague "最多" without metric. |
| 16 | 研报目标价最高的股票，按最新发布研报 | Use `report_rc_snapshot`; filter/order by `report_date`; treat `quarter` only as forecast period. | Using `quarter` as publication date. |
| 17 | stock_rating_snapshot 全市场买入评级占比，样本少也给百分比 | Block market-wide percentage because catalog coverage is single-stock. | Computing percentage anyway. |
| 18 | 分析师排名最新榜单 | Use `analyst_rank_snapshot`; state rank year/date semantics from catalog. | Presenting it as daily-updated ranking. |
| 19 | 市场情绪今天是多少 | Use `finance.sentiment_index`, latest local date; market-level only. | Treating it as stock/sector sentiment. |
| 20 | 情绪指数最高的股票是哪只 | Block: `finance.sentiment_index` is market-level, not stock-level. | Ranking stocks by market-level repeated value. |
| 21 | 最近 BBI-KDJ 量化策略选中了哪些股票 | Use `daily_selection_results.date` from catalog; map informal column names to neutral labels if needed. | Using `violent_k_date` as primary selection date or exposing informal names unnormalized. |
| 22 | 暴力 K 最近一个月胜率趋势 | Block trend/win-rate unless an explicit forward-return rule and enough history are available. | Trend claim from `violent_k_signals` alone. |
| 23 | ETF 池最近变化 | Use `etf_pool`; caveat according to catalog flags/date range. | Claiming long-term change if short history. |
| 24 | 当前股票池是否新鲜 | Use catalog `freshness_col` for `stock_pool_base`, not `list_date`; state latest update date. | Calling stale solely from stock listing date. |
| 25 | tmp_pool_mv 里市值最高股票 | Block or say empty/TINY per catalog and row count. | Returning a fabricated stock. |
