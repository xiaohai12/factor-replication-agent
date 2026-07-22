---
type: architecture
status: active
project: factor-replication-agent
created: 2026-05-12
updated: 2026-06-21
version: 9
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
| LLM 只生成 signal + hooks | `compute_signal()` 由 LLM 生成；非标准回测步骤由 LLM 生成 hook 函数；标准步骤由 BacktestExecutor 固定代码处理 |
| 回测骨架固定，步骤顺序不变 | 固定顺序的执行链路（见 §3、§4.6 完整列表）；每步走 standard／multi-dim／overlap／hook 路径由 MethodSpec 判断，但顺序本身不允许 LLM 改变 |
| standard vs hook 由 MethodSpec 驱动 | BacktestExecutor 对每个步骤维护 standard set；MethodSpec 字段值在 standard set 内走 config，超出则触发 LLM 生成对应 hook 函数 |
| paper-first MethodSpec | 从论文原文提取方法事实；C&Z / OSAP 只作 evaluation，不覆盖 paper-stated 内容 |
| 所有决定都在 MethodSpec 里 | Resolution Applier 将 unspecified 字段决定写入 MethodSpec 的具体字段（`resolution_log` 追踪来源）；列名映射写入 `data.normalized_mapping`；不维护单独的 impl_config 文件 |
| 反馈回路有界 | 每个 factor 最多回溯 3 次（`MAX_BACKTRACK_DEPTH=3`）；超过即转人工干预 |

---

## 3. 流水线 / Pipeline

```text
[original paper PDF]
        │
        ▼
[1. Semantic Extractor]                    ◄──────────────────────────────────┐
从 original paper 提取因子定义、公式、数据字段、timing、missing policy 等        │ targeted re-extraction
输出: draft MethodSpec JSON                                                    │ (Review Gate → Extractor)
        │                                                                      │
        ▼                                                                      │
[2. Review Gate]                                                               │
审查 MethodSpec 的 paper evidence、schema 正确性、codegen-readiness              │
    ├── local issues ──► [2.1 MethodSpec Resolution Applier]                   │
    │                    对 existing JSON 做字段级 resolution：                  │
    │                    • 将 unspecified 高影响字段决定写入具体 spec 字段         │
    │                    • DataDictionary.normalize_fields() 生成列名映射          │
    │                      写入 spec.data.normalized_mapping                      │
    │                    • 所有人工决定追加到 resolution_log                       │
    └── structural issues ──────────────────────────────────────────────────── ┘
输出: reviewed + resolved MethodSpec JSON（codegen_ready: true）
        │
        ▼
[3. Meta-Coder]
输入: resolved MethodSpec（列名映射和所有决定已在 spec 字段中）
① BacktestExecutor._detect_hooks(spec) 判断哪些步骤需要 hook（2026-07-20 起大幅收窄，见 §4.6——filter_universe/多维排序/return_combination/overlapping/Fama-MacBeth 均已默认走确定性标准实现，只有真正 paper-specific 的情况才 hook）
② LLM 生成 compute_signal() — 所有因子必有
③ LLM 生成 hook 函数（仅当步骤超出 standard set 时，参见 §4.6 表格）：
     compute_breakpoints_hook / assign_portfolios_hook /
     compute_returns_hook / apply_missing_policy_hook 等
输出: per-factor plugin（compute_signal + 按需 hook 函数）
        │
        ▼
[4. Future-Leak Scan]
扫描生成代码中的禁用模式：shift(- / lead( / .future
命中即拒绝并返回 Meta-Coder 重新生成（≤3 次）
        │ passed
        ▼
[5. Dual-Track + Factorial Controller]
用同一个 signal plugin，跑不同 implementation settings：
  • original_method  — 按 MethodSpec paper-stated 方法
  • standardized_hxz — 统一 HXZ-style 设置
  • ablation_*       — 每次只改一个 implementation switch
读取预存本地数据（data/local/*.parquet）
        │
        ▼
[6. Evidence Store + Run Registry]
每次 run 记录: config hash、code hash、MethodSpec hash、metrics、return series
        │
        ▼
[7. Factorial Attribution Layer]           ──► anomaly detected ──► [2. Review Gate] re-review
对比 original_method vs standardized_hxz vs ablation variants                （t-stat sign flip 或 >50% gap）
分解 replication gap：来自 universe / 断点 / 加权 / lag / missing policy / …
输出: attribution matrix、per-factor evidence report
```

### 3.1 反馈回路 / Feedback Loops

