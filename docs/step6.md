# Step 6 —— 研究设计与实现现状

> 本文件由原 `plan.md`（step6 实现现状描述）与 step6 研究设计讨论合并而成，
> 2026-08-16。
>
> **阅读顺序说明**：
> - **Part I–II 是权威的**，是后续所有工程决策的依据。
> - **Part III 只是"当前代码长什么样"的快照**。step6 很可能被重构，因此
>   Part III 的细节会先于 Part I–II 过时。**两者冲突时以 Part I–II 为准。**

---

## 0. 术语速查表（后文符号 A/Z/P/H、`C_agent`/`C_cz`/`C_std`、①–⑥ 都在这里）

**先说"两个独立实现者"是什么意思**：一篇论文的方法描述是自然语言，会留下
很多没写清楚的细节（缺失值怎么处理？断点用哪批股票？调仓多频繁？）。
**C&Z 和我们的 agent，是两个互不知情地各自读这篇论文、各自做出实现选择的
主体**——C&Z 是一个人类团队，读了论文写代码；agent 是 LLM，只读论文文本
（`AGENTS.md` 的硬约束：**永远不把 C&Z 的 SignalDoc/代码喂给提取器**，
否则 agent 就是在抄答案，不再是"独立"实现者）。

**关键推理**：如果这两个互不知情的实现者，各自对同一篇论文做出的选择
（config）不一样，这个不一样**不是谁的错**，而是论文本身没把这件事说
清楚的证据——这就是我们说的"论文的欠定性"。人类不可能雇几百个团队各自
独立实现同一篇论文来测这件事，但 agent 可以规模化地扮演"第二个独立
实现者"这个角色，这也是 LLM 在本项目里唯一不可替代的价值（见 §6）。

### 行（信号来源）——"谁写的 `compute_signal`"

| 记号 | 含义 |
|---|---|
| **P**（Paper）| 论文本身。**不可观测**——论文只有文字描述，没有可执行代码，这正是"复现"问题的根源，P 这一行在网格里不存在 |
| **A**（Agent）| LLM 从论文提取后生成的信号公式 |
| **Z**（C&Z）| C&Z 团队的信号（公式移植 or 官网下载的数值，见 §21 缺口 #4）|
| **H**（HXZ）| **不是信号来源**！HXZ 论文从未提供可执行的信号代码，它唯一的贡献是一套统一的组合构建协议（见下）|

### 列（组合构建配置）——"用什么规则把信号切成多空组合"

| 记号 | 含义 | 从哪来 |
|---|---|---|
| `C_agent` | agent 从论文提取、resolve 出的 config | agent 的 MethodSpec |
| `C_cz` | C&Z 团队对同一篇论文实际做出的配置选择 | SignalDoc 列 + 代码里的隐含默认值（§9）|
| `C_std` | **HXZ 标准化配置**（VW、NYSE 断点、十分组、年度调仓、universe 改为真正生效的 `exchcd`/`siccd` 过滤，均逐字段对照论文核实，见下方 2026-08-16 更新）| `data/reference/hxz_standard_config.yaml`（单一权威来源，经 `HXZ_STANDARD_CONFIG` 加载） |

### 网格 = 行 × 列

| | `C_agent` | `C_cz` | `C_std` |
|---|---|---|---|
| **A**（agent 信号） | ① | ② | ③ |
| **Z**（C&Z 信号） | ④ | ⑤ | ⑥ |

**① 到 ⑥ 都是"用某一行的信号 + 某一列的配置，在我们自己的引擎上实际跑出
一个回测结果"**——都是我们要跑的东西，不是外部数字。

### 外部锚点——已发表的数字，从不在我们引擎上重跑

| 记号 | 含义 |
|---|---|
| `N_paper` | 论文自己报告的头条 t 值/收益率（人工摘录，存在 MethodSpec 里）|
| `N_cz` | C&Z 自己用他们的代码重算出的组合收益/t 值（需下载，不在本仓库）|
| C&Z 的 AltPorts | C&Z 自己发布的标准化变体（如 VW 十分组）的收益数字（需下载）|
| `N_hxz` | HXZ 论文附表里对应因子的标准化 t 值（若查得到，待办）|

这些数字只用来做**校准**（验证我们引擎/数据没问题）或**背景**（端到端差距
的量级参考），**从不参与"哪个字段导致了差距"这种归因计算**——归因只能
来自网格里我们自己跑出来、两两可比的那些格子（①–⑥）。

---

# Part I. 研究设计（权威）

## 1. 研究问题

> **一篇论文的方法描述，在多大程度上唯一决定了它的实证结果？**

之所以值得做，是因为它击中了 HXZ 与 C&Z 争论中**双方共享的、未经检验的前提**：

- HXZ (2020) 说："我用统一协议**替换**了论文的方法" → 约三分之二异象失效
- C&Z (2022) 说："我**忠实实现**了论文的方法" → 绝大多数异象可复现
- **两边都假定"论文的方法"是一个定义明确的对象。**

我们要测量的，就是"它"到底存不存在、有多确定。

### 三个子问题（对应三个正交轴）

| | 子问题 | 怎么测 | 学术含义 |
|---|---|---|---|
| **Q1** | 两个独立实现者从同一篇论文读出的**组合构建配置**差多少？差异在实证上重要吗？ | `C_agent` vs `C_cz` 的 config diff | **协议的欠定性** |
| **Q2** | 两个实现者写出的**信号公式**差多少？重要吗？ | `A` vs `Z`，config 钉死 | **公式的欠定性** |
| **Q3** | 换成统一的 HXZ-style 标准，结果怎么变？ | `C_cz` → `C_std` + ablation 分解 | **HXZ vs C&Z 之争本身**（已拍板降级为校准/背景，非贡献，见 §25） |

## 2. 核心论点

**用 Q1+Q2 测出的"实现者间自然分歧"当尺子，去度量 Q3 的标准化效应。**

- 若某因子在"两个诚实实现者的自然分歧范围内"就能从 t=8 掉到 t=2 →
  HXZ 把它杀死**不是**"强加外来标准"的问题，这个因子本来就没有唯一答案，
  争论"它复现了没有"是伪命题。
- 若某因子在自然分歧下岿然不动，一进 HXZ 协议就崩 → 这才是**实质性的
  方法论分歧**，值得吵。

> **贡献定位：我们不站队 HXZ 或 C&Z，我们提供一个判据，说明在哪些因子上
> 他们的争论是实质的，在哪些因子上争论本身就是伪问题。**

## 3. 四个对象归到两个正交轴

**关键澄清：C&Z 和 HXZ 不在同一个轴上。**

| | 提供**信号定义** | 提供**组合配置** | 提供**已发表数字** |
|---|---|---|---|
| **Paper (P)** | ❌ 不可观测（复现问题的根源） | ✅ 论文描述 → MethodSpec | ✅ `SignalDoc.Return`/`T-Stat`（手工摘录） |
| **C&Z (Z)** | ✅ 代码可读 / 数值可下载 | ✅ SignalDoc + 代码隐含惯例 | ✅ 需下载（不在仓库） |
| **Agent (A)** | ✅ LLM 生成的 `compute_signal` | ❌ **自己不带 config**，用的是论文的 | — |
| **HXZ (H)** | ❌ **不是信号源** | ✅ 唯一贡献：统一标准 | — |

