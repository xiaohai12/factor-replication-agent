---
type: architecture
status: draft
project: factor-replication-agent
created: 2026-05-12
updated: 2026-06-11
version: 5
tags: [architecture, thesis, factor-replication, agent, quant, harness, meta-coder]
---

# Factor Replication Agent Architecture

> 中文名：**受控元代码生成的因子回测流水线与实现偏差归因框架**  
> English title: **Controlled Meta-Coder Agents for Auditable Factor Backtesting Pipeline Generation and Implementation-Gap Attribution**

## 1. 项目定位 / Positioning

这个项目不是一个 autonomous trading agent，也不是让 LLM 自由做金融研究或自由修改回测代码。

它更适合被定义为一个：

> **Auditable AI-generated factor backtesting pipeline system**  
> 一个可审计的、由 AI 辅助生成因子回测流水线的系统。

核心研究问题是：

> LLM 能否根据学术论文中的因子描述，自动生成因子信号构造代码，同时保证回测过程可审计、时间上正确，并且能够解释不同实现方式造成的 replication gap？

一句话概括：

> **让 LLM 写因子 signal，不让 LLM 控制实证结论。**

---

## 2. 核心思想 / Core Idea

本框架采用：

> **Controlled Meta-Coder + Adversarial Sandbox** architecture

也就是：

1. LLM 在 **Semantic Extractor** 阶段只读取 original paper text（和必要的 data dictionary 用于字段名校验）；
2. LLM 可以提取因子定义和方法假设；
3. LLM 可以生成 factor-specific signal plugin；
4. 但 LLM 不能自由决定完整回测流程；
5. universe、breakpoint、weighting、portfolio construction、return computation、metrics 和 evidence logging 由固定框架控制；
6. 所有 generated code 都必须经过验证；
7. 最终用 dual-track 和 factorial attribution 解释不同实现设定带来的结果差异。

核心分工是：

| 部分 | 谁负责 | 作用 |
|---|---|---|
| 因子含义提取 | Semantic Extractor | 从论文中提取 paper-first 因子定义和方法假设，生成 draft MethodSpec，不负责后续 resolution |
| MethodSpec 审查 | Review Gate | 严格审查 draft MethodSpec 的 paper evidence、schema/parser contract 和 codegen-readiness，输出 review report 和 remediation mode |
| MethodSpec 解决器 | MethodSpec Resolution Applier | 根据 approved review findings 对 existing JSON 做字段级 resolution；默认不重生成整份 JSON |
| 数据目录映射 | Data Catalog / Normalizer | 把 paper-stated source hints 映射到 executable tables/columns/filters，不改写 paper facts |
| 信号代码生成 | LLM | 基于 approved MethodSpec + normalized data mapping 生成 raw signal construction plugin |
| 回测生命周期 | Controlled Engine | 根据 approved MethodSpec / implementation config 受控执行 universe、breakpoint、portfolio、return、metrics |
| 代码验证 | Sandbox | 检查生成代码是否可运行、是否有未来函数、是否符合 MethodSpec |
| 多版本实验 | Controller | 跑 original track、standardized track 和 ablation variants |
| 结果归因 | Attribution Layer | 解释 replication gap 来自哪些 implementation choices |

---

## 3. 总体架构 / High-Level Architecture

```text
Input Sources
Extractor: original paper text + data dictionary
Evaluation/Normalizer: C&Z metadata / OSAP reference code / implementation rules
        │
        ▼
[1. Semantic Extractor]
从 original paper 提取因子定义、公式、数据字段、timing、missing policy 等，生成 draft MethodSpec
        │
        ▼
[2. Review Gate]
审查 MethodSpec 的 paper evidence、schema/parser contract、architecture boundary 和 codegen-readiness
        │
        ├── local clear issues ──► [2.1 MethodSpec Resolution Applier]
        │                          根据 review report 对 existing JSON 做字段级 resolution
        │
        ├── structural extraction issue ──► [1. Semantic Extractor]
        │                                   targeted re-extraction of specific fields/sections
        │
        ▼
[2.5 Data Catalog / Normalizer]
把 approved paper-stated data concepts/source hints 映射为 executable database tables/columns 和 implementation config
        │
        ▼
[3. Controlled Meta-Coder]
根据 approved MethodSpec + normalized data mapping 生成 factor-specific signal plugin
        │
        ▼
[4. Adversarial Sandbox]
验证 generated plugin：语法、schema、时间正确性、未来函数、可复现性
        │
        ▼
[5. Plugin Registry]
保存通过验证的 plugin、code hash、MethodSpec hash、validation report
        │
        ▼
[6. Controlled Backtesting Lifecycle Engine]
受控执行回测生命周期：根据 approved MethodSpec / implementation config 执行 universe、breakpoints、portfolios、returns、metrics
        │
        ▼
[7. Dual-Track + Factorial Controller]
用同一个 signal plugin 跑 original / standardized / ablation variants
        │
        ▼
[8. Evidence Store + Run Registry]
保存每次 run 的 config、hash、metrics、artifacts 和 logs
        │
        ▼
[9. Factorial Attribution Layer]
分解 replication gap，解释差异来自哪些 implementation choices
```

### 3.1 Feedback Loops / 反馈回路

线性流程之外，以下情况会触发 **backtrack**：