> **2026-07-22 更新**：本节最初描述的 `Pipeline.run_factor()` 曾因为在仓库里没有
> 任何调用方、且下表里除 Sandbox→Meta-Coder 之外的三条回路始终只是 TODO 占位
> （递增 `backtrack_count` 后立刻失败，从未真正回调上游阶段）而被删除（详见
> `docs/decision-log.md` 对应条目）。同一天，1/2/6/7 步（SemanticExtractor /
> ReviewGate / DualTrackController / AttributionLayer）被重新接入编排层，新方法
> `Pipeline.run_full_pipeline()` 跑完全部 7 步，但**刻意不实现**下表里除
> Sandbox→Meta-Coder 之外的三条跨阶段回路——遇到 Review 未通过 / Sandbox 经验性
> 问题 / Attribution 异常时直接 fail-fast 并在返回的 `PipelineStatus` 上报告
> 是哪一步失败，而不是假装会自动重试。每一步也都可以单独调用来测试/调试
> （`pipeline.extractor`/`pipeline.review_gate`/`pipeline.meta_coder`/
> `pipeline.sandbox`/`pipeline.runner`/`pipeline.controller`/
> `pipeline.attribution`）。真正的跨阶段回路仍然是 roadmap Phase 2 的范围。

`src/pipeline.py` 的 `Pipeline.run_full_pipeline()` 目前串联下面 7 步（全局
`MAX_BACKTRACK_DEPTH` 已随旧 `run_factor()` 一起移除，不再使用）：

| 触发条件 | 回路方向 | 上限 | 实现状态 |
|---|---|---|---|
| Future-Leak Scan / 技术性校验失败 | Sandbox → Meta-Coder 重新生成 | `MAX_REPAIR_RETRIES = 3` | ✅ 已实现（`_validate_with_repair()`，`run_from_method_spec()`/`run_full_pipeline()` 共用） |
| Review Gate 未通过（非 `requires_human`） | Review Gate → Extractor 重新提取 | — | ❌ 未实现：`run_full_pipeline()` 直接 fail-fast 返回，不自动重新提取 |
| Sandbox 检测到经验性问题（temporal leakage 等） | Sandbox → Review Gate 重新送审 | — | ❌ 未实现：同上，直接 fail-fast |
| Attribution 检测到**异常**（sign flip 或 >50% gap） | Attribution → Review Gate 触发重审 | — | ❌ 未实现：`attribute_ablation()` 的结果目前不会触发任何回路 |


流水线阶段状态机：`pending → extract → review → generate → validate → run → attribute → done / failed`。

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

### 4.3 Meta-Coder

输入 resolved MethodSpec（`spec.data.normalized_mapping` 已填充，所有字段已 resolved），分两阶段生成 per-factor plugin：

**阶段 1：Hook 检测**

调用 `BacktestExecutor._detect_hooks(spec)`，对比 MethodSpec 字段值与各步骤的 standard set，返回需要 LLM 生成的 hook 列表。

**阶段 2：LLM 代码生成**

```
signal_plugin_{factor_id}.py
  ├── compute_signal(df)                   ← 所有因子必有，LLM 生成
  │     接收 keyed [permno, time_avail_m] 的 annual df
  │     使用 spec.data.normalized_mapping 提供的物理列名
  │     只做公式计算，禁止处理 lag
  │     输出 [permno, yyyymm, signal]
  │
  └── {step}_hook(df, config)              ← 仅当该步骤超出 standard set 时生成（2026-07-20 起
        例：compute_breakpoints_hook          实际触发条件已收窄很多，见 §4.6 完整表格）
            assign_portfolios_hook        — 3+ 维排序，或无法识别 size 维度的多维排序
            compute_returns_hook          — 非标准权重（capped_vw）/ factor_model_alpha 等
            apply_missing_policy_hook     — winsorize 等列选择是 paper-specific 的 missing_action
```

Hook 函数边界：
- ✅ 可以：实现该步骤的自定义逻辑，接收 df + config，返回同一步骤的标准输出格式
- ❌ 不能：跨步骤（hook 不能同时做 breakpoints + portfolio assignment）、修改执行顺序、调用外部 API

Meta-Coder 还实现 `repair_plugin(plugin, errors)`，在 Future-Leak Scan 命中后重新生成（≤ `MAX_REPAIR_RETRIES = 3` 次）。

### 4.4 Future-Leak Scan

在 plugin 运行前做唯一必要的安全检查：扫描生成代码中的禁用模式。

