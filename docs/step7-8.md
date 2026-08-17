# Step 7–8 —— 实现现状与待定事项

> 讨论稿，配合 `docs/step6.md`（研究设计的权威来源，尤其 §4a/§4c 的归因方法论
> 与 §21 缺口清单）一起读。本文件只覆盖 step7（`ReplicationDiff`/`bundle.py`）
> 和 step8（LLM 辅助解释层）这两步，2026-08-17 建仓，用于讨论怎么做，不代表
> 已拍板的决定。

---

## 0. 两步各自的角色（不要混）

- **step7**（`src/steps/step7_replication_diff/`）—— 纯确定性计算层。输入是
  已经跑完的 `RunRecord` 列表（每条轨道的 config + metrics），输出是
  `comparison.json` 里的 `config_diff`/`gap_decomposition`/`derived`/
  `bridge_comparison` 等区块。**不含任何 LLM 调用**，是终态报告，不是反馈
  循环触发器（`docs/decision-log.md`）。
- **step8**（`src/steps/step8_diagnosis/`）—— 可选的 LLM 辅助解释层，**只读**
  step7 已经写好的 `comparison.json`，只负责挑措辞/归因叙述，不允许写任何
  数字（`render.py` 的确定性渲染器从 bundle 里重新插入每个数字），且每类
  claim 必须引用 `CLAIM_EVIDENCE_REQUIREMENTS` 规定形状的证据。step8 完全
  关闭时，报告必须能可复现地生成同一份结果。

**关键约束**：step8 的可信度上限由 step7 决定——step7 算错/算漏的东西，
step8 没有办法、也没有权限去补救或猜测。所以下面按"先让 step7 的数字站得住
脚，再谈 step8 怎么引用"的顺序讨论。

---

## Part I. step7 现状

### 1. `ReplicationDiffResult`（`__init__.py`）当前长什么样

```python
factor_id, original_tstat, standardized_tstat, total_gap
contributions: dict[str, float]        # 目前只由 t_stat 差值算出
interaction_effects: dict[str, float]  # 声明了，从未被任何代码写入
explained_fraction, residual
```

`ReplicationDiff.diff_ablation(runs)`：
- 找 `original_method`/`standardized_hxz` 两条轨道算 `total_gap`（**在
  t_stat 上做减法**）
- 找所有 `track.startswith("ablation_")` 的轨道，逐个算
  `original_tstat - run.t_stat`，存进 `contributions`
- `residual = total_gap - sum(contributions)`，`explained_fraction`

### 2. `bundle.py` 在 step7 之上叠加的东西

- `build_track_vs_paper` / `classify_overall`：单轨道 vs 论文自报数字的
  确定性比较（sign/ratio/significance），产出 `overall_tag`
- `build_config_diff`：baseline-vs-each 的 config 逐键 diff（不是全体两两
  diff，避免 ablation 轨道一多就组合爆炸）
- `build_gap_decomposition`：直接包一层 `diff_ablation` 的结果，`available`
  完全取决于有没有 `contributions`
- `build_spec_quality`/`build_menu_deviations`：读 MethodSpec review 结果、
  `defaults_applied`，跟归因数学无关，运行良好
- `build_bridge_comparison`：bridge 轨道 vs 配对轨道各自的 `vs_paper`，判断
  谁复现了论文符号——这块逻辑独立，不受下面几条问题影响

### 3. 已确认的具体问题（2026-08-17 讨论中发现，均可在真实 `comparison.json`
中复现）

#### 3.1 `contributions`/`gap_decomposition` 只认 `ablation_` 前缀

`step6` 的 `MultiTrackController`（`_factorial_track_specs`）现在**默认**
按 `docs/step6.md` §4a 的策略产出 `factorial_*`/`cz_factorial_*` 轨道
（<=5 个差异字段时的全组合路径），但 `diff_ablation` 里这一行：

```python
ablation_runs = [r for r in runs if r.track.startswith("ablation_")]
```

完全不认 `factorial_`/`cz_factorial_` 前缀。实测（`runs/backtest_scripts/
results/099f6e1136bd316c/comparison.json`）：8 个 `factorial_*` 轨道全部
执行成功、metrics 齐全，但 `gap_decomposition.available == false`，理由
写着 `"no ablation_* tracks executed"`——**这是假阴性，证据其实已经落盘,
只是这一行没读到**。

#### 3.2 归因目前在 `t_stat` 上做减法，`docs/step6.md` §4a 已经否决了这种做法

`t = μ / (σ/√N)` 是比值，不具有可加性；`contributions`/`explained_fraction`/
`residual` 现在全部构建在 t_stat 之上,这正是 §4a 那次方法论修订要纠正的
问题（原先的加法归因例子就是因为在 t 值上做被推翻的）。好消息是所需的
输入（`mean_return`）其实已经在每条轨道的 metrics 里（`RunMetrics.
mean_return`,之前误以为是 `None`，实际字段名不同，数据本身早已存在）。

