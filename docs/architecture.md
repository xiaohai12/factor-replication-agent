---
type: architecture
status: active
project: factor-replication-agent
created: 2026-05-12
updated: 2026-06-20
version: 6
tags: [architecture, factor-replication, agent, quant]
---

# Factor Replication Agent Architecture

> 中文名：**受控元代码生成的因子回测流水线与实现偏差归因框架**
> English title: **Controlled Meta-Coder Agents for Auditable Factor Backtesting Pipeline Generation and Implementation-Gap Attribution**

---

## 1. 项目定位 / Positioning

核心研究问题：

> LLM 能否根据学术论文中的因子描述，自动生成因子信号构造代码，同时保证回测过程可审计、时间上正确，并且能够解释不同实现方式造成的 replication gap？

一句话概括：

> **让 LLM 写因子 signal，不让 LLM 控制实证结论。**

---

## 2. 核心设计原则 / Design Principles

| 原则 | 说明 |
|---|---|
| LLM 只生成 signal | `compute_signal()` 由 LLM 生成；universe / 断点 / 加权 / lag 由 MethodSpec + impl_config 驱动 |
| 回测骨架固定 | 步骤顺序固定（见 §3）；每步的具体内容按 MethodSpec 配置，不让 LLM 自由改实证逻辑 |
| paper-first MethodSpec | 从论文原文提取方法事实；C&Z / OSAP 只作 evaluation，不覆盖 paper-stated 内容 |
| impl_config 显式记录人工决定 | MethodSpec 里 unspecified 的高影响字段由人工在 impl_config 里定死并标注来源 |

---

## 3. 流水线 / Pipeline

```text
[original paper PDF]
        │
        ▼
[1. Semantic Extractor]
从 original paper 提取因子定义、公式、数据字段、timing、missing policy 等
输出: draft MethodSpec JSON
        │
        ▼
[2. Review Gate]
审查 MethodSpec 的 paper evidence、schema 正确性、codegen-readiness
    ├── local issues ──► [2.1 MethodSpec Resolution Applier]
    │                    对 existing JSON 做字段级 resolution
    └── structural issues ──► [1. Semantic Extractor] targeted re-extraction
输出: reviewed + resolved MethodSpec JSON（codegen_ready: true）
        │
        ▼
[2.5 impl_config]
手写 per-factor JSON，完成两件事：
  (a) 概念 → 物理列名（paper source hints → funda.at / msf.ret / msf.me …）
  (b) 显式定死 MethodSpec 里 unspecified 的高影响字段（记为人工决定）
        │
        ▼
[3. Meta-Coder（单文件生成模式）]
输入: resolved MethodSpec + impl_config
输出: per-factor Python 文件，包含：
  • compute_signal(df) ← LLM 生成，只做公式计算，不处理 lag
  • 固定骨架函数（模板带入）:
      load_data / build_signal_master_table / merge_signal / filter_universe /
      compute_breakpoints / assign_portfolios / compute_returns /
      compute_long_short / compute_metrics / run()
生成后做一行 future-function 扫描（shift(- / lead( / .future），命中即报错
        │
        ▼
[4. Dual-Track 执行]
用同一个 signal plugin，跑不同 implementation settings：
  • original_method  — 按 MethodSpec paper-stated 方法
  • standardized_hxz — 统一 HXZ-style 设置
  • ablation_*       — 每次只改一个 implementation switch
读取预存本地数据（data/local/*.parquet）
        │
        ▼
[5. Evidence Store + Run Registry]
每次 run 记录: config hash、code hash、MethodSpec hash、metrics、return series
        │
        ▼
[6. Factorial Attribution Layer]
对比 original_method vs standardized_hxz vs ablation variants
分解 replication gap：来自 universe / 断点 / 加权 / lag / missing policy / …
输出: attribution matrix、per-factor evidence report
```

---

## 4. 各模块说明 / Module Details

### 4.1 Semantic Extractor

从 original paper 提取 paper-first MethodSpec。

- 输入仅限论文文本 + data dictionary（字段名校验）；不读 C&Z / OSAP
- 提取内容：factor definition、formula、data fields、timing、lag、universe、breakpoints、weighting、missing policy 等
- paper 未明确的字段标注 `status: unspecified / inferred / conflicting`，写入 `ambiguous_fields`
- 输出：`draft MethodSpec JSON`（schema: `methodspec.v1`）

评估：提取完成后将 MethodSpec 与 C&Z SignalDoc.csv 逐字段对比，计算 extraction accuracy。差异记入 eval report，**不回灌修正 MethodSpec**。

### 4.2 Review Gate