```text
[4. Sandbox] ──technical error──► [3. Meta-Coder]          (bounded repair, max 3 retries)
[4. Sandbox] ──empirical issue──► [2. Review Gate]          (lag/missing/leakage 需重审)
[2. Review Gate] ──local fixes──► [2.1 MethodSpec Resolution Applier]  (字段级 resolve existing JSON)
[2. Review Gate] ──structural issue──► [1. Extractor]       (targeted re-extraction, not full regeneration by default)
[9. Attribution] ──anomaly─────► [2. Review Gate]           (结果异常，可能 MethodSpec 有误)
[6. Lifecycle] ──data error────► [Data Layer]               (字段缺失、linking 问题)
```

触发条件与处置：

| 触发点 | 条件 | 回退目标 | 处置 |
|---|---|---|---|
| Sandbox → Meta-Coder | syntax error, schema mismatch, type error | Meta-Coder | LLM bounded repair, ≤3 次；超过 → Review Gate |
| Sandbox → Review Gate | temporal leakage, lag violation, forbidden pattern (empirical) | Review Gate | MethodSpec 可能有误，需要重新审查 |
| Review Gate → MethodSpec Resolution Applier | 问题是局部的、字段级的、paper evidence clear（如 enum/schema drift、missing standard field、quote precision、reported metric omission） | Resolution Applier | 基于 review report resolve existing JSON；不重新生成整份 JSON |
| Review Gate → Extractor | formula / target / main spec / timing / portfolio construction 等结构性错误，或 reviewer 发现漏读关键 section/table | Extractor | targeted re-extraction of affected fields/sections；默认不 full regenerate；必要时升级 `needs_human_confirmation` |
| Attribution → Review Gate | original_method 结果与论文 reported 值偏差 >50%（or t-stat 符号翻转） | Review Gate | 可能 MethodSpec 提取错误，复查 signal definition 和 timing |
| Lifecycle → Data Layer | 字段不存在、CCM link 覆盖率异常低、数据量级不合理 | Data Layer | 检查 data dictionary mapping、snapshot 完整性 |

**Max backtrack depth:** 任何单个 factor 的 backtrack 链不超过 3 轮。超过 3 轮 → 标记 `status: needs_manual_intervention`，暂停该 factor 的自动化流程。

### 3.2 Data Layer / 数据层

Data Layer 是所有模块的底层依赖，为 Semantic Extractor（字段校验）、Lifecycle Engine（回测执行）和 Evidence Store（snapshot 记录）提供数据服务。

```text
┌─────────────────────────────────────────────────────┐
│                    Data Layer                        │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │  CRSP    │  │ Compustat │  │   CCM Linktable  │  │
│  │ (msf,   │  │ (funda,   │  │  (gvkey↔permno,  │  │
│  │  msenames,│ │  fundq)   │  │   linkdt range)  │  │
│  │  dlret)  │  │           │  │                  │  │
│  └────┬─────┘  └─────┬─────┘  └────────┬─────────┘  │
│       │              │                 │             │
│       └──────────────┼─────────────────┘             │
│                      ▼                               │
│         ┌────────────────────────┐                   │
│         │  Data Dictionary Layer │                   │
│         │  字段名 → 含义/单位/日期 │                   │
│         └────────────┬───────────┘                   │
│                      │                               │
│         ┌────────────▼───────────┐                   │
│         │   Snapshot Manager     │                   │
│         │  versioned data pulls  │                   │
│         └────────────────────────┘                   │
└─────────────────────────────────────────────────────┘
```

#### 数据来源 / Data Sources

| 数据集 | 内容 | 用途 |
|---|---|---|
| CRSP `msf` | 月度股票价格、收益率、市值 | return computation, market cap weighting |
| CRSP `msenames` | 股票名称、交易所、share code | universe filtering (common shares, exchange) |
| CRSP `dlret` | 退市收益率 | delisting-adjusted returns |
| Compustat `funda` | 年度财报 (assets, BE, sales, earnings...) | signal construction (annual factors) |
| Compustat `fundq` | 季度财报 | signal construction (quarterly factors) |
| CCM `ccmxpf_linkhist` | gvkey ↔ permno link table with date ranges | CRSP-Compustat merge |

数据通过 WRDS (Wharton Research Data Services) 获取。

#### Point-in-Time Available Date (`time_avail_m`) / 时点可用日期

借鉴 C&Z `SignalMasterTable.py` 的核心设计：Data Layer 在预处理阶段为每条 Compustat 记录计算 `time_avail_m`（该记录最早可被投资者合法使用的月份），将 accounting lag 统一内化到数据层。

好处：
- signal plugin 只需按 `[permno, time_avail_m]` merge 并计算 formula，**不需要自行处理 lag**；
- 消除了因 plugin 各自实现 lag 导致的不一致性和 look-ahead bias 风险；
- lag 作为 implementation choice 由 Lifecycle Engine / MethodSpec config 控制，便于 ablation。

```
原始 Compustat 记录: gvkey=001234, datadate=2020-12-31, ceq=500
                ↓ accounting lag = 6 months
time_avail_m = 2021-06  （最早可用于 portfolio formation 的月份）
```

#### Data Snapshot / 数据快照策略

每次正式实验使用 **frozen data snapshot**，确保结果可复现：

