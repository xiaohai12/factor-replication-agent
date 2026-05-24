
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

1. LLM 可以读取论文、metadata 和 reference code；
2. LLM 可以提取因子定义和方法假设；
3. LLM 可以生成 factor-specific signal plugin；
4. 但 LLM 不能自由决定完整回测流程；
5. universe、breakpoint、weighting、portfolio construction、return computation、metrics 和 evidence logging 由固定框架控制；
6. 所有 generated code 都必须经过验证；
7. 最终用 dual-track 和 factorial attribution 解释不同实现设定带来的结果差异。

核心分工是：

| 部分 | 谁负责 | 作用 |
|---|---|---|
| 因子含义提取 | LLM + Review | 从论文中提取因子定义和方法假设 |
| 信号代码生成 | LLM | 生成 raw signal construction plugin |
| 回测生命周期 | Controlled Engine | 根据 approved MethodSpec / implementation config 受控执行 universe、breakpoint、portfolio、return、metrics |
| 代码验证 | Sandbox | 检查生成代码是否可运行、是否有未来函数、是否符合 MethodSpec |
| 多版本实验 | Controller | 跑 original track、standardized track 和 ablation variants |
| 结果归因 | Attribution Layer | 解释 replication gap 来自哪些 implementation choices |

---

## 3. 总体架构 / High-Level Architecture

```text
Input Sources
论文 / C&Z metadata / OSAP reference code / data dictionaries
        │
        ▼
[1. Semantic Extractor]
从资料中提取因子定义、公式、数据字段、timing、missing policy 等
        │
        ▼
[2. Review Gate]
审查 MethodSpec，确认关键 empirical assumptions
        │
        ▼
[3. Controlled Meta-Coder]
根据 approved MethodSpec 生成 factor-specific signal plugin
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
[4. Sandbox] ──technical error──► [3. Meta-Coder]     (bounded repair, max 3 retries)
[4. Sandbox] ──empirical issue──► [2. Review Gate]     (lag/missing/leakage 需重审)
[2. Review Gate] ──blocked──────► [1. Extractor]       (重新提取或请求 human input)
[9. Attribution] ──anomaly─────► [2. Review Gate]      (结果异常，可能 MethodSpec 有误)
[6. Lifecycle] ──data error────► [Data Layer]          (字段缺失、linking 问题)
```

触发条件与处置：

| 触发点 | 条件 | 回退目标 | 处置 |
|---|---|---|---|
| Sandbox → Meta-Coder | syntax error, schema mismatch, type error | Meta-Coder | LLM bounded repair, ≤3 次；超过 → Review Gate |
| Sandbox → Review Gate | temporal leakage, lag violation, forbidden pattern (empirical) | Review Gate | MethodSpec 可能有误，需要重新审查 |
| Review Gate → Extractor | 字段 conflicting 或 unspecified 且 high-impact | Extractor | 重新读取论文/code，或升级 `needs_human_confirmation` |
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

---

## 4. 各模块作用 / Module Responsibilities

### 4.1 Input Sources / 输入来源

输入包括：

- original paper text；
- Chen-Zimmermann metadata；
- Open Source Asset Pricing reference code；
- CRSP / Compustat / CCM data dictionaries； 
  - **CRSP**：美国股票价格、收益率、市值、退市收益等市场数据；
  - **Compustat**：公司财报和基本面数据，如 assets、sales、book equity、earnings；
  - **CCM**：CRSP/Compustat Merged link table，用于把 Compustat 的 `gvkey` 和 CRSP 的 `permno` 正确连接起来；
  - **data dictionary**：字段说明书，用于确认变量含义、单位、日期定义、缺失值和可用字段，防止 LLM 猜字段。
- researcher notes。

作用：

> 为 LLM 和后续审查提供因子定义、变量说明、组合构造规则和参考实现。

---

### 4.2 Semantic Extractor / 语义提取器

作用：

