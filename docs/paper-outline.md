# 毕业论文结构讨论稿 (Paper Outline, v0.1)

> 讨论用中文，论文正文用英文。本文件只做结构讨论，不是论文正文。
> 定稿后再生成 `paper/` 下的 LaTeX 骨架。

**已锁定的前提**

| 项 | 决定 |
|---|---|
| 形式 | 毕业论文，内容组织按计算金融/交叉学科期刊模式，不绑定学校排版模板 |
| 语言 | 英文正文 |
| 定位 | 系统 / 实证 / benchmark 三者兼有，**以实证发现为主线** |
| 规模 | **待最终定案，见 §5.3（2026-08-19 更新）**：xlsx 分歧证据清单 7 候选中 1 个硬否决（`Leverage`），
  剩 `GP`/`PS`/`fgr5yrLag`/`AssetGrowth`/`OScore`/`FailureProbability`；`FailureProbability` 工程投入大，
  是否也剔除待定。`AssetGrowth` 已跑通 13 个 track。**旧的 6 因子清单（`BrandInvest`/`OperProfRD`/`grcapx3y`）已被替换，不再是当前方向**。 |
| Q2 (bridge track) | 移出主线，仅作 Future Work |
| 章节数 | 8 章 + 附录 |

---

## 一、Introduction 的框架之争（这是本稿最需要先定的事）

你的直觉是对的：**不该以「复现危机」开头**。理由如下。

### 方案 A（不推荐）：复现危机 → 痛点 → 我们的方法

```
因子动物园有几百个因子 → HXZ 发现 65% 复现不了 → 复现危机很严重
→ 但人工复现很慢很贵 → 我们用 LLM agent 自动化 → 更快更便宜
```

问题：

1. **这个开头已经被 HXZ (2020) 和 C&Z (2022) 占满了。** 你无法在「谁复现得更多」
   这条赛道上超过他们——他们有更多人力、更长时间、更完整的数据。
2. **它把论文降格成一个工程贡献。** 读者的问题会变成「你的 agent 准不准」，
   而不是「你发现了什么」。而 agent 准不准恰恰是最容易被攻击的点
   （n=3–5，无 within-agent dispersion 研究）。
3. **「危机」这个词预设了有人错了。** 但你的整套设计（受控消融、
   gap 分解、identification level）恰恰在说：**没人错，是论文没说清楚**。
   开头和结论互相打架。

### 方案 B（推荐）：分歧 → 分歧是可测量的 → 分歧带决定了「可复现」是否有唯一答案

```
同一篇论文、同样诚实、同样胜任的两个实现者，会做出不同的实现 —— 而且结果不同。
→ 证据就摆在文献里：HXZ 说大部分因子复现失败，C&Z 说大部分复现成功，
   两者用的是同一批论文、同一批数据源。这个矛盾本身不是谁的错误，
   而是「论文没有唯一确定实现方法」的直接证据。
→ 那么真正的问题不是「这个因子能不能复现」，而是：
   「这个因子的复现结论，在论文所允许的实现空间里，是否唯一？」
→ 要回答它，你需要 (a) 一个能穷举实现空间的受控执行引擎，
   (b) 一个独立于人类先验的方法抽取器 —— 这就是 LLM agent 的位置。
→ 我们把 agent 与 C&Z 的分歧作为「诚实分歧的自然尺度」，
   在这个尺度上重新校准 HXZ 式标准化协议的效应。
```

优点：

1. **痛点从「复现率低」变成「复现结论不唯一」**——这个痛点没人做过量化。
2. **LLM 的角色从「省人力的工具」变成「一个可控的、独立的第二实现者」**。
   这才是 LLM 在这里不可替代的理由：人类复现者会不自觉地看别人的代码、
   用领域惯例补全论文没说的东西；受控 agent 在防泄漏边界下不会。
   这一点要在 Introduction 里就点破，它是整篇论文的方法论支点。
3. **它天然把 n=3–5 的局限性变成可接受的。** 因为你不是在做 survey，
   而是在做 identification——每个因子是一个精心构造的受控实验，不是一个样本点。
4. 结论章能干净收尾：某些因子的「可复现性」是欠定的（underdetermined），
   这对因子动物园的清点工作有直接含义。

### 0bis. 与 HXZ / C&Z / JKP 三方的定位差异（2026-08-18 核实版，取代早前未核实的转述）

本节数字全部从下载到 `docs/` 的四篇 PDF（HXZ 2017、HXZ 2020、C&Z 2021/2022、JKP 2023）
原文逐句核对，**之前草稿里出现过的「437 个变量 / 63% 失效」是编错的数字，已作废**。

| 来源 | 逐字/核实过的关键数字 | 出处 |
|---|---|---|
| HXZ (2020) 摘要 | 452 个 anomaly 中 65%（NYSE 断点+VW）在 \|t\|≥1.96 下失效；改用多重检验门槛 2.78 后升到 82% | RFS 33(5), abstract |
| HXZ (2020) 正文 | 原样本期内失效率 65.3%（NYSE+VW）；换成 equal-weighted + NYSE-Amex-NASDAQ 断点（放任 microcap）后**降到 43.1%** | §I，本文 C1 的关键外部弹药：HXZ 自己量化过 weighting 维度的影响 |
| C&Z (2021/2022) | 319 个特征里仅 3 个复现失败（近 100%）；复现 t 值对手工采集 t 值回归，slope=0.88，R²=82% | Introduction，引用 HXZ 原话「65.4% cannot clear \|t\|≥1.96...drops to 43.1% if we allow microcaps to run amok」 |
| JKP (2023) Figure 1 | 六根柱：35%（HXZ 原始）→ 55.6%（JKP 可比口径）→ 61.3%（剔除原文本不显著的 34 个）→ 82.4%（CAPM alpha 而非原始收益）→ 75.6%（Benjamini–Yekutieli 多重检验）→ 82.4%（JKP 贝叶斯框架） | §II，footnote 4 给出 JKP vs HXZ 的完整方法论差异清单（tercile/decile、断点门槛、accounting lag 月数、capped VW、holding period） |

**三方共同的局限，正是本文 C1 的切入点**：HXZ 只给一个总失败率，C&Z 是人工判断「差异是因子无效还是方法偏离」，
JKP 是换掉全部协议去「抹平」分歧。三家都没有对同一个信号，用受控反事实执行把
「信号理解差异」和「组合构造差异」分开测量——这是本文与三者的差异化定位，Ch.1/Ch.3 要点破。

### 建议的 Introduction 五段式（2026-08-19 更新：¶1 改为具体案例开头）

| 段 | 内容 | 关键句（草稿方向） |
|---|---|---|
| ¶1 | **用一个具体因子的对立判决开头**（取代总体失败率数字） | "Consider Piotroski's (2000) F-score. Hou, Xue, and Zhang (2020) report that under their standardized replication protocol, it fails [HXZ own notation: `F`]. Chen and Zimmermann (2021/2022), using the paper's own stated method, replicate it with a t-statistic of 3.29. Same factor, same underlying economic idea, opposite verdicts." |
| ¶2 | 这不是孤例；补一笔总体统计量作背景（不再是开场句，压力小很多） | 引用 HXZ 65%/C&Z 近 100% 的总体数字，同时提醒读者两者口径不同，所以更需要一个能拆解到字段级的框架，而不是停留在总体统计量层面。 |
| ¶3 | 分歧的来源不是错误，是欠定 | 论文正文平均不指定 N 个会实质影响结果的实现选择（用你的 `spec_quality`/`menu_deviations` 给出真实数字）。 |
| ¶4 | 因此真正的问题被问错了 | 应该问的不是 "does it replicate"，而是 "why do two careful teams reach opposite verdicts, and can we attribute the disagreement to specific, falsifiable causes"。 |
| ¶5 | 要回答它需要什么 + 我们发现了什么 + 贡献列表 | 需要一个可穷举、可审计、且抽取过程不受既有实现污染的执行框架；LLM 只出现在两处；给出 §5.3 因子清单的核心数字。 |