#### 3.3 `interaction_effects` 从未被填充

字段声明了 (`default_factory=dict`)，全文件搜不到任何赋值。§4c 描述的
"每个字段在其余字段所有取值下的平均效应"这套全组合计算完全没有对应函数。

#### 3.4 `paired_test`/`t_channel_decomposition` 未实现

`CHANGELOG.md` 自己写明"Proposed new `ReplicationDiffResult` fields
`paired_test` and `t_channel_decomposition` (not yet implemented in code)"。
需要的输入（月度收益序列本身 vs 只有汇总 `mean_return`/`t_stat`/`n_months`）
是个更大的问题——见下面 §5"数据可得性缺口"。

#### 3.5 OAT 路径的"起点依赖"警告目前没有代码层面的保护

`docs/step6.md` 指出 OAT 有"固定基线"vs"累积路径"两种做法，结果依赖顺序；
现在 `_ABLATION_SWITCH_TO_CONFIG_KEY`/`diff_ablation` 只实现了固定基线一种，
这本身没问题（也是 §4a 建议的做法），但代码里没有任何地方**显式声明**"这是
固定基线 OAT，非可加",`bundle.py` 的 `OAT_INTERACTION_CAVEAT` 字符串算是
一种文档化,但只在 OAT 路径触发,全组合路径目前完全不可达（见 3.1），所以
这条警示语从未真正需要过。

---

## Part II. step8 现状（不受上面问题直接阻塞，但下游会变准）

### 4. 已经做得比较完整的部分

- 证据白名单机制（`flatten()` 产出的 `evidence_keys`，claim 只能引用其中的
  key）
- `CLAIM_EVIDENCE_REQUIREMENTS`/`REASON_LAYER_BY_CLAIM_TYPE`/
  `IDENTIFICATION_BY_CLAIM_TYPE`：按 claim 类型强制要求的证据形状、
  `identification_level`、`evidence_strength` 全部由代码派生，不给 LLM
  authored 的机会
- 拒绝循环（`MAX_DIAGNOSIS_ROUNDS=2`）：round 1 起草，round 2 只重提被拒的
  claim 并附拒绝理由，不重问已通过的
- 确定性渲染器 `render.py`：所有数字从 bundle 里插入，LLM 输出的是模板占位

### 5. step8 会被 step7 的问题拖累在哪

- `bundle.gap_decomposition.available == False` 时，`step8` 里
  `IDENTIFICATION_BY_CLAIM_TYPE`/`_SWITCH_FROM_CONTRIBUTION_KEY` 相关的
  attribution 类 claim 直接没有证据可引用——**不是 step8 的 bug，是
  上游证据缺失的必然传导**，修 3.1 之后这类 claim 才有机会被生成
- 一旦 `interaction_effects`（3.3）真正被填充，`step8` 的 prompt/
  `CLAIM_EVIDENCE_REQUIREMENTS` 需要新增一类"交互效应"claim 的证据契约,
  现在完全没有这个 claim type
- `paired_test`（3.4）填充后，`step8` 的"significance"claim 目前引用的是
  单轨道 `t_stat_significant`（论文 vs 单一轨道），需要新增一种"两轨道差值
  是否显著"的 claim 类型和对应证据契约

---

## Part III. 待讨论的问题（不是结论，需要一起定）

### Q1. 归因量纲：t_stat 要不要保留、怎么保留（2026-08-17 讨论后确定方向）

**结论：mean_return 和 t_stat 是两个独立产出，都要，互不替代，不存在"切换/
丢弃"。**

- `contributions`/`interaction_effects`（主效应 + 全部两两交互，见 Q3）
  **只在 `mean_return` 上做**——这是唯一具有可加性的量纲，§4a 已经论证
  过 t_stat 不行。对应原选项 A：`total_gap`/`contributions`/`residual`
  改成基于 `mean_return`，全组合路径下 `residual` 恒为 0。
- t_stat **不通过加法归因保留，而是通过恒等式保留**：`t_channel_
  decomposition`（Q4/Q5 已在规划）对每条轨道相对 baseline 算
  `log t = log μ − log σ + ½ log N` 的三通道拆分——这本身就是 t_stat 的
  归因，只是不是加法形式，是精确恒等式，不需要可加性假设。两块产出各自
  独立成一个 evidence 区块（`gap_decomposition`（μ）vs
  `t_channel_decomposition`（t）），`step8` 分别引用，不合并成一套字段
  以免语义混淆。
- 原选项 B（μ/t 两套平行字段共存在同一个 `contributions` 结构里）**不
  采用**——两种量纲数学性质不同（可加 vs 恒等式），塞进同一个字典反而
  让消费方分不清"这个数字能不能跨行相加"，分成两个顶层区块更清楚。

