-- ============================================================
-- data-agent 语义视图（阶段 0 / G1）
-- 目的：把"确定性的物理布局"收口成视图，让 Agent 永远查 v_*，
--       不再自己拼分片表名 / 记忆物理细节。
-- 重新执行安全：CREATE OR REPLACE。
-- ============================================================

-- ------------------------------------------------------------
-- v_kline：14 张按代码前缀分片的个股日 K 线合并视图
--   - 列结构已核实 14 张完全一致，UNION ALL 安全
--   - 额外加 src_table 列，便于排查某行来自哪张分片表
--   - Agent 一律查 Stock.v_kline，禁止直接查 kline_xxx
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW Stock.v_kline AS
SELECT 'kline_000' AS src_table, `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_000
UNION ALL SELECT 'kline_001', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_001
UNION ALL SELECT 'kline_002', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_002
UNION ALL SELECT 'kline_003', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_003
UNION ALL SELECT 'kline_300', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_300
UNION ALL SELECT 'kline_301', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_301
UNION ALL SELECT 'kline_302', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_302
UNION ALL SELECT 'kline_600', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_600
UNION ALL SELECT 'kline_601', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_601
UNION ALL SELECT 'kline_603', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_603
UNION ALL SELECT 'kline_605', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_605
UNION ALL SELECT 'kline_688', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_688
UNION ALL SELECT 'kline_689', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_689
UNION ALL SELECT 'kline_920', `date`,`code`,`name`,`open`,`close`,`high`,`low`,`volume`,`amount`,`turnover`,`pctChg` FROM Stock.kline_920;

-- ------------------------------------------------------------
-- v_stock_moneyflow_yi：个股资金流，金额统一为亿元
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW Stock.v_stock_moneyflow_yi AS
SELECT
  trade_date,
  ts_code,
  LEFT(ts_code, 6) AS code,
  net_mf_amount / 10000 AS net_mf_yi,
  (buy_lg_amount + buy_elg_amount - sell_lg_amount - sell_elg_amount) / 10000 AS main_net_yi,
  (buy_sm_amount - sell_sm_amount) / 10000 AS small_net_yi,
  buy_lg_amount / 10000 AS buy_lg_yi,
  sell_lg_amount / 10000 AS sell_lg_yi,
  buy_elg_amount / 10000 AS buy_elg_yi,
  sell_elg_amount / 10000 AS sell_elg_yi
FROM Stock.stock_moneyflow_snapshot;

-- ------------------------------------------------------------
-- v_board_moneyflow_dc_yi：东财板块资金流，金额统一为亿元
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW Stock.v_board_moneyflow_dc_yi AS
SELECT
  trade_date,
  ts_code,
  name,
  content_type,
  pct_change,
  close,
  `rank`,
  net_amount / 100000000 AS net_yi,
  buy_elg_amount / 100000000 AS buy_elg_yi,
  buy_lg_amount / 100000000 AS buy_lg_yi,
  buy_md_amount / 100000000 AS buy_md_yi,
  buy_sm_amount / 100000000 AS buy_sm_yi,
  net_amount_rate
FROM Stock.dc_moneyflow_snapshot;

-- ------------------------------------------------------------
-- v_board_moneyflow_ths_yi：同花顺板块资金流，金额统一为亿元
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW Stock.v_board_moneyflow_ths_yi AS
SELECT
  trade_date,
  ts_code,
  name,
  board_type,
  board_type_name,
  close,
  pct_change,
  company_num,
  pct_change_stock,
  lead_stock,
  net_buy_amount / 100000000 AS net_buy_yi,
  net_sell_amount / 100000000 AS net_sell_yi,
  net_amount / 100000000 AS net_yi
FROM Stock.ths_moneyflow_snapshot;

-- ------------------------------------------------------------
-- v_top_inst_net_yi：龙虎榜席位按股票/日期聚合，金额统一为亿元
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW Stock.v_top_inst_net_yi AS
SELECT
  trade_date,
  ts_code,
  LEFT(ts_code, 6) AS code,
  SUM(buy) / 100000000 AS buy_yi,
  SUM(sell) / 100000000 AS sell_yi,
  SUM(net_buy) / 100000000 AS net_buy_yi,
  COUNT(*) AS seat_count
FROM Stock.top_inst_snapshot
GROUP BY trade_date, ts_code;

-- ------------------------------------------------------------
-- v_strategy_selection_latest：策略选股结果，规范化常用策略标签
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW Stock.v_strategy_selection_latest AS
SELECT
  code,
  name,
  market,
  sw_l1,
  sw_l2,
  sw_l3,
  ths_industry,
  ths_region,
  ths_concepts,
  mktcap,
  pe,
  pb,
  CAST(`date` AS DATETIME) AS selection_date,
  `is_B2战法` AS is_b2_pullback_strategy,
  `is_少妇战法` AS is_bbi_kdj_strategy,
  `is_搬砖战法` AS is_brick_chart_strategy,
  `is_补票战法` AS is_bbi_short_long_strategy,
  violent_k_count,
  violent_k_date,
  violent_k_pct_chg,
  violent_k_vol_ratio,
  violent_k_prev_j,
  violent_k_curr_j,
  close,
  pctChg,
  bbi,
  K,
  D,
  J,
  turnover,
  amount
FROM Stock.daily_selection_results
WHERE `date` = (SELECT MAX(`date`) FROM Stock.daily_selection_results);