**已确认（2026-08-19）**：采用方案 B。¶1 用 `PS`（Piotroski F-score）这个具体案例开头——
好处是不需要处理"总体失败率口径不同"这个麻烦（HXZ 是统一协议失败率，C&Z 是原始方法能否显著，
两者不可直接相减），一个具体因子的对立判决足够尖锐，且已核实：
- HXZ (2020) 判定失败（论文自己的记号 `F`，见附录 A.4.21，本文 §5.3 已核实）
- C&Z 用论文原始方法复现出 t=3.29（原文 t=5.59），归为 Clear Predictor

**风险与应对**：¶1→¶2 需要处理"一个案例 → 一般化"的跳跃，不能显得以偏概全——
¶2 明确写"这不是孤例"，再补总体统计量作背景，且借机说明"总体统计量口径不可比"
这件事本身就是本文要解决的问题之一（需要拆到字段级才能真正比较）。

**待你确认**：¶1 我打算直接引用 HXZ vs C&Z 的结论差异作为开场事实。
这需要核对两篇论文的原话和口径（HXZ 的 65% 是 microcap-adjusted 后的口径，
C&Z 的「大部分可复现」是另一个口径），**不能把口径差异说成矛盾**，
否则会被审稿人一击致命。是否要我去核实两篇论文的准确口径？

---

## 二、章节结构（8 章）

### Ch.1 Introduction
按上面的五段式。**2026-08-18 三次修订：项目原本就有两个并行动机——C&Z/HXZ 复现分歧的金融讨论（RQ1），
和 agent 完成复现任务这一能力本身的探索（RQ2）。RQ2 不是 RQ1 的陪衬工具，是一个独立问题；两者互相提供
可信度背书，关系需诚实写清楚（见 C1/C2 之间的说明），不装扮成单一主线。**

**评价单位的界定（贯穿全文的措辞纪律）**：本文评价的对象是 **agent 这个系统**——LLM + 工具接口 +
review gate + validator + 沙箱 + 人工确认环节，**人工确认是 agent 的设计组件，不是外部干预**。
因此全文不写「LLM 读论文准不准」这类把系统降格为单个模型的表述；人工介入发生在哪里，衡量的是
**agent 自主性的边界**，而不是某个模型的阅读错误。

结尾给 contributions 三条：

- **C1（RQ1 的答案，实证，主线）**：对每个因子，把 C&Z 实测与论文自己报告值 `P` 的总差距 `CZ − P`，
  用三个受控反事 track——`A`（agent 信号+agent 读到的论文配置，作为「论文忠实基准」）、
  `A@cz`（agent 信号+C&Z 配置）——干净地拆成三项恒等式（外加窗口/口径失配残差项，见下）：

  $$\underbrace{CZ - P}_{\text{总差距}} = \underbrace{(CZ - A_{cz})}_{\text{纯信号+环境差异}} + \underbrace{(A_{cz} - A)}_{\text{纯配置差异}} + \underbrace{(A - P)}_{\text{agent 复现残差}}$$

  HXZ 侧把 `A_{cz}` 换成 `A_{hxz}` 同理。这三项的“纯度”不等：第一项除了信号差异还混了数据
  vintage/引擎差异（environment residual），第三项是 agent 对论文的复现偏差，不是论文歧义——
  必须分开说明，不能笼统统当同一种误差处理。这是 HXZ（只给总失败率，且不跟论文自己的报告值比）、
  C&Z（人工判断因子无效 vs 方法偏离，也不拆到字段级）、JKP（换协议「抹平」分歧而非「分解」分歧）
  三者都没做过的度量。
- **C2（RQ2 的答案，agent 能力发现，独立成立，不是陪衬）**：报告 agent 在「从论文产出可执行复现」
  这个任务上的**自主性与能力边界**，即使去掉 RQ1 也能单独站住。人工确认既然是 agent 的一环，
  介入足迹本身就是自主性的度量：
  - **自主性足迹**：每个因子有多少高影响字段是 agent 自主完成、多少触发人工确认（占比）；
  - **端到端完成度**：5 个因子里，几个从 PDF 一路到可执行 t 值中间零人工改代码；
  - **能力边界定位**：人工介入系统性集中在哪类字段（信号定义 / 加权 / 断点 / 样本期），
    以及其中多少属于纯技术性介入（类型不符、菜单外取值）vs 涉及经验取值的介入
    ——后者才是自主性的真实边界，也是 §C1 防泄漏论证的风险点（见下）。

  数据来源：这三个数是跑完 5 个因子的**免费副产品**，不需要单独建人工标注语料库——
  `apply_value_patches` 已把每次人工确认写进 `SourcedValue.evidence`（`"human correction: {reason}"`）
  并将 `status` 置为 `CLEAR`，只看最终 spec 即可统计。
- **C3（方法，两条 RQ 共同的可信度前提）**：一套受控、防泄漏、LLM-assisted 但非 LLM-controlled 的
  复现流水线；所有经验数字在 LLM 关闭时确定性可复现。它不是独立发现，而是让 C1 和 C2 的数字都能被
  信任的共同基础设施——没有这套约束，C2 的自主性数字没人信是「客观测量」而非「自我报告」，
  C1 里 `A`/`A@cz` 这些反事实 track 也没人信是「受控执行」而非「拼凑」。

**⚠️ 防泄漏边界的收紧（必须主动写，不能等审稿人发现）**：C1 的方法论支点是「agent 是未被已有实现
污染的独立第二实现者」。但既然人工确认是 agent 的一环，而做确认的人是看过 C&Z 的，防泄漏就从
**系统层面的硬隔离**降级为**系统硬隔离 + 人工环节的操作自律**。诚实的处理是：
(1) 把人工介入分成纯技术性与涉及经验取值两类，分开统计，并报告后者占比；
(2) 对涉及经验取值的介入，在 `reason` 里明确记录依据来源是「论文原文某句」还是「领域惯例」；
(3) Ch.8 明确写出：SignalDoc.csv 在系统层面从不进入 pipeline（这是硬的），
但人工审核环节的独立性依赖操作者自律（这是软的），这是本文一个已知边界。

**C1 与 C2 之间的诚实关系（写进 Ch.1 收尾一段，不要包装成互相印证）**：C2 的结果（自主性足迹、能力边界）
决定了 C1 的可信度上限——若 agent 在高影响字段上频繁需要人工介入，C1 三项恒等式里 `(A − P)` 这一项就会偏大，
`(CZ − A_{cz})` 那一项的「纯净度」也随之打折扣，必须在 C1 里坦白这一点，不能反过来拿 C1 的数字
去美化 C2。

### Ch.2 Related Literature
三条线，各 1–1.5 页：

1. **因子复现文献** — 核心是 HXZ (2020) / C&Z (2021–2022) / JKP (2023) 这场跨越多年的
   方法论辩论，而非平行罗列。用一张定位表说清楚本文和三者的关系（数字均已逐句核对原文，
   见 §0bis）：

   | | 做了什么 | 缺什么，本文补上什么 |
   |---|---|---|
   | HXZ (2020) | 452 个 anomaly 用统一协议（NYSE 断点+VW）重跑，65% 失败；换成 EW+NYSE-Amex-NASDAQ 断点后降到 43.1% | 只给总失败率，没有把单个因子的差距拆到字段级 |
   | C&Z (2021/2022) | 逐条**人工**判定 HXZ 的失败案例是「因子无效」还是「方法偏离原文」，319 个特征里近 100% 复现成功 | 人工分类，没有真的把 C&Z 的信号放进 HXZ 的配置里反事实执行一遍 |
   | JKP (2023) | 用统一贝叶斯协议重跑全部样本，Figure 1 六根柱子（35%→55.6%→61.3%→82.4%→75.6%→82.4%）逐条归因协议差异 | 是在**抹平**分歧（换成我的协议），不是在**分解**分歧（多少归信号、多少归配置） |
   | **本文** | 用 `A@cz`/`A@hxz` 混血 track 做真实反事实执行，把每个因子的总差距干净劈成信号差异和配置差异两块 | — |

   Harvey–Liu–Zhu (2016)、McLean–Pontiff (2016) 作为背景一段带过：这些工作把「实现选择」
   当作需要被标准化掉的噪声，而本文把它当作研究对象本身。