### Q2. `factorial_*` 消费方式（2026-08-17 已定：方案 B，不改轨道命名逻辑）

**结论：`RunRecord` 新增 `switches_flipped: dict[str, Any] | None` 字段，
step7 直接读这个字段，完全不解析轨道名字**（曾短暂考虑过"从名字反解析"，
已否决——字符串解析不可靠，命名规则改一次就可能解析错误或解析失败，不
接受这个技术债）。

- **不需要碰 `_factorial_track_specs`/轨道命名规则本身**——找到了更干净
  的数据来源：`ExperimentSpec.resolved_diff`（`experiment_spec.py` 的
  `_resolved_diff()`）**已经在给每一条轨道**（无论来自 factorial、
  ablation、sweep 还是 yaml 手写）算一份 config-key 级别的差异
  `{config_key: {baseline_value, track_value}}`，专门用来派生
  `identification_level`，算完就被扔了，从没存到 `RunRecord` 上。
- 只需要：把 `_ABLATION_SWITCH_TO_CONFIG_KEY`（`step6_dual_track_
  controller/__init__.py`，`breakpoint`/`weighting`/`lag`/`missing`/
  `rebalance`/`universe` 六个开关名 -> config key）反转成
  `config_key -> switch_name`，在 `run_from_matrix` 里对每个
  `exp in matrix.experiments` 用这个反转表过滤 `exp.resolved_diff`，得到
  `{switch_name: track_value}`，存进一个 `switches_by_track: dict[str,
  dict]` 局部变量。这跟现有的 `identification_by_track` 是同一个模式——
  同一个循环、同一种"事后按 `run.track` 回填"写法，`run_from_matrix` 已经
  在用这招给 `run.logs` 追加 `family`/`identification_level` 那几行，照着
  抄一遍逻辑，不是新写一套机制。
- 好处：**任何路径产生的轨道都自动覆盖**——不止 factorial/ablation，连
  yaml 手写的 `config_overrides`、以后可能新增的实验生成方式，只要改了六
  个已知开关里的某个 config key，`switches_flipped` 就会自动填上，完全不
  依赖轨道叫什么名字，命名规则改多少次都不受影响。

### Q3. `interaction_effects` 输出形状（2026-08-17 已定：全部两两交互）

**结论：字段数不管多少，都输出全部两两交互项**（不做"只留合并残差"的
简化），比如 3 个字段（`weighting`/`breakpoint`/`universe`）会有
`weighting_x_breakpoint`/`weighting_x_universe`/`breakpoint_x_universe`
三个 key，都摊平进 `evidence_keys`（如 `interaction_effects.
weighting_x_breakpoint`），供 step8 引用具体的交互假设（比如 §8 预注册的
weighting×breakpoint 假设）。

- 代价：字段数一旦增多，两两交互组合数会变多（C(n,2)），但 §4c 规定超过
  `MAX_FACTORIAL_SWITCHES`（现改为 4，见 Part V）差异字段时退回 OAT（不
  做全组合，也就不存在这个交互表），所以全组合路径本身已经把 n 限制在
  <=4，两两交互最多 C(4,2)=6 项，可控。
- 三阶及以上的交互（比如 `weighting × breakpoint × universe` 三者同时的
  联合效应）**不单独输出**——全组合的"主效应 - 全部两两交互 = 剩余残差"
  天然就是三阶及以上交互的合并残差，不需要再拆分，"精确加总到总差距为 0"
  这一保证不受影响。

### Q4. `paired_test` 需要月度收益序列，但目前 `RunMetrics` 只存汇总统计量

- `paired_test`（配对差值序列的 mean/t/Newey-West）**需要两条轨道的完整
  月度收益时间序列**，不是现在 `RunMetrics` 里的 `mean_return`/`t_stat`/
  `n_months` 几个标量。roadmap.md 的 Phase A1 提到"持久化完整的信号/收益
  中间产物"目前还没做（"complete signal/return/intermediate artifact
  persistence...no evidence-store hashing/provenance yet"）。
- 需要决定：是现在就把每条轨道的月度收益序列存下来（哪怕只在
  `runs/evidence/` 临时存一份，不追求完整 provenance），还是先實現一个
  "轻量版"——重新跑一次两条轨道对应的脚本、在内存里拿到序列、算完就扔，
  不落盘。后者更快能验证方法论，但每次要重新算一遍，不可审计、不可复用。

### Q5. `t_channel_decomposition` 的 σ 反解在 μ<0 时无定义，怎么降级

- §4a 已经预料到这个问题（"μ<0 时对数无定义，退回报绝对差并单独标注"），
  需要定下：这个降级路径的具体输出形状是什么（比如
  `t_channel_decomposition.degenerate: true` + 一个单独的绝对差字段），
  以及 step8 的 claim 契约要不要区分"正常对数分解"和"降级绝对差"两种
  证据强度。

