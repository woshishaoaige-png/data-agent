# data-agent

自然语言查询 A 股数据库的 Agent 基础设施。当前完成 **阶段 0：数据治理**。

## 目录

```
├── catalog.json          ← 【真相源】自动生成，描述全部表的结构/行数/覆盖度，勿手改
├── SKILL.md              ← Agent 硬规则：先 catalog，再 reference，再 SQL
├── evals/                ← 25 题行为评测集
├── references/           ← 高 ROI 参考：陷阱、JOIN 白名单、核心领域
├── sql/
│   └── create_views.sql  ← 语义视图（v_kline = 14 张分片表合并）
└── tools/
    ├── build_dashboard.py ← 单文件 HTML dashboard：KPI、图表、可筛选表格
    ├── db.py             ← Agent 唯一数据库连接入口（统一 mysqlconnector 驱动）
    ├── check_all.py      ← 本地总检查入口
    ├── context_extractor.py ← 从 catalog 生成业务域 reference/eval 草稿
    ├── gen_catalog.py    ← catalog.json 自省生成器
    ├── lint_references.py← 防止 reference 复制 catalog 事实
    ├── profile_table.py  ← 表画像：空值、distinct、日期/数值范围、重复 key
    ├── query_guard.py    ← SQL 静态护栏：表/单位/coverage/join 检查
    ├── run_eval_cases.py ← 可执行 QueryGuard 回归用例
    ├── smoke_eval.py     ← 快速机制冒烟检查
    └── validate_result.py← 查询结果验证：空结果、趋势点数、重复粒度、异常指标
```

## 阶段 0 已落地（G1–G4）

| 项 | 内容 |
|----|------|
| G1 | `Stock.v_kline` 视图收口 14 张 kline 分片表 — Agent 一律查 `v_kline`，禁止直接查 `kline_xxx` |
| G2 | `catalog.json` 由 information_schema 自省生成，替代会漂移的 Obsidian 笔记 |
| G3 | 每表自动打 `coverage` 主档 + `flags` 多标签，作为稀疏/过期/短历史熔断依据 |
| G4 | `tools/db.py` 为 Agent 提供唯一连接入口（不改动现有 42 个采集脚本） |

## 当前语义视图

- `Stock.v_kline`：14 张 K 线分片的唯一 Agent 入口
- `Stock.v_stock_moneyflow_yi`：个股资金流，金额统一为亿元
- `Stock.v_board_moneyflow_dc_yi`：东财板块资金流，金额统一为亿元
- `Stock.v_board_moneyflow_ths_yi`：同花顺板块资金流，金额统一为亿元
- `Stock.v_top_inst_net_yi`：龙虎榜席位按股票/日期聚合，金额统一为亿元
- `Stock.v_strategy_selection_latest`：最新策略选股结果，策略标签规范化

## 维护：加表/改表后刷新真相源

```bash
PY=/Users/weini/.hermes/venv/bin/python3

# 改了表结构 → 重建视图（如新增 kline 分片）
mysql -uroot -p******* < sql/create_views.sql

# 任何加表/数据变化后 → 刷新 catalog
$PY tools/gen_catalog.py

# 快速检查：catalog 机制 + reference 漂移风险
$PY tools/lint_references.py
$PY tools/smoke_eval.py
$PY tools/run_eval_cases.py
$PY tools/check_all.py
```

> 建议把 `gen_catalog.py` 加到 `run_board_collectors.sh` 收尾，实现"加数据即刷新"。

## coverage 熔断约定（供后续 Skill 引用）

- `SINGLE_STOCK`：仅 1 只股票，禁止用于跨股票对比/排名/横截面
- `TINY`：行数 < 100，时序/趋势结论不可靠，回答须披露样本量
- `OK`：横截面可正常查询，但仍需看 `flags`

## flags 熔断约定

- `SHORT_HISTORY`：不同日期 < 3，禁止做趋势/时序/“过去 N 月”类结论
- `STALE_CURRENT`：真日期/新鲜度列距今 > 2 天，不能当成今日/当前结果

## 单位约定

`catalog.json` 只对高风险金额表维护 `unit` 字段。跨资金表比较前必须归一，
推荐统一报 `亿元`。典型陷阱：