```yaml
snapshot_id: "snap-2026-05-01"
pull_date: "2026-05-01"
crsp_end_date: "2024-12-31"
compustat_end_date: "2024-12-31"
storage: "data/snapshots/snap-2026-05-01/"
format: parquet
hash: "sha256:abc123..."
```

- **Phase 1（开发阶段）：** 使用 WRDS query + 本地 parquet 缓存，snapshot = 一次 pull 的结果。
- **Phase 2+（正式实验）：** snapshot freeze，所有 runs 使用同一份数据。数据变更需要 new snapshot + new snapshot_id。

#### CCM Linking 规则 / CCM Link Handling

CCM linking 由 Lifecycle Engine 统一处理，不由 signal plugin 自行实现：

- 使用 `linktype IN ('LC', 'LU')`，`linkprim IN ('P', 'C')`；
- 按 `linkdt` / `linkenddt` 范围匹配，确保 point-in-time correctness；
- 一个 `permno` 在同一时间只匹配一个 `gvkey`（优先 `linkprim = 'P'`）；
- duplicate links 和 link gap 的处理 logged in evidence store。

#### Data Dictionary Integration / 数据字典集成

Data Layer 维护一份 **field registry**，Semantic Extractor 和 Review Gate 用它来校验 MethodSpec 中的字段名：

```yaml
# 示例 entry
- field: ceq
  dataset: compustat
  table: funda
  description: "Total Common/Ordinary Equity"
  unit: millions_usd
  frequency: annual
  available_from: 1950
  notes: "may be negative; check for missing vs. zero"
```

如果 MethodSpec 引用的字段不在 registry 中 → Review Gate 自动 flag 为 `needs_llm_review`。

#### Data Catalog / Normalizer Mapping / 数据目录映射层

MethodSpec extractor output 中的 `data.sources[].source_details` 和 `data.required_fields[].source_detail` **不是 codegen-ready physical table**。它们保留 paper wording / annotator wording，作为 source hint。

例如 extractor 可以保留：

```text
"annual industrial files"
"monthly stock return files"
"PST Active/Research"
"daily NYSE/AMEX File"
"historical CUSIPs"
```

这些字段不要求在 extraction 阶段统一成 `crsp.msf`、`crsp.dsf`、`comp.funda` 或 `ccm.ccmxpf_linkhist`。真实数据库映射由 Data Catalog / Normalizer 完成。

数组/string 规则：`source_details` 是复数数组，用在 `data.sources[]`；`source_detail` 是单数字符串，用在 `data.required_fields[]`。

Data Catalog entry 示例：

```yaml
concept_id: crsp_monthly_stock_return
paper_aliases:
  - monthly stock return files
  - CRSP monthly stock returns
source_hint:
  dataset: crsp
  source_detail: monthly stock return files
implementation:
  provider: wrds
  library: crsp
  table: msf
  required_columns:
    permno: permno
    date: date
    return: ret
    price: prc
    shares_outstanding: shrout
quality_checks:
  - nonmissing_permno_date
  - valid_return_range
```

Normalizer 的职责：

| Input from MethodSpec | Data Catalog output | Notes |
|---|---|---|
| paper-stated dataset/source hint | physical provider/library/table/columns | e.g. CRSP monthly returns → WRDS CRSP monthly table |
| paper-stated exchange names | implementation filter | e.g. NYSE/Amex/NASDAQ → approved exchange-code mapping |
| paper-stated accounting fields | concrete Compustat variables | only after dictionary/reviewer approval |
| sample coverage notes | data-loader requirements/warnings | e.g. survivor-bias-free coverage, delisting treatment |
| ambiguous MethodSpec fields | blocked or candidate implementation choice | no silent defaults |

**Codegen contract:** Controlled Meta-Coder / Lifecycle Engine should consume the normalized Data Catalog mapping or approved implementation config, not raw `MethodSpec.data.*.source_detail(s)` strings directly.

---

## 4. 各模块作用 / Module Responsibilities

### 4.1 Input Sources / 输入来源

输入源分两类，避免 evaluation answer 泄漏到 extraction：

**Semantic Extractor 可用：**

- original paper text；
- CRSP / Compustat / CCM data dictionaries（仅用于字段名和字段含义校验，不用于补 paper 没说的实现细节）；
  - **CRSP**：美国股票价格、收益率、市值、退市收益等市场数据；
  - **Compustat**：公司财报和基本面数据，如 assets、sales、book equity、earnings；
  - **CCM**：CRSP/Compustat Merged link table，用于把 Compustat 的 `gvkey` 和 CRSP 的 `permno` 正确连接起来；
  - **data dictionary**：字段说明书，用于确认变量含义、单位、日期定义、缺失值和可用字段，防止 LLM 猜字段。
- researcher notes。

**Extractor 不可用、但后续可用：**

- Chen-Zimmermann metadata：用于 extraction evaluation / downstream acronym mapping；
- Open Source Asset Pricing reference code：用于 diagnostic cross-check / normalizer，不作为 paper MethodSpec 证据；
- implementation defaults：只在 standardized track 或 approved implementation config 中使用。

作用：

> Extractor 从 paper 中提取 paper-stated method facts；C&Z / OSAP / reference code 用于事后评价和标准化实现，不回灌覆盖 paper-first MethodSpec。