### Q6. step8 的新 claim 类型什么时候加

- 建议顺序：先把 Q1-Q5 的 step7 数字填对、跑通、有真实 `comparison.json`
  验证过，再回头给 step8 加"交互效应"、"配对显著性"这两类新 claim——避免
  跟 §23 重构同样的"对着还不存在的数字设计 prompt 契约"的问题。

### Q7. 显著性门槛：HXZ 论文实际用的是三级门槛，不是单一 1.96（2026-08-17，讨论中新增）

已核实 `docs/Hou 等 - 2020 - Replicating Anomalies.pdf` 原文："a, b, and c
indicate absolute t-values exceeding the thresholds of **1.96, 2.78, and
3.39**, respectively"——这是 Harvey-Liu-Zhu (2016) 多重检验调整的标准三级
门槛（因子测试得越多，需要的显著性门槛越高）。现在 `bundle.py` 只有一个
二元 `SIGNIFICANCE_T_THRESHOLD = 1.96`（`paper_significant`/
`track_significant`/`significance_agrees` 都是布尔值）。

待讨论：
- 是否要把 `significance_agrees` 这种布尔判定换成三档标签
  （`not_significant`/`significant_1.96`/`significant_2.78`/
  `significant_3.39`），还是新增一个平行字段，保留现有布尔字段不破坏
  `step8`/前端已有的消费方
- 三级门槛该套用在哪些地方：只用于"论文 vs 单轨道"的 `build_track_vs_paper`，
  还是也要用于归因里"这个字段的贡献是否显著"（跟 `paired_test`/Q4 的
  显著性检验是两件不同的事，要不要统一到同一套门槛常量）
- 只是记录讨论，暂不实现（用户 2026-08-17 明确要求"先不做"）

**2026-08-17 后续讨论，已定**：`paper_significant`/`track_significant`/
`significance_agrees` 这三个既有布尔字段**保留不动**（避免破坏 `step8`/
前端已有的消费方），新增两个平行的整数分档字段 `paper_significance_tier`/
`track_significance_tier`（取值 0/1/2/3，对应"不显著/过 1.96/过 2.78/过
3.39"），用一个新的 `_significance_tier(t)` 辅助函数计算。仍然**只用于
`build_track_vs_paper`**（论文 vs 单轨道），不套用到 `paired_test`/
`joint_test` 的显著性判断上——这是两件独立的事，配对/联合检验用的是它们
自己的检验统计量和 p 值，不复用这套 t 值门槛。

**2026-08-17 测试影响核查后修正**：`SIGNIFICANCE_T_THRESHOLD = 1.96`
**原样保留，不改名、不改类型**——`tests/test_replication_diagnosis.py`
直接 `from ...bundle import SIGNIFICANCE_T_THRESHOLD` 并断言
`vs["significance_threshold"] == SIGNIFICANCE_T_THRESHOLD`，改动这个常量
本身会让这个测试真实报错（不是假设风险，是核查测试代码后确认的）。三级
门槛改用**全新的独立常量** `SIGNIFICANCE_T_THRESHOLDS = (1.96, 2.78,
3.39)`，`_significance_tier()` 用这个新常量算，不碰旧常量。

### Q8. 更好的对比/可视化方法（2026-08-17，讨论中新增，暂不实现）

候选方向（配合现有/计划中的数据结构）：
- **森林图**：每条轨道一行，t-stat 点 + Q7 的三条门槛竖线，一眼看出每条
  轨道落在哪一档
- **瀑布图**：① → ③ 的总差距，按 §4c 全组合分解拆成"主效应们 + 交互项 +
  残差"逐段叠加，比 `contributions` 表格直观，尤其适合展示 Q3 的交互项
- **配对差值时间序列图**：`paired_test`（Q4）做出来后，两条轨道逐月收益
  差值的滚动均值/累积和，能看出差距是全程稳定还是某段时间突变
- **config diff 热力图**：轨道 × config key 矩阵，按 `stage_of` 分组上色，
  直接对应 `build_config_diff` 现有输出，改动量最小、可以最先做
- 待讨论：这些图是加进 `app.py`/`frontend/`（面向人看的探索性视图）还是
  只是分析脚本产出（面向论文写作），两者的实现成本和维护责任不一样

---

## Part IV. 建议的落地顺序（讨论用，未拍板）

1. **Q2 最小修法**：先让 `diff_ablation`/`build_gap_decomposition` 认
   `factorial_`/`cz_factorial_` 前缀（哪怕先按"当成单开关 OAT 一样减",
   不做真正的平均效应），至少让你已经跑出来的真实数据不再被完全丢弃，
   验证链路先打通。
2. **Q1**：把归因量纲切到 `mean_return`，同时决定字段并存/替换的方案。
3. **Q2 完整版**：轨道名 -> 开关子集解析（或 schema 显式记录），做真正的
   全组合平均效应计算，`interaction_effects` 按 Q3 的形状填充。