👉 "C&Z vs HXZ" 唯一有意义的精确表述是：**同一份信号，在 C&Z 配置下
vs 在 HXZ 配置下**——一次纯粹的 config 轴移动。

## 4. 实验网格

行 = 信号来源，列 = 配置：

| | `C_agent`<br>(agent 从论文提取) | `C_cz`<br>(C&Z 的实际选择) | `C_std`<br>(HXZ-style 标准化，见 §25) |
|---|---|---|---|
| **A**（agent 信号） | ① | ② | ③ |
| **Z**（C&Z 信号） | ④ | ⑤ | ⑥ |

外部锚点（**不跑**，只对比）：`N_paper`（已有）、`N_cz`（需下载）、
C&Z 的 AltPorts（需下载）、`N_hxz`（待查 HXZ 论文附表）。

### OAT 与 Factorial 是什么（后面反复用到的两个术语）

- **OAT（One-At-a-Time，一次一个）**：从起点 config 出发，每次只翻一个
  字段，其余保持起点原值，跑 n 次（n = 起点与终点不同的字段数）。能算出
  "每个字段单独的贡献"，**假设各字段互不干扰**。跑的次数与字段数成
  **线性**关系，便宜。
- **Factorial（全因子/全组合）**：n 个字段各有 2 个取值（起点值/终点值），
  全组合是 $2^n$ 种全部跑一遍。除了单独贡献，还能算出**交互项**（两个字段
  同时变动时，效果是否比"分别单独变动之和"更大或更小）。跑的次数随 n
  **指数**增长，n>4-5 就很贵。
- 两者的关系：起点相同、终点相同时，**OAT 的每条轨道也是 factorial 网格里
  的一个点**——OAT 不是 factorial 的替代品，是它的一个**低成本子集**（只测
  "单变一个"的那几个角，不测"同时变多个"的中间角）。

## 4a. Phase 1（核心）：①②③ + 两组 OAT —— 只用 agent 自己的信号

**跑什么**：

| 轨道 | 信号 | Config | 用途 |
|---|---|---|---|
| ① `original_method` | Agent | `C_agent` | 基线 |
| ② | Agent | `C_cz` | Q1 实证后果 |
| ③ `standardized_hxz`（代码轨道名不变，概念上即 `C_std`） | Agent | `C_std` | Q3 实验臂 |
| `ablation_*`（①→②，仅对 `C_agent`≠`C_cz` 的字段） | Agent | 逐字段翻转 | Q1 归因 |
| `ablation_*`（①→③，现有机制） | Agent | 逐字段翻转 | Q3 归因 |
| `C_agent` vs `C_cz` 字段级 diff（**不跑回测**）| — | — | 分歧本身，零成本，最先做 |

**为什么叫"核心"**：全程只在 config 轴移动，**信号钉死为 agent 的实现**，
不需要下载/移植任何 C&Z 数据，因此不受 §21 的适配层风险影响，是投入产出比
最高、最先能跑通的一层。

### Phase 1 能得出的结论

- **Q1 的完整归因**：agent 的 config 换成 C&Z 实际选择后，总差距是多少，
  哪个字段贡献最大（① vs ②，OAT 拆解 + `explained_fraction` + `residual`）。
- **Q3 实验臂的完整归因**：agent 的实现标准化到 HXZ 协议后，总差距是多少，
  哪个字段贡献最大（① vs ③，同样拆解）。
- **两个差距的大小可以横向比较**：① vs ② 与 ① vs ③ 哪个更大，初步回答
  "agent 提取的 config 离 C&Z 更近还是离 HXZ 更近，这个距离是否有实证后果"。
- **"分歧 ≠ 后果"的雏形映射**：结合零成本的字段级 diff，能说"论文在 N 个
  字段上和 C&Z 不一致，其中字段 X 的不一致真的改变了结论，字段 Y 的不一致
  没什么影响"——这已经是 Type I–IV 分类的骨架。

### Phase 1 **不能**得出的结论

- **无法区分"这个因子天生对标准化敏感"还是"agent 这份实现格外脆弱"**。
  只看到 agent 信号一条线的表现，没有 C&Z 信号跑同样路径作对照，Type II
  vs Type IV 的判定在方法论上还不完整。
- **仪器没有被校准过**——没有 ⑤ vs `N_cz` 这一步，无法确认我们自己的引擎/
  数据抽取是对的。Phase 1 的所有数字都建立在"假设流水线没问题"这个未经
  验证的前提上，必须在报告里明确写成限制条件。
- **Q2（信号公式的欠定性）完全做不了**——需要 C&Z 的信号才能比。
- **无法回答端到端问题**（① vs `N_paper` 差多少、差在哪）——这类比较仍然
  混杂着数据 vintage、我们引擎实现等因素，只能做背景参考，不能归因。

### 归因方法（2026-08-16 确定，取代下面旧版加法示例）

**只在平均月收益 μ 上做加法归因，不在 t 值上做。** t = μ/(σ/√N) 是比值，
不具有可加性；μ 在不同 config 间近似可加，所有"字段 X 贡献了多少"的说法
都只在 μ 上做。

**字段数 ≤5 时，跑全组合（factorial），不是 OAT。** `C_agent` 与 `C_cz`/
`C_std` 通常只差 2–4 个字段（见 §11），全组合成本很低（n=3→8 次回测，
n=4→16 次）。每个字段的贡献 = 该字段翻转时 μ 的平均变化（对其余字段的
所有取值取平均）——所有主效应 + 所有交互项**精确加总 = 总差距，残差恒为
0**，顺带填充 `interaction_effects`（缺口 #7）。字段数 >5 时退回 OAT 筛出
贡献最大的 2–3 个字段，只对它们补跑小规模全组合，其余字段固定在终点值，
并诚实报告"其余字段按 OAT 处理，未做完整交互分解"。

**t 值的变化单独用恒等式解释，不做加法归因：**

$$\log t=\log\mu-\log\sigma+\tfrac12\log N$$

t 的变化 = 收益变化 − 波动变化 + 样本量变化，三项精确加总，没有残差。
`BacktestExecutor.compute_summary_stats` 已经返回 `mean_monthly_return`、
`t_stat`、`n_months`，σ 直接反解（`σ = μ/t·√N`），不需要改引擎。（μ<0 时
对数无定义，退回报绝对差并单独标注，不要硬套。）

**每个对比都要配对显著性检验，只有显著的字段才能称"重要"**：先取两条
轨道的月份交集（config 改动可能改变有效月份），构造差值序列
`d_t = r_a,t − r_b,t`，报告均值、t 值、Newey-West（lag 6–12）稳健版本。
`ReplicationDiffResult` 建议新增 `paired_test: {mean_diff, t_stat,
nw_t_stat, n_overlap_months}` 与 `t_channel_decomposition: {d_log_mu,
d_log_sigma, d_log_n}` 两个字段；`explained_fraction`/`residual` 在全组合
路径下 residual≡0，仅 OAT 回退路径使用，且总差距接近 0 时不报比例（避免
稳健因子上分母趋零导致比例爆炸）。

一个具体例子见 §4c（原 Phase 3 位置，现为归因的默认路径）。

## 4b. Phase 2（扩展）：④⑤⑥ —— 引入 C&Z 的信号

**跑什么**：