2. **研究者自由度 / multiverse** — specification curve (Simonsohn et al.)、
   multiverse analysis (Steegen et al.)、金融领域的 p-hacking 文献。
   本文与之的区别：multiverse 通常穷举「研究者可能做的所有选择」，
   本文只穷举「两个真实实现者实际分歧的那些选择」，所以分歧带是经验校准的，不是想象的。
3. **LLM agent 做科研自动化** — 强调效度风险，并说明本文的应对：
   LLM 只写 `compute_signal`，不碰任何经验参数。

**待你核实一遍再定稿**：上表数字已逐句核对四篇 PDF 原文（2026-08-18），
但引用页码/图号/脚注编号请在正式引用前再对一遍原文，避免转述漂移。

### Ch.3 Conceptual Framework
形式化，不含实现细节。

- 记号（2026-08-18 扩充，纳入论文锚点）：$P$（论文自己报告的数）、$A$（agent 信号 + agent
  读到的论文配置，作为论文忠实基准）、$A_{cz}$/$A_{hxz}$（agent 信号 + C&Z/HXZ 配置的混血 track）、
  $CZ$/$HXZ$（各自的实测结果）、track、freeze。
- **欠定性的定义**：给定论文 $P$，其允许的实现集合 $\mathcal{I}(P)$；
  若 $\{ \text{verdict}(i) : i \in \mathcal{I}(P) \}$ 不是单点集，则该因子的复现结论欠定。
- **分歧带的定义**：用 $A$ 与 $CZ$ 的差异集张成的子空间作为
  $\mathcal{I}(P)$ 的经验下界估计（强调是**下界**：真实分歧只会更宽）。
- **论文锚点三项分解恒等式**（取代旧版仅比较 $CZ$ vs $HXZ$ 的无锚点写法）：
  $CZ - P = (CZ - A_{cz}) + (A_{cz} - A) + (A - P)$，分别对应信号/环境差异、
  配置差异、agent 复现残差；HXZ 侧换 $A_{hxz}$ 同理。
  只在论文对该字段**明确表态**时才成立（$A - P$ 才有锚点意义）；论文沉默字段仍退回上面的
  分歧带逻辑，两套分工不变。
- **窗口/口径失配残差项（已定：取方案 a，2026-08-18）**：上式四个端点并不在同一口径上——
  $P$ 是论文自己的样本期与当年算法；$A$/$A_{cz}$ 是本引擎的覆盖期 + Newey-West；
  $CZ$ 取自 `CZReferenceProfile`（SignalDoc.csv 的静态 `mean_return`/`t_stat`，**窗口不可调**）；
  $HXZ$ 取自 `hxz_bridge.compute_hxz_reported()`（窗口可指定、且已刻意对齐引擎的 NW 口径）。
  因此恒等式实际写成四项，多出的一项单列为窗口/口径失配残差。这不是妥协：
  恒等式依旧精确成立，而该项本身就回答了「光是样本期不同造成多大差异」这个有信息量的问题。
- **LLM-assisted vs LLM-controlled 原则** + 防泄漏边界（SignalDoc.csv 只用于事后评估）。

### Ch.4 The Controlled Replication Pipeline
Step 1–8 走一遍。图 F1 架构图。重点讲**为什么这样设计能保证可审计**：

- MethodSpec 作为唯一的方法载体 + review gate（`codegen_ready`）
- 固定配置菜单 + `registry.build_config` 的 clamping（越界值一律回落菜单默认）
- sandbox 验证 / repair-then-refreeze（技术性修复会重跑整批，保证 code hash 一致）
- evidence store 与哈希（artifact hash vs semantic hash）
- step7 evidence bundle → step8 validator 约束下的解释层

### Ch.5 Data and Factor Sample
- CRSP 月度、Compustat（CCM 链接）、point-in-time 时序处理、snapshot 哈希
- FF 因子、HXZ 标准配置 (`data/hxz/hxz_standard_config.yaml`)
- C&Z SignalDoc.csv 的**仅评估用**地位（这是防泄漏设计的核心，必须单独一小节）
- **Scope and Assumptions 小节**（详见第四节）——数据源、频率、组合构造、配置菜单的实现边界
- **因子筛选标准**（见第五节）+ 最终选定的 3–5 个因子及其画像

### Ch.6 Experimental Design
- track grid（signal × config）+ 图 F2，含 $A$/$A_{cz}$/$A_{hxz}$/$CZ$/$HXZ$/$P$ 六个参照点
- Q1 设计：$A$ vs $CZ$
- Q3 设计：$A$ vs $HXZ$-style 标准协议
- OAT vs 全因子；何时用哪个
- **论文锚点三项分解恒等式**：$CZ - P = (CZ - A_{cz}) + (A_{cz} - A) + (A - P)$，
  HXZ 侧换 $A_{hxz}$ 同理；实现上再加一项**窗口/口径失配残差**（方案 a，见 Ch.3），
  因为 $CZ$ 的 SignalDoc 数字窗口不可调，而 $P$/$A$ 的窗口又各自不同
- **字段级 gap 分解恒等式**：把上式中的配置差异项 $(A_{cz} - A)$ 再拆到具体配置字段，
  $\sum \text{main} + \sum \text{interaction} = (A_{cz} - A)$，残差恒为 0
- **t 通道分解**：$\log t = \log \mu - \log \sigma + \tfrac{1}{2}\log n$（恒等式，非假设），
  并说明为什么 t 值不能像均值那样做可加分解
- identification level 分级（controlled / harmonized / observational / unidentified）
- 显著性分层（1.96 / 2.78 / 3.39）与结果分类标签

### Ch.7 Results

**2026-08-18 重新组织（n=6 定案后）**：不要把 6 个因子当 6 个对称的案例平铺——
每个因子在 §5.3 里被选中都是因为它演示了一个**特定的分歧轴**，Ch.7 的叙事顺序
应该沿着这些轴推进，而不是按字母/发表年份排列。跨因子的部分（RQ2、t 通道、
敏感性带、结果分类）合并成单张表/图，不要每个因子重复一遍相同结构的小节。

0. **RQ2 结果（C2，独立成立，跨全部 6 个因子一次性汇报）**：agent 自主性足迹
   （高影响字段中自主完成 vs 触发人工确认的占比）、端到端零改代码完成度、
   能力边界定位（人工介入集中在哪类字段，纯技术性介入 vs 涉及经验取值的介入
   各占多少）（T1，6 行，一张表）
1. **单因子深挖，按分歧轴顺序排列**（不是字母序）：
   1. `AssetGrowth` —— 已验证的锚点案例，先讲清楚三项分解恒等式怎么读（教学作用）
   2. `GP` —— 断点轴：论文陈述 NYSE 断点，但最优实现是全样本断点（矛盾，非欠定）
   3. `BrandInvest` —— 加权轴：论文明确说 VW+10%上限，C&Z 直接改 EW（矛盾最直接）
   4. `OperProfRD` —— 反例/对照锚点：C&Z 已是 VW+NYSE，标准化预期几乎不变，
      同时演示一个独立的 lag 矛盾（与断点/加权正交的第三个分歧维度）
   5. `PS` —— 全书信息量最大的案例：三重独立歧义（加权+rebalance 近似+BM 筛选），
      同时是唯一需要声明 `accepted_unapplied` 偏离的因子，适合放在深挖部分收尾，
      借机讨论"声明式偏离"这个方法论装置本身
   6. `grcapx3y` —— 收尾的特殊案例：唯一显式点名"HXZ"三个字母的因子，
      但样本区间短（1976–1999），只作定性佐证，不参与需要长样本的检验（见第 6 点）

   每个因子的深挖用同一套模板：$A$ vs $CZ$ 字段级分歧（T2）→ baseline vs 论文报告值（T3）
   → 论文锚点三项分解 + 配置字段级分解（T4a/T4b）——但**只对该因子演示的那个轴展开叙述**，
   其余字段一笔带过，避免 6 次重复相同的解说词。
2. **跨因子 gap 分解汇总**（新增，直接回答"为什么会分歧"这个核心问题）：
   一张表把 6 个因子的 $(A_{cz}-A)$/$(A_{hxz}-A)$ 分解结果并排放，看主导字段是否
   因子而异（比如 GP 主导项是断点、BrandInvest 主导项是加权）——这张表本身就是
   "C&Z/HXZ 分歧的机制"这一核心论证的直接证据，配 tornado 图（F3）