禁用模式：`shift(-`、`.future`、`lead(`

命中即拒绝，返回 Meta-Coder 重新生成（最多 3 次）。其余检查（语法、schema、reproducibility）运行时自然暴露，无需静态扫描。

### 4.5 Data Layer（本地文件模式）

预存两张表（来源不限，可从 WRDS 导出后本地存好）：

| 文件 | 内容 | 关键列 |
|---|---|---|
| `data/local/funda.parquet` | Compustat annual（已 CCM 关联好，带 permno） | `permno, datadate, at, siccd, exchcd, shrcd` |
| `data/local/msf.parquet` | CRSP monthly returns | `permno, date, ret, me`（`me = abs(prc)*shrout`） |

`build_signal_master_table`：`time_avail_m = datadate + lag_months → YYYYMM`，输出年度表 keyed `[permno, time_avail_m]`，`at` 已按时点对齐——signal plugin 只读列，不处理 lag。

### 4.6 BacktestExecutor：Standard Set + Hook 机制

**（2026-07-20 更新，见 `plan.md` Phase 0-7 / `CHANGELOG.md` 对应条目；2026-07-21 步骤目录改为带序号命名；2026-07-21 `BacktestEngine` 类名与目录改名为 `BacktestExecutor`/`step5_executor`；2026-07-22 生成时决策层 `registry.py` 移到 `step3_codegen/`；2026-07-22 整个引擎库从 `src/steps/step5_executor/` 搬到 `src/infra/backtest_engine/`——它是被 `pipeline.py`/`step6`/`app.py`/十几个单测共用的计算基础设施，不是任何一个编号 step 的私有实现；"Step 5" 现在特指 `pipeline.py` 里"生成脚本 → 校验 → subprocess 执行"这个动作本身，见 §3 表格）** `src/infra/backtest_engine/` 现在是两个文件 + 一个瘦身后的 `registry.py`：

| 文件 | 职责 |
|---|---|
| `__init__.py` | 编排：`BacktestExecutor`、`Step` Protocol、`BacktestContext` dataclass、`run()`/`run_with_config()`/`_dispatch()` |
| `steps.py` | 计算：所有 standard 步骤的纯函数实现（无 class state） |
| `registry.py` | 运行时：只剩 `load_hooks()`（`run_with_config()` 唯一会调的"registry"逻辑） |

`STANDARD`、`detect_hooks()`、`build_config()` 这三个**只在生成时**被调用（从不被 `run_with_config()`/`_dispatch()` 自己调用）的选择逻辑，住在 `src/steps/step3_codegen/registry.py`——这样 `step3_codegen`（生成 `compute_signal()` + hook 代码、组装完整回测脚本）不再需要依赖引擎库；`BacktestExecutor._detect_hooks()`/`_build_config()`/`_resolve_long_leg()`/`_resolve_short_leg()`/`_normalize_leg()` 仍然保留在 `src/infra/backtest_engine/__init__.py` 里，作为对旧调用方（含测试）的薄委托，转发到 `step3_codegen.registry`。

单一执行路径：`src/steps/step3_codegen/script_generator.py` 生成的独立脚本现在是薄封装，直接 `import BacktestExecutor` 调 `run_with_config()`，不再内联重复实现 9 步逻辑——engine 与生成脚本不可能再互相漂移。

BacktestExecutor 对每个步骤维护一个 **standard set**——值在集合内走固定实现（读 config），超出集合则期望 plugin 提供对应 hook 函数。集合取值直接引用 `src/infra/models/method_spec.py` 里定义的枚举：

```python
STANDARD = {
    "breakpoint_source":       {"full_sample", "nyse"},
    "weighting":               {"vw", "ew"},
    "missing_action":          {"drop", "unspecified"},
    "portfolio_construction":  {"characteristic_sort", "regression_weighted", "unspecified"},
    "return_combination":      {"extreme_group_spread", "average_leg_spread",
                                 "single_signal_portfolio_return", "full_portfolio_return",
                                 "unspecified"},
}
```

`filter_universe` 曾经**无条件**不在 `STANDARD` 里（每次都生成 hook）。Phase 2.5 把 `UniverseFilterSpec`/`FilterOp` DSL 接入 `steps.filter_universe()`（`apply_universe_filters`，覆盖全部 14 个 FilterOp 取值），现在 filter_universe **默认走确定性实现**；plugin 若定义了 `filter_universe_hook` 仍然优先生效（这是插件作者的选择，不是 `detect_hooks()` 会预测的东西）。

