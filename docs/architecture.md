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
| LLM 只生成 signal + hooks | `compute_signal()` 由 LLM 生成；非标准回测步骤由 LLM 生成 hook 函数；标准步骤由 BacktestEngine 固定代码处理 |
| 回测骨架固定，步骤顺序不变 | 11 个步骤的执行顺序固定（见 §3）；每步走 standard 路径还是 hook 路径由 MethodSpec 判断，但顺序本身不允许 LLM 改变 |
| standard vs hook 由 MethodSpec 驱动 | BacktestEngine 对每个步骤维护 standard set；MethodSpec 字段值在 standard set 内走 config，超出则触发 LLM 生成对应 hook 函数 |
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
① BacktestEngine._detect_hooks(spec) 判断哪些步骤需要 hook
② LLM 生成 compute_signal() — 所有因子必有
③ LLM 生成 hook 函数（仅当步骤超出 standard set 时）：
     compute_breakpoints_hook / filter_universe_hook /
     assign_portfolios_hook / compute_returns_hook 等
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

`src/pipeline.py` 的 `Pipeline` 类实现以下有界回路（全局上限 `MAX_BACKTRACK_DEPTH = 3`）：

| 触发条件 | 回路方向 | 上限 |
|---|---|---|
| Future-Leak Scan 发现禁用模式 | Scan → Meta-Coder 重新生成 | `MAX_REPAIR_RETRIES = 3` |
| Review Gate 未通过（非 `requires_human`） | Review Gate → Extractor 重新提取 | 计入 backtrack_count |
| Attribution 检测到**异常**（sign flip 或 >50% gap） | Attribution → Review Gate 触发重审 | 计入 backtrack_count |
| backtrack_count ≥ 3 | 任何阶段 → `needs_manual_intervention = True` | — |

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

调用 `BacktestEngine._detect_hooks(spec)`，对比 MethodSpec 字段值与各步骤的 standard set，返回需要 LLM 生成的 hook 列表。

**阶段 2：LLM 代码生成**

```
signal_plugin_{factor_id}.py
  ├── compute_signal(df)                   ← 所有因子必有，LLM 生成
  │     接收 keyed [permno, time_avail_m] 的 annual df
  │     使用 spec.data.normalized_mapping 提供的物理列名
  │     只做公式计算，禁止处理 lag
  │     输出 [permno, yyyymm, signal]
  │
  └── {step}_hook(df, config)              ← 仅当该步骤超出 standard set 时生成
        例：compute_breakpoints_hook       — double-sort / 非标准分位
            filter_universe_hook          — industry-neutral / 自定义过滤
            assign_portfolios_hook        — conditional sort / 复杂分组
            compute_returns_hook          — 非标准权重 / capped VW
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

### 4.6 BacktestEngine：Standard Set + Hook 机制

BacktestEngine 对每个步骤维护一个 **standard set**——值在集合内走固定实现（读 config），超出集合则期望 plugin 提供对应 hook 函数。

```python
STANDARD = {
    "breakpoint_source": {"full_sample", "nyse"},
    "weighting":         {"vw", "ew"},
    "sort_type":         {"single_sort"},
    "missing_action":    {"drop", "unspecified"},
    "universe_filter":   {"standard_crsp"},   # shrcd/exchcd 标准组合
}
```

**`_detect_hooks(spec) → dict[step, reason]`**

对比 resolved MethodSpec 字段与 STANDARD，返回哪些步骤需要 hook：

| MethodSpec 字段 / 值 | 触发 hook |
|---|---|
| `portfolio.sort.type = "double_sort"` | `compute_breakpoints_hook` + `assign_portfolios_hook` |
| `universe` 含 industry-neutral 条件 | `filter_universe_hook` |
| `weighting` 不在 `{vw, ew}` | `compute_returns_hook` |
| `missing_policy.action = "winsorize"` | `apply_missing_policy_hook` |

**执行时，每步优先调 hook，无 hook 走标准实现：**

```python
bp = plugin.hooks.get("compute_breakpoints", self._compute_breakpoints)(merged, config)
```

**标准步骤实现（所有因子共用）：**

| 步骤 | Standard 实现 |
|---|---|
| `merge_signal` | 年度 signal 展开到 Jul t – Jun t+1，merge 到 msf |
| `filter_universe` | `shrcd in (10,11)`、`exchcd in (1,2,3)`、排除金融股、2 年 seasoning |
| `compute_breakpoints` | full_sample 或 NYSE 子集的分位断点 |
| `assign_portfolios` | 按断点单排序分组 |
| `compute_returns` | VW（`me` 权重）或 EW |
| `compute_long_short` | 方向取 MethodSpec `implied_factor_direction` |
| `compute_metrics` | 月度均值、Newey-West t-stat、coverage、microcap share |

Attribution 保证：两个 track 使用同一个 plugin（含相同 hook），只改 config → 结果差异 100% 来自 config 选择。

---

## 5. 文件结构 / File Layout

```
app.py                          # Streamlit dashboard（主要人工交互入口）

data/
  method_specs/
    curated/                    # raw extracted MethodSpec（未审查）
    reviewed/                   # reviewed MethodSpec + review report
    resolutions/                # Review Gate 生成的逐字段 resolution 建议
    resolved/                   # post-resolution MethodSpec（codegen_ready: true）
                                # 含 data.normalized_mapping + resolution_log
  plugins/                      # 生成的 per-factor signal plugin Python 文件
  paper_text_cache/             # PDF 转换后的文本缓存（审计用）
  eval_history/                 # 批量 extraction accuracy 评估记录
  local/                        # ⚠ 尚未建立（见 §10）
    funda.parquet               # Compustat annual（需人工导出后放置）
    msf.parquet                 # CRSP monthly（需人工导出后放置）

evidence/                       # EvidenceStore 输出目录（运行后生成）
  {factor_id}/{run_id}/         # per-run artifacts

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

# Step 4: 通过 Pipeline 生成 plugin + 运行实验（需先准备 data/local/*.parquet）
python - <<'EOF'
from src.pipeline import Pipeline
pipeline = Pipeline()
runs, status = pipeline.run_factor(
    factor_id="cooper_gulen_schill_2008_asset_growth",
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
| Pipeline 反馈回路 | ✅ 已实现 | `src/pipeline.py`，见 §3.1 |
| Streamlit Dashboard | ✅ 已实现 | `app.py`，覆盖 extract → review → resolve → codegen |
| BacktestEngine standard steps | ✅ 已实现 | 全部 7 个 standard 步骤实现；`_detect_hooks(spec)` + `_build_config()` 完成 |
| BacktestEngine hook dispatch | ✅ 已实现 | 每步 `_dispatch()` — hook 优先，无 hook 走 standard；见 §4.6 |
| Attribution Layer | 🚧 基础结构已有 | `AttributionResult` 结构定义完毕，分解算法待实现 |
| data/local/*.parquet | ⏳ 未建立 | 需人工从 WRDS 导出 funda + msf 后放置 |
| WRDS 实时连接 / CCM merge | ⏳ 未实现 | 需要数据版本管理或定期更新时扩展 |
| Plugin hash 持久化 | ⏳ 未实现 | Plugin Registry 当前为 in-memory；需要跨进程追溯时扩展到磁盘 |