3. **t 通道分解**（T5，跨因子一张表）
4. **核心结果**：敏感性带 vs HXZ 点估计 vs 论文点估计（T6 + **F4 招牌图**，6 个因子一图打尽）
5. **发表后衰减**（insamp/between/postpub）：**`grcapx3y` 样本区间短（1976–1999），
   `between`/`postpub` 窗口可能月数不足，需先核实再决定是否放进这项检验**——
   若数据不支持，明确写"n=5"并说明原因，不要静默跳过。
   **2026-08-18：本地暂无数据可跑（`data/local/` 只有未解压的 `.zip`），用户确认
   延后到实际跑 pipeline 时再核实，此处先按"待核实"占位，不阻塞大纲/写法讨论。**
6. **跨因子结果分类**（T7）：6 个因子按 replication outcome label 分类收尾，
   呼应 Ch.1 的贡献列表

### Ch.8 Discussion, Limitations and Conclusion

**2026-08-18 展开（原来只有 4 条 bullet，现在把全文散落的诚实性承诺收拢到一处，
按"方法论局限 / 数据局限 / 因子特定局限"分组，避免审稿人发现某条没写而质疑是回避）**

**8.1 结果的含义**：对因子动物园清点工作的含义——如果 C&Z/HXZ 的分歧在多个因子上
系统性地能被 $A$（论文忠实基准）解释为"谁偏离了论文"而非"论文本身欠定"，
说明很多所谓的"复现失败"其实是**实现选择的分歧被误记成了因子失效**；
反过来，凡是论文对该字段沉默、三方选择各不相同却又不影响结论的因子，
才是真正稳健的因子。用 6 个因子的结果分类（T7）具体印证。

**8.2 局限（按类型分组，逐条注明"威胁的是哪个结论"）**

*方法论局限*：
- **无 within-agent 分散度研究**（同一 agent 对同一论文重复抽取 K≥5 次的方差未测）
  —— 威胁 C1：$A_{cz}-A$ 里混了 LLM 采样噪声，不全是论文歧义（两侧偏误的"高估"一侧，见 §4.2）
- **无 Q2 bridge track**（C&Z 参考信号未跑过我们自己的引擎）—— 威胁两件事：
  (a) 无法用 C&Z 自己发布的 AltPorts 数字交叉校验引擎的绝对输出是否正确；
  (b) $(CZ-A_{cz})$ 这一项里"信号差异"和"环境/vintage 差异"目前无法进一步拆开，
  只能作为一个合并残差报告
- **人工确认环节的独立性依赖操作者自律**（见 Ch.1 防泄漏边界收紧一节）——
  系统层面的硬隔离（SignalDoc.csv 从不进 pipeline）不等于人工审核环节的认知独立，
  这是已知的、无法完全消除的软边界
- **固定配置菜单低估欠定性**（§4.2 双向偏误的另一侧）——分歧带只是下界

*数据局限*：
- 单一 WRDS 数据 vintage，样本期未在代码里硬编码，需人工核实写入附录 F
- 仅美国普通股、仅月频组合收益、仅 CRSP–Compustat 年度（§4.3–4.5 的实现边界）

*因子特定局限*（逐条对应 §5.3 表格里的已知取舍，不要笼统带过）：
- **`PS`**：BM 最高五分位筛选未实现，声明为 `accepted_unapplied`——本文报告的 F-score
  结果是"全样本排序"，不是论文原文的"高 BM 子集内排序"，两者不能直接比较数值
- **`grcapx3y`**：样本区间仅 1976–1999（24 年），发表后衰减检验（§Ch.7 第 5 点）
  可能因窗口月数不足而无法覆盖此因子，需在结果呈现时明确注明 n=5 或 n=6 的差异
- **估计量限制**：仅支持 `portfolio_sort`，不支持 Fama–MacBeth——本文的因子筛选
  本身就排除了主结果为回归系数的论文（如 Richardson et al. 2005、FF OperProf），
  这是选择偏误的一种，需要承认"能被本框架研究的因子"本身是一个子集

**8.3 Future Work**（按价值排序）：
1. **within-agent 分散度研究**（K≥5 次重复抽取）——直接解决 8.2 里最大的高估偏误风险，
   优先级最高
2. **Q2 bridge track**（C&Z 信号 × 我们的引擎）——解锁信号/配置分离，并校准引擎绝对输出
3. **扩到 HXZ∩C&Z 交集全体**（n=141，`docs/step6.md` §11 已有系统性数字）或
   SignalDoc 全体（n=331）——把 6 个深挖案例的机制假设做大样本检验
4. **Shapley 归因**——现有 gap 分解在字段数 >5 时全因子组合数爆炸，
   Shapley 值是更通用的归因方式
5. **扩展引擎能力**——Fama–MacBeth 估计量、派生列筛选、非对称切分——
   每多支持一种能力，因子筛选的选择偏误就少一分

### 附录
A MethodSpec schema 与示例 · B 配置菜单与 clamping 规则 · C prompt 模板 ·
D validator 与防泄漏规则 · E 逐因子明细表（含 §5.3 的 6 个因子 + 已知取舍） ·
F 可复现性（哈希、snapshot id、版本、WRDS vintage 人工记录）

---


## 三、表格与图（占位列名对齐真实产物字段）

| 编号 | 内容 | 数据来源 |
|---|---|---|
| T1 | 逐因子 agent 自主性足迹 / 能力边界（人工确认字段占比、技术性 vs 经验取值介入分类）+ spec 欠定程度 | `SourcedValue.evidence` 里的 `human correction` 记录 + `comparison.json: spec_quality` |
| T2 | $A$ vs $CZ$ 字段级差异 | `comparison.json: config_diff` |
| T3 | baseline vs 论文报告（spread, t, 符号一致, 显著性层, n_months, coverage, microcap_share） | `.metrics.json` + `paper_reported` |
| T4a | 论文锚点三项分解（$CZ-P$ / $HXZ-P$ 各拆信号+环境、配置、agent 残差三项） | 新增，需 `A_cz`/`A_hxz` track + `paper_reported` |
| T4b | 配置差异项字段级分解（主效应 + 交互 + explained_fraction + residual） | `comparison.json: gap_decomposition` |
| T5 | log-t 三通道分解 | `t_channel_decomposition` |
| T6 | 敏感性带（菜单内 t 的 min/max）vs HXZ 点 vs 论文点 | `robustness_summary` + 各 track |
| T7 | 复现结果分类 | step7/step8 分类标签 |
| F1 | 流水线架构图 | 手绘 / TikZ |
| F2 | track 网格（signal × config） | 手绘 / TikZ |
| F3 | 配置字段贡献 tornado 图 | `gap_decomposition` |
| F4 | 逐因子 t 值分歧带 vs 论文/HXZ 点 | 各 track `t_stat` |

**F4 是本文的招牌图**：横轴因子，每个因子画一条区间（菜单内 t 的取值范围），
区间上标出论文报告的 t、HXZ 标准化下的 t。如果论文的 t 落在区间外、
或 HXZ 的 t 落在区间内，一图说完全部结论。建议优先把这张图做出来。

---

## 四、Scope and Assumptions（实现边界，必须写进论文）

以下全部核实自代码，不是设想。写作位置：**Ch.5 单列一小节**（正面陈述「本文研究的是什么」），
**Ch.8 引用**（反面陈述「因此结论不能外推到什么」），**附录 B** 放完整的配置菜单表。

### 4.1 一个关键的框架点：菜单不只是局限，它是本文成立的前提

不要把「只支持固定配置菜单」写成道歉。要正面写：

> 本文之所以能定义「实现空间」$\mathcal{I}(P)$ 并在其上做穷举，**恰恰是因为实现空间被显式枚举了**。
> 传统复现研究的实现选择散落在几万行代码里，无法穷举、无法归因；
> 本文把它压缩成一个有限的、带默认值的菜单，代价是覆盖面变窄，收益是**可识别性**。