**`detect_hooks(spec) → dict[step, reason]`**

全部走确定性字段比较，不做自由文本关键词匹配：

| MethodSpec 字段 / 值 | 触发 hook |
|---|---|
| `breakpoint_source` 不在 `{full_sample, nyse}`（含 `conditional`/`paper_specific`） | `compute_breakpoints_hook` |
| `weighting` 不在 `{vw, ew}`（如 `capped_vw`） | `compute_returns_hook` |
| `missing_policy.action` 不在 `{drop, unspecified}`（`winsorize` 等——刻意保留 hook：具体要 winsorize 哪些列是 paper-specific 的，引擎无法安全猜测） | `apply_missing_policy_hook` |
| `overlapping_portfolios=true` **且** `len(sorts) > 1` 同时出现 | `merge_signal_hook`（重叠 cohort 与多维排序两条标准路径 v1 不支持同时启用） |
| `len(portfolio_return.sorts) > 1` 且 `resolve_sort_dims()` 无法映射（非「特征 x size」两维排序，或 3+ 维） | `compute_breakpoints_hook` + `assign_portfolios_hook` |
| `portfolio_return.construction_type` 不在 `{characteristic_sort, regression_weighted, unspecified}`（如 `factor_model_alpha`、`event_window_return`、`other`） | `compute_returns_hook` |
| `portfolio_return.return_combination.type` 不在 STANDARD 集合（如 `alpha_estimate`、`other`） | `compute_long_short_hook` |

**已从「无条件 hook」变为「默认标准，仅特定组合仍需 hook」的四类**（Phase 2.5/3/4/5/7）：
- `filter_universe`：Phase 2.5 起默认确定性（DSL），不再无条件 hook。
- 多维排序：Phase 3 起「特征 x size」两维排序走 `compute_breakpoints_multi`/`assign_portfolios_multi`，只有 resolve_sort_dims() 无法识别的组合才 hook。
- `return_combination`：Phase 4 起 `average_leg_spread`/`full_portfolio_return` 也走标准 `compute_long_short`（四种组合类型统一实现），只有 `alpha_estimate`/`other` 仍 hook。
- `overlapping_portfolios`：Phase 5 起默认走 `merge_signal_overlap` 等标准重叠 cohort 实现，只有与多维排序同时出现才 hook。
- `portfolio_construction`：Phase 7 起 `regression_weighted` 路由到标准 Fama-MacBeth estimator（`steps.compute_fama_macbeth`，走 `linearmodels`），完全跳过 sort/breakpoints/assign/returns/combine 链路，不再需要 hook。

因为 `reported_results.return_calculation.portfolio_return` 字段较深、容易在提取阶段漏填，ReviewGate 的 `_check_portfolio_structure_consistency` 安全网检查仍然保留：自由文本明显暗示复杂结构但结构化字段为空时 block，要求人工补齐。

**执行时，每步优先调 hook；否则走标准/多维/重叠三选一的分发：**

```python
def _dispatch(self, step, *args, config):
    if step in self._hooks:
        return self._hooks[step](*args, config)
    if config.get("overlapping") and step in self._OVERLAP_STEPS:
        return getattr(steps, f"{step}_overlap")(*args, config)
    if len(config.get("sort_dims") or []) > 1 and step in self._MULTI_DIM_STEPS:
        return getattr(steps, f"{step}_multi")(*args, config)
    return getattr(steps, step)(*args, config)
```

**标准步骤实现（所有因子共用，固定执行顺序，`run_with_config()` 中）：**