C&Z 资源的完整说明（SignalDoc.csv 字段、代码结构、数据集、编程接口、与架构模块的映射）见 [[cz-reference]]。

---

### 4.2 Semantic Extractor / 语义提取器

作用：

> 把 original paper 中的自然语言描述，转换成结构化的 `MethodSpec` / `FactorSpec`。

它需要提取：

- factor definition；
- economic intuition；
- required data fields；
- signal formula；
- timing assumptions；
- formation month；
- rebalance frequency；
- holding period；
- accounting lag；
- missing-value policy；
- universe restrictions；
- breakpoint rule；
- weighting rule；
- long-short direction；
- source citations；
- ambiguous fields。

这一层可以使用 LLM，因为论文通常是不结构化的；但 extractor 阶段不读取 C&Z / OSAP / reference implementation，避免把答案当输入。

但它的输出不是代码，而是：

> **结构化方法说明 MethodSpec。**

#### 提取策略 / Extraction Strategy

Semantic Extractor 采用 **paper-first extraction**：LLM 仅从论文原文提取 MethodSpec，不在提取阶段参考 C&Z metadata 或 reference code。C&Z SignalDoc.csv 保留为 **evaluation ground truth**，用于量化提取准确率。

提取分三步：

1. **Paper extraction.** LLM 从论文原文中提取所有 MethodSpec 字段。输入仅限论文文本 + data dictionary（字段名校验）。不提供 SignalDoc.csv 或 OSAP reference code，避免信息泄漏。
2. **Ambiguity tagging.** 论文中未明确说明的字段写入 `ambiguous_fields`，用 `status: inferred / unspecified / weak_or_conflicting / conflicting` 等状态标记，供 Review Gate 审查。
3. **Evaluation against C&Z.** 提取完成后，将 MethodSpec 与 SignalDoc.csv 对应行逐字段比对，计算 extraction accuracy。差异记入 eval report，但**不回灌修正 MethodSpec**——差异本身是研究数据（LLM extraction 能力的度量）。

这个设计的好处：
- **测试 LLM 真实提取能力**：从非结构化学术文本到结构化 MethodSpec 的完整链路；
- **C&Z 作为 ground truth 而非 shortcut**：避免 "用答案当输入" 的循环论证；
- **extraction accuracy 本身是 thesis contribution**：量化 LLM 对因子定义的理解程度。

#### Extractor Boundary / Extractor 边界

Semantic Extractor 只负责 **paper → draft MethodSpec**。它不负责 review 后的 JSON resolution，也不应在 review 阶段重新生成整份 MethodSpec。

默认修复流程是：

```text
Draft MethodSpec JSON
        ↓
Review Gate produces field-level findings
        ↓
MethodSpec Resolution Applier applies approved local edits
        ↓
Review Gate re-checks resolved JSON
```

Extractor 只有在以下情况才重新介入：

- factor / signal set 识别错误；
- formula、timing、sample、portfolio construction 等 high-impact 字段整体不可信；
- reviewer 发现 extractor 漏读关键 section / table / appendix；
- paper target scope 选错，例如 multi-asset paper 被错误合并成一个 executable target。

即便 extractor 重新介入，也优先做 **targeted re-extraction**，只重读相关 section/table 并重提取 affected fields。Full regeneration 只用于 JSON 大面积不可信、schema version 大改、或原始 target 选择根本错误的情况。

#### MethodSpec 输出格式 / MethodSpec Schema

`MethodSpec` 采用 `methodspec.v1` JSON：它记录 **original paper 直接陈述的方法事实**，而不是 C&Z / OSAP 标准化后的选择。C&Z `SignalDoc.csv` 只用于事后 evaluation；除 `cz_acronym` 这个映射字段外，不应作为 extractor 的输入来源。

当前内部表示是 `methodspec.v1` JSON，规范见 `schemas/methodspec-json-template.md` 和 `schemas/methodspec.v1.schema.json`。

关键 parser contract：

- `source.location / quote / interpretation` 必须字段级保留；
- `signal.formula.expression` 是 codegen 输入，`paper_expression` 是 paper audit 输入；
- `reported_results.return_calculation` 使用 `input_return` + `portfolio_return` 两层；
- paper 未明确的 high-impact 字段，不应在主字段里硬填 inferred value；主字段保持 `unspecified`，候选值放 `ambiguous_fields.candidate_value`；
- `cz_acronym` 只是 optional downstream mapping metadata，不是 extraction target，也不能作为 source evidence。

#### 提取质量评估 / Extraction Validation

对 pilot factors，将 LLM 提取的 MethodSpec 与 C&Z `SignalDoc.csv` 逐字段比对：

| 评估维度 | 方法 |
|---|---|
| 字段覆盖率 | MethodSpec 中非空字段数 / 总字段数 |
| 字段准确率 | 与 C&Z SignalDoc 一致的字段数 / 可比较字段数 |
| 歧义率 | `ambiguous_fields` 数量 / 总字段数 |
| 关键字段命中 | `formula`, `lag`, `breakpoints`, `weighting` 四个核心字段的准确率 |
| 差异分类 | 每个不一致字段标注原因：论文模糊 / LLM 误读 / C&Z 自行补充 / 合理分歧 |