| 轨道 | 信号 | Config | 用途 |
|---|---|---|---|
| ④ | C&Z（下载值）| `C_agent` | Q3 对照臂起点 |
| ⑤ | C&Z（下载值）| `C_cz` | **校准锚点 1**（vs `N_cz`）|
| ⑥ | C&Z（下载值）| `C_std` | **校准锚点 2**（vs AltPorts/`N_hxz`）+ Q3 对照臂终点 |
| `ablation_*`（④→⑥，对照臂）| C&Z | 逐字段翻转 | Q3 对照臂归因 |
| ① vs ④（钉死 config）| — | — | Q2：信号公式的欠定性 |

**前置条件**：C&Z 的信号数值"能不能直接跑"本身是个真实的工程风险，不是
下载完就能直接喂进引擎——具体见 §21 缺口 #2、#4 和下面的适配层清单。

### Phase 2 能得出的结论（补齐 Phase 1 的缺口）

- **完成 Type II vs Type IV 的判定**：对照臂 ④→⑥ 若也大幅下降（比如
  t=7.0→3.2），说明是**因子本身脆弱**（支持 Type II，真实的方法论分歧）；
  若基本扛住（比如只掉到 6.0），说明是 **agent 实现的人为脆弱性**，不能
  归咎于因子本身。
- **Q2**：① vs ④（config 钉死）测出公式本身的分歧有多大后果。
- **仪器校准**：⑤ vs `N_cz`、⑥ vs AltPorts/`N_hxz` 通过后，Phase 1 的数字
  才真正可信，不再只是"假设流水线没问题"。

### Phase 2 的前置风险（信号适配层，跑之前必须处理）

下载的信号数值**不能直接塞进 `precomputed_signal_path`**，至少要处理：

1. **符号约定**：下载的 wide 格式已经"按预期方向翻过符号"，我们引擎会
   自己再翻一次方向——两次翻等于翻反了，必须择一。
2. **重复滞后**：C&Z 的 `time_avail_m` 已经是点时点可得值（他们自建时已做
   过会计滞后），若我们引擎按自己 config 的 `accounting_lag_months` 再滞后
   一次，就是双重滞后。
3. **1 个月组合构建滞后错位**（§9 已查实的 `yyyymm+1`）：需要显式选定并
   记录处理方式，两边不一致会造成系统性错位（缺口 #2）。
4. **样本对齐**：我们的数据快照与 C&Z 下载数据的 permno 覆盖/起止年份
   未必完全一致，比较前需收窄到重叠区间。

**建议做法**：先只在**一个因子**（如 AssetGrowth）上把适配层跑通、
`⑤ vs N_cz` 校准过关，再推广到其余候选因子——不要一次性对全部因子做。
第一次跑 ⑤ 对不上 `N_cz` 是**预期内的诊断信号**，不是"仪器整体不可信"的
判决，应先逐条排查上面 4 条。

## 4c. 全组合归因的例子 + 何时退回 OAT（2026-08-16 取代原"Phase 3 可选"框架）

**不再有独立的"Phase 3"。** 全组合就是 §4a 归因方法的默认路径（字段数
≤5 时），OAT 只在字段数 >5 时作为退回方案，理由：

- 全组合的主效应/交互项**精确加总 = 总差距，残差恒为 0**，不像 OAT 依赖
  任意选定的基线；
- §11 的统计显示实际差异字段大概率只有 2–4 个，$2^4=16$ 次回测完全可承受；
- **只有 >5 个字段时才退回 OAT**：先用 OAT 挑出贡献最大的 2–3 个字段补一次
  小规模全组合，其余字段固定在终点值，诚实报告未做完整交互分解。

### 具体例子（虚构数字，仅用于说明推理结构，不是真实结果）

因子 X，`C_agent` 与 `C_cz` 差 3 个字段（`weighting`、`n_groups`、
`rebalance_frequency`），全组合跑 8 次，记平均月收益 μ（%）：

| # | weighting | n_groups | rebalance | μ |
|---|---|---|---|---|
| 1 | EW | 5 | 年 | 0.80 ← ① |
| 2 | VW | 5 | 年 | 0.60 |
| 3 | EW | 10 | 年 | 0.90 |
| 4 | EW | 5 | 月 | 0.78 |
| 5 | VW | 10 | 年 | 0.55 |
| 6 | VW | 5 | 月 | 0.58 |
| 7 | EW | 10 | 月 | 0.88 |
| 8 | VW | 10 | 月 | 0.53 ← ② |

`weighting`（EW→VW）在其余字段全部取值下的平均效应：
`(0.60−0.80 + 0.55−0.90 + 0.58−0.78 + 0.53−0.88) / 4 = −0.275`。
同理 `n_groups` 贡献 +0.075，`rebalance` 贡献 −0.020。
三者之和 −0.22，总差距 0.53−0.80=−0.27，差的 −0.05 即交互项（此处主要是
`weighting × n_groups`：VW 的负效应在十分组下更强，−0.35 vs −0.20，印证
§8 的事前预测）。**主效应 + 交互项精确加总 = 总差距，无残差。**

对每一对轨道（比如①②）都要跑一次配对检验：取两条轨道的月度收益差值序列
`d_t`，报告 `mean(d_t)` 和 `t_stat(d_t)`；只有显著的字段才能称"重要"。

### 一个关键的方法论提醒：OAT 的"起点"选择本身会影响结论

OAT 有两种做法，数值上通常不同：**(A) 固定基线**（每次都从 agent 原始
config 出发，只改一个字段，现有 `ablation_switches` 的实现方式）；
**(B) 累积路径**（改完第一个字段后，以新点为基础再改下一个，逐步走到
终点，结果依赖改动顺序）。**若怀疑有交互，(A)+(B) 可能给出不同的
"谁贡献更大"，且 (B) 依赖任意选定的顺序**——这正是全组合作为默认路径的
理由：全组合不依赖任何路径顺序，是精确解，OAT 仅在字段数超限时作退回。



## 5. 因子分类学（可交付成果）

| | **对标准化不敏感** | **对标准化敏感** |
|---|---|---|
| **实现者分歧小** | **I. 稳健因子**<br>两派都该认可 | **II. 纯协议之争**<br>👉 HXZ vs C&Z 的**实质战场** |
| **实现者分歧大** | **III. 欠定但幸运**<br>论文写得糟，结论碰巧稳健 | **IV. 伪命题**<br>👉 **两派都没识别的类别** |

Type III / IV 是 HXZ 和 C&Z 谁都没承认其存在的类别——**这是我们最新颖的主张**。

选因子的目标是**覆盖不同格子**，不是挑好移植的。

## 6. 定位：深度案例研究（3–5 个因子）

明确**不**主张：

- ❌ 不主张"异象文献整体可不可信"（n=3–5，没有统计基础）
- ❌ 不主张"LLM 能复现论文"（工程结论，金融审稿人不关心）
- ❌ 不主张 HXZ 或 C&Z 谁对——我们提供判据，不做裁决
- ✅ **LLM 是仪器，不是研究对象**。价值在于：可规模化、无门户之见的第二实现者

### 核心 + 扩展结构（不被单点阻塞）

**核心（今天可做，最严谨）**：全程只在 config 轴移动，**不依赖任何我们
自己写的信号实现**，因此绕开了"你的引擎/移植不对"这个最常见攻击点。