4. **Q4/Q5**：视是否已经有真实待验证的 μ<0 因子或需要 paired_test 的场景
   而定优先级，不阻塞 1-3。
5. **Q6**：最后再动 step8 的 claim 契约。

---

## Part V. 文献综述后确定要做的三件事（2026-08-17）

用户提供的文献综述（Menkveld et al. 2024 "Nonstandard Errors"、Soebhag et al.
2024、Ledoit-Wolf 2008、Simonsohn et al. 2020 等，详见对话记录）之后，确定
**先在 step7 里实现这三个方法，用 AssetGrowth 真实数据验证过可行**：

1. **Shapley 值分解**（μ 上，替代/补充 Q3 的两两交互方案，顺序无关）
2. **配对 Newey-West 显著性检验**（单开关效应是否显著，不只是"观察到不同"）
3. **联合 Wald 检验**（多个开关加在一起是否显著解释了差距，防止只挑最大的
   一个开关下结论——类似 ANOVA 的整体 F 检验先于事后两两比较）

### `MAX_FACTORIAL_SWITCHES` 从 5 改成 4（2026-08-17，讨论后决定）

`src/steps/step6_dual_track_controller/__init__.py` 里的
`MAX_FACTORIAL_SWITCHES = 5` 改成 **4**——全组合成本从 $2^5=32$ 次回测降到
$2^4=16$ 次，超过 4 个差异字段就退回 OAT（`ablation_*`/`cz_ablation_*`）。
这个常量同时也是 Shapley 分解"能不能算"的门槛（Shapley 需要凑齐 $2^n$ 个
格子，`compute_shapley_effects` 里"完整性检查"的 n 上限应该跟这个常量
保持一致，不要各写各的、以后改一个忘了改另一个）。**这一条先记录决定，
代码还没改**（后面 todo 里补一项）。

**已用真实数据验证**（`runs/backtest_scripts/results/099f6e1136bd316c/`，
AssetGrowth，universe/weighting/breakpoint 三个开关）：
- Shapley：`weighting` 贡献总差距的 96%（−0.005645/−0.005895），跟 §8 预
  注册的"weighting × breakpoint 共同主导"基本吻合；跟文档 §4c 原有的"对
  其余开关取均匀平均"方法比（−0.005658）数值接近但不相等——Shapley 按子集
  大小加权（1/3、1/6、1/6、1/3），朴素平均是均匀权重（各 1/4），交互强的
  时候两者会给出不同排序。
- 配对检验：`original_method` vs `factorial_weighting`，取两条轨道
  `metrics.by_sample_period.insamp` 共同的 432 个月（**已确认月度收益序列
  已经落盘**，`results_dir/<track>.csv`，`yyyymm`/`ls_return` 两列，不需要
  额外持久化工作），差值序列 Newey-West（6 阶滞后）：mean diff=0.00702/月，
  t=2.74，显著。
- 联合 Wald 检验：3 个开关各自的"baseline − 单开关翻转"对比序列，构造
  3×3 的 HAC 协方差矩阵（含交叉项，因为三条对比序列共享 baseline、月份高
  度重叠，不独立），Wald 统计量 21.62（df=3），p≈0.00008——三者联合显著。

### 实现计划

**新文件 `src/steps/step7_replication_diff/attribution.py`**（跟 `bundle.py`
平级，同样是纯计算，不含 LLM 调用）：

- `compute_shapley_effects(tracks: dict[str, dict], baseline_track="original_method") -> dict`：
  每条轨道的 `switches_flipped`（现在从 `tracks[name]["switches_flipped"]`
  读，`_finalize_batch` 需要把 `RunRecord.switches_flipped` 顺手也塞进
  `tracks_summary`，跟现有的 `"config"`/`"metrics"`/`"is_bridge_track"`
  三个 key 平级）汇总出全部涉及的开关集合 N；**必须凑齐 2^|N| 个格子**
  （baseline + 每个非空子集恰好一条轨道，按 `switches_flipped` 的 key 集合
  精确匹配子集，不是按名字模糊匹配）才计算，否则返回 `{"available":
  False, "reason": "incomplete factorial grid, missing subsets: [...]"}`
  （明确列出缺哪些，不是笼统说不可用）；凑齐了就用标准 Shapley 公式在
  `mean_return` 上算，`identification_level="controlled"`（对应
  `diagnosis.py` 文档字符串里已经预留的这一档）。
- `_load_insample_series(results_dir: Path, track: str, start: int | None, end: int | None) -> pd.Series | None`：
  读 `results_dir / f"{track}.csv"`（`write_comparison_summary` 已经算出
  `results_dir = self.scripts_path / "results" / _spec_factor_id(spec)`，
  这个路径需要新传给 `build_evidence_bundle`），按 `sample_start_year`/
  `sample_end_year`（从 baseline 轨道的 resolved config 里取）过滤到
  in-sample 窗口。文件不存在时返回 `None`（旧批次/测试用的假轨道没有
