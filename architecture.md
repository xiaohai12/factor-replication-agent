---
type: architecture
status: draft
project: factor-replication-agent
created: 2026-05-12
updated: 2026-05-20
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

---

## 4. 各模块作用 / Module Responsibilities

### 4.1 Input Sources / 输入来源

输入包括：

- original paper text；
- Chen-Zimmermann metadata；
- Open Source Asset Pricing reference code；
- CRSP / Compustat / CCM data dictionaries；
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

---

### 4.3 Review Gate / 审查关卡

作用：

> 防止 LLM 把不确定或错误的提取结果直接变成 empirical truth。

Review Gate 需要检查：

- MethodSpec 格式是否正确；
- 关键假设是否有 citation；
- 字段是否存在于数据字典；
- timing 是否符合论文；
- missing-value policy 是否明确；
- lag 和 reporting-date alignment 是否合理；
- paper、metadata 和 reference code 是否冲突。

重要原则：

> missing-value imputation、winsorization、sample restriction、lag choice 和 field substitution 都是 empirical choices，不是普通 bug fix。

这些内容必须写入 `MethodSpec`，并经过 review 后才能进入代码生成阶段。

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