| 步骤 | Standard 实现 |
|---|---|
| `load_data` | 读 `msf.parquet`（或 `load_daily_msf` 把日频源数据压缩成月度面板，Phase 6） |
| `apply_delisting_returns` | 有 `dlret` 列时按 CRSP 惯例并入 `ret`；无该列则 no-op（Phase 2.5） |
| `apply_missing_policy` | 默认 drop；`winsorize` 等仍需 hook（见上） |
| `filter_universe` | 基线 `shrcd in (10,11)`/`exchcd in (1,2,3)`/排除金融股，叠加 `portfolio.universe_filters` 的 FilterOp DSL（Phase 2.5），可选 microcap 排除 |
| `apply_excess_returns` | 有 `factors`（含 `rf`）且 `return_basis=excess`（默认）时减去无风险利率；否则 no-op（Phase 6，非 `_dispatch` 分发，直接调用） |
| `merge_signal` | 年度 signal 展开持有；`overlapping=true` 时走 `merge_signal_overlap`（多个错开 cohort 各自形成子组合，按月平均，Phase 5） |
| **[Fama-MacBeth 分支]** | `estimator="fama_macbeth"` 时到这里整体跳过以下 sort 相关步骤，改走 `steps.compute_fama_macbeth`（Phase 7） |
| `neutralize_signal` | 确定性 no-op scaffold（`neutralization="none"` 默认），非 none 时需 hook（Phase 2.5） |
| `compute_breakpoints` | full_sample/NYSE 分位断点；`sort_dims` 2+ 维时走 `compute_breakpoints_multi`（Phase 3） |
| `assign_portfolios` | 按断点单排序分组；多维时走 `assign_portfolios_multi`（独立/条件排序） |
| `compute_returns` | VW（`me` 权重）或 EW；多维/重叠各有对应变体 |
| `compute_long_short` | 支持 `extreme_group_spread`/`average_leg_spread`/`single_signal_portfolio_return`/`full_portfolio_return` 四种组合（Phase 4） |
| `compute_metrics` | 月度均值、Newey-West t-stat、Sharpe（Phase 2）；有 `factors` 时额外算 `compute_factor_alphas`（CAPM/FF3/FF5，`statsmodels` OLS+HAC） |

Attribution 保证：两个 track 使用同一个 plugin（含相同 hook），只改 config → 结果差异 100% 来自 config 选择。



---

## 5. 文件结构 / File Layout

```
app.py                          # Streamlit dashboard（主要人工交互入口）

data/
  paper_text_cache/             # PDF 转换后的文本缓存（审计用）
  eval_history/                 # 批量 extraction accuracy 评估记录
  test_method_specs_human_labeled/  # 人工标注的 ground truth MethodSpec（评估用，非生成）
  local/                        # ⚠ 尚未建立（见 §10）
    funda.parquet               # Compustat annual（需人工导出后放置）
    msf.parquet                 # CRSP monthly（需人工导出后放置）

runs/                            # ⚠ gitignored — 所有 pipeline 运行时生成的产物统一放这里
  method_specs/
    unreviewed/                 # raw extracted MethodSpec（未审查）
    reviewed/                   # reviewed MethodSpec + review report
    resolutions/                # Review Gate 生成的逐字段 resolution 建议
    resolved/                   # post-resolution MethodSpec（codegen_ready: true）
                                 # 含 data.normalized_mapping + resolution_log
  plugins/                      # 生成的 per-factor signal plugin Python 文件
  backtest_scripts/             # generate_backtest_script() 生成的独立可运行回测脚本
    results/                    # 脚本自己写的 CSV/metrics.json（临时，随时可删）
  evidence/                     # EvidenceStore 输出目录：{factor_id}/{run_id}/metadata.json

tests/
  fixtures/                     # ⚠ 提交进 git —— 测试 & 手动调试用的固定参考样本
    method_specs/               # golden-number 测试依赖的 resolved MethodSpec
    plugins/                    # 对应的已验证 signal plugin

src/
  pipeline.py                   # Pipeline 主编排器（含反馈回路，见 §3.1）
  pdf_mapper.py                 # PDF 文本提取工具
  llm.py                        # LLM client（支持 OpenRouter / Claude CLI / Codex）
  extractor/                    # Semantic Extractor
  review_gate/                  # Review Gate + Resolution Applier
  meta_coder/                   # MetaCoder（generate_plugin + repair_plugin）
  sandbox/                      # Future-Leak Scan（future-function 禁用模式检测）
  registry/                     # Plugin Registry（暂不使用，pilot 阶段 deferred）
  data_layer/                   # DataLayer + DataDictionary + TimeAvailComputer
  engine/                       # BacktestEngine（骨架，WIP）
  controller/                   # DualTrackController + ExperimentPlan
  attribution/                  # AttributionLayer + AttributionResult
  evidence/                     # EvidenceStore + RunRegistry
  evaluation/                   # Extraction accuracy evaluation（vs C&Z SignalDoc）
  models/                       # Pydantic models（MethodSpec、PluginRecord、RunRecord …）

scripts/
  extract_methodspecs.py        # CLI：从 PDF 批量提取 MethodSpec
  review_methodspecs.py         # CLI：批量 LLM review
  resolve_review_blocks.py      # CLI：批量应用 resolution
  validate_methodspecs.py       # CLI：校验 MethodSpec schema
  convert_papers_to_md.py       # PDF → Markdown 转换
  download_papers.py            # 下载论文 PDF
  download_osap.py              # 下载 OSAP 数据
  csv_to_gold_standard.py       # C&Z SignalDoc → gold standard 格式转换
```