> 把论文和 reference materials 中的自然语言描述，转换成结构化的 `MethodSpec` / `FactorSpec`。

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

这一层可以使用 LLM，因为论文和参考代码通常是不结构化的。

但它的输出不是代码，而是：

> **结构化方法说明 MethodSpec。**

#### 提取策略 / Extraction Strategy

Semantic Extractor 采用 **multi-source triangulation**：不依赖单一来源，而是同时读取论文原文、C&Z metadata 和 OSAP reference code，交叉校验字段定义。

提取分三步：

1. **Structured source first.** 优先从 C&Z metadata 和 OSAP reference code 中提取，因为这些已经是半结构化的，extraction accuracy 高。
2. **Paper fill-in.** 对于 metadata 中缺失或模糊的字段（如 missing-value policy、exact lag、skip month），回到论文原文中查找。
3. **Ambiguity tagging.** 如果论文本身也没有明确说明，该字段标记为 `source: inferred` 或 `source: unspecified`，并写入 `ambiguous_fields` 列表，供 Review Gate 审查。

#### MethodSpec 输出格式 / MethodSpec Schema

```yaml
factor_id: "hml"
factor_name: "High Minus Low (Book-to-Market)"
paper_ref: "Fama and French (1993)"

# --- 信号定义 ---
signal:
  formula: "book_equity / market_equity"
  required_fields: [ceq, at, lt, txditc, pstkrv, pstkl, pstk, csho, prcc_f]
  field_sources:
    ceq: {dataset: compustat, table: funda, description: "common equity"}
    prcc_f: {dataset: compustat, table: funda, description: "fiscal year-end price"}
  timing:
    formation_month: 6          # June
    rebalance_frequency: annual
    holding_period: 12           # months
    accounting_lag: 6            # months minimum
    skip_month: null
  missing_policy:
    action: drop                 # drop | fill_zero | fill_median | winsorize
    threshold: null              # max missing ratio before dropping firm-year

# --- 组合构造 ---
portfolio:
  universe: "NYSE + AMEX + NASDAQ, common shares only"
  breakpoints: {source: NYSE, quantiles: [30, 70]}
  weighting: value_weighted
  long_leg: high
  short_leg: low

# --- 元数据 ---
extraction_sources:
  - {type: paper, ref: "Fama and French (1993)", sections: ["Section III"]}
  - {type: cz_metadata, ref: "SignalDoc.csv", row: "bm"}
  - {type: osap_code, ref: "bm.sas"}
ambiguous_fields:
  - field: missing_policy
    reason: "paper does not specify; OSAP code drops missing BE"
    source: inferred
    confidence: medium
```

#### 提取质量评估 / Extraction Validation

对 pilot factors，使用 C&Z metadata 作为 ground truth，评估 extraction accuracy：

| 评估维度 | 方法 |
|---|---|
| 字段覆盖率 | MethodSpec 中非空字段数 / 总字段数 |
| 字段准确率 | 与 C&Z metadata 一致的字段数 / 可比较字段数 |
| 歧义率 | `ambiguous_fields` 数量 / 总字段数 |
| 关键字段命中 | `formula`, `lag`, `breakpoints`, `weighting` 四个核心字段的准确率 |

Phase 1 的 acceptance criteria：核心字段准确率 ≥ 80%（pilot factors）。如果达不到，需要增加 structured prompting 或 few-shot examples。

---

### 4.3 Review Gate / 审查关卡

作用：

> 由一个默认非常严格、picky 的 **LLM Reviewer** 主导审查，防止不确定或错误的提取结果直接变成 empirical truth。

Review Gate 需要检查：

- MethodSpec 格式是否正确；
- 关键假设是否有 citation；
- 字段是否存在于数据字典；
- timing 是否符合论文；
- missing-value policy 是否明确；
- lag 和 reporting-date alignment 是否合理；
- paper、metadata 和 reference code 是否冲突。