- `_load_insample_series(results_dir: Path, track: str, start: int | None, end: int | None) -> pd.Series | None`：
  读 `results_dir / f"{track}.csv"`（`write_comparison_summary` 已经算出
  `results_dir = self.scripts_path / "results" / _spec_factor_id(spec)`，
  这个路径需要新传给 `build_evidence_bundle`），按 `sample_start_year`/
  `sample_end_year`（从 baseline 轨道的 resolved config 里取）过滤到
  in-sample 窗口。文件不存在时返回 `None`（旧批次/测试用的假轨道没有
  `.csv`，不能让整个 bundle 崩溃）。
- `paired_switch_significance(results_dir, tracks, baseline_track="original_method", lags=6) -> dict`：
  对每条 `switches_flipped` 恰好 1 个键的轨道（覆盖 `ablation_*` 和
  factorial 网格里的单开关角，判断标准是字典长度而不是名字），取跟
  baseline 的共同 in-sample 月份，算差值序列的 Newey-West mean/t，输出
  `{"available": True/False, "per_switch": {switch: {mean_diff, t_stat,
  n_overlap_months}}}`。
- `joint_switch_wald_test(results_dir, tracks, switches, baseline_track="original_method", lags=6) -> dict`：
  复用 `paired_switch_significance` 已经加载的对比序列，构造 3×n（或 k×n）
  矩阵、算含交叉项的 HAC 协方差矩阵、`scipy.stats.chi2` 求 p 值，输出
  `{"available": True/False, "wald_stat", "df", "p_value"}`。

**`bundle.py`/`build_evidence_bundle` 的改动**：新增 `results_dir: Path |
None = None` 形参（`write_comparison_summary` 已经有这个路径,顺手传进
来），内部调用上面三个函数，产出三个新的顶层 key：`shapley_attribution`/
`paired_tests`/`joint_test`，全部摊平进 `evidence_keys`，供 step8 引用。
任何一步的前置条件不满足（没有 `results_dir`、CSV 缺失、格子不全）都必须
返回 `"available": False` + 具体 `reason`，不能静默跳过或报虚假的 0。

### 前端改动（同一轮做，不是后续步骤）

现状（见上一轮讨论）：[frontend/src/components/StepOutputView.tsx](frontend/src/components/StepOutputView.tsx)
的 `step === 7` 分支只读了 `derived`/`gap_decomposition`/`config_diff`
三个 key，`GapWaterfallChart` 在 `gap_decomposition.available=false` 时
显示"No gap decomposition available"这句具有误导性的空态（数据其实存在,
只是没算）。这轮要在同一个分支里新增三块渲染，全部走已有的
`bundle.<new_key>.available` 判断（`available=false` 时显示具体 `reason`
文本，不是笼统的空态）：

- **Shapley 归因表**：新组件（或扩展 `GapWaterfallChart`，让它同时能读
  `shapley_attribution.shapley_effects` 和旧的 `gap_decomposition.
  contributions` 两种数据源）——柱状图，每个开关一根柱子，tooltip 显示
  `identification_level: controlled`。
- **配对检验结果**：`paired_tests.per_switch` 每个开关一行，显示
  `mean_diff`/`t_stat`/`n_overlap_months`，t 值超过 1.96 高亮。
- **联合检验结果**：`joint_test` 一行文字（`wald_stat`/`df`/`p_value`），
  当 `p_value >= 0.05` 时要有醒目提示——**这是给人看的门槛**：联合检验不
  显著时，上面 Shapley 归因表的数字仍然显示，但应该弱化/加警示样式，提醒
  "单个开关的归因数字缺乏联合显著性支撑"（呼应 §Part V 里"联合检验当
  gap_attribution 前置门槛"的设计，UI 层面先做视觉提示，不必等 step8 的
  claim 契约改完）。

不需要新建路由/页面——复用 `step === 7` 这同一个分支，三块新内容加在
`GapWaterfallChart`/`DiffView` 之间即可。

**范围声明**：这一轮做这三个方法的后端计算 **+ 对应的前端展示**；Q3 原定的
"全部两两交互"表格、Q5 的 `t_channel_decomposition`、step8 的 claim 契约
改动（新增 `shapley_effects.`/`paired_test.`/`joint_test.` 证据前缀、把联合
检验当 `gap_attribution` 的前置门槛）都是后续步骤，本轮不动。

## Part VI. 生产环境发现的歧义 bug + 按对比线拆分（2026-08-17）