菜单外的取值会被 `registry.build_config` 的 `_clamp()` 确定性地回落到默认值，
并记录在 `config["defaults_applied"]` 里 —— 这个记录本身就是论文的一个数据产物
（可以报告「平均每个因子有 N 个字段被 clamp」，直接量化论文与引擎的表达力差距）。

### 4.2 双向偏误（⚠️ 这是审稿人一定会问的，必须主动写在 Ch.8）

本文测得的「分歧带」同时受两个方向相反的偏误影响，**必须同时承认**：

| 偏误 | 方向 | 原因 |
|---|---|---|
| 配置菜单有限 | **低估**欠定性（分歧带是下界） | 菜单外的合理实现选择被 clamp 掉，永远进不了分歧带 |
| LLM 单次抽取 | **高估**欠定性（分歧带是上界） | agent 与 C&Z 的差异里混入了 LLM 采样噪声，不全是论文歧义 |

诚实的表述是：**分歧带的宽度不是欠定性的无偏估计**。
但核心结论（HXZ 效应是否落在带内）在两个方向上的稳健性可以分别讨论：
若 HXZ 效应落在带内，低估偏误只会让这个结论更强（真实的带更宽）；
高估偏误则是真正的威胁 —— 唯一的解法是做 within-agent 分散度研究（K≥5 次重复抽取），
目前**未做**，必须列为首要 future work（`docs/known-gaps-paper-first-v2.md` Gap #4）。

### 4.3 数据边界

| 维度 | 支持 | 不支持 |
|---|---|---|
| 市场 | **仅美国股票** | 国际股票、债券、期货、加密资产 |
| 收益面板 | CRSP 月度股票文件（CIZ 格式）+ 退市收益 | 日频组合收益、盘中数据 |
| 样本筛选 | `shrcd ∈ {10,11,12}`（普通股，CIZ 近似映射）、`exchcd ∈ {1=NYSE, 2=AMEX, 3=Nasdaq}` | 其他交易所、OTC |
| 会计数据 | Compustat 年度（`compustat_fundamental_annual`，全量字段已注册） | 年度表未注册的字段需先在 `sources.py` 注册 |
| 链接表 | CCM（`linktype ∈ {LC,LU}`, `linkprim ∈ {P,C}`）、IBES–CRSP | — |
| 分析师数据 | IBES **仅年度 EPS 一致预期汇总**（meanest/medest/numest/stdev） | IBES 实际值、季度预期、评级明细（数据文件在，但未注册为 signal source） |
| 机构持股 | 13F（instown_perc，硬编码 2 个月申报滞后） | ⚠️ CUSIP→permno **非 point-in-time**，被重新分配的 CUSIP 可能链错 |
| 期权 | — | OptionMetrics 已于 2026-07-31 移除，完全不可用 |
| 文本 / 宏观 | — | 无 10-K/新闻/情绪数据源；FF 因子仅作超额收益扣减，未注册为 signal source |

**⚠️ 必须手工补的一项**：`data/snapshots/` 目前是空的，代码里也没有硬编码起止日期，
实际覆盖区间完全取决于 `data/local/` 下的 CSV 文件。
**论文里的样本期与 WRDS vintage 必须人工核实后写死**，不能靠自动记录。
建议在附录 F 明确写出：CRSP/Compustat/IBES 各自的下载日期、覆盖区间、行数。

### 4.4 频率边界

- **组合收益只支持月频。** `BacktestExecutor` 全程以 `yyyymm`（int）为键，日频组合无法通过引擎。
- 日频 CRSP 数据**可以加载**（`load_daily_msf_ciz()`）用于计算日频输入的信号
  （如短期反转、已实现波动），但信号必须先聚合到月频（`asof_align_to_monthly()`）才能进组合。
- 调仓频率仅三档：`{"annual"(12月), "quarterly"(3月), "monthly"(1月)}`；
  实际持有期 `= min(holding_period_months, rebalance_step)`。
- 季度会计数据只能前向填充到月频（受 `signal_max_staleness_months` 约束），
  引擎内没有真正的季度调仓逻辑。

### 4.5 组合构造边界

| 项 | 状态 |
|---|---|
| 单变量排序 | ✓ 完整支持，分位数 N 任意 |
| 双变量独立排序 | ✓ 支持（2026-07-24 重新加入） |
| 双变量序贯排序 | ✗ 未重新实现 |
| within-group 排序 | ✗ 未实现，**显式报错**（不静默降级） |
| 排序维度上限 | 2（`MAX_SUPPORTED_SORT_DIMENSIONS`），3+ 维自动裁剪到 2 |
| 重叠持有期（sticky cohort） | ✗ 2026-07-24 移除，未重新实现；只支持非重叠 |
| 估计量 | **仅 `portfolio_sort`** —— ⚠️ **不支持 Fama–MacBeth 回归**。很多因子论文的主结果是 FM 回归系数与 t 值，这类论文要么不能选，要么只能与其组合排序表对比 |
| 加权 | vw / ew |
| 断点 | nyse / full_sample |
| 退市收益 | ✓ 默认并入最后一个月 |

### 4.6 Universe filter 边界

- ✓ 静态列筛选（`shrcd`、`exchcd` 等），支持人类可读标签→物理编码翻译（`FILTER_VALUE_ENCODINGS`）
- ✓ **SIC 区间筛选（`op="between"`/`"not_between"`）已支持**（`_apply_filter_op`，
  `src/infra/backtest_engine/__init__.py`）——排除金融业（SIC 6000–6999）等区间条件
  零引擎改动即可实现；**之前这里写的"未支持"是错的，已于 §5.1 纠正，此处同步更正**
- ✗ **派生列筛选不支持**（如「Compustat 上市满 2 年」需要 groupby-min），
  只能在 MethodSpec 里标 `accepted_unapplied=True` 并写明理由
  —— 这类 backfill-bias 筛选的缺失会系统性影响小盘股占比，Ch.8 要提

### 4.7 信号函数边界

- 只支持**确定性的、纯逐行/回看窗口的公式**；
  自适应信号（如滚动窗口训练的 ML 模型）不可行
- 滞后单位只支持**月**（`accounting_lag_months`）；论文若指定日/季度滞后会被报为不支持
- **信号插件内绝不允许写滞后逻辑**（硬约束），滞后属于 DataLayer 的加载层

### 4.8 建议的 Ch.5 写法（一段话版本）

> We restrict attention to US common equity (CRSP share codes 10–12, exchange codes 1–3) at
> monthly frequency, with accounting inputs from the CRSP–Compustat merged annual file.
> Portfolio construction is restricted to univariate and independent bivariate sorts with
> non-overlapping holding periods, estimated by portfolio sorts rather than cross-sectional
> regressions. These restrictions are not incidental: they define the implementation space
> $\mathcal{I}(P)$ over which our disagreement band is enumerated, and they are enforced
> mechanically — any choice outside the menu is deterministically clamped to a default and
> logged, so the restriction is observable rather than silent.

---

## 五、待定：选哪 3–5 个因子

建议的筛选标准（按重要性排序）。**前三条是硬约束，由第四节的实现边界直接导出**：

1. **论文的主结果必须是组合排序的 long-short spread + t 值**
   —— 不能是 Fama–MacBeth 回归系数（引擎只有 `portfolio_sort` 一个估计量）
2. **信号可由 CRSP 月度 + Compustat 年度算出**
   —— 不依赖日频组合、期权、文本、IBES 明细、国际数据
3. ~~universe 筛选不依赖 SIC 区间排除~~ —— **已纠正，SIC 区间筛选已支持
   （`op="between"`/`"not_between"`），不再是硬约束，见 §5.1**。
   **仍然真实的约束**：universe 筛选不能依赖派生列（如"上市满 2 年""BM 最高五分位"）
   或非等分位/非对称切分——这两项确实未实现
4. **歧义程度有梯度**：至少 1 个论文写得很清楚的（对照组）、
   1 个明显欠定的（主打案例）、其余居中
5. **C&Z rep-quality 分层有差异**（他们标注的复现质量不全相同）
6. **文献知名度**：至少 2 个是教科书级因子，读者有先验，结论才有冲击力