Phase 1 的 acceptance criteria：核心字段准确率 ≥ 80%（pilot factors）。如果达不到，需要增加 structured prompting 或 few-shot examples。

**注意：** evaluation 是事后比对，不是实时纠正。差异分类本身是论文的分析素材——可以回答 "LLM 在哪些类型的因子定义上提取最容易出错"。

---

### 4.3 Review Gate / 审查关卡

作用：

> 由一个默认非常严格、picky 的 **LLM Reviewer** 主导审查，防止不确定或错误的提取结果直接变成 empirical truth。

Review Gate 需要检查：

- MethodSpec 格式是否符合 `methodspec.v1` JSON Schema；
- 关键假设是否有 paper citation / section evidence；
- 字段是否存在于数据字典；
- timing 是否符合论文；
- missing-value policy 是否明确；
- lag 和 reporting-date alignment 是否合理；
- `sign`、`portfolio.implied_factor_direction`、`reported_results.comparison_policy` 是否一致；
- `reported_results.return_calculation.input_return`、`portfolio_return`、paper-reported spreads / t-stats 是否来自论文主结果表；
- C&Z / OSAP 是否仅作为 evaluation / diagnostic cross-check 使用，而不是偷偷覆盖 paper-first MethodSpec。

LLM Reviewer 的默认策略是：

> 宁可 reject / ask for clarification，也不要默认通过有歧义的 empirical assumption。

重要原则：

> missing-value imputation、winsorization、sample restriction、lag choice 和 field substitution 都是 empirical choices，不是普通 bug fix。

这些内容必须写入 `MethodSpec`，并通过 picky review 后才能进入代码生成阶段。LLM Reviewer 可以批准常规一致性检查；但当证据不足或相互冲突，且假设会 materially affect empirical results 时，必须升级为 `needs_human_confirmation`。

#### Review Gate Output and Remediation Mode / 审查输出与修复模式

Review Gate 默认 **不直接修改 JSON**，而是输出结构化 review report。Review report 必须包含：

- `review_status`: `approved | revision_required | blocked`；
- `codegen_ready`: `yes | no`；
- `paper_faithful`: `yes | no`；
- issue list with severity, field path, current value, paper evidence, recommended fix；
- `remediation_mode`。

`remediation_mode` 只能是：

| Mode | When to use | Next step |
|---|---|---|
| `resolve_existing_json` | 问题是局部字段级，paper evidence clear，现有 MethodSpec target 可信 | MethodSpec Resolution Applier applies field-level edits to existing JSON |
| `targeted_reextraction` | high-impact field 可能整体误读，或漏读关键 section/table，但 target 大体可信 | Semantic Extractor re-reads specific paper sections and regenerates only affected fields |
| `full_regeneration` | factor target / schema / JSON structure 大面积不可信 | Regenerate MethodSpec from scratch; use only when necessary |

默认选择 `resolve_existing_json`。不要因为发现几个 parser/schema 问题就 full regenerate。

Review report 应给出 resolution-friendly table：

```text
| Severity | Field path | Current value | Recommended value | Evidence | Resolution confidence |
```

Review Gate 可以建议 resolution，但 resolution 执行由 MethodSpec Resolution Applier 或 human-approved edit step 完成。

#### MethodSpec Resolution Applier / MethodSpec 解决器

MethodSpec Resolution Applier 的职责是：

> 根据 approved review findings，对 existing MethodSpec JSON 做最小字段级修改。

Resolution Applier 输入：

- existing MethodSpec JSON；
- Review Gate report；
- optional user-approved subset of fixes。

Resolution Applier 规则：

1. 只修改 review report 明确指出、且 evidence clear / user approved 的字段；
2. 不重新生成整份 JSON；
3. 不重新解释 paper，也不引入新的 paper facts；
4. 不修改 review report 未提到的字段，除非是 parser-required placeholder（例如 `benchmark: null`, `adjustments: []`）；
5. 修改后必须重新运行 JSON parse 和 parser contract checks；
6. 输出 resolution log，列出每个 changed field。

如果 resolution applier 发现需要重新解释 paper 才能决定字段值，应停止并返回 Review Gate / Extractor，改为 `targeted_reextraction`。

#### Review Decision Matrix / 审查决策矩阵

每个 MethodSpec 字段按 **empirical impact** 和 **evidence quality** 两个维度分类，决定 LLM Reviewer 的处置方式：

| Evidence \ Impact | Low impact | High impact |
|---|---|---|
| **Clear paper evidence** | `auto_approve` | `auto_approve` |
| **Paper evidence partial / ambiguous** | `auto_approve` with flag | `needs_llm_review` |
| **Unspecified in paper** | `leave_empty` or `approve_with_default` only for standardized track | `needs_human_confirmation` for `original_method` |
| **Paper vs. C&Z/OSAP differ** | `flag_for_eval` | `needs_llm_review`; do not overwrite paper-first value without human decision |

**High-impact fields**（改变会 materially affect empirical results）：
- `formula`
- `signal.sign`, `portfolio.implied_factor_direction`, `reported_results.comparison_policy`
- `timing.accounting_lag_months`, `timing.formation`, `timing.rebalance_frequency`, `timing.holding_period_months`, `timing.skip_months`
- `universe.missing_policy`, `universe.winsorize_bounds`
- `portfolio.sort.breakpoint_source`, `portfolio.sort.ls_quantile`
- `portfolio.weights`, `portfolio.weighting_scheme`, `reported_results.return_calculation.portfolio_return.weighting`
- `universe`, `filter`（especially microcap / exchange / share-code treatment）
- `reported_results.return_horizon`, `reported_results.spreads`, `reported_results.return_type`（用于 replication-gap normalization）