1. 测量分歧：`C_agent` vs `C_cz` 字段级 diff（零回测成本）
2. 区分来源：人工标注三方比对，剥离"agent 误读"
3. 测量后果：**钉死同一信号**，只切三套配置跑回测 + ablation
4. 分类：用步骤 1 当尺子量步骤 3 → Type I–IV

**扩展（需下载 C&Z 数据）**：5. 校准；6. Q2 信号轴。

## 7. Q1 的致命效度威胁与解法

agent 配置 ≠ C&Z 配置，有两种解释：**(a) 论文写得不清楚**（要测的）
vs **(b) agent 读错了**（工具 bug）。**不区分则 Q1 一文不值。**

解法：`data/test_method_specs_human_labeled/` 的 **12 份人工标注**做三方比对：

| 人类标注 | agent | 判定 |
|---|---|---|
| = C&Z | ≠ C&Z | **agent 误读**（不计入欠定性） |
| ≠ C&Z | ≠ C&Z | **论文欠定**（真信号）👈 |
| ≠ C&Z | = C&Z | 人类误读 / 欠定的另一面 |

## 8. 事前预测（可预注册，2026-08-16 记录）

> 在 `C_cz → C_std` 的分解中，**`weighting_rule`（EW→VW）与
> `breakpoint_source`（全样本→NYSE）应共同主导**，二者都直接作用于微盘股
> 权重，且**很可能存在显著交互**（NYSE 断点把微盘股推入极端组，VW 又降低
> 其权重，方向相反）。

两重价值：
1. **效度检验**——跑出来若非如此，大概率是引擎或数据有问题
2. **方法论姿态**——事前写下预测，抵御"你是不是挑了个好看的分解方式"

👉 也回答了"交互效应重不重要"：**在这两个开关上重要**，应真正估计
`interaction_effects`，而不是让它停在字段占位。

---

# Part II. 事实基础（已查证，2026-08-16）

## 9. C&Z 的隐含惯例（全部来自其源码）

### 默认值层（`Portfolios/Code/01_PortfolioFunction.R:83-93`）

C&Z 自己的注释：`we use NA as "function default" and then transform to real defaults here`

```r
if (is.na(sweight))    {sweight = 'EW'}
if (is.na(startmonth)) {startmonth = 6}
if (is.na(portperiod)) {portperiod = 1}
if (is.na(q_cut))      {q_cut = 0.2}
```
第 124 行：`if (!is.na(q_filt)) { if (q_filt=='NYSE') {...} }` → **空 = 全样本断点**

👉 **C&Z 有一套与我们 step2 完全同构的"合理默认值"层。SignalDoc 的空值 =
"论文没钉死，回落到 house convention"。**

### 会计滞后（`Signals/pyCode/DataDownloads/`）

- **年度 Compustat**：`time_avail_m = datadate + 6个月`（固定，全局硬编码），
  然后每条年报展开成 12 个月向前填充
- **季度 Compustat**：`max(datadate + 3个月, rdq)`，且 `rdq - datadate > 6个月` 则丢弃

### 组合构建滞后（`01_PortfolioFunction.R`）

```r
signallag = signal[, yyyymm := yyyymm + 1]   # 所有因子无差别滞后 1 个月
```

⚠️ **不在 SignalDoc 里，是全局硬编码。我们的引擎若不施加同样的 1 个月错位，
校准必然对不上，且是系统性偏差。这是目前最容易踩的坑。**

### 再平衡语义

```r
rebmonths = (startmonth + seq(0,12)*portperiod) %% 12
# port 在非再平衡月置 NA，然后 fill(port) 向前填充
```
👉 `portperiod` = **再平衡间隔（月）**，干净映射到 `rebalance_frequency`。
**持有期恒等于再平衡间隔，无重叠组合。**

### 缺失值

`01_PortfolioFunction.R:30` `filter(!is.na(signal))` → 等价于 `missing_action="drop"`

### Universe（2026-08-16 补上，之前完全遗漏）

`Signals/pyCode/SignalMasterTable.py`——**每个 predictor 都基于这张共享底座表构建**，
不是某个因子单独的脚本：

```python
# keep if (shrcd == 10 | shrcd == 11 | shrcd == 12) & (exchcd == 1 | exchcd == 2 | exchcd == 3)
df = df[(df['shrcd'].isin([10, 11, 12])) & (df['exchcd'].isin([1, 2, 3]))].copy()
```

同一文件里 C&Z 自己留的开发者注释：`# TBC: remove and use this filter as default
in SignalDoc.csv`——说明这条筛选**从未被记录进 SignalDoc**，`CZReferenceProfile`
从 SignalDoc 解析不到任何 universe 信息完全是预期之中，不是我们漏读。之前
`cz_profile_to_config_override()` 完全没有设置 `universe_filters`，②
(`cz_actual_config`) 轨道此前实际继承的是论文自己 MethodSpec 的 universe_filters
(可能为空)，不是 C&Z 真正用的 universe——2026-08-16 已修，加了
`{shrcd: in [10,11,12]}` + `{exchcd: in [1,2,3]}`。这一层没有排除金融行业、没有
排除负 book equity、没有价格筛选——那些是各个 predictor 自己脚本里可能加的
`filterstr`（见下），不是这张共享底座表的全局规则。

### 长短腿分配（查证后确认：不是缺口，`long_leg`/`short_leg` 没有 per-track override 这个机制）

`01_PortfolioFunction.R:88-89`：`if (is.na(longportname[1])) {longportname = 'max'}`
/ `if (is.na(shortportname[1])) {shortportname = 'min'}`——**long 恒等于最高信号
分位组，short 恒等于最低分位组**，跟具体因子的 `Sign` 无关，因为 `Sign` 是在排序
**之前**直接乘到原始信号上的（`signal$signal = signal$signal*Sign`，第 54 行）：
先把信号按 Sign 翻转，再统一按"最高/最低"分桶，所以桶位分配本身是全局常量。

之前判断这里"暂不实现，怕做错"——**推翻，判断错了机制**。查了
`registry._build_config_from_resolved`（第 656-661 行）：`config["long_leg"]`/
`config["short_leg"]` 只是从 `long_portfolios`/`short_portfolios`（真正驱动组合
构建的数字桶列表）反推出来的展示字符串，不是驱动执行的输入；真正的多空分配来自
`_resolve_legs(paper, ...)` 直接读 `paper.portfolio.legs`（论文自己描述的哪个
分位是多/空），而 `paper` 对同一因子的每条 track 都是**同一个 MethodSpec**，
不受任何 config override 影响——这个引擎根本没有"按 track 覆盖多空腿"这个能力，
所以 C&Z 的"Sign 翻转 + 固定 max/min"和我们的"直接提取论文原文定义"两条路径，
对同一个因子必然收敛到同一个多空分配，不存在需要在 `cz_profile_to_config_override`
里补一个 `long_leg`/`short_leg` override 的问题。

## 9b. 引擎能力约束 与 C&Z 的兼容因子筛选（2026-08-16）

我们的 `BacktestExecutor` 有两条硬约束，决定了 212 个 C&Z predictor 里哪些
能进实验网格：