候选池方向（**2026-08-18 更新**：Accruals/Momentum/Gross Profitability 这版候选池已被
§5.1/§5.2 的逐条核实取代——GP 已解除阻塞、Momentum 的重叠持有期问题仍未解决。
下表保留作历史记录，**选因子请以 §5.1「单因子论文的最终建议」（首选 `GP`，次选
`OPLeverage`，备选 `OScore`）或 §5.2 的 6 候选核实表为准**）：

| 因子 | 优势 | 需核实的风险 |
|---|---|---|
| Asset Growth (Cooper–Gulen–Schill 2008) | **已跑通 13 个 track**，作深挖案例 | — |
| Accruals (Sloan 1996) | 教科书级，`tests/test_accruals_e2e.py` 已有 fixture | 应计费用口径多，部分需 Compustat 未注册字段 |
| Momentum (Jegadeesh–Titman 1993) | 形成期/跳月/持有期是经典欠定点，最适合做主打案例 | 原文用**重叠持有期**，而引擎只支持非重叠 ⚠️ **仍未解决** |
| ~~Gross Profitability (Novy-Marx 2013)~~ | 分母口径歧义大 | ~~排除金融业的 SIC 区间筛选~~ **已解除阻塞，现为 §5.1/§5.2 首选候选** |
| Net Stock Issues / Investment 类 | 与 Asset Growth 形成对照，数据需求相似 | 与 Asset Growth 相关性过高，可能信息量不足 |

**两个已识别的冲突（需你定夺）**：

1. **Momentum 的重叠持有期**。JT1993 的标准做法是每月形成、持有 6 个月、
   同时持有 6 个 cohort（重叠）。引擎已于 2026-07-24 移除 sticky-cohort 支持。
   选项：(a) 不选 momentum；(b) 重新实现重叠持有（工作量中等）；
   (c) 只做非重叠版本并在论文里明确声明这是一个偏离。
   **建议 (b)** —— momentum 是最好的欠定性案例，值得为它补这个能力。
2. ~~Gross Profitability 的 SIC 排除~~ —— **已纠正，不是问题，详见 §5.1 中的纠错说明**。

---

## 5.1 对已提议的 5 个因子的核对结论（2026-08-18）

核对方法：以 `data/CZ code/SignalDoc.csv` 的 `Test in OP` 字段判定
「论文主结果是不是组合排序」，以 `Detailed Definition` / `Filter` 判定实现可行性。

| # | 因子 | C&Z Acronym | `Test in OP` | 结论 |
|---|---|---|---|---|
| 1 | Richardson et al. (2005) Total Accruals | `TotalAccruals` | **mv reg** | ❌ **否决** |
| 2 | Campbell–Hilscher–Szilagyi (2008) Failure Prob. | `FailureProbability` | port sort | ⚠️ 可行但代价大 |
| 3 | Fama–French Operating Profitability | `OperProf` | **mv reg** | ❌ **否决** |
| 4 | Piotroski (2000) F-score | `PS` | port sort | ⚠️ 当前被阻塞（BM 分位条件，与 SIC 无关） |
| 5 | Ohlson (1980) / Dichev (1998) O-score | `OScore` | LS port | ✅ **已纠正为可行，见下方纠错说明** |

**❗ 重要纠错（2026-08-18 补补）：之前写的“SIC 区间筛选未实现”是错的**

代码实际已支持。`src/infra/backtest_engine/__init__.py` 的 `_apply_filter_op` 里
`FilterOp` 早已有 `between` / `not_between` 两个操作符（`series.between(lo, hi)` /
取反），而且 CRSP 的 `siccd` 字段已注册、实测就是干净的 `int64`（无字符串混入）。
排除金融业（SIC 6000–6999）只需在 MethodSpec 里写一条
`{"concept_id": "sic", "op": "not_between", "value": [6000, 6999]}`，**零引擎改动**。
之前两轮对话里关于“SIC 区间需要工程投入”的判断均不成立，以本节为准。

这个纠正直接改变了两个结论：

- **GP 的 “Drop if financial” 现在可以完整实现**，不需要接受声明式偏离（上一轮说错了）。
- **OScore 的 “Exclude if SIC between 3999–4999 or >5999” 同样可实现**，
  它真正剩下的唇点只有非对称切分（long 低 70% / short 高 10%）——
  这需要在 `breakpoint_quantiles` 之外新增一个自定义切点参数（中等工作量，仍需引擎改动）。
- **OperProfRD 同理也可实现**，不再是阻塞项。

**仍然真正卡死的只有两个**：

1. **TotalAccruals ❌** —— `Test in OP = mv reg`，Key Table 8A 是**多元回归**，
   `Return` 字段为空、只有 `T-Stat = 6.38`。引擎只有 `portfolio_sort` 估计量，
   且 T3 表没有可比的 spread 目标。直接违反筛选标准 #1。
2. **OperProf ❌** —— 两个问题：(a) `Test in OP = mv reg`，同 #1；
   (b) **论文归属错了**：C&Z 的 `OperProf` 挂在 **Fama–French (2006)**，不是 FF(2015)。
   FF2015 的主结果是五因子模型，其 RMW 来自 size×OP 的 2×3 独立排序（引擎支持），
   但那不是一个「论文报告的异象 spread」，与 T3 的比较口径对不上。

**两个需要接受声明式偏离（但已能跑）**：

3. **FailureProbability ⚠️** —— `port sort` ✓、`Return=0.525` / `T=1.41` ✓、
   `Filter = abs(prc)>1`（简单静态筛选，支持）✓。但信号定义需要四样目前没有的东西：
   (a) `ltq`、`cheq` 季度字段——`comp_fundq` 只注册了 `atq/ceqq/saleq/ibq`；
   (b) `mktrf` 作为**信号输入**（算 EXRETAVG）——FF 因子未注册为 signal source；
   (c) `IdioRisk` 需要日频波动率——日频可加载但要走聚合路径；
   (d) `RSIZE` 需要每月最大 500 家公司的市值合计（截面聚合，可在 `compute_signal` 内算 ✓）。
   另注：C&Z 标 `Predictability = 4_not`、t=1.41 不显著，且备注说
   「原文目的不是证明它能预测，而是证明它不能解释其他预测变量」——
   把它当「复现失败案例」写是可以的，但要非常小心表述。
4. **PS ⚠️** —— `port sort` ✓、`Return=1.96` / `T=5.59` ✓、VW 十分位 ✓。
   但定义里写明 **"Include highest quintile of book-to-market only"**：
   这既可以读成「派生列（BM 五分位）筛选」（**未实现**），
   也可以读成「组内排序」（**显式报错，未实现**）。两条路都堵死。
   另外 C&Z 自己注明 `Portfolio Period=1` 是对原文
   「年内复利、财年结束后 4 个月调仓」的**近似**，且原文没说 EW 还是 VW
   —— 这两点其实是极好的欠定性素材，可惜前面的 BM 条件卡住了。
5. **OScore ✅（已纠正）** —— `LS port` ✓，定义里 “Exclude if SIC code between 3999
   and 4999, or greater than 5999” **现在可用 `not_between` 直接实现**。唯一剩下的真障碍是
   Key Table 的 **“long 低 70% / short 高 10%”非对称切分**，不是 `breakpoint_quantiles`
   能表达的形式，需要引擎新增自定义切点参数（中等工作量）。
   C&Z 还注明原文没提价格筛选，但加上 `abs(prc)>5` 后结果才接近
   —— 同样是好素材，且现在只差非对称切分一项就能跑。

### 更根本的战略问题：这 5 个优化错了维度

这 5 个里有 4 个是**多输入复合评分**（F-score 九个指标、O-score logit、
Failure Prob 八项加权、Total Accruals 分段定义）。它们考验的是
**信号公式的抽取难度**，也就是 **Q2**。

但 Q2 已被移出主线、放进 future work。论文主线是
**Q1（配置分歧）+ Q3（标准化敏感性）**，这两个都关于**组合构造配置**，不关于公式。
复合评分因子的配置通常反而是标准的十分位排序 —— **公式越难，配置越平淡**。

换句话说，这套选择在为「不研究的那个维度」做优化。

### 应该按什么选：用 SignalDoc 的 `Stock Weight` / `Quantile Filter` 做设计