**Low-impact fields**（通常不影响核心结论）：
- `factor_name`, `paper_ref`, `pdf_file`
- `economic_intuition`, `annotator_notes`
- `paper_sections`
- `cz_acronym`（仅映射字段）

#### 处置定义 / Disposition Definitions

| 处置 | 行为 |
|---|---|
| `auto_approve` | LLM Reviewer 直接通过，无需人工介入 |
| `auto_approve` with flag | 通过，但在 MethodSpec 的 `review_notes` 中标记，供后续审计 |
| `leave_empty` | paper 未说明且 README 规则允许留空时，保持 empty/null，不发明设定 |
| `approve_with_default` | 仅用于 `standardized_hxz` track 的 sensible default（如 lag=6m, missing=drop），标记 `source: default`，写入 `ambiguous_fields` |
| `flag_for_eval` | 保留 paper-first MethodSpec，同时记录与 C&Z / OSAP 的差异，供 extraction evaluation 使用 |
| `needs_llm_review` | LLM Reviewer 需要给出 reasoning 并做出判断，记录 rationale |
| `needs_human_confirmation` | **Hard block.** 生成 review ticket，暂停 pipeline 等待人工确认 |

#### Sensible Defaults / 合理默认值

当论文没有明确说明、且当前运行的是 `standardized_hxz` track 时，才使用以下 defaults（基于 HXZ / C&Z 惯例）：

| 字段 | Default | 来源 |
|---|---|---|
| `timing.accounting_lag_months` | 6 months | HXZ convention |
| `universe.missing_policy.action` | drop | C&Z common practice |
| `timing.formation.month` | June (annual) | FF convention |
| `portfolio.sort.breakpoint_source` | NYSE | HXZ standardized |
| `portfolio.weights` / `portfolio_return.weighting` | value-weight | HXZ standardized |
| `timing.rebalance_frequency` | annual | FF convention |

**注意：** 这些 defaults 只在 `source: unspecified` 时使用，且只应用于 `standardized_hxz` track。`original_method` track 中如果关键字段 unspecified，必须升级为 `needs_human_confirmation`。

#### Review 输出格式

```yaml
review_id: "rev-hml-001"
methodspec_version: "v1"
reviewer: llm          # llm | human
disposition: approved   # approved | revision_required | blocked
remediation_mode: resolve_existing_json  # resolve_existing_json | targeted_reextraction | full_regeneration
codegen_ready: true
paper_faithful: true
review_notes:
  - field: missing_policy
    status: leave_empty
    reason: "paper does not state how missing signal values are handled; original_method keeps this unspecified"
  - field: breakpoint_source
    status: auto_approve
    reason: "paper Table III states NYSE breakpoints"
  - field: cz_acronym
    status: flag_for_eval
    reason: "mapping to SignalDoc.csv only; not used to overwrite extracted fields"
blocked_fields: []      # list of fields requiring human confirmation
```

---

### 4.4 Controlled Meta-Coder / 受控元代码生成器

作用：

> 根据 approved MethodSpec 生成 factor-specific signal plugin。

它可以做：

- 声明 required fields；
- mapping raw fields to semantic variables；
- 构造 raw signal；
- 输出 formation-level signal table。

它不能做：

- 计算 portfolio returns；
- 分组或决定 breakpoints；
- 决定 weighting；
- 构造 long-short portfolios；
- 计算 t-stat；
- 修改 universe；
- 偷偷改变 missing-value policy；
- 改变 lag assumption；
- 调整样本来贴近目标结果。

核心边界：

> LLM 生成的是 signal construction plugin，不是完整 backtest script。

---

### 4.5 Adversarial Sandbox / 对抗式沙盒

作用：

> 在 generated plugin 被正式使用前，测试它是否可运行、是否符合 MethodSpec、是否存在未来函数或其他风险。

主要检查：

- syntax / import / type checks；
- output schema check；
- forbidden-pattern scan；
- synthetic-data oracle test；
- temporal leakage test；
- lag / date alignment check；
- reproducibility check；
- reference sanity check。

如果是技术性错误，例如 syntax error、字段名错误、schema mismatch，可以允许 LLM 做 bounded repair。

如果涉及 empirical assumptions，例如 lag、missing policy、sample restriction、temporal leakage，则必须回到 Review Gate。

---

### 4.6 Plugin Registry / 插件注册表

作用：

> 保存通过验证的 generated plugins，并为后续实验提供可追溯记录。

需要记录：

- plugin id；
- factor id；
- generated code；
- generated code hash；
- MethodSpec hash；
- MethodSpec version；
- validation status；
- validation report；
- repair trace。

这样每个实验结果都可以追溯到具体的 signal plugin 和 MethodSpec。

---

### 4.7 Controlled Backtesting Lifecycle Engine / 受控回测生命周期引擎

作用：

> 提供所有因子共享的 controlled empirical lifecycle。

它负责：