1. **只支持月度收益面板**（CRSP monthly `yyyymm`）。日频收益面板已在
   2026-07-31 被移除（`load_daily_msf`，见 `tests/test_daily_frequency.py`
   说明）——本来也不是瓶颈，C&Z 的 predictor 组合本身默认就是月度的
   （`Portfolio Period` 只控制再平衡间隔，不是收益频率；日频收益是他们
   另一个可选下载产品）。
2. **只实现分位数分组（quantile sort）**，不支持类别/阈值分组——`GroupType`
   文档字符串明确写着 `CATEGORICAL`/`THRESHOLD` 是已知的具体引擎能力缺口。

第 2 条恰好对应 SignalDoc 的 **`Cat.Form`** 字段（`continuous`/`discrete`），
`01_PortfolioFunction.R` 的分支处理证实这就是同一个区分：`continuous` 走
`single_sort`（分位数排序，我们引擎能做），`discrete` 走类别直接赋值
（`port = support 里的序号`，我们引擎做不了）。

### 筛选结果

| | `continuous`（单一连续信号，兼容） | `discrete`（类别型，已知缺口） |
|---|---|---|
| 212 个 Predictor 全体 | **179 (84%)** | 33 (16%) |
| HXZ∩C&Z 交集 (n=141) | **133 (94%)** | 8 (6%) |

👉 **绝大多数 C&Z predictor（含 HXZ 争论涉及的 141 个中的 94%）都是
"月度收益 + 单一连续信号"，与引擎能力完全匹配，不构成严重瓶颈。**

### 5 个候选因子里，`ConvDebt` 恰好落在例外的 6% 里

| 候选 | `Cat.Form` | 兼容？ |
|---|---|---|
| AssetGrowth / OrgCap / ResidualMomentum / BetaFP | continuous | ✅ |
| **ConvDebt** | **discrete** | ❌ 引擎已知缺口 |

这也**修正了 §10 里一处误判**：`ConvDebt` 的 `LS Quantile=NaN` 之前被归类为
"落默认值（C&Z 兜底成五分组）"——这是错的。真实原因是 `Cat.Form=discrete`：
C&Z 根本没在这个信号上做分位数排序，`LS Quantile` 是**不适用**，不是**兜底**。

### 一个意外但更有价值的发现：`ConvDebt` 暴露的是比 Q1 更底层的欠定性

我们自己那份人工标注的 `ConvDebt` MethodSpec 写着（`portfolio.sort`）：

```json
"group_type": "quantile", "n_groups": 5,
"source": {"quote": "five quantiles", ...}
```

**论文原文明确说"分成五个分位数"——一个连续变量的分位数排序。** 但 C&Z
（`Cat.Form=discrete`）把它实现成了一个**二元/类别指标**（有无可转换债务）。

这不是配置分歧（Q1），甚至不只是公式分歧（Q2）——这是**两个独立实现者对
"这个信号本身是什么类型"的分歧**：一个读成连续变量，一个读成离散指标。
这是我们框架能捕捉到的最强形式的论文欠定性之一。

**建议**：`ConvDebt` 不适合作为要跑完整 2×3 网格的候选（引擎做不了 C&Z 那边
的离散实现），但值得**单独作为一个不需要跑回测的案例**写进论文——只需对比
MethodSpec 与 SignalDoc 就足以说明问题。主网格的第 5 个候选，建议从
HXZ∩C&Z 交集里另选一个 `continuous` 因子替换。

## 10. `C_cz` 的可观测分辨率

| registry config 键 | SignalDoc 列 | 可映射? |
|---|---|---|
| `weighting_rule` | `Stock Weight` (EW/VW) | ✅ 干净 |
| `breakpoint_quantiles` | `LS Quantile` (0.1→10组, 0.2→5组) | ✅ 干净 |
| `breakpoint_source` | `Quantile Filter` (NYSE/空=全样本) | ✅（但 99% 是默认） |
| `rebalance_frequency` | `Portfolio Period` | ✅ 干净 |
| `universe` | `Filter`（自由文本 R 表达式，per-predictor 额外筛选） | ✅ 2026-08-22 已实现（`_parse_cz_filter_expr`，`src/infra/reference/__init__.py`）——覆盖 `field%in%c(...)`、`==`/`!=`/`<=`/`>=`/`<`/`>`、`abs(field)>N`（精确翻译成 `not_between`）这几类 SignalDoc 里实际出现的写法，逗号分隔的多条件按 AND 叠加在全局底座筛选之后。**实测覆盖率 76/78**（331 个 predictor 里有 78 个非空 `Filter`）；剩下 2 个（`Mom6mJunk`: `abs(prc)>5, me>me_nyse20`、`BetaBDLeverage`: `me > me_nyse10`）阈值是"相对 NYSE 分位断点"这种动态变量（`me_nyse20`/`me_nyse10`），不是字面数值，解析器目前不支持这类，查询②时会报 `CzFilterParseError`（422，人工可见），不会静默丢弃或猜错 |
| `universe_filters`（全局 shrcd/exchcd） | ❌ SignalDoc 无 → **从代码读**（`shrcd∈{10,11,12}`, `exchcd∈{1,2,3}`, `Signals/pyCode/SignalMasterTable.py`）| ✅ 间接，2026-08-16 已实现 |
| 样本期 | `SampleStartYear/EndYear` | ✅ 100% 覆盖 |
| formation 月 | `Start Month` | ✅ |
| `accounting_lag_months` | ❌ SignalDoc 无 → **从代码读**（=6） | ✅ 间接 |
| `missing_action` | ❌ SignalDoc 无 → **从代码读**（=drop） | ✅ 间接 |

### 212 个 Predictor 的落默认率

| 字段 | 记录 | 落默认 | 占比 | C&Z 默认值 |
|---|---|---|---|---|
| `Stock Weight` | 212 | 0 | 0% | EW |
| `Portfolio Period` | 211 | 1 | 0% | 1（月度） |
| `Start Month` | 211 | 1 | 0% | 6（六月） |
| `LS Quantile` | 130 | **82** | **39%** | 0.2（五分组） |
| `Quantile Filter` | **3** | **209** | **99%** | 全样本断点 |

> ⚠️ **重要限定 1**：SignalDoc 记录的是 **C&Z 的实现决定**，不是"论文原话"
> （证据：`Portfolio Period` 211/212 有值，但论文几乎不明说调仓频率 → 他们把
> 自己的判断也记成了值）。**因此"落默认率"只是欠定性的下界。**
>
> ⚠️ **重要限定 2**（2026-08-16 补充）：`LS Quantile` 的 82 个 NaN 里，一部分
> 并非"论文没钉死、C&Z 兜底成五分组"，而是 `Cat.Form=discrete`——**这个信号
> 根本不做分位数排序，`LS Quantile` 是不适用，不是默认值**（33 个 predictor
> 是 discrete，见 §9b 的 `ConvDebt` 例子）。真实的"分位数落默认"占比应该用
> `continuous` 子集重新算，39% 这个数字目前虚高。

### 全文最有力的单一事实

> **HXZ 与 C&Z 之争最核心的差异——NYSE 断点 vs 全样本断点——在 C&Z 这边，
> 99% 的因子是一个沉默的默认值，不是"论文这么说的"。**
>
> 这场争论的很大一部分是**两套 house convention 的对撞**，双方都不是"论文说的"。

## 11. 争议总体（HXZ ∩ C&Z，n=141）