Q3 问的是「HXZ 式标准化（VW + NYSE 断点 + 排除微盘）是否实质改变结论」。
那么最有信息量的对比是：

- **高敏感组**：C&Z 用 **EW + 无 NYSE 断点**的因子 —— 它们的十分位价差由微盘驱动，
  标准化会重击。这是 Q3 最强的证据。
- **对照组**：C&Z 本来就用 **VW + NYSE 断点**的因子 —— 标准化几乎不动。
  没有这个对照，「标准化有影响」这句话就没有反事实。

这样选出来的是一个**有设计的对比**，不是随机样本 —— 对 n=3–5 的论文至关重要。

### 通过引擎约束筛选后的可用池（23/331）

筛选条件：`Test in OP ∈ {port sort, LS port}`（严格，排除各种 alpha/adjusted 变体）
且 `Return` 与 `T-Stat` 均非空 且 `Cat.Data = Accounting`（纯会计，避开 IBES/日频）
且 `LS Quantile` 非空（是真正的分位排序）且 `Filter` 不含 SIC/行业/BM 条件。

| Acronym | 作者 | 年 | Ret | T | W | LSq | QFilt | Per | Filter |
|---|---|---|---|---|---|---|---|---|---|
| `ChTax` | Thomas & Zhang | 2011 | 1.30 | 11.26 | EW | 0.1 | | 3 | |
| `AssetGrowth` | Cooper, Gulen & Schill | 2008 | 1.73 | 8.45 | EW | 0.1 | | 12 | |
| `InvGrowth` | Belo & Lin | 2012 | 0.89 | 6.64 | EW | 0.1 | | 12 | |
| `ChEQ` | Lockwood & Prombutr | 2010 | 0.80 | 5.38 | EW | 0.2 | | 12 | |
| `grcapx` | Anderson & Garcia-Feijoo | 2006 | 0.57 | 5.05 | EW | 0.2 | | 12 | |
| `grcapx3y` | Anderson & Garcia-Feijoo | 2006 | 0.60 | 4.71 | EW | 0.2 | | 12 | |
| `CF` | Lakonishok, Shleifer & Vishny | 1994 | 0.66 | 3.38 | EW | 0.1 | | 12 | `exchcd in (1,2)` |
| `OPLeverage` | Novy-Marx | 2011 | 0.51 | 3.38 | EW | 0.2 | | 12 | |
| `PctTotAcc` | Hafzalla, Lundholm & Van Winkle | 2011 | 0.71 | 3.29 | EW | 0.1 | | 12 | |
| `cfp` | Desai, Rajgopal & Venkatachalam | 2004 | 1.27 | 2.77 | EW | 0.2 | | 12 | |
| `Cash` | Palazzo | 2012 | 0.69 | 2.14 | EW | 0.1 | | 1 | |
| `CBOperProf` | Ball et al. | 2016 | 0.47 | 3.17 | VW | 0.1 | **NYSE** | 12 | |
| `GP` | Novy-Marx | 2013 | 0.31 | 2.49 | VW | 0.2 | | 12 | |
| `OperProfRD` | Ball et al. | 2016 | 0.29 | 1.84 | VW | 0.1 | **NYSE** | 12 | |
| `realestate` | Tuzel | 2010 | 0.24 | 1.80 | VW | 0.2 | | 12 | |

（完整 23 条见筛选脚本输出；上表已略去若干小众因子。）

---

## 5.2 单因子论文的候选清单（2026-08-18，已定为单因子路线）

**筛选逻辑变了**：单因子论文不需要"有设计的跨因子对比"，需要的是
**这一个因子本身有多少论文留下的真实歧义**，且证据要来自 C&Z 的原话
（`Notes` 字段），不是我推断的。以下 6 个全部满足「纯 Compustat annual + CRSP monthly」，
按"零工程投入优先"排序，且逐一核对了字段注册与筛选可行性（不是猜测）：

| # | 候选 | Ret/T | W | C&Z 原话（歧义证据） | 字段是否已注册 | 筛选是否可行 |
|---|---|---|---|---|---|---|
| 1 | **`OPLeverage`** (Novy-Marx 2011) | 0.51/3.38 | EW | "EW raw returns strong... **somewhat weaker** after factor adjustment or in **VW** returns" | ✅ `xsga`/`cogs`/`at` 全部已注册 | ✅ 无需筛选 |
| 2 | **`GP`** (Novy-Marx 2013) | 0.31/2.49 | VW | "Tab 2a **says NYSE breakpoints**, but our code gets much closer to their result **without** all-stock breakpoints" | ✅ `sale`/`cogs`/`at` 全部已注册 | ✅ "Drop if financial" 用 `not_between` 直接实现（见 §5.1 纠错） |
| 3 | `OperProfRD` (Ball et al. 2016) | 0.29/1.84 | VW | "OP states they **lag** denominator, but 2015 JFE **does not lag**, no clear motivation" — 两篇姊妹论文互相矛盾；t=1.84 本身临界不显著 | ✅ `revt`/`cogs`/`xsga`/`xrd`/`at` 全部已注册 | ✅ SIC 6000–6999 排除同样用 `not_between` |
| 4 | `PctTotAcc` (Hafzalla et al. 2011) | 0.71/3.29 | EW | "t-stat is **approximate**, I converted the p-value to t... table says p<.001 instead of giving a value" | ⚠️ 需新注册 `ni`/`prstkcc`/`sstk`/`dvt`/`oancf`/`fincf`/`ivncf`（**原始 CSV 里都有，只是没写进 `sources.py`**，机械性工作） | ✅ 无需筛选 |
| 5 | **`OScore`** (Ohlson 1980 / Dichev 1998) | 1.17/3.36 | EW | "OP does not mention price screen, but without the screen results are far, and with it results are very close" | ✅ 判别式里的字段（`at`/`lt`/`act`/`lct`/`ib`/`fopt`≈`oancf`）除 `lt` 外基本已注册，`lt`/`oancf` 需要新注册（机械性） | ⚠️ SIC 排除可行（`not_between`），**但 long 低 70%/short 高 10% 是非对称切分**，`breakpoint_quantiles` 表达不了，需引擎新增自定义切点参数（中等工作量，唯一动核心排序逻辑的地方） |
| 6 | `PS`（Piotroski F-score，2000） | 1.96/5.59 | VW | "OP **does not explicitly say** if EW or VW... To approximate, we..." — 三处独立歧义 | ⚠️ 需新注册 `oancf`/`txt`（原始 CSV 有） | ❌ "仅纳入 BM 最高五分位" 是派生列筛选/序贯排序，两者都未实现，需接受声明式偏离 |

**关于你特别交代要保留的 OScore**：核实结论是**可以做**，但要接受一项真实的引擎改动——
非对称切分（long 70% / short 10%）。这不是"能不能"的问题，是"值不值得"：
OScore 本身歧义证据很强（C&Z 自己说"论文没提价格筛选，但不加结果差很远"），
且判别式是纯 Compustat 字段的 logit 组合，不需要 CRSP 以外的数据源。
如果你愿意为它做这一处引擎改动，它是本清单里"故事最完整"的候选之一。

### 单因子论文的最终建议

**首选 `GP` (Novy-Marx 2013 Gross Profitability)**：

- 零字段注册、零引擎改动（SIC 排除已被 §5.1 的纠错解除阻塞）
- C&Z 的 Notes 提供了一个**论文陈述与最优实现直接矛盾**的证据（断点方式），
  比"论文没说清楚"更有冲击力——是"论文说了，但说的不对"
- 信号公式极简单 `(sale − cogs) / at`，不会被质疑"复杂度掩盖了配置问题"
- 教科书级（后来进入 FF5 的 RMW），审稿人有先验
- 样本期 1963–2010，覆盖足够长

**次选 `OPLeverage` (Novy-Marx 2011)**：唯一真正端到端零工程投入的候选，
且歧义证据（加权方式改变结论显著性）直接对应 Q3 主线，若 GP 因某种原因不可行，
这是最稳的备胎。

**你点名的 `OScore`**：留作**正式备选**，需要引擎补一个自定义非对称切点参数；
若你觉得这个投入值得，可以替换 GP 成为主选——它的三层歧义（价格筛选、SIC 排除、
非对称切分）比 GP 的单一断点矛盾信息量更大，代价是唯一一个要动核心排序逻辑的选项。