真实跑了一次批次后发现：同一批次里同时存在 ①→②（`cz_factorial_*`）和
①→③（`factorial_*`）两条对比线时，两条线各自"只翻了 universe 这一个开关"
的轨道（`factorial_universe` vs `cz_factorial_universe`）会在
`switches_flipped` 层面撞名——它们的 key 集合都只有 `{"universe"}`，只是
目标值不同。

**第一步修复（止损）**：`compute_shapley_effects` 本来就会拒绝这种歧义
（"ambiguous, refusing to pick one"）；但 `paired_switch_significance`/
`joint_switch_wald_test` 当时是用普通字典 `single_switch_tracks[switch] =
name` 收集映射，**同一个 key 被赋值两次会静默覆盖**，导致联合检验用的
`universe` 到底来自哪条线,取决于 Python 字典遍历顺序,不可复现。修成
`_single_switch_track_map` 返回 `(resolved, ambiguous)`，歧义的开关一律
报告、排除，不再静默选一个。

**第二步修复（根治）**：止损版本会让"有歧义就丢掉这个开关"，损失掉这个
开关在两条线里各自的证据。真正的根源是"两条对比线的轨道被塞进同一次
计算"，不是"检测歧义的逻辑不够聪明"。新增
`attribution.split_tracks_by_comparison_line(tracks, baseline_track)`，
在调用三个函数**之前**就把批次拆成 `to_hxz`/`to_cz` 两组（复用现有的
`cz_` 前缀命名——这是已经存在、承重的命名区分，不是新发明的脆弱解析），
`bundle.build_shapley_and_significance` 对每条线各跑一次，输出嵌套一层：

```json
{
  "shapley_attribution": {"to_hxz": {...}, "to_cz": {...}},
  "paired_tests": {"to_hxz": {...}, "to_cz": {...}},
  "joint_test": {"to_hxz": {...}, "to_cz": {...}}
}
```

只有一条线时只有一个 key（大多数 session 没设 `cz_config_override`，只有
①→③）；一条线都没有时（没有任何 factorial/ablation 轨道）保持原来的扁平
`{"available": false, ...}` 形状不变。

前端 `Step7Output.tsx` 新增 `linesOf()` 归一化函数，识别嵌套/扁平两种
形状，每条线渲染成一个独立的带边框区块，标注"① → ② (C&Z actual
config)"/"① → ③ (HXZ standardized config)"。`AttributionPanel.tsx` 的三个
组件本身不用改，只是现在按线调用，不再是按批次调用一次。

**讨论并明确拒绝的第三条线**：②→③（C&Z config 直接对 HXZ config）需要
全新的 baseline（②本身）和重新跑一批全组合轨道，不属于项目声明的核心贡献
（Q1，§25 决定A），现有①→②/①→③ 的结果已经能大致拼出"C&Z 和 HXZ 在哪些
开关上选择不同"这个信息，性价比不够，明确不做。

## Part VII. 基于真实数据的结论示例（2026-08-17，逐条确认后再考虑并入 step8）

用真实跑出来的 AssetGrowth 批次（`runs/backtest_scripts/results/099f6e1136bd316c/`，
Part VI 修复之后重跑）的 `comparison.json` 数字，逐条验证"不靠 step8，光看
step7 的确定性数字，能安全下什么结论"——每条都跟用户逐一确认过是否合理，
只有确认过的才会考虑写进 step8 的 claim 类型。

### 示例 1（已确认）：`overall_tag` 必须用论文自己的样本区间对比，不能用全历史

**发现的 bug**：`build_track_vs_paper`（进而 `derived.overall_tag`）之前拿
`paper_reported`（论文自己样本区间上报的数字，见
`_spec_paper_reported`：直接来自 `spec.paper.reported_results`）去对比我们
track 的**全历史**指标（`RunMetrics` 顶层的 `mean_return`/`t_stat`，覆盖
到发表后几十年，882 个月），而不是同一个样本区间上的数字
（`by_sample_period.insamp`，432 个月）——两个数字的计算窗口根本不一样,
是苹果对橙子的对比。

`by_sample_period` 三段的定义（`src/infra/backtest_engine/__init__.py`
`_sample_period_metrics`）：
- `insamp`：`sample_start_year <= year <= sample_end_year`（论文自己声称
  研究的区间——**唯一跟 `paper_reported` 的计算窗口一致的一段**）
- `between`：`sample_end_year < year <= publication_year`（样本结束到发表
  之间的空档期）
- `postpub`：`year > publication_year`（发表后的样本外数据——这是
  `build_publication_decay` 单独回答"效应有没有衰减"用的，不该跟"有没有
  复现"这个结论混在一起）

**修复**：`bundle.py` 新增 `_in_sample_metrics()`，`derived.tracks[*].vs_paper`
现在优先用 `insamp`，没配置 `sample_start_year`/`sample_end_year` 时才退回
全历史（不影响没配置这两个字段的旧 run）。

