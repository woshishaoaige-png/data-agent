# Workflows

These recipes describe useful answer patterns. Catalog still owns table
coverage, dates, flags, units, keys, and freshness.

## Daily Market Recap

User asks: "今天盘面怎么样?"

Use:
- `Stock.v_kline` for breadth, top gainers/losers, volume/amount.
- `Stock.ths_daily_snapshot` or board money-flow tables for leading boards.
- `Stock.hsgt_moneyflow_snapshot` for northbound if catalog says usable.
- `finance.sentiment_index` for market-level sentiment only.

Answer: one-line conclusion, 3-5 bullets, one catalog caveat, source footer.

## Board Heat And Rotation

User asks: "哪个方向强?" or "资金去哪了?"

Use board daily tables for price strength and board flow tables for net flow.
Use common overlapping dates if joining price and flow. Do not fuzzy-join DC and
THS board codes unless the user accepts exploratory matching.

## Stock Diagnostic

User asks: "这只票为什么涨/跌?" or "弱在哪里?"

Use `Stock.v_kline`, stock money flow, margin detail, top list/institution
records, and current sector mapping. Lead with price action, then flow,
leverage/top-list evidence, then sector context.

## Money-Flow Comparison

User asks for "谁流入更多" or a ratio.

Normalize units to `亿元`, align dates, and disclose if latest dates differ.
If no common date exists, do not provide a clean ratio.

## Top List Read

User asks: "龙虎榜机构今天偏买还是偏卖?"

Use `top_inst_snapshot` for institution/seat buy-sell aggregation and
`top_list_snapshot` for stock-level reasons and turnover context. Use latest
available date if "today" is not present.

## Strategy Pool Read

User asks about strategy hits or pools.

Use `daily_selection_results`, `violent_k_signals`, and pool tables after
checking catalog freshness. Use neutral strategy names in the final answer.

## Freshness Fallback

If the requested "today/current/latest" source is stale, answer with the latest
available local date and say: "本地库最新为 YYYY-MM-DD，不代表今日实时行情。"