---

## 5.3 最终确定：因子清单（2026-08-19，替换为 xlsx 分歧证据清单）

**⚠️ 本节替换 2026-08-18 版的 6 因子清单**（`GP`/`PS`/`BrandInvest`/`OperProfRD`/`grcapx3y`+`AssetGrowth`）。
用户提供了 `data/test_papers/test_papers_data_sources.xlsx`，直接从 **HXZ 和 C&Z 各自的实际判决**
（而不是 C&Z 单方 Notes 里的措辞）出发选因子，覆盖的分歧机制更丰富。核对方法：
逐条对照 `data/CZ code/SignalDoc.csv` 交叉验证 xlsx 里的数字/引用，并按 §4 的实现边界核实可行性。

| # | Acronym | 作者年份 | 分歧类型（xlsx 原始分类） | 数据 | 状态 |
|---|---|---|---|---|---|
| 1 | `GP` | Novy-Marx 2013 | **两篇论文罕见一致**（C&Z 0.30/2.38，HXZ 0.20/1.85） | Compustat+CRSP | ✅ 可行，零改动（见 §5.1）；⚠️ xlsx 数字与 SignalDoc.csv 的 0.31/2.49 不完全一致，需确认 xlsx 原始出处再定稿引用 |
| 2 | `PS`（Piotroski F-score） | 2000 | HXZ 判"fails to replicate"；C&Z 原始方法判成功（t=3.29 vs 论文 5.59，归为 Clear Predictor） | Compustat+CRSP | ✅ 可行，需声明 BM 分位偏离（见 §5.1）；本条证据最干净——两边给出**相反的最终判决**，不只是数字不同 |
| 3 | `fgr5yrLag` | La Porta 1996 | **数据版本分歧**：差异既非权重/断点，也非滞后结构，源于 IBES 这类会被回溯修订的数据源在不同抓取时间点内容不同——**"agent 理论上无法通过纯方法论比对发现"**（用户原话） | Compustat+CRSP+**IBES** | ⚠️ 需新注册 `ibes_ltg`（IBES 长期增长率预测，大概率是 `IBES_UNADJUSTED_SUMMARY.csv` 里 `MEASURE="LTG"` 的行，同一文件、同一 schema，只是 `raw_filters` 换值——机械性，但**具体 MEASURE 取值待实际跑数据时确认**，未扫描内容验证） |
| 4 | `Leverage` | Bhandari 1988 | HXZ 判定失败，C&Z 用原始方法论判定成功 | Compustat+CRSP | ❌ **硬否决**：本节新核实，`Test in OP = mv reg`，`LS Quantile` 为空——和已否决的 `TotalAccruals`/`OperProf` 同一类硬伤，论文/C&Z 都没给组合排序 spread，只有回归系数，`portfolio_sort` 用不了 |
| 5 | `AssetGrowth` | Cooper, Gulen & Schill 2008 | 已跑通锚点；xlsx 额外提供 HXZ 的 I/A 年度版本（NYSE-VW t=2.89，量级仅原文 VW 版 42%）+ C&Z 的季度版本 `AssetGrowth_q`（t=4.84，强）| Compustat+CRSP | ✅ 已跑通；建议用 xlsx 提供的这两个额外已发表数字**加厚**现有案例，不是替换 |
| 6 | `OScore` | Dichev 1998 | 严重分歧：HXZ 判定失败，C&Z 用原始方法判定成功 | Compustat+CRSP | ⚠️ 可行但需引擎新增非对称切分（long 70%/short 10%，见 §5.1/§5.2），xlsx 这条证据加强了投入这项工程的理由——证明 HXZ vs C&Z 真分歧确实存在，不只是实现歧义 |
| 7 | `FailureProbability` | Campbell, Hilscher & Szilagyi 2008 | **两边都失败** | Compustat+CRSP+**日频+市场收益** | ⚠️ 仍需 `mktrf` 作信号输入（未注册）、`ltq`/`cheq` 季度字段（未注册）、日频波动率聚合路径（见 §5.1）——工程投入大，暂不建议优先 |

**这份新清单覆盖的分歧机制**（比旧的 6 因子清单更丰富，直接对应"为什么会分歧"这个研究问题）：
两边一致（GP，对照锚点）、HXZ 失败/C&Z 成功（PS、Leverage 硬否决、OScore）、
**纯数据版本分歧、非方法论分歧**（fgr5yrLag，本框架的已知盲区，诚实披露价值高）、
两边都失败（FailureProbability，第二种对照锚点）。

**待确认/待办**：
1. **`GP` 的数字来源需核实**：xlsx 的 0.30/2.38 vs SignalDoc.csv 的 0.31/2.49，
   引用前要确认 xlsx 这两个数字的原始出处（HXZ 论文附表？另一份转录？），
   避免两个数字在正文里打架。
2. **`Leverage` 建议整体剔除**，除非愿意为它单独接受"只报回归系数、无法用组合排序对比"
   这个例外——不建议，会打破全文"只比较组合排序 spread"的一致口径。
3. **`fgr5yrLag` 的 IBES `MEASURE="LTG"` 取值**需要在实际拉数据时确认（本节未扫描文件内容验证，
   只确认了 `MEASURE` 字段本身存在）。
4. **因子数量**：7 个候选里 1 个硬否决（`Leverage`），剩 6 个（`GP`/`PS`/`fgr5yrLag`/
   `AssetGrowth`/`OScore`/`FailureProbability`）。`FailureProbability` 工程投入大，
   是否也先剔除、留 5 个？需要你定。

---

### ⚠️ 关于 HXZ 的 `portf_*_monthly_2025.csv`

你提到从 HXZ 的 `inv_monthly_2025.zip` / `prof_monthly_2025.zip` 取组合收益文件。
注意 `AGENTS.md` 的既定框架：**HXZ 在本项目里是「标准化配置的来源」
（一份我们施加在自己信号上的 config），不是外部结果**。
如果直接引入 HXZ 已发布的组合收益序列做对比，identification level 会降级为
`observational`（外部已发布输出，无法控制其信号与数据 vintage），
这与 Q3 的受控设计不是一回事，两者不能混在同一张表里。

建议：HXZ published returns 可以作为**第三方 sanity check** 放在附录，
但主结果的 Q3 必须是「我们的信号 × HXZ 配置」在我们引擎上的运行结果。

> **2026-08-18 更新**：上面这条警告写于 `hxz_bridge.compute_hxz_reported()` 之前，
> 当时还没有一个受控的「按窗口取 HXZ 报告值」机制。现在 $HXZ$ 端点已经走
> `compute_hxz_reported_both_windows()`（见 Ch.3 的窗口/口径失配残差项），
> 不是直接搬运 `portf_*_monthly_2025.csv` 的外部收益序列，警告本身仍然
> 适用（不要在正文用外部 AltPorts 收益替换 `A_hxz` track），但已被 Ch.3/Ch.6
> 的正式处理取代，此处保留仅作历史记录。

---

## 六、其他待决事项

1. **`paper/` 目录是否入 git？** 建议入（论文源码值得版本化），
   但编译产物（`*.aux/*.log/*.pdf`）加进 `.gitignore`。
2. **是否要 `scripts/export_paper_tables.py`**，从 `comparison.json` 自动生成
   LaTeX 表格正文？强烈建议做——手抄数字是这类论文最常见的错误来源，
   而且你后面还要重跑。但这是独立的实现任务，可以晚一步。
3. **参考文献管理**：`natbib + bibtex`（Overleaf 兼容性最好）还是
   `biblatex + biber`（功能强）？毕业论文建议前者。
4. **HXZ vs C&Z 口径核实**（见第一节末尾的红旗）—— 是否现在就做？
5. **样本期与 WRDS vintage 必须人工核实**（见 4.3 末尾）—— `data/snapshots/` 是空的，
   代码里没有硬编码日期范围，这个数字只能你手工确认后写进附录 F。
6. **是否为 momentum 补重叠持有期、为 profitability 补 SIC 区间筛选**（见第五节两个冲突）
   —— 这两个决定会直接改变因子选择，越早定越好。
