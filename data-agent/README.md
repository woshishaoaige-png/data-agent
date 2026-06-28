# data-agent

自然语言查询 A 股数据库的 Agent 基础设施。当前完成 **阶段 0：数据治理**。

## 目录

```
data-agent/
├── catalog.json          ← 【真相源】自动生成，描述全部表的结构/行数/覆盖度，勿手改
├── SKILL.md              ← Agent 硬规则：先 catalog，再 reference，再 SQL
├── evals/                ← 25 题行为评测集
├── references/           ← 高 ROI 参考：陷阱、JOIN 白名单、核心领域
├── sql/
│   └── create_views.sql  ← 语义视图（v_kline = 14 张分片表合并）
└── tools/
    ├── db.py             ← Agent 唯一数据库连接入口（统一 mysqlconnector 驱动）
    ├── check_all.py      ← 本地总检查入口
    ├── gen_catalog.py    ← catalog.json 自省生成器
    ├── lint_references.py← 防止 reference 复制 catalog 事实
    ├── query_guard.py    ← SQL 静态护栏：表/单位/coverage/join 检查
    ├── run_eval_cases.py ← 可执行 QueryGuard 回归用例
    └── smoke_eval.py     ← 快速机制冒烟检查
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
mysql -uroot -p******* < data-agent/sql/create_views.sql

# 任何加表/数据变化后 → 刷新 catalog
$PY data-agent/tools/gen_catalog.py

# 快速检查：catalog 机制 + reference 漂移风险
$PY data-agent/tools/lint_references.py
$PY data-agent/tools/smoke_eval.py
$PY data-agent/tools/run_eval_cases.py
$PY data-agent/tools/check_all.py
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