审查 MethodSpec 的可信度和 codegen-readiness。

审查内容：
- schema 是否符合 `methodspec.v1`
- 关键假设是否有 paper citation
- timing、lag、sign、weighting、reported results 是否一致
- 高影响字段（formula / lag / universe / breakpoints / weighting）是否有清晰 evidence

输出 review report，包含 `review_status`、`codegen_ready`、`remediation_mode` 和逐字段 resolution 建议。

修复模式（`remediation_mode`）：

| 模式 | 使用时机 |
|---|---|
| `resolve_existing_json` | 局部字段级问题，paper evidence clear |
| `targeted_reextraction` | 高影响字段可能整体误读，但 target 大体可信 |
| `full_regeneration` | JSON 大面积不可信（极少用）|

高影响字段（改变会 materially affect 实证结果）：`formula`、`timing.*`、`universe.*`、`portfolio.sort.*`、`portfolio.weights`、`reported_results.*`。

### 4.3 impl_config

每因子一个 JSON，做两件事：

```json
{
  "factor_id": "cooper_gulen_schill_2008_asset_growth",
  "column_mapping": {
    "total_assets": "at",
    "monthly_return": "ret",
    "market_equity": "me",
    "exchange": "exchcd",
    "sic": "siccd"
  },
  "implementation_decisions": {
    "breakpoint_source": "full_sample",
    "weighting": "vw",
    "quantiles": 10,
    "accounting_lag_months": 6,
    "_note": "source: human decision — unspecified in paper"
  }
}
```

所有 `unspecified` 的高影响字段必须在这里显式定死并标注 `_note`，不允许 LLM 自行填入。

### 4.4 Meta-Coder（单文件生成）

输入 resolved MethodSpec + impl_config，输出一个 per-factor Python 文件：

```
factor_backtest_{factor_id}.py
  ├── compute_signal(df)             ← LLM 生成
  │     接收 keyed [permno, time_avail_m] 的 annual df
  │     使用 impl_config 提供的物理列名
  │     只做公式计算，禁止在此处处理 lag
  │     输出 [permno, yyyymm, signal]
  │
  ├── load_data(data_path)           ┐
  ├── build_signal_master_table(...) │
  ├── merge_signal(...)              │ 模板固定，读 config
  ├── filter_universe(...)           │ 不让 LLM 改
  ├── compute_breakpoints(...)       │
  ├── assign_portfolios(...)         │
  ├── compute_returns(...)           │
  ├── compute_long_short(...)        │
  ├── compute_metrics(...)           ┘
  └── run(data_path, config)         ← 串起全部步骤
```

`compute_signal` 的边界：
- ✅ 可以：声明 required fields、mapping 列名到语义变量、构造 raw signal formula
- ❌ 不能：计算 portfolio returns、决定 breakpoints、改 missing policy、处理 lag、修改 universe

### 4.5 Data Layer（本地文件模式）

预存两张表（来源不限，可从 WRDS 导出后本地存好）：

| 文件 | 内容 | 关键列 |
|---|---|---|
| `data/local/funda.parquet` | Compustat annual（已 CCM 关联好，带 permno） | `permno, datadate, at, siccd, exchcd, shrcd` |
| `data/local/msf.parquet` | CRSP monthly returns | `permno, date, ret, me`（`me = abs(prc)*shrout`） |

`build_signal_master_table`：`time_avail_m = datadate + lag_months → YYYYMM`，输出年度表 keyed `[permno, time_avail_m]`，`at` 已按时点对齐——signal plugin 只读列，不处理 lag。

### 4.6 回测骨架函数说明

固定步骤，参数全部取自 config（来自 MethodSpec + impl_config）：

| 步骤 | 内容 |
|---|---|
| `merge_signal` | 年度 signal（June-t 成形）展开到 Jul t – Jun t+1 的 12 个月，merge 到 msf |
| `filter_universe` | `shrcd in (10,11)`、`exchcd in (1,2,3)`、排除 `6000 ≤ sic ≤ 6999`、两年 Compustat seasoning |
| `compute_breakpoints` | 按 config 十分位断点（full_sample 或 NYSE 子集） |
| `assign_portfolios` | 按断点分组 |
| `compute_returns` | VW（`me` 权重）+ EW |
| `compute_long_short` | low − high，方向取 MethodSpec `implied_factor_direction` |
| `compute_metrics` | 月度均值、Newey-West t-stat、coverage、microcap share |

---

## 5. 文件结构 / File Layout