- loading approved data snapshots；
- CRSP / Compustat / CCM linking；
- applying approved lag rules；
- applying missing-value policy；
- universe filtering；
- breakpoint computation；
- portfolio assignment；
- EW / VW / capped VW return computation；
- long-short return construction；
- t-stat、alpha、coverage、microcap share 等 metrics；
- evidence logging。

这一层的代码在 formal experiments 中应该 frozen and versioned，但具体参数可以由 approved MethodSpec / implementation config 控制。

LLM 可以在开发阶段帮助写这个 base framework，但正式实验时不能随意修改。

原因是：

> 回测逻辑里的很多代码改动，本质上是 empirical assumption changes，会直接影响结论。

---

### 4.8 Dual-Track + Factorial Controller / 双轨与因子实验控制器

作用：

> 用同一个 accepted signal plugin，在不同 implementation settings 下运行实验。

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

#### 文章自己的回测周期 / Article-Specific Timing

为了复现文章，`original_method` 应该遵守原文或 reference implementation 的回测周期，例如：

- formation month；
- rebalance frequency；
- holding period；
- return horizon；
- skip month；
- portfolio start / end month；
- accounting lag；
- overlapping portfolios。

这些周期由 Semantic Extractor 读取，写入 MethodSpec，经 Review Gate 审查后，由 Controlled Backtesting Lifecycle Engine 执行。

`standardized_hxz` 才使用统一标准化周期和规则。

---

### 4.9 Evidence Store + Run Registry / 证据存储与运行注册表

作用：

> 保存每次实验的所有关键信息，使结果可复查、可复现、可审计。

每次 run 应该记录：

- run id；
- factor id；
- plugin id；
- MethodSpec version / hash；
- generated code hash；
- base lifecycle commit；
- data snapshot hash；
- implementation config hash；
- metrics；
- return series path；
- signal series path；
- logs；
- status。

Run Registry 则记录每个 factor × variant 的状态：

- pending；
- running；
- success；
- failed；
- needs_review。

---

### 4.10 Factorial Attribution Layer / 实现偏差归因层

作用：

> 解释为什么 `original_method` 和 `standardized_hxz` 的结果不同。

它回答的问题包括：

- 差异有多少来自 universe？
- 有多少来自 breakpoint？
- 有多少来自 weighting？
- 有多少来自 accounting lag？
- 有多少来自 rebalance frequency？
- 有多少来自 missing-value policy？
- 有多少来自 winsorization？
- 是否存在 interaction effects？

可能使用的方法：

- one-at-a-time ablation；
- full-factorial ANOVA；
- variance decomposition；
- Shapley-style decomposition；
- interaction-effect analysis。

输出包括：

- attribution matrix；
- implementation-choice deviation matrix；
- per-factor evidence report；
- cross-factor summary table；
- generated-code failure taxonomy。

---

## 5. 框架中的 Agentic 部分 / What Counts as Agentic?

| 模块 | Agentic? | 说明 |
|---|---:|---|
| Semantic Extractor | Yes | LLM 读取 original paper text（和字段字典校验），提取 paper-first MethodSpec。 |
| Review Gate | Partly | LLM 可辅助检查，但关键 empirical assumptions 需要 rule / human approval。 |
| Controlled Meta-Coder | Yes | LLM 生成 factor-specific signal plugin。 |
| Adversarial Sandbox | Partly | 测试是 deterministic；LLM 只做 bounded repair。 |
| Controlled Backtesting Lifecycle Engine | No during formal experiments | 正式实验中代码 frozen and versioned；参数由 approved MethodSpec / implementation config 控制。 |
| Dual-Track Controller | Mostly no | 按 explicit rules 运行 variants。 |
| Attribution Layer | Partly | 统计分解 deterministic；LLM 可辅助解释和报告。 |

---

## 6. 为什么不让 LLM 自由修改回测？

因为回测不是普通工程代码，很多细节就是研究设计本身。

例如：

- universe 怎么选；
- NYSE breakpoints 还是 full-sample breakpoints；
- equal-weighted 还是 value-weighted；
- accounting lag 几个月；
- missing values 丢弃还是填 0；
- 是否包含 delisting returns；
- long-short direction 怎么定义。

这些都会直接改变 empirical results。

所以正式实验中需要：

> LLM 可以生成 signal plugin，但不能自由修改 backtesting lifecycle。

否则 replication gap 无法归因，也无法判断结果差异到底来自文章设定、标准化规则，还是 LLM 自己改了代码。

---

## 7. 这个框架的论文贡献 / Thesis Contribution

这个框架的主要贡献可以概括为：

1. **Controlled Meta-Coder architecture**  
   把 LLM 限制为 signal plugin generator，而不是 autonomous empirical researcher。

2. **MethodSpec-first workflow**  
   先提取并审查 empirical assumptions，再生成代码。

3. **Separation of signal and lifecycle**  
   signal construction 由 LLM plugin 完成，portfolio construction 和 return computation 由 controlled lifecycle engine 完成。

4. **Adversarial validation**  
   用 sandbox 检查 generated code 是否可执行、是否时间正确、是否存在未来函数。

5. **Dual-track replication design**  
   同时支持 original-method reproduction 和 standardized HXZ-style robustness test。