LLM Reviewer 的默认策略是：

> 宁可 reject / ask for clarification，也不要默认通过有歧义的 empirical assumption。

重要原则：

> missing-value imputation、winsorization、sample restriction、lag choice 和 field substitution 都是 empirical choices，不是普通 bug fix。

这些内容必须写入 `MethodSpec`，并通过 picky review 后才能进入代码生成阶段。LLM Reviewer 可以批准常规一致性检查；但当证据不足或相互冲突，且假设会 materially affect empirical results 时，必须升级为 `needs_human_confirmation`。

#### Review Decision Matrix / 审查决策矩阵

每个 MethodSpec 字段按 **empirical impact** 和 **evidence quality** 两个维度分类，决定 LLM Reviewer 的处置方式：

| Evidence \ Impact | Low impact | High impact |
|---|---|---|
| **Clear evidence** (paper + code agree) | `auto_approve` | `auto_approve` |
| **Single source** (only paper or only code) | `auto_approve` with flag | `needs_llm_review` |
| **Inferred** (neither paper nor code explicit) | `approve_with_default` + flag | `needs_human_confirmation` |
| **Conflicting** (paper vs. code disagree) | `needs_llm_review` | `needs_human_confirmation` |

**High-impact fields**（改变会 materially affect empirical results）：
- `signal.formula`
- `signal.timing.accounting_lag`
- `signal.missing_policy`
- `portfolio.breakpoints`
- `portfolio.weighting`
- `portfolio.universe`（microcap treatment）
- `portfolio.long_leg` / `portfolio.short_leg`

**Low-impact fields**（通常不影响核心结论）：
- `factor_name`, `paper_ref`
- `signal.required_fields`（只要 formula 正确，字段名对错是 technical issue）
- `signal.timing.formation_month`（多数因子是 June，偏差通常可检测）

#### 处置定义 / Disposition Definitions

| 处置 | 行为 |
|---|---|
| `auto_approve` | LLM Reviewer 直接通过，无需人工介入 |
| `auto_approve` with flag | 通过，但在 MethodSpec 的 `review_notes` 中标记，供后续审计 |
| `approve_with_default` | 使用 sensible default（如 lag=6m, missing=drop），标记 `source: default`，写入 `ambiguous_fields` |
| `needs_llm_review` | LLM Reviewer 需要给出 reasoning 并做出判断，记录 rationale |
| `needs_human_confirmation` | **Hard block.** 生成 review ticket，暂停 pipeline 等待人工确认 |

#### Sensible Defaults / 合理默认值

当论文和 reference code 都没有明确说明时，使用以下 defaults（基于 HXZ / C&Z 惯例）：

| 字段 | Default | 来源 |
|---|---|---|
| `accounting_lag` | 6 months | HXZ convention |
| `missing_policy` | drop | C&Z common practice |
| `formation_month` | June (annual) | FF convention |
| `breakpoints` | NYSE | HXZ standardized |
| `weighting` | value_weighted | HXZ standardized |
| `rebalance_frequency` | annual | FF convention |

**注意：** 这些 defaults 只在 `source: unspecified` 时使用，且只应用于 `standardized_hxz` track。`original_method` track 中如果关键字段 unspecified，必须升级为 `needs_human_confirmation`。

#### Review 输出格式

```yaml
review_id: "rev-hml-001"
methodspec_version: "v1"
reviewer: llm          # llm | human
disposition: approved   # approved | revision_required | blocked
review_notes:
  - field: missing_policy
    status: approve_with_default
    reason: "paper silent on missing BE; OSAP drops; using drop as default"
  - field: breakpoints
    status: auto_approve
    reason: "paper Table III and OSAP code both use NYSE 30/70"
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
| `original_method` | 尽量忠实复现 original paper / C&Z / OSAP 的设定 |
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
| Semantic Extractor | Yes | LLM 读取论文和 reference materials，提取 MethodSpec。 |
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