---

## 6. 端到端流程示例 / End-to-End Example

### 6.1 Streamlit Dashboard（推荐入口）

```bash
# 启动 dashboard（需先激活 virtualenv）
source .venv/bin/activate
streamlit run app.py
# 浏览器访问 http://localhost:8501
```

Dashboard 覆盖完整人工环节：PDF 上传 → 提取 MethodSpec → LLM 审查 → 应用 resolution → MetaCoder 生成 plugin → Sandbox 验证。

### 6.2 CLI 脚本（批量 / 无界面）

```bash
# Step 1: 从 PDF 提取 MethodSpec
python scripts/extract_methodspecs.py --pdf papers/cgs2008.pdf --provider claude

# Step 2: LLM review
python scripts/review_methodspecs.py --factor cooper_gulen_schill_2008_asset_growth

# Step 3: 应用 resolution（审查后生成 codegen_ready=true 的 JSON）
python scripts/resolve_review_blocks.py --factor cooper_gulen_schill_2008_asset_growth

# Step 4: 通过 Pipeline 生成 plugin + 运行实验（需先准备 data/local/*.parquet 并注册 snapshot）
python - <<'EOF'
from src.pipeline import Pipeline
pipeline = Pipeline()
runs, status = pipeline.run_factor(
    factor_id="cooper_gulen_schill_2008_asset_growth",
    snapshot_id="<registered snapshot id>",
    paper_text=open("data/paper_text_cache/cgs2008.txt").read(),
)
print(status)
EOF
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

`standardized_hxz` 使用统一标准化周期和规则（lag=6m、NYSE 断点、VW、annual rebalance 等），HXZ 默认配置见 `src/controller/__init__.py` 中的 `HXZ_STANDARD_CONFIG`。

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

异常判定标准（触发 Attribution → Review Gate 回路）：
- t-stat 符号翻转（original 与 standardized 方向相反）
- `|gap| / |original_tstat| > 50%`

---

## 10. 模块实现状态 / Implementation Status

| 模块 | 状态 | 说明 |
|---|---|---|
| Semantic Extractor | ✅ 已实现 | LLM 提取 + data dictionary 校验 |
| Review Gate | ✅ 已实现 | rule-based + LLM review，`review_with_llm()` |
| Resolution Applier | ✅ 已实现 | 字段级 patch，`codegen_ready=true` 写入 |
| Meta-Coder | ✅ 已实现 | `compute_signal()` + hook 函数两阶段生成；读 `spec.data.normalized_mapping` |
| Future-Leak Scan | ✅ 已实现 | 扫描 `shift(-`/`.future`/`lead(`，命中即拒绝重生成 |
| Plugin Registry | ⏳ 暂不需要 | pilot 阶段用文件路径追溯即可；多因子跨实验时扩展 |
| Evidence Store + Run Registry | ✅ 已实现 | 磁盘持久化，per-run artifact 目录 |
| Dual-Track Controller | ✅ 已实现 | `ExperimentPlan` + `HXZ_STANDARD_CONFIG` |
| Pipeline 反馈回路 | ⚠️ 部分实现 | `src/pipeline.py`，见 §3.1——`run_full_pipeline()` 已把 1/2/6/7 步接回编排层，但只有 Sandbox→Meta-Coder 技术性修复是真正实现的回路，其余三条仍是 fail-fast（Phase 2 范围） |
| Streamlit Dashboard | ✅ 已实现 | `app.py`，覆盖 extract → review → resolve → codegen |
| BacktestExecutor standard steps | ✅ 已实现 | 全部 7 个 standard 步骤实现；`_detect_hooks(spec)` + `_build_config()` 完成 |
| BacktestExecutor hook dispatch | ✅ 已实现 | 每步 `_dispatch()` — hook 优先，无 hook 走 standard；见 §4.6 |
| Attribution Layer | 🚧 基础结构已有 | `AttributionResult` 结构定义完毕，分解算法待实现 |
| data/local/*.parquet | ⏳ 未建立 | 需人工从 WRDS 导出 funda + msf 后放置 |
| WRDS 实时连接 / CCM merge | ⏳ 未实现 | 需要数据版本管理或定期更新时扩展 |
| Plugin hash 持久化 | ⏳ 未实现 | Plugin Registry 当前为 in-memory；需要跨进程追溯时扩展到磁盘 |