`Docs/Comparison_to_MetaReplications.csv` 含 C&Z 做的元研究对照表
（HXZ 452 条 / GHZ 102 / MP 97），映射 HXZ 因子名 ↔ C&Z acronym ↔ `holdper`。

**141 个 C&Z Predictor 在 HXZ 中有对应 = 212 的 67%**，这就是争论真实存在的总体。

| | C&Z 实际 | HXZ 强制 |
|---|---|---|
| 加权 | **EW 122 (87%)** / VW 19 | 100% VW |
| 断点 | **全样本 138/141 (98%，兜底默认)** | 100% NYSE |
| 分组 | 49/141 (35%) 落默认（五分组） | 十分组 |
| 再平衡 | 年度 73 / 月度 61 | 月度 |

## 12. 候选因子（5 个，同时满足：有人工标注 + 在 HXZ∩C&Z + 有论文 PDF）

| 人工标注名 | C&Z acronym | 加权 | 分组 | 断点 | 再平衡 | 起始月 | 筛选 | 样本 | t 值 | C&Z 复现质量 |
|---|---|---|---|---|---|---|---|---|---|---|
| `AssetGrowth` | `AssetGrowth` | EW | 十分组 | 全样本 | 年度 | 6 | — | 68-03 | **8.45** | 1_good |
| `BlitzHuijMartens_ResidualMomentum` | `ResidualMomentum` | EW | 十分组 | 全样本 | 月度 | **12** | `abs(prc)>1` | 30-09 | 8.22 | 1_good |
| `FrazziniPedersen2014_BAB_US_Equity` | `BetaFP` | EW | 十分组 | 全样本 | 月度 | 6 | — | 29-12 | 7.12 | **3_distant** |
| `EisfeldtPapanikolaou2013_OMK` | `OrgCap` | **VW** | 五分组 | 全样本 | 年度 | 6 | — | 70-08 | **2.85** | 1_good |
| `Valta_..._ConvertibleDebt` | `ConvDebt` | EW | N/A（`Cat.Form=discrete`，非落默认，见 §9b） | 全样本 | 月度 | 6 | — | 85-12 | 4.50 | 1_good |

**这个组合的张力很好：**
- **OrgCap t=2.85** —— 唯一边缘因子，唯一 VW。最可能标准化下翻车 → Type II/IV 候选
- **BetaFP `3_distant`** —— **C&Z 自己标注其实现偏离原论文**，欠定性的自我承认 → Type III 候选
- **ConvDebt**：`Cat.Form=discrete`（C&Z 实现成二元指标），而我们人工标注的
  MethodSpec 显示论文原文是"五个连续分位数"——**信号类型本身的分歧**，比
  Q1/Q2 更底层，但**引擎做不了 discrete 分组**（见 §9b），不适合进主实验
  网格，建议单独作为案例研究、并从 HXZ∩C&Z 交集里另选一个 `continuous`
  因子填补第 5 个网格候选位
- **ResidualMomentum** —— 唯一有 universe 筛选、唯一 12 月起始
- **AssetGrowth t=8.45** —— 最强的，Type I 对照

> 注：`AnAngBaliCakici2013_*`（→ `dVolCall`/`dVolPut`/`dCPVolSpread`）是期权类，
> **不在 HXZ 中**，不适合作为候选。

## 13. 数据可得性

| 需要 | 状态 |
|---|---|
| **`N_cz`**（C&Z 多空月度收益，following OPs） | ✅ 官网现成 wide csv / 212 个单因子 csv（含各分组腿） |
| **firm-level 信号数值** | ✅ 209 个 wide 格式（1.6GB）或 `pip install openassetpricing` 取全部 212 |
| **标准化变体收益（AltPorts）** | ✅ VW/EW × 十/五分组、NYSE-only、ME>NYSE20pct |
| 论文 PDF | ✅ `data/papers/` 154 篇（文件名是标题，需手工映射到 acronym） |
| 论文文本缓存 | ⚠️ `data/paper_text_cache/` 只转换了 2 篇，需跑 `scripts/convert_papers_to_md.py` |
| 当前版本 | v2.0.0（2025-10），数据到 2024-12，信号已全部转 Python |

### ⚠️ 必须承认的一点：Q3 不能算我们的贡献

`30_PredictorAltPorts.R` 显示 C&Z **已经发布**了 `q_cut=0.1 + sweight='VW'`
（VW 十分组 = HXZ 协议核心）等变体。

- ❌ **"把 C&Z 信号放进 HXZ 协议看它死不死"——已经发表了，不能当贡献**
- ✅ **但它给了我们第二个校准锚**：引擎不仅要复现 C&Z baseline，还要复现其
  VW-decile 变体 → **在 config 轴上校准，而不只是单点校准**

| | 已被 C&Z 发表？ | 能否作为贡献 |
|---|---|---|
| **Q3 标准化敏感度** | ✅ 基本已发表 | ❌ 只作**校准与背景** |
| **Q1 协议欠定性** | ❌ 无人做过 | ✅ **唯一真正新颖的核心** |
| **Q2 公式欠定性** | ❌ 无人做过 | ✅ 新颖，但需下载 |

### 其它陷阱

- wide 格式 firm-level 信号是 **"signed so future mean returns increase"**
  ——已按预期方向翻过符号，比对论文符号前必须用 `SignalDoc.Sign` 还原
- 本地 `data/CZ code/` 的 SignalDoc 必须与下载的收益数据**同版本**，
  否则校准被静默污染

---

# Part III. 当前实现现状（快照，可能被重构）

> ⚠️ 以下描述的是 2026-08-16 时 `src/steps/step6_dual_track_controller/` 的样子。
> **step6 很可能按 Part I 的设计重构，届时本节即过时。**

## 14. 它现在是什么

多轨道批次编排器。给定一个已验证的 `PluginRecord` + 一份 resolved `MethodSpec`，
对每个 config override（"轨道"）跑一次 Step 5（build script → execute），
写出一份聚合的 `comparison.json`。不变量：跨轨道只有 config 变，代码永不变。

类名已从 `DualTrackController` 重命名为 **`MultiTrackController`**（2026-08-16）；
模块目录名 `step6_dual_track_controller` 暂保留（改目录名涉及导入路径）。

## 15. 两个入口，一套执行实现

- `run_experiment(plugin, spec, plan: ExperimentPlan, snapshot_id)` —— 遗留的
  Python 构造入口，现在是薄适配器（`_plan_to_matrix`）。
  **⚠️ 这是目前唯一被前端 UI 触发的生产路径**
  （`POST /api/sessions/{id}/steps/6/experiment`）。
- `run_from_matrix(...)` —— 声明式入口，读
  `experiments/<factor_id>.experiments.yaml`。
  **⚠️ 目前在 `backend/`、`app.py`、`scripts/` 中没有任何生产调用，只在测试里用。**

即：更严谨的 yaml 矩阵机制（校验、`experiment_spec_hash`、sweep、
`expected_diff` 交叉核对）对最终用户完全不可达。

## 16. 轨道类型