**真实影响**（AssetGrowth, `original_method` track, `runs/backtest_scripts/results/099f6e1136bd316c/comparison.json`，
用户在此修复落地后于 2026-08-17 13:xx 实际重跑 step6 生成，磁盘上验证过，
不是预演数字）：

| | 修复前（全历史 882 月，磁盘旧文件） | 修复后（论文样本区间 432 月，磁盘当前文件） |
|---|---|---|
| track alpha_ff3 | 0.00988 | 0.01475 |
| track alpha_ff3 t 值 | 6.01 | 6.16（`t_stat_comparable=false`：论文报的是 alpha 的 t 值，这里目前存的是原始价差的 t 值，两者不可比，代码里没有硬比） |
| abs_spread_ratio | 1.41 | **2.107** |
| `overall_tag` | `close_replication` | `sign_agrees_magnitude_differs` |

`CLOSE_REPLICATION_RATIO_BAND = (0.5, 2.0)` —— 2.107 只是刚好超出上界
（超出约 5.3%），是边界案例，不是差很远。

**结论文字**："基线（`original_method`）在论文自己的样本区间内，方向和
论文一致（FF3 alpha 都为正）、双方都在最严格档（|t|>3.39）显著；但量级是
论文的 2.11 倍，刚好超出 `close_replication` 判定的 2 倍上界——不能说
完全贴近复现，但也不是差很远，是个边界情况，不宜简单二分为'成功/失败'。"

### 示例 2（已确认）：Shapley 归因 —— 每个 switch 各贡献了多少 gap

**背景**：①→③ 这条线（baseline `original_method` vs `standardized_hxz`），
weighting/breakpoint/universe 三个 switch 同时变了，`total_gap` = 标准化后
的效应 - 原始方法的效应，Shapley 值把这个总差距公平拆给每个 switch。

**真实数字**（同一份重跑后的文件，`shapley_attribution.to_hxz`）：

```
total_gap = -0.005895

weighting  贡献 = -0.005645  (占 96%)
breakpoint 贡献 = -0.001828  (占 31%)
universe   贡献 = +0.001578  (占 -27%，方向相反)

三者相加 = -0.005895 == total_gap  ✓（Shapley 效率性质，精确相等）
```

**结论文字**："把方法从论文原始设定换成 HXZ 标准化设定后，效应变小了
（gap=-0.0059）。其中 `weighting`（加权方式）单独就能解释 96% 的变化，是
最主要的驱动因素；`breakpoint`（分组断点）贡献了 31%；`universe`（样本
过滤）其实是反方向的，本来会让效应变大，但被前两者压过去了。三个贡献值
精确相加等于总差距——这是 Shapley 值的数学性质（efficiency property），
不是巧合或估算误差。"

### 示例 3（已确认）：配对显著性检验 —— 哪些 switch 的效应是真的，哪些可能是噪音

**真实数字**（同一份重跑后的文件，`paired_tests.to_hxz`，Newey-West t 检验，
432 个月重叠样本）：

```
universe:   mean_diff = -0.000207 (每月), t = -0.52  → 不显著（|t|<1.96）
weighting:  mean_diff = +0.007020 (每月), t = +2.74  → 显著
breakpoint: mean_diff = +0.003634 (每月), t = +4.15  → 显著
```

**结论文字**："三个 switch 里，`weighting` 和 `breakpoint` 各自单独的效应
都是统计上可信的（分别 t=2.74、t=4.15，都超过 1.96 门槛）；但 `universe`
的效应（t=-0.52）统计上跟零没有区别——即使示例 2 的 Shapley 归因给了它
-27% 的贡献占比，这个占比本身不能被当作'universe 这个改动确实有影响'的
证据，因为这个数字的不确定性太大，可能就是噪音。'Shapley 有非零贡献'
和'这个贡献统计上可信'是两回事，必须分开看。"

### 示例 4（已确认）：联合检验 —— 这几个 switch 加起来是不是真的说明问题，还是巧合

**真实数字**（同一份重跑后的文件，`joint_test`）：

```
①→③ 这条线：wald_stat=21.62, df=3, p_value=0.0000784  → 高度显著
①→②这条线：unavailable —— "需要至少2个single-switch track才能做联合检验，这里只有1个"
```

**结论文字**："①→③ 这条线的联合检验高度显著（p < 0.0001）——三个 switch
加在一起绝对不是巧合凑出来的，确实共同解释了这个 gap。这是关键的'守门'
结论：正因为联合检验通过了，示例 2/3 里对 `weighting`/`breakpoint` 的单独
归因才站得住脚，不是从多个候选里挑了个看起来最大的凑数（多重比较陷阱）。
①→②这条线因为只有 1 个 switch，联合检验本来就不适用（'联合'需要至少 2
个对象）——这不是 bug，是设计上的合理限制，这种情况下只能看示例 3 那种
单个 switch 的配对检验。"