6. **Implementation-gap attribution**  
   用 ablation / factorial methods 分解 replication gap 来自哪些 implementation choices。

7. **Evidence-based auditability**  
   每个结果都有 MethodSpec hash、code hash、data snapshot hash、base commit 和 config hash。

最终 framing：

> 本项目研究 LLM 是否可以作为受控的 Meta-Coder，为学术因子自动生成 signal construction plugins；同时通过 controlled empirical lifecycle、adversarial validation 和 factorial attribution，保证因子复现过程的可审计性、时间正确性和实现偏差可解释性。

---

## 8. 与 Quant Team 协作 / Collaboration with Quant Team

> Corrected phrasing: **Cooperate with the quant team to create a factor replication agent.**

这个项目需要与 quant team 协作，而不是由 LLM 或单个工程模块独立完成。Quant team 的角色不是简单“验收代码”，而是共同定义 empirical standards、确认数据口径、审查关键假设，并把系统输出转化为可用于研究与复现的证据链。

### 8.1 协作目标 / Collaboration Goal

与 quant team 共同构建一个：

> **能够从论文描述出发，自动生成、验证并运行因子复现流水线的受控 agent 系统。**

具体目标包括：

- 将论文中的 factor definition 转换为结构化 `MethodSpec`；
- 由 LLM 生成 factor-specific signal plugin；
- 由 controlled lifecycle engine 统一执行 portfolio construction 和 return computation；
- 与 quant team 一起审查 high-impact assumptions；
- 对复现结果和论文 / C&Z / OSAP 结果之间的差异做 attribution；
- 形成可审计、可复现、可扩展的 factor replication workflow。

### 8.2 Quant Team 的核心职责 / Quant Team Responsibilities

| 协作环节 | Quant Team 负责什么 | 系统 / Agent 负责什么 |
|---|---|---|
| MethodSpec review | 判断论文假设是否被正确理解；确认 formula、lag、universe、breakpoints、weighting 等关键设定 | 从 original paper 提取结构化 MethodSpec，并把 C&Z / OSAP 差异作为 evaluation note |
| Data mapping | 确认 CRSP / Compustat / CCM 字段含义、单位、可用时间和 linking 规则 | 根据 data dictionary 做字段校验和 schema 检查 |
| Empirical assumption approval | 对 high-impact 或 conflicting assumptions 做最终确认 | 自动 flag ambiguity，并生成 review ticket |
| Signal validation | 检查 generated signal 是否符合经济含义 | 生成 signal plugin，并通过 sandbox 做技术与时间正确性测试 |
| Backtest design | 确认 original-method 与 standardized-HXZ track 的实验设定 | 用 controlled lifecycle engine 执行统一回测 |
| Result interpretation | 判断 replication gap 是否经济上合理，是否需要复查 MethodSpec | 生成 attribution matrix、run evidence 和 anomaly report |

### 8.3 协作边界 / Collaboration Boundary

Quant team 主要介入 **empirical judgment**，agent 主要承担 **automation and auditability**。

- Quant team 不需要手写每个因子的完整 backtest script；
- Agent 不允许自行决定会影响结论的 empirical assumptions；
- 所有 high-impact choices 必须可追溯到 paper、reference code、data dictionary 或 human review；
- 若 agent 与 reference implementation 冲突，不能自动“调参贴结果”，必须记录为 implementation-gap evidence。

### 8.4 推荐协作流程 / Suggested Workflow

```text
Quant team selects pilot factor
        │
        ▼
Agent extracts MethodSpec from paper
        │
        ▼
Quant team reviews high-impact assumptions
        │
        ▼
Agent generates signal plugin
        │
        ▼
Sandbox validates code and timing correctness
        │
        ▼
Controlled engine runs original / standardized / ablation tracks
        │
        ▼
Agent produces attribution report
        │
        ▼
Quant team reviews economic plausibility and signs off
```

### 8.5 可交付成果 / Deliverables for Quant Collaboration

每个 pilot factor 应该交付：

1. `MethodSpec.json`：结构化因子定义与 paper-first 方法假设；
2. `review_report.yaml` / `review_report.md`：Quant / LLM Reviewer 的审查记录，包含 `remediation_mode` 和 field-level recommended resolutions；
3. `resolution_log.yaml`：MethodSpec Resolution Applier 对 existing JSON 做的字段级修改记录；
4. `signal_plugin.py`：通过 sandbox 的 generated signal code；
5. `validation_report.json`：schema、timing、leakage、synthetic oracle 测试结果；
6. `run_registry.csv`：所有 original / standardized / ablation runs 的状态；
7. `replication_gap_attribution.md`：差异归因解释；
8. `evidence_bundle/`：code hash、MethodSpec hash、data snapshot hash、logs 和 artifacts。

### 8.6 简历 / Project Description 可用表述

如果需要在 resume、project page 或 thesis proposal 中压缩成一句话，可以写：

> **Cooperated with a quantitative research team to design a controlled LLM meta-coder agent that extracts factor definitions from academic papers, generates auditable signal-construction plugins, validates temporal correctness in a sandbox, and attributes replication gaps across portfolio construction choices.**

更短版本：

> **Built a controlled LLM-based factor replication agent with a quant team, enabling auditable signal generation, sandbox validation, and implementation-gap attribution for academic asset-pricing factors.**