| 轨道 | 来源 |
|---|---|
| `original_method` | 无 override 基线 |
| `standardized_hxz` | 整包 `HXZ_STANDARD_CONFIG`（手工策展） |
| `ablation_*` | 单开关翻转，`_ABLATION_SWITCH_TO_CONFIG_KEY` |
| `factorial_*` | 2^n 笛卡尔积，去全 baseline 角，按名去重 |
| bridge 轨道 | `signal_input_ref: "cz_bridge[:factor_id]"` |
| sweep | 仅 yaml 路径，`_expand_sweep` |

## 17. 声明式矩阵的校验哲学（`experiment_spec.py`）

- `family` / `identification_level` / `resolved_diff` **一律派生，不允许 yaml 手写**。
  恰好 1 个 key 不同 → `controlled`；0 或 >1 → `unidentified`/拒绝
- 整个文件 load 时经 `registry.build_config` 校验，**一条坏实验让整个文件失败**
- no-op 实验（resolved config == baseline）load 时拒绝
- `expected_diff` 与真实 diff 交叉核对，捕捉"菜单 clamp 悄悄抵消了 override"
- `experiment_spec_hash` = 矩阵内容哈希，属运行身份的一部分
- 未实现（已明确记录）：`baseline_ref` 链式基线、`snapshot_ref` 数据 vintage

## 18. Auto-freeze（`_run_tracks_with_freeze`）

1. Pass 1：所有轨道跑，允许修复
2. 检查成功轨道的 code_hash 是否仍等于批次冻结哈希
3. 有漂移 → 取**第一个**漂移轨道的 plugin，整批重跑，**禁止修复**
   （`_NoRepairMetaCoder`，`llm_client=None`）
4. `max_refreeze_attempts` 默认 1
5. `len(track_specs) <= 1` 永不 refreeze（一致性是跨轨道属性）

默认参数下 `batch_invalidated=True` 只有传 `max_refreeze_attempts=0` 才触发。

## 19. Bridge 轨道（`_run_bridge_track`）

计算 C&Z 参考信号落盘 parquet，经
`build_script(..., precomputed_signal_path=...)` 注入，绕过 agent 的
`compute_signal` 但复用相同下游 config 与引擎。未注册 → 返回 `None` 记入
`skipped`，不算失败。不走 `RepairLoop`。`code_hash = "cz_bridge:<factor_id>"`，
`is_bridge_track=True`，被排除在跨轨道代码一致性检查外。

## 20. `_finalize_batch`

给每个 `RunRecord` 打 `experiment_batch_id` / `frozen_plugin_hash` /
`batch_invalidated` / `batch_invalidation_reason`；构建 `tracks_summary`；
经 `runner.write_comparison_summary` 写 `comparison.json`；可选调 step8
诊断器（best-effort）。

---

# Part IV. 现状与设计的差距

## 21. 阻塞 Part I 设计的实现缺口

| # | 缺口 | 阻塞什么 | 优先级 |
|---|---|---|---|
| 1 | **`C_cz` 不是可运行 config** —— `CZReferenceProfile` 只是从 SignalDoc 解析的元数据 dataclass，未映射到 `registry` 菜单键 | 第 ②⑤⑥ 列全部做不了，Q1 步骤 3、校准都不行 | **最高，Phase 1 前置** |
| 2 | **引擎未施加 C&Z 的 1 个月组合滞后**（`signal[, yyyymm := yyyymm + 1]`，§9）——2026-08-16 改判：这不是外部依赖项，是 `C_cz` 的定义组成部分，轨道 ② 依赖它，应做成 registry 菜单键 `formation_lag_months`（默认 0）而非硬编码开关 | 不加则轨道 ② 是虚构配置，且校准必然对不上（系统性偏差，对动量类因子尤甚） | **最高，Phase 1 前置**（原文误列为 Phase 2，已改） |
| 3 | **`N_cz` 未下载** | 校准 | 高 |
| 4 | **`cz_bridge` 是我们的转写而非 C&Z 数值** | Q2 被污染；且只有 3 个因子 | 高（Q2 才需要） |
| 5 | ~~`HXZ_STANDARD_CONFIG` 保真度~~ **已核实 2026-08-16**：`rebalance_frequency=annual` 是论文真实值；`accounting_lag_months=6` 逐字段核实后确认論文对年度会计变量本就隐含 ~6 个月滞后（与 FF 惯例同值,并非偷懒未改），lag 通道因此仍不会在①→③分解里出现差异——这不是遗留缺陷，是论文本身对这个场景的真实处理；universe 从纯装饰性字符串改为真正生效的 `exchcd`/`siccd`/`ceq`（经 Compustat join）过滤，这里才是新增的真实差异通道 | ~~Q3 归因的完整性~~ 已按论文实际内容重新评估 | ~~中~~ |
| 6 | **人工标注命名与 C&Z acronym 不一致**（纯命名问题，已确认因子都存在） | Q1 步骤 2 的三方比对 | 中 |
| 7 | **`interaction_effects` 从未被填充** | 事前预测里的交互效应估计 | 中 |
| 8 | **`data/paper_text_cache/` 只转了 2 篇** | agent 提取 | 低（跑脚本即可） |
| 9 | **候选因子 `ConvDebt` 的 `Cat.Form=discrete`，引擎不支持类别分组** | 5 个候选因子里有 1 个跑不了完整网格，需替换（见 §9b） | 中（可绕过：单独案例研究不跑回测） |

## 22. `cz_bridge` 的建议转向

> **从"复现 C&Z 的信号"改为"从 C&Z 代码提取其隐含配置选择"。**

理由：
- 读出"他们用了 6 个月 lag / 1 个月组合滞后 / drop 缺失"是**低风险**的离散事实，
  容易人工核验；重新实现整条公式并保证数值一致是**高风险**的
- 不受"公式够不够简单"限制，覆盖面能大幅扩展
- 把 `cz_bridge` 从主路线上的脆弱环节变成稳固的辅助工具
- 真正的 Z 臂应改为**下载 C&Z 的 firm-level 信号数值**（零转写）

## 23. step6 架构层面的设计推论

1. **每条轨道必须声明它在网格里的坐标**（signal_source × config_profile），
   而不是现在扁平的 track 名字。`original_method`/`standardized_hxz` 把
   "信号"和"配置"糊在了一起。
2. **对比应是一等公民，轨道是二等公民。** 现在输出"一堆轨道"，step7 再猜怎么
   配对。应该反过来：声明要做哪些**对比**，系统推导出需要跑哪些轨道——
   这样天然保证"每次只动一个轴"。
3. **`identification_level` 应从"差几个 config 键"升级为"在网格里移动了几个轴"。**
   现在只看 config diff，完全看不见 signal 轴——所以 bridge 轨道（换了信号轴！）
   直接被跳过了 family/identification 赋值，一条"既换信号又换 config"的实验
   不会被标成 unidentified。**这是真实漏洞。**
4. **校准实验应是每个因子的前置门槛**，而不是可选轨道。
5. **跨因子聚合只在标准化列合法。** C&Z 的协议是因子特异的，HXZ 的是统一的；
   论文列每个因子配置都不同，跨因子平均是把苹果和橘子平均。应系统强制或显式标注。

## 24. 遗留的实现级待决问题（来自原 plan.md）

1. **两个入口的长期归宿** —— `ExperimentPlan` 是唯一生产路径，yaml 矩阵无人调用。
   是让 UI 切到矩阵，还是把矩阵定位为"脚本化高级通道"并在文档中钉死？