- `hsgt_moneyflow_snapshot` / `stock_moneyflow_snapshot`：万元
- `dc_moneyflow_snapshot` / `dc_moneyflow_mkt_snapshot` / `ths_moneyflow_snapshot`：元

## 多数据库配置

data-agent 的连接与自省支持 MySQL / PostgreSQL / Hive，通过 `databases.yaml` 配置。

1. 复制模板：`cp databases.example.yaml databases.yaml`
2. 填写数据源；密码用 `${ENV_VAR}` 引用环境变量，不要写明文。
3. 设置激活源：yaml 的 `active` 字段，或环境变量 `DATA_AGENT_DATASOURCE`。
4. 导出密码后生成 catalog：

   ```bash
   export MYSQL_PWD=...           # 对应 yaml 里的 ${MYSQL_PWD}
   python tools/gen_catalog.py
   ```

说明：
- MySQL 的 `schemas` 是 database 名列表；PostgreSQL 需额外 `database` 字段，`schemas` 指 PG schema。
- `psycopg2` / `PyHive` 仅在用对应引擎时安装。
- 视图 `sql/create_views.sql` 与单位/维度业务知识是 A 股数据集特定的，换库时需相应调整。
- `DATA_AGENT_DB_URL` 可整体覆盖连接串。

## Anthropic data plugin 借鉴后的新增流程

### 1. 执行前护栏

```bash
$PY tools/query_guard.py \
  --intent "最新行业板块涨幅 Top5" \
  --sql "SELECT ... FROM Stock.ths_daily_snapshot ..."
```

### 2. 执行后结果验证

```bash
$PY tools/validate_result.py \
  --intent "最近半年板块资金流趋势" \
  --sql "SELECT trade_date, net_yi FROM Stock.v_board_moneyflow_ths_yi ..."
```

用于发现空结果、趋势点数不足、重复 grain（疑似 join explosion）、全 NULL 指标、百分比尺度异常、TopN 行数不足。

统计型问题还会校验样本量、自检列和数值边界：相关系数必须在 `[-1,1]`，回归 `r2` 必须在 `[0,1]`，标准差不能为负，滚动结果必须暴露 `window_n`。

### 3. 新表/陌生表画像

```bash
$PY tools/profile_table.py --table Stock.stock_moneyflow_snapshot --limit 5000
```

用于补充 `catalog.json` 没表达的真实值分布：空值率、distinct、top values、日期范围、数值范围、重复自然 key。

### 4. 可视化 / Dashboard

```bash
$PY tools/build_dashboard.py \
  --title "板块资金流 Dashboard" \
  --sql "SELECT trade_date, name, net_yi FROM Stock.v_board_moneyflow_ths_yi ..." \
  --out /tmp/board_moneyflow_dashboard.html
```

生成单文件 HTML，内嵌数据，提供 KPI、自动图表、可筛选/排序表格。Dashboard 是呈现层：SQL 仍应先过 `query_guard.py`，结果仍应先过 `validate_result.py`。

### 5. 新业务域上下文草稿

```bash
$PY tools/context_extractor.py \
  --domain moneyflow \
  --pattern moneyflow \
  --out-dir /tmp/data-agent-context
```

这会生成可 review 的 reference markdown 和 eval 候选。草稿不自动进入 `references/` 或 `evals/`，需要人工确认业务口径后再固化。

### 6. 复杂 SQL 能力参考

- `references/statistical_sql.md`：CORR / REGR / STDDEV 的样本量、配对非空、单位归一和输出自检规则。
- `references/window_frames.md`：滚动、累计、排名、最新 TopN 的窗口帧和 CTE 分层规则。

复杂统计或窗口 SQL 应先按 reference 写成 staged CTE，再过 `query_guard.py`；执行后用 `validate_result.py` 检查样本量和结果边界。

### 7. 对抗性 Eval

`tools/run_eval_cases.py` 支持两类用例：

- `tool=query_guard`：静态 SQL 风险检查。
- `tool=validate_result`：用 `rows_json` 检查执行后结果形状。

新增复杂 SQL 能力时，eval 至少经过两轮对抗：第一轮生成攻击样本，第二轮审查已落地规则的 false negative / false positive，再把稳定样本固化进 `evals/eval_cases.json`。