```
data/
  method_specs/
    curated/          # raw extracted MethodSpec
    reviewed/         # reviewed MethodSpec + review report
    resolved/         # post-resolution MethodSpec（codegen_ready: true）
    impl_config/      # per-factor column mapping + implementation decisions
  local/
    funda.parquet     # Compustat annual（预存）
    msf.parquet       # CRSP monthly（预存）
  plugins/            # 生成的 per-factor Python 文件

src/
  extractor/          # Semantic Extractor
  review_gate/        # Review Gate + Resolution Applier
  meta_coder/         # 生成器 + 模板
  data_layer/         # local loader + build_signal_master_table + impl_config loader
  models/             # MethodSpec、PluginRecord 等 Pydantic models
  llm.py              # LLM client

scripts/
  run_factor_backtest.py   # 端到端驱动脚本
```

---

## 6. 端到端流程示例 / End-to-End Example

```bash
# 1. 已有 reviewed/resolved methodspec，准备好本地数据后：
python scripts/run_factor_backtest.py \
  --factor cooper_gulen_schill_2008_asset_growth

# 输出：
# MethodSpec loaded: cooper_gulen_schill_2008_asset_growth (codegen_ready=True)
# impl_config loaded: breakpoint_source=full_sample, weighting=vw, quantiles=10
# Plugin generated: data/plugins/cooper_gulen_schill_2008_asset_growth.py
# Future-function scan: PASS
# Running backtest...
# VW low-high spread: +X.XX% / month   t-stat: X.XX
# EW low-high spread: +X.XX% / month   t-stat: X.XX
# Coverage: XX%   Microcap share: XX%
# Paper reported (CGS2008 Table II): ~XX% / year
```

---

## 7. Dual-Track + Factorial Controller / 双轨与因子实验控制器

作用：

> 用同一个 signal plugin，在不同 implementation settings 下运行实验。

主要 track：

| Track | 作用 |
|---|---|
| `original_method` | 尽量忠实复现 original paper stated method；C&Z / OSAP 只作 diagnostic comparison |
| `standardized_hxz` | 用统一 HXZ-style 设置做标准化 robustness test |
| `ablation_*` | 每次只改变一个 implementation choice |
| `factorial_*` | 对多个 implementation choices 做 full-factorial combinations |

关键原则：

> 不同 track 使用同一个 signal plugin，只改变 approved implementation switches。

这样可以保证结果差异来自 implementation choices，而不是来自重新生成代码。

`original_method` 应该遵守原文的回测周期：formation month、rebalance frequency、holding period、return horizon、skip month、accounting lag、overlapping portfolios 等。这些由 MethodSpec 提取、经 Review Gate 审查后，由回测骨架执行。

`standardized_hxz` 使用统一标准化周期和规则（lag=6m、NYSE 断点、VW、annual rebalance 等）。

---

## 8. Evidence Store + Run Registry / 证据存储与运行注册表

作用：

> 保存每次实验的所有关键信息，使结果可复查、可复现、可审计。

每次 run 记录：

- run id、factor id、plugin id
- MethodSpec version / hash、generated code hash
- data snapshot hash、implementation config hash
- metrics（spread、t-stat、alpha、coverage、microcap share）
- return series path、signal series path
- logs、status

Run Registry 记录每个 factor × variant 的状态：`pending / running / success / failed / needs_review`。

---

## 9. Factorial Attribution Layer / 实现偏差归因层

作用：

> 解释为什么 `original_method` 和 `standardized_hxz` 的结果不同。

回答的问题：

- 差异有多少来自 universe？
- 有多少来自 breakpoint？
- 有多少来自 weighting？
- 有多少来自 accounting lag？
- 有多少来自 rebalance frequency？
- 有多少来自 missing-value policy？
- 是否存在 interaction effects？

可能使用的方法：one-at-a-time ablation、full-factorial ANOVA、variance decomposition、Shapley-style decomposition。

输出：attribution matrix、implementation-choice deviation matrix、per-factor evidence report、cross-factor summary table。

---

## 10. 以后可扩展的部分 / Currently Deferred

以下模块在当前 pilot 阶段暂不实现，骨架代码保留 stub：

| 模块 | 扩展时机 |
|---|---|
| Adversarial Sandbox（完整检查） | 扩展到多因子批量分析时 |
| Plugin Registry（hash + 版本管理） | 需要跨实验可追溯时 |
| WRDS 实时连接 / CCM merge / snapshot 哈希 | 需要数据版本管理或定期更新时 |
| Dual-Track Controller（§7）实现 | 单因子 pilot 跑通后 |
| Factorial Attribution Layer（§9）实现 | 有多个 track 结果后 |
| Evidence Store + Run Registry（§8）实现 | 结果需要完整审计链时 |