2. **refreeze 仲裁武断** —— "选第一个漂移轨道的 plugin"在多轨道各自漂移时
   缺乏方法论依据。是否改成任何漂移直接判批次失败、交人工复核？
3. **`batch_invalidated` 默认不可达** —— 保留为保险，还是承认它只是文档？
4. **skipped 实验可见性** —— 矩阵声明 10 个只跑 4 个不会让批次报警，是否加阈值？
5. **模块目录名** `step6_dual_track_controller` 是否随类名一起改。

---

# Part V. 下一步

## Phase 1 前置项（工程量不小，非"零成本"，但无外部依赖）

1. 把 `C_cz` 做成可运行 config（缺口 #1，Phase 1 的 ②③ 需要）
2. 给引擎加 `formation_lag_months` registry 菜单键（默认 0，C&Z 档位=1，
   缺口 #2，2026-08-16 从 Phase 2 上移，理由见 §21 缺口 #2 及下方决定 D）
3. 修复 bridge 轨道绕过 `identification_by_track` 赋值的 bug（§23.3，
   与整体重构无关，现在就做，见下方决定 D）

## 离线、零成本，可与上面并行

4. 跑 `scripts/convert_papers_to_md.py` 转换候选因子的论文
5. 建立候选因子的 人工标注名 ↔ C&Z acronym 映射（手工）
6. 从 HXZ∩C&Z 交集的 `continuous` 子集里，另选一个因子替换 `ConvDebt`
   （§9b），补满 5 个可跑完整网格的候选
7. `C_agent` vs `C_cz` 字段级 diff（不跑回测，§4a）

## Phase 1 正式执行

8. 跑 ①②③ + 全组合归因（§4a/§4c）+ 每对轨道的配对显著性检验

## 需要外部依赖（Phase 2）

9. 下载 `openassetpricing` 数据（`N_cz` + AltPorts + firm-level 信号）
10. 先在单一因子（建议 AssetGrowth）上打通信号适配层（§4b 四条风险），
    并为符号约定、1 个月滞后对齐这两条静默出错风险写单测锁死（决定 B
    的附加条件）
11. 跑校准：⑤ vs `N_cz`，⑥ vs AltPorts/`N_hxz`
12. 校准通过后，跑 Phase 2 其余因子：④⑥ + 对照臂 OAT（§4b）

## 仅在字段数 >5 时触发（§4c 的 OAT 退回路径）

13. 用 OAT 筛出贡献最大的 2–3 个字段，补跑小规模全组合，其余字段固定，
    诚实报告未做完整交互分解

## 25. 已拍板的决定（2026-08-16）

**A. Q3 降级为"校准与背景"，不算贡献 —— 接受。**
C&Z 的 `30_PredictorAltPorts.R` 已发布 VW-十分组等标准化变体的收益数字
（§13），把它包装成贡献会被一句话否掉。③⑥ 两条轨道照跑，但只用于
(a) 校准引擎（⑥ 应对上 AltPorts 已发表数字）(b) 差距量级的背景参考。
论文叙事重心从"参与 HXZ vs C&Z 之争"移到 Q1（协议欠定性，见 §13 表格，
唯一未被人做过的核心）。

**B. `cz_bridge` 从"复现 C&Z 信号"转向"提取 C&Z 的隐含配置事实" —— 接受，
附加条件：适配层必须补单测。**
现状 `cz_bridge` 是我们对 C&Z 公式的重写，只覆盖 3 个因子，且一旦跑不对，
无法区分是"两个实现者真的不同"还是"我们抄错了"（§22）。改为读取
低风险的离散事实（会计滞后=6、组合滞后=1、缺失值处理=drop），覆盖面
扩展到全部 212 个因子；真正的 Z 臂改为直接下载 firm-level 信号数值，
零转写。附加条件：§4b 列的适配层 4 条风险里，符号约定（wide 格式已翻
方向）和 1 个月滞后对齐属于**静默出错**类型，必须写单测锁死，否则只是
把风险从"我们的转写"搬到了"我们的适配"。

**C. `HXZ_STANDARD_CONFIG` 的 lag 缺陷 —— 原判定"降级表述、不做忠实修正"
已推翻,同一天晚些时候改为真正核实每个字段。**
最初判定：`accounting_lag_months=6` 恰好等于 C&Z 惯例（§9），导致 lag 通道
在①→③分解里永远不出现差异；投入产出比差，決定只降级表述为"HXZ-style"、
全文改名 `C_hxz` → `C_std`，不追求忠实复现。**推翻原因**：实际读取本仓库
自带的论文 PDF（`docs/Hou 等 - 2020 - Replicating Anomalies.pdf`）逐字段核实
后确认：论文明确写了年度会计变量用 6 月分组、7 月至次年 6 月持有
（`rebalance_frequency="annual"`, `holding_period_months=12`）——这条是真的
遗留问题，已修。但 `accounting_lag_months` 核实后**维持 6 不变**：论文对
"非盈利季度数据"确实写了"4 个月滞后"，但那一段说的是按季重分组的场景
（`rebalance_frequency="monthly"`），不是这里用的 `annual`——论文对年度会计
变量本身从未给出显式滞后月数，只隐含了 12 月财年末到 6 月分组之间与 FF 相同
的 ~6 个月滞后，所以这里恰好和 `original_method` 自己的 `SENSIBLE_DEFAULTS`
同值，lag 通道并不会因此在①→③分解里产生差异（不是缺陷，是论文本身如此）。
真正新增的差异通道是 `universe`：论文明确写"NYSE, Amex, and NASDAQ stocks"
+ "We exclude financial firms" + "firms with negative book equity"（同一句
一般样本准则），已在 `data/reference/hxz_standard_config.yaml` 落地为真正
生效的 `universe_filters`（`exchcd`/`siccd`/`ceq`）；此前的
`universe: "<描述字符串>"` 从未被引擎读取过，是纯装饰性文字。`ceq`
（Compustat 普通股权益，不是论文别处用的完整 book equity 瀑布公式）经
`universe_filter_join_sources` 由生成脚本 point-in-time join 上去，复用
`compute_signal` 输入本就用的同一套 Compustat 拼接机制，未改动引擎。
`C_std` 改名保留（`C_hxz` 这个记号不再使用）。`missing_action` 字段同时
删除：引擎无条件丢弃缺失收益行，从不读这个 config 值，写它纯属摆设。

**D. step6 是否按 §23 整体重构 —— 方向接受，但现在不做；唯一例外是
bridge 轨道 identification 漏洞，现在就修。**
`C_cz` 目前还不可运行（缺口 #1），没有一条真实 Phase 1 数字能驱动重构，
现在做 §23.1/23.2（网格坐标 + 对比为一等公民）大概率是对着想象的需求
过度设计。例外：§23.3 指出的 bridge 轨道绕过 `identification_by_track`
赋值是已确认的真实 bug（一条同时换信号轴和 config 轴的实验不会被标
`unidentified`），成本低、与"整体重构"无关，列入 Phase 1 前置项现在
就修。缺口 #2（组合滞后）借这次机会一并做成 registry 菜单键
`formation_lag_months`，理由见 §21 缺口 #2 的改判。执行顺序：
`C_cz` 可运行 → `formation_lag_months` 菜单键 → 修 bridge bug →
跑 Phase 1 → 用真实数字驱动 §23 重构。
