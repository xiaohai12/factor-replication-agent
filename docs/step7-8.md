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
（**2026-08-17 已实现**，见 CHANGELOG "step7: implemented Q5's
`t_channel_decomposition`"）

- §4a 已经预料到这个问题（"μ<0 时对数无定义，退回报绝对差并单独标注"），
  需要定下：这个降级路径的具体输出形状是什么（比如
  `t_channel_decomposition.degenerate: true` + 一个单独的绝对差字段），
  以及 step8 的 claim 契约要不要区分"正常对数分解"和"降级绝对差"两种
  证据强度。
- **已定/已实现**：`build_t_channel_decomposition(tracks, baseline)`
  （`src/steps/step7_replication_diff/bundle.py`），baseline-vs-each（跟
  `build_config_diff` 同一个组织方式，不是按 switch/comparison-line 分组）。
  每条非 baseline 轨道 `degenerate: false` 时带 `log_t_ratio`/
  `channels.{mean_return,volatility,sample_size}`/`channel_sum_check`（三个
  channel 精确加总到 `log_t_ratio`，恒等式，没有残差）/`implied_sigma`；
  `degenerate: true` 时只有 `reason` + `t_stat_abs_delta`（`|t_track| -
  |t_baseline|`）。降级条件比"μ<0"更精确：baseline 或 track 的
  `mean_return` 只要**不是都严格 > 0** 就降级（不是"同号就行"——单独的
  `log(mean_return)` 在个体为负时就没定义，即使比值是正的），另外
  `t_stat`/`n_months` 缺失或非正、或 `t_stat`/`mean_return` 符号不一致
  （反解出的隐含 σ 会是负数）也降级。已挂进 `build_evidence_bundle`（新
  顶层 key `t_channel_decomposition`，自动摊平进 `evidence_keys`）。
  **没做**：对应的 step8 claim type（沿用 Q6 的顺序，这次先只做 step7
  侧；`gap_attribution_shapley`/`switch_significance`/
  `joint_attribution_support` 三个新 claim type 的先例已经证明这个模式
  跑得通，后续需要时照抄即可）。7 个新测试
  （`TestTChannelDecomposition`，覆盖精确恒等式、纯 N 变化隔离、μ<0 降级、
  异号降级、缺字段降级、无轨道、bundle 接线）。

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

### Q8. 更好的对比/可视化方法（2026-08-17，讨论中新增；**森林图 + config
diff 热力图已实现**，见 CHANGELOG "frontend: Q8 ForestPlot +
ConfigDiffHeatmap"——其余两个候选仍未做）

候选方向（配合现有/计划中的数据结构）：
- **森林图**（**已实现**：`AttributionPanel.tsx::ForestPlot`，接在
  `Step7Output.tsx` 的 `overall_tag` 徽章下面）：每条轨道一行，t-stat 点 +
  Q7 的三条门槛竖线（正负各一条，共 6 条参考线），一眼看出每条轨道落在
  哪一档；纯读 `derived.tracks[*].vs_paper.track_raw_t_stat`/
  `track_significance_tier`，不需要新的后端计算或额外请求。
- **瀑布图**：① → ③ 的总差距，按 §4c 全组合分解拆成"主效应们 + 交互项 +
  残差"逐段叠加，比 `contributions` 表格直观——**未实现**；现在 Shapley
  归因表（`ShapleyAttributionTable`）已经是柱状图形式，是否还需要专门再做
  一个瀑布图版本待定，优先级较低。
- **配对差值时间序列图**：`paired_test`（Q4）做出来后，两条轨道逐月收益
  差值的滚动均值/累积和，能看出差距是全程稳定还是某段时间突变——**未
  实现，明确的范围限制**：`Step7Output.tsx` 现在只接收 `bundle` 这一个
  prop，没有 `sessionId`/`run_id`，画这张图需要按 track 名找到对应
  `run_id`（`fetchRuns()`/`useStep6Runs` 那一套，`Step6Output.tsx` 已经在
  用）再 `fetchReturnSeries` 拉月度收益序列、按月份对齐两条序列算差值——
  这是一次结构性改动（`Step7Output` 需要新增 `sessionId` prop 并接入新的
  查询），没有在这轮跟着森林图/热力图一起顺手做，风险和改动量都明显更大，
  留作独立任务。
- **config diff 热力图**（**已实现**：`AttributionPanel.tsx::
  ConfigDiffHeatmap`，接在 Step7Output 的"Compare against baseline"
  复选框上面）：轨道 × config key 矩阵，按 `stage_of` 分组上色（hover 显示
  `baseline_value → track_value`），直接对应 `build_config_diff` 现有
  输出，是这几个候选里改动量最小的，已确认最先做。
- 待讨论：这些图是加进 `app.py`/`frontend/`（面向人看的探索性视图）还是
  只是分析脚本产出（面向论文写作），两者的实现成本和维护责任不一样——
  已实现的两个都加在了 `frontend/`（`Step7Output.tsx`），跟现有 Shapley/
  配对检验/联合检验组件同一个消费路径。

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

### 示例 5（已确认）：①→②这条线本身 —— universe 是两个独立实现者唯一的
分歧点，且统计上是临界的

**背景**：`AGENTS.md` 定义的研究核心是"agent vs C&Z 的一致程度"（①→②），
不是①→③——前四个例子全部围绕①→③，这个例子单独把①→②当结论讲。

**真实过滤条件差异**（同一份 `comparison.json`，`config_diff`；C&Z 侧见
`src/infra/reference/__init__.py::cz_profile_to_config_override`，不是
猜测/编造的）：

```
我们(agent, original_method) universe_filters:
  siccd not_between [6000,6999]   （排除金融股）

C&Z(cz_actual_config) universe_filters:
  shrcd in [10,11,12]             （普通股）
  exchcd in [1,2,3]               （纽交所/美交所/纳斯达克上市）
```

**真实数字**（`paired_tests.to_cz.universe`，432 个月重叠样本）：

```
mean_diff = +0.000874/月 (≈ +1.05%/年), t = 1.781, n = 432
```

`joint_test.to_cz`：`available=false`（"只有 1 个 single-switch track，
联合检验至少需要 2 个"）——①→②这条线目前没有可供交叉验证的第二个 switch，
这本身就是"两个独立实现者分歧很小"的证据，不是数据缺口。

**结论文字**："同一篇论文，我们的 agent 和 C&Z（一个独立的人工复现）在
universe 过滤条件上做出了不同的选择——C&Z 用的是'普通股 + 纽交所/美交所/
纳斯达克上市'这套 CRSP 口径的通用过滤，我们只排除了金融股（按 SIC code）。
这个实现差异带来的月度收益差距是 +0.00087（约年化 1.05%），**统计上处于
临界状态**（t=1.78，略低于 1.96 的门槛）——不能斩钉截铁地说这个差异是'真
的'，但也没法完全忽略。这正是项目要研究的核心问题的一个具体样本：论文里
对'样本筛选'的描述可能不够精确，导致两个独立的、都认真读了论文的实现者，
在这一个维度上做出了不完全一致的选择；但相比①→③里三个 switch 同时不同
（示例 2-4），①→②这条线的分歧要小得多——只有一个维度不同，且这个维度
的效应本身没有达到统计显著。'inter-implementer agreement 高、但实现选择
仍有一处临界分歧'，是目前这一个因子上能给出的最准确概括。"

**注意**：目前只有 AssetGrowth 一个因子验证过这条线；universe 恰好是唯一
分歧点，可能是这篇论文的特例（论文对 universe 的描述本来就比其他维度更
模糊），不能直接推广成"C&Z 和 agent 通常只在 universe 上分歧"——需要更多
因子的①→②数据才能验证这是不是普遍模式。

### 示例 6（已确认）：样本外衰减（`publication_decay`）—— universe 这个
switch 恰好是①→③里唯一不衰减的，跟①→②的结论连起来看

**背景**：`build_publication_decay` 已经在跑（`bundle.py`），比较每条轨道
`insamp`（论文样本区间）vs `postpub`（发表后）两段的 t 值，`decayed`=
样本内显著但样本外不显著。这个区块此前没有出现在任何一个结论示例里。

**真实数字**（同一份 `comparison.json`，`publication_decay.tracks`）：

```
                          insamp_t   postpub_t   decayed
standardized_hxz            3.60       -0.54        是
cz_actual_config             7.11        2.29        否
factorial_universe           7.45        2.84        否
factorial_weighting           4.10        0.14        是
factorial_breakpoint          6.62        1.80        是
factorial_weighting_universe  4.09       -0.09        是
factorial_breakpoint_universe 7.52        2.83        否
```

**结论文字**："在①→③的三个单开关轨道里，只翻 `universe` 的轨道
（`factorial_universe`）是唯一一个样本外（发表后）依然显著的（t=2.84）；
只翻 `weighting`/`breakpoint` 的轨道样本外都衰减到不显著。换句话说，
`weighting`/`breakpoint` 虽然在示例 2/3 里对样本内的效应量/显著性贡献
最大，但这两个改动换来的效应主要是样本内的，出了论文自己的研究窗口就
站不住；`universe` 单独看效应量小（示例 2 里贡献只有 -27%，示例 3 里配对
检验也不显著），但恰恰是这个维度让效应在样本外活得下来。连到示例 5：
①→②这条线里，agent 和 C&Z 唯一的分歧点正好就是 universe——如果这个
'universe 决定样本外稳健性'的模式在更多因子上也成立，那意味着两个独立
实现者在这一篇论文上的分歧,恰好落在对样本外稳健性最关键、但对样本内
效应量贡献最小的那个维度上，是个值得在报告里明确讨论的巧合（或非巧合，
需要更多因子验证）。"

**注意**：`robustness_summary`/`bridge_comparison` 这批次都是
`available: false`（分别缺 `ablation_*` 轨道、缺 `cz_bridge` 轨道）——
不是算错，只是这批次没跑那类轨道，暂不纳入报告。

---

## Part VIII. step8 claim 契约扩展设计（承接 Q6，2026-08-17，设计稿；
**2026-08-17 后续已实现**，见 CHANGELOG 同日 "step8: implemented Part VIII's
3 new claim types"、"`render.py`: deterministic sentence templates" 两条——
`ClaimType`/5 张表/`comparison_line`/entailment/joint-test 降级/3 个 bundle
tool/`render.py` 三个模板全部落地，有 12 个新测试覆盖；前端渲染 Part IX 才做）

Part VII 示例 2/3/4/5 用到的 `shapley_attribution`/`paired_tests`/
`joint_test` 三个新区块已经摊平进 `evidence_keys`（`bundle.py` 早就做了），
但 `src/infra/models/diagnosis.py` 的 `ClaimType`/`CLAIM_EVIDENCE_
REQUIREMENTS` 等表还没有认识这三个区块——step8 现在**引用不了**它们。
本节把"加什么"钉死成可以直接照做的表，`publication_decay`（示例 6）不在
这次改动范围内，因为它对应的 `publication_decay` claim type 早就存在且
证据形状没变，示例 6 直接能用现有契约生成。

### 8.1 新增一个字段：`comparison_line`

Part VI 把三个区块按对比线嵌套成 `{"to_hxz": {...}, "to_cz": {...}}`（只有
一条线时只有一个 key）。现有 `DiagnosisClaim.subject_track` 只能定位到
"哪条轨道"，定位不到"哪条对比线"——`paired_tests.to_cz.per_switch.universe`
和 `paired_tests.to_hxz.per_switch.universe` 是两个不同的证据,不能靠
`subject_track` 区分（两者的 subject_track 概念也不一样：这三个区块本来
就是"按 switch"而不是"按 track"组织的）。

新增 `DiagnosisClaim.comparison_line: Literal["to_hxz", "to_cz"] | None`，
派生方式完全照抄 `subject_track` 现有的模式（`_cited_tracks`/
`_subject_track_reason`）：

```python
_LINE_FROM_NESTED_KEY = re.compile(
    r"^(?:shapley_attribution|paired_tests|joint_test)\.([^.]+)\."
)

def _cited_lines(keys: list[str]) -> set[str]:
    lines = set()
    for k in keys:
        m = _LINE_FROM_NESTED_KEY.match(k)
        if m:
            lines.add(m.group(1))
    return lines
```

`_subject_track_reason` 的姊妹函数 `_comparison_line_reason`：cited_lines
为空则跳过（非嵌套证据）；只有一条线时允许不声明；声明了但对不上就拒绝；
引用了两条线又没声明就拒绝。三个新 claim type（8.2）在 `_derive_claim_
fields` 里自动回填 `comparison_line`（同一条线只有一个候选值时），跟
`subject_track` 的回填逻辑完全一致，不是新机制。

### 8.2 新增三个 claim type

| claim_type | 引用前缀 (`CLAIM_EVIDENCE_REQUIREMENTS`) | 必须包含的子串 (`CLAIM_EVIDENCE_SUBSTRINGS`) | 允许的 relation | `reason_layer` |
|---|---|---|---|---|
| `gap_attribution_shapley` | `shapley_attribution.` | `shapley_effects` | `associated_change` | `config_sensitivity` |
| `switch_significance` | `paired_tests.` | `t_stat`（不是 `mean_diff`，强制引用统计量而非只引用效应量） | `significant` / `insignificant` | `config_sensitivity` |
| `joint_attribution_support` | `joint_test.` | `p_value` | `significant` / `insignificant` | `config_sensitivity` |

不复用现有的 `gap_attribution`/`significance` 两个 claim type，原因跟 Q1
决定"μ/t 两块证据分开成两个顶层 key、不混进同一个字典"是同一个道理——
`gap_attribution` 现在的证据形状是 OAT 的 `gap_decomposition.
contributions.*`（≤2 个轨道时用，或 >4 个差异字段退回 OAT 时用），跟
Shapley 的证据形状/identification 语义不同，混用会让"这个 claim 到底
identification_level 多高"变得含糊；`significance` 现在锚定的是
`derived.tracks.*.track_significant`（论文 vs 单轨道），跟"某个 switch 的
配对效应是否显著"是两个不同问题，Q7 决定时已经明确说了"两件独立的事,不
复用同一套门槛常量"，claim type 层面延续这个原则。

### 8.3 entailment 检查（`_entailment_reason` 新增三个分支）

阈值判断照抄现有 `_n_months_mismatch_reason` 的先例——在 step8 里内联算,
不需要 `bundle.py` 先预计算好布尔值再传过来（`gap_attribution` 的 n_months
比例检查就是这么做的，不是每个派生判断都要求 step7 先算出一个布尔字段）。

```python
JOINT_TEST_ALPHA = 0.05  # 跟 GAP_ATTRIBUTION_N_MONTHS_RATIO_THRESHOLD 同级的模块常量

elif claim_type == "gap_attribution_shapley":
    effect_key = next((k for k in keys if ".shapley_effects." in k), None)
    if effect_key is None:
        return "gap_attribution_shapley must cite a shapley_attribution.<line>.shapley_effects.<switch> value"
    # 联合检验守门（呼应前端 ShapleyAttributionTable 的 dim+badge 设计，Part V）：
    # 不拒绝这个 claim，但如果同一条线的 joint_test 已经跑出来且不显著，
    # 强制 evidence_strength 降到 low —— 在 _derive_claim_fields 里做，见 8.4。

elif claim_type == "switch_significance":
    t_key = next((k for k in keys if k.endswith(".t_stat") and ".per_switch." in k), None)
    if t_key is None:
        return "switch_significance must cite a paired_tests.<line>.per_switch.<switch>.t_stat value"
    t = evidence_keys.get(t_key)
    if t is None:
        return "switch_significance's cited t_stat is null; cite evidence_limitation instead"
    expected = "significant" if abs(t) >= SIGNIFICANCE_T_THRESHOLD else "insignificant"
    if relation != expected:
        return f"relation {relation!r} contradicts the cited t_stat value ({t!r})"

elif claim_type == "joint_attribution_support":
    p_key = next((k for k in keys if k.endswith(".p_value")), None)
    if p_key is None:
        return "joint_attribution_support must cite a joint_test.<line>.p_value value"
    p = evidence_keys.get(p_key)
    if p is None:
        return "joint_attribution_support's cited p_value is null; cite evidence_limitation instead"
    expected = "significant" if p < JOINT_TEST_ALPHA else "insignificant"
    if relation != expected:
        return f"relation {relation!r} contradicts the cited p_value ({p!r})"
```

`SIGNIFICANCE_T_THRESHOLD` 直接从 `bundle.py` 复用（`step8_diagnosis/
__init__.py` 已经 `from ...bundle import CLOSE_REPLICATION_RATIO_BAND,
stage_of`，加一个名字到同一行 import 即可，不是新依赖）——**不**用 Q7 的
三级门槛（`SIGNIFICANCE_T_THRESHOLDS`），因为 Q7 那三级门槛明确只用于
"论文 vs 单轨道"（`build_track_vs_paper`），`switch_significance` 判断的
是"两条轨道的配对差值"，跟论文自报数字无关,延续 Q7 自己定的边界。

### 8.4 identification_level / evidence_strength 派生（`_derive_claim_fields` 新增分支）

```python
elif claim_type == "gap_attribution_shapley":
    switch = re.search(r"\.shapley_effects\.([^.]+)$", next(k for k in keys if ".shapley_effects." in k)).group(1)
    identification_level = evidence_keys.get(f"shapley_attribution.{comparison_line}.identification_level") or "controlled"
    # 联合检验守门：同一条线的 joint_test 存在且不显著时，实证强度封顶 low，
    # 不管 shapley 本身的 identification_level 多"controlled"——呼应 Part V
    # 前端 ShapleyAttributionTable 的 dim+badge 设计，在这里做成数据层面的
    # 强制降级，而不是只在 UI 视觉上弱化。
    joint_significant = evidence_keys.get(f"joint_test.{comparison_line}.p_value")
    if joint_significant is not None and joint_significant >= JOINT_TEST_ALPHA:
        evidence_strength = "low"
    else:
        evidence_strength = EVIDENCE_STRENGTH_BY_IDENTIFICATION.get(identification_level, "low")

elif claim_type == "switch_significance":
    identification_level = "harmonized"  # 单开关配对轨道，跟 ablation_* 同一识别层级，不随 line 变化

elif claim_type == "joint_attribution_support":
    identification_level = "harmonized"  # Wald 检验不要求全组合网格齐全（跟 Shapley 不同），只是"harmonized"而非"controlled"
```

`switch_significance`/`joint_attribution_support` 的 identification_level
是静态常量（不像 `gap_attribution_shapley` 那样动态读 bundle），原因写在
代码注释里了：配对检验/联合检验的"能不能算"跟"网格是否齐全"无关（只要有
≥1 / ≥2 个单开关轨道就行），不享有 Shapley 那种"全组合网格保证" 的
`controlled` 级别。

### 8.5 需要改的文件清单（这次只是设计，未动手）

- `src/infra/models/diagnosis.py`：`ClaimType` 加 3 个值，`DiagnosisClaim`
  加 `comparison_line` 字段，5 张表（`CLAIM_EVIDENCE_REQUIREMENTS`/
  `CLAIM_EVIDENCE_SUBSTRINGS`/`CLAIM_RELATIONS`/`REASON_LAYER_BY_CLAIM_TYPE`/
  `IDENTIFICATION_BY_CLAIM_TYPE`）各加 3 行。
- `src/steps/step8_diagnosis/__init__.py`：`_entailment_reason`/
  `_derive_claim_fields` 各加 3 个分支（8.3/8.4）；`_cited_lines`/
  `_comparison_line_reason`（8.1）；新增 3 个 `_bundle_section_tool(...)`
  调用（`shapley_attribution`/`paired_tests`/`joint_test`，跟现有
  `PUBLICATION_DECAY_TOOL`/`ROBUSTNESS_SUMMARY_TOOL` 同一模式，加进
  `STEP8_TOOLS` 列表）；新增 `JOINT_TEST_ALPHA` 模块常量；`SIGNIFICANCE_
  T_THRESHOLD` 加进已有的 bundle import 行。
- `prompts/analysis/replication_diagnosis.md`：新增这三个 claim type 的
  说明段落 + JSON 示例（含 `comparison_line` 字段怎么填），并说明"只有一条
  对比线时可以省略 `comparison_line`"这条规则；补一句"`switch_significance`
  的显著与否只看这一个 switch 自己的配对检验，`gap_attribution_shapley`
  的强度会被同一条线的联合检验自动打折"，帮助 LLM 理解为什么同一个
  switch 在 Shapley claim 和 significance claim 里可能呈现不同的
  `evidence_strength`。
- 新测试（`tests/test_step8_diagnosis.py` 或同名测试文件，具体位置以现有
  文件为准）：3 个新 claim type 的 accept/reject 用例（含引用错误 line 的
  拒绝用例、`comparison_line` 两条线都引用但未声明的拒绝用例、joint_test
  不显著时 `gap_attribution_shapley` 的 `evidence_strength` 降级用例、
  `t_stat`/`p_value` 为 null 时退回 `evidence_limitation` 的用例）。

### 8.6 明确不做的事（避免范围蔓延）

- **不**给 `publication_decay` claim type 做任何改动——示例 6 已经能用
  现有契约生成，Part VI 的 to_hxz/to_cz 嵌套没有影响到
  `publication_decay`（它本来就是按 track 不按 line 组织的，见 Part VII
  示例 6 的数据形状）。
- **不**做 Q3 的"全部两两交互"表（Part V 已经决定用 Shapley 代替）、
  **不**做 Q5 的 `t_channel_decomposition`（仍然待 Q5 自己拍板降级形状后
  再谈对应 claim type）。
- **不**在这一轮改 `render.py` 的确定性渲染模板之外的东西——`render.py`
  只需要给这三个新 claim type 各加一个模板（从 `evidence_keys` 里重新插入
  `shapley_effects`/`t_stat`/`p_value` 的数字），不需要改现有模板。

---

## Part IX. step8 分层展示设计（承接 Part VIII，2026-08-17，方向已定：方案
B + 选项 1 + 分两轮；**后端 + 前端均已实现，已知限制也已补上**，见 CHANGELOG
同日 "step8: implemented Part IX's backend"、"frontend: layered step8 UI"、
"step8/frontend: `rendered_sentence` per claim" 三条——`analysis_stage`/
`DiagnosisSummary`/`build_deterministic_summary`/`render.py` 按 stage 分组 +
`## Summary` 区块、`frontend/src/components/steps/Step8Output.tsx` 的分层
折叠 UI，以及 `report_to_jsonable` 把 `render.py::deterministic_sentence`
算出的句子塞进 `diagnosis.json` 供前端直接展示（不再是 LLM 原始 `text`），
全部落地；13 个后端测试 + 前端 tsc/oxlint 清洁验证）

Part VIII 解决的是"step8 认不认识新证据"；这一节解决"认识了之后，叙事和 UI
怎么组织"——用户明确要求"分析1/分析2/分析3 + 总结分析"这种分层结构，UI 也
要分层显示。跟用户讨论后确定的方向：

- **分层方案：方案 B**（按"分析依赖链"分层，不是直接套用现成的三值
  `ReasonLayer`）。`ReasonLayer`（`config_sensitivity`/`signal_fidelity`/
  `temporal_pattern`）继续保留、含义不变——它管的是"这是配置敏感性问题 /
  信号保真度问题 / 时间模式问题"这个更粗的分类，新加的层是在
  `config_sensitivity` 这个大类内部再细分叙事顺序。
- **总结：选项 1**（确定性 rollup，不新增 LLM 自由文本层，不引入新的
  "claim 之上再一层 claim" 信任面）。
- **落地顺序：分两轮**——第一轮先做 Part VIII（新 claim type 能被引用），
  第二轮再做本节的分层渲染。本节现在只是设计，不跟 Part VIII 一起动手。

### 9.1 四层的定义

新增 `DiagnosisClaim.analysis_stage: Literal["per_switch", "joint_gate",
"vs_paper", "auxiliary"] | None`，从 `claim_type` 静态映射（跟 `reason_
layer` 的推导方式一样，不是 LLM authored）：

| `analysis_stage` | 包含的 claim_type | 回答的问题 |
|---|---|---|
| `per_switch`（分析 1） | `switch_significance`、`gap_attribution_shapley` | 每个 switch 单独看，效应量多大、这个效应本身是不是噪音 |
| `joint_gate`（分析 2） | `joint_attribution_support` | 这些 switch 合起来是不是真的解释了差距，而不是"挑了个看起来最大的" |
| `vs_paper`（分析 3） | `sign_agreement`、`magnitude_gap`、`significance`、`config_divergence` | 跟论文本身比，复现了没有——不需要 switch 级别证据，独立于分析 1/2 |
| `auxiliary`（附加层） | `publication_decay`、`signal_reproducibility`、`implementation_robustness`、`evidence_limitation` | 正交的补充信息（样本外衰减、bridge 信号一致性、鲁棒性），不参与分析 1→2 的依赖链 |

`gap_attribution` （旧的、仅 OAT 场景用的 claim type）跟着它引用的
`gap_decomposition` 是不是来自 shapley-完整网格走：有 `switches_flipped`
完整网格时优先产出 `gap_attribution_shapley`（进 `per_switch`），否则退回
`gap_attribution`（>4 个差异字段的 OAT 情形）——这种情况下没有
`joint_gate` 可用（`joint_switch_wald_test` 需要 ≥2 个 single-switch
track，`ablation_*` 满足这个条件，所以其实 OAT 场景一样能有 `joint_gate`
分析，不是只有 factorial 网格才有；只有 `gap_attribution_shapley`
本身需要网格完整）——所以 `gap_attribution` 沿用现在的
`config_sensitivity`/无 `analysis_stage`（`None`，归入"未分层的老 claim
type"），不强行并入 `per_switch`，避免把"网格不完整"的证据也包装成
跟完整网格同等地位的"分析 1"。

### 9.2 每层内部：joint_gate 对 per_switch 的降级已经在 Part VIII 定义过

Part VIII §8.4 已经设计了"`joint_test` 不显著时 `gap_attribution_shapley`
的 `evidence_strength` 强制降到 low"——分层展示直接复用这个字段，不需要
在渲染层重新判断一次"分析 2 没过，分析 1 要不要弱化"，UI 只要"读
`evidence_strength` 决定视觉样式"，判断逻辑仍然只在 8.4 那一处。

### 9.3 总结（选项 1：确定性 rollup，新增 `ReplicationDiagnosisReport.summary`）

不新增 claim type、不再问一次 LLM。新增一个纯代码函数
`build_deterministic_summary(claims: list[DiagnosisClaim], bundle: dict) ->
DiagnosisSummary`（`render.py` 旁边新文件或同文件均可），输入是**已经通过
验证**的 `report.claims`（不是原始 bundle，摆脱"总结要重新读证据"的顾虑
——它只是对已经站得住脚的 claim 做结构化汇总，不会引入新的未验证结论），
按 `comparison_line` 分组（Part VIII §8.1 已有这个字段），每条线输出：

```python
class DiagnosisSummary(BaseModel):
    comparison_line: str | None
    overall_tag: str                       # 直接抄 derived.overall_tag，不重算
    per_switch_summary: dict[str, str]     # {switch: "significant"|"insignificant"|"unavailable"}，
                                            # 从 switch_significance claims 的 relation 直接读
    joint_supported: bool | None           # 从 joint_attribution_support claim 的 relation 读；
                                            # 没有对应 claim 时 None（不是 False——"没测"跟"测了不显著"不能混）
    dominant_switches: list[str]           # per_switch 里 evidence_strength 没被 joint_gate 降级、
                                            # 且 relation=significant 的 switch，按 shapley 绝对值排序
                                            # （排序用的数字从 bundle 读，不是 LLM 给的）
    caveats: list[str]                     # 固定模板句子（不是自由文本）：比如 joint_supported=False
                                            # 时固定拼一句"联合检验未通过，dominant_switches 的归因
                                            # 不具备联合显著性支撑"
```

**关键约束**：`caveats`/所有文字都是**固定模板**（`f"..."` 里插值,不是
生成式文本），整个函数是纯 Python，没有 LLM 调用——这跟 Part VII 例子 4
"联合检验是关键的守门结论"这句话的逻辑完全一致,只是从"我手写"变成
"代码按模板自动拼"。`report.summary: list[DiagnosisSummary]`（每条线一个)
新增到 `ReplicationDiagnosisReport`，`diagnose()` 在 return 前调用一次
`build_deterministic_summary`，不影响现有的 `claims`/`rejected_claims`
字段。

### 9.4 `render.py`/前端的分层渲染

- `render_markdown`：`## Findings` 现在按 `claim_type` 平铺分组，改成先按
  `analysis_stage` 分组（`per_switch` → `joint_gate` → `vs_paper` →
  `auxiliary` → 无 stage 的老 claim type 兜底放最后），组内再按
  `claim_type` 分组（沿用现有逻辑，不用重写）；最上面新增一个`## Summary`
  区块，直接渲染 `report.summary`（每条线一段，纯模板拼接，字段列在
  9.3）。
- 前端 `StepOutputView.tsx` 的 step8 分支：现在是纯平铺 `<p>` 列表（比
  `render.py` 还简陋），改成——总结区块（`report.summary`，默认展开，
  放最上面）+ 4 个可折叠区块（分析 1/2/3/附加层，默认折叠，每条 claim
  显示 `evidence_strength`/`identification_level` 徽章，`evidence_
  strength=low` 时视觉弱化，复用 Part VIII §8.4 已经算好的字段，前端不
  判断阈值）+ `rejected_claims` 审计区（保持在最下面，不变）。
- `frontend/src/lib/evidence.ts`（或等价的类型定义文件）的 claim 类型
  定义要加 `analysis_stage`/`comparison_line`字段（镜像 Part VIII 已经
  提到的 `switches_flipped` 加法模式，只是加类型字段，不改现有字段）。

### 9.5 需要改的文件清单（这次只是设计，未动手，且明确排在 Part VIII 之后）

- `src/infra/models/diagnosis.py`：`DiagnosisClaim` 加 `analysis_stage`
  字段 + 一张 `ANALYSIS_STAGE_BY_CLAIM_TYPE` 静态映射表；新增
  `DiagnosisSummary` model；`ReplicationDiagnosisReport` 加 `summary`
  字段。
- `src/steps/step8_diagnosis/__init__.py`：`_derive_claim_fields` 里加
  `analysis_stage` 派生（纯查表，不需要新逻辑）；`diagnose()` 结尾调用
  新的 `build_deterministic_summary`。
- `src/steps/step8_diagnosis/render.py`（或新文件
  `summary.py`）：`build_deterministic_summary` 实现；`render_markdown`
  改成按 stage 分组 + 渲染 `## Summary`。
- `frontend/src/components/StepOutputView.tsx` + 相关类型定义文件：分层
  UI（本节 9.4）。
- 新测试：`build_deterministic_summary` 的单测（每条 comparison_line 一个
  `DiagnosisSummary`、`joint_supported=None` vs `False` 区分、
  `dominant_switches` 排序正确性）；`render_markdown` 按 stage 分组的
  快照式测试。

### 9.6 明确不做的事

- **不**让总结引用原始 bundle key 或重新计算任何数字——只读已验证 claim
  的 `relation`/`evidence_strength`/`comparison_line` 这几个字段,保持
  "总结只是对已验证结论的结构化重排",不是"又一次证据分析"。
- **不**在这轮把 `auxiliary` 层的三种 claim type（`publication_decay`/
  `signal_reproducibility`/`implementation_robustness`）纳入
  `dominant_switches`/`joint_supported` 这些跟 switch 归因相关的总结字段
  ——它们跟 per_switch/joint_gate 是正交问题，混进同一个总结字段会重新
  制造"到底能不能相加"的语义混淆（Q1 已经在数据层面吸取过这个教训）。
- **不**現在就决定"选项 2"（LLM 二级总结）要不要做——如果选项 1 的模板
  总结跑出来读着太机械，再单独讨论要不要加，这轮不预留接口。

---

## Part X. 多因子验证：可行性评估（2026-08-17，评估结论，未执行）

用户要求继续做"多因子验证"（Part VII 所有示例目前只在 AssetGrowth 一个
因子上验证过真实数字）。评估过后决定：**这次不动手跑一个全新的真实第二
因子**，原因和现状记录如下,供下次继续时参考,不要重新调查一遍。

### 现状盘点

- `tests/fixtures/method_specs/` 有 4 个 v1（curated schema）MethodSpec
  fixture（asset_growth/book_to_market/gross_profitability/accruals），但
  `src/infra/models/method_spec.py`（v1 模型）**目前仍然存在**（跟
  `/memories/repo/methodspec_schema_notes.md` 里"v1 已完全删除"的记录矛盾
  ——那条记忆可能来自另一次会话/未完成的重构状态，这次实际检查以代码库
  当前真实状态为准：v1 模型还在）。
- `tests/_spec_test_helpers.py` 有两个已验证的 **v2**
  `ResolvedMethodSpec` fixture：`asset_growth_resolved_spec()`（Part VII
  所有例子的数据来源）和 `accruals_resolved_spec()`——但 accruals 这个
  fixture 明确复用的是 `asset_growth_synthetic_data.expected_metrics()`
  的**合成数据**（`tests/synthetic_data/accruals_synthetic_data.py`
  docstring 自己写的），不是独立的真实 WRDS 数字。用它跑一遍能验证
  "Shapley/paired/joint 这套方法论对另一种 MethodSpec 形状（6 个
  concept、不同 weighting/breakpoint）是否也能跑通"，但**不能**当成
  "第二个独立因子的真实经济结论"。
- `data/local/` 下有真实 WRDS CSV（Compustat annual/quarterly、CRSP
  monthly、CCM link），`gross_profitability`/`book_to_market` 需要的
  revt/cogs/at/ceq 等列都在——理论上可以支持一个真正独立的第二因子，但
  这两个 fixture 是 v1 curated schema，需要先按照当前 v2
  `PaperMethodSpec`/`ResolvedMethodSpec` schema 重新构建（照抄
  `asset_growth_resolved_spec()`/`accruals_resolved_spec()` 的模式），
  这本身是一次不小的建模工作，不是"顺手跑一下"。
- `runs/backtest_scripts/results/` 目前只有一个结果目录
  （AssetGrowth 的 `099f6e1136bd316c/`）——没有现成的第二因子产出可以
  直接拿来核实,必须真正重新跑一遍 pipeline。

### 决定：这轮不做，记录一个具体的后续执行计划

跑一次真正独立的第二因子验证（真实数据、真实经济结论）需要：
1. 选定因子——建议 `gross_profitability`（Novy-Marx 2013）：单一
   accounting ratio、`data/local` 里所需列已确认存在，是这几个候选里
   经济结构最简单的。
2. 参照 `asset_growth_resolved_spec()` 的模式，为它写一个新的、当前 v2
   schema 下的 `ResolvedMethodSpec`（不是照抄 v1 fixture 转格式，需要
   重新过一遍 concept_mapping/universe_filters/portfolio.sorts 的正确性）。
3. 确认 `src/infra/reference`（`CZReferenceProfile`/SignalDoc）里有没有
   `GP`（gross profitability）这个 acronym 的条目，决定能不能同时产出
   ①→②（C&Z）这条线，还是只能先验证①→③。
4. 通过 `MultiTrackController`/`run_from_matrix` 真的执行一批 factorial
   轨道（不是只调用 `build_evidence_bundle` 传合成数字），产出真实
   `comparison.json`，重复 Part VII 的"逐条核实再考虑写进结论"流程。
5. 这是一个需要真实回测运行时间 + 新建模型验证的独立任务，建议单独一个
   会话做（同类工作量参照 Part VII/示例 1-6 最初建仓那次讨论的量级），
   不要在做 Q5/Q8 的同一轮里顺带完成——避免为了赶进度在没有充分验证
   MethodSpec 正确性的情况下就生成"看起来是真的"但实际经济设定有误的
   第二因子数字。

---

## Part XI. step8 总结重新设计：从"字段罗列"到"综合叙事"（2026-08-17，已实现）

用户反馈 Part IX 的分层展示"分层方式不喜欢、内容不深刻"。讨论后确定的
方向，全部已落地：

### 11.1 三个具体改动

1. **去掉"①→②/①→③"记法**——`render.py`/前端的 `_LINE_LABELS`/
   `LINE_LABELS` 只保留描述性文字（`"vs. HXZ standardized config"`/
   `"vs. C&Z actual config"`），claim 句子模板里"On comparison line
   {line}"改成"On the {line} line"，避免"line vs. line"式的措辞重复。
2. **"switch"（讨论时中文叫"开关"）→ 前端/文档统一用"choice"/"实现
   选择"这个说法**——代码内部变量名/`switches_flipped` 等既有字段名不改
   （改名成本高、破坏面广，且这是 step6/7 早就定下的既有概念），只改
   **面向读者的文案**（叙事段落、claim 模板句子）。
3. **主次关系倒过来**：`AGENTS.md` 的研究核心是 agent vs C&Z 的一致程度
   （① → ②），不是 agent vs HXZ 标准化（① → ③）——之前的实现把两条线
   当平级处理，这轮改成 **`to_cz` 永远排第一、篇幅和分析深度也对应更
   丰富**（`_summary_line_priority`/前端 `summaryLinePriority`：
   `to_cz` → 0，`to_hxz` → 1，其他 → 2，无对比线（"Overall"）→ 3）。

### 11.2 核心新增：`DiagnosisSummary.narrative`（`to_cz`）+
`build_vs_paper_narrative`（新增 `ReplicationDiagnosisReport` 字段）

关键设计决定：**这段叙事直接从 `bundle` 生成，不依赖 LLM 是否碰巧产出了
对应的 claim**（`src/steps/step8_diagnosis/summary.py` 模块文档已更新
说明这一点）——比"聚合已验证 claim"（Part IX 原方案）更确定，因为
`bundle` 本身就是纯 step7 计算，跟 LLM 输出质量完全无关。

`to_cz`（主线）的叙事逻辑——对 `config_diff.pairs.cz_actual_config` 里
**每一个**跟 baseline 不同的 config key，做三选一归因（`_divergence_reason`）：

- **`house_convention`**：这个 key 在
  `CZ_HOUSE_CONVENTION_KEYS`（`weighting_rule`/`breakpoint_quantiles`/
  `breakpoint_source`/`accounting_lag_months`/`missing_action`/
  `formation_lag_months`/`universe_filters`——`cz_profile_to_config_
  override` 对每个 C&Z 因子都无条件覆盖的字段，是这个函数实现方式本身
  的通用事实，不是针对某一篇论文的判断）里——说明这个分歧是 **C&Z 自己
  的跨因子标准化惯例**，不是论文含糊也不是实现误差。
- **`paper_ambiguous`**：不在上面那个集合里，但 `spec_quality.
  weak_fields` 标记过这个字段（按 `stage_of`/config key 名字做子串匹配，
  是个近似判断，不是精确的 MethodSpec 字段路径映射）——说明论文本身
  写得不够清楚。
- **`unresolved`**（诚实的兜底）：两者都不是——**不**冒充"这一定是 C&Z
  的惯例"或"这一定是实现错误"，只说"现有证据解释不了，需要人工复核"。
  之前讨论时想要的"论文写清楚了但还是分歧→一定是实现误差"这个二分法被
  推翻了——真实数据显示 universe 这个真实分歧其实是 `house_convention`
  （C&Z 的跨因子标准化），不是"论文含糊"也不是"实现误差"，所以设计成
  三选一,且 `unresolved` 分支刻意写得谨慎、不过度归因。

每条分歧还带：该 key 对应的配对检验效应量/显著性（`_format_paired_
effect`，复用已有的 `paired_tests`/`SIGNIFICANCE_T_THRESHOLD`），以及
**跨线呼应**——同一个 choice 在 `to_hxz` 线上对应的单开关轨道
（`factorial_<switch>`）在 `publication_decay` 里是否衰减（呼应 Part VII
例子 6 的发现）。结尾按"是否所有分歧都能被 house_convention/paper_
ambiguous 解释 + 是否有个体显著效应"分叉出不同的收尾句,明确点出"这对
可复现性研究问题意味着什么"。

`to_hxz`（及其他非 `to_cz` 线）的叙事（`_build_sensitivity_narrative`）
更简单：总差距 + 联合检验守门 + 逐 choice 的 Shapley 份额/配对显著性,
明确标注"用作敏感度支撑材料，不是可复现性问题本身"（跟 `to_cz` 的措辞
区分开，避免喧宾夺主）。

`build_vs_paper_narrative`（跟论文本身比，报告级、不分线）新增
"我们自己的 baseline 有没有依赖论文完全没提、靠引擎默认值填的字段"这个
诚实局限说明（读 `menu_deviations.clamped_by_track[baseline_track]`，
只挑 `paper_value` 是 `None`/`"unspecified"` 的——这是论文压根没讲，不是
论文讲了但有争议）——真实 AssetGrowth 数据验证过：`original_method` 有
`accounting_lag_months`/`missing_action` 两个这样的字段，2.11 倍的量级
差距不能全部算实现的锅。

### 11.3 用真实 AssetGrowth 数据验证过的效果（跑 `build_deterministic_
summary`/`build_vs_paper_narrative` 直接对着 `099f6e1136bd316c/
comparison.json` 生成，不是编的）：额外发现 `formation_lag_months`
（0 vs 1）也是一个真实的 `house_convention` 分歧,之前讨论时只手动核实过
`universe_filters`，这次是代码自己从真实数据里找出来的,不是我提前预设的。

### 11.4 明确的已知局限

- `_is_weak_in_paper` 的 config_key → MethodSpec field_path 匹配是**子串
  近似**，不是精确映射——`_CONFIG_KEY_TO_SWITCH_NAME` 只覆盖 6 个已知
  switch，新增 config key 需要跟着更新这个表（镜像
  `step6_dual_track_controller._CONFIG_KEY_TO_SWITCH`，特意不跨 step
  import，避免 step7/8 依赖 step6 内部实现）。
- `CZ_HOUSE_CONVENTION_KEYS` 是**代码里硬编码的固定集合**（`cz_profile_
  to_config_override` 的无条件覆盖字段）——如果那个函数以后新增/移除
  无条件覆盖的 key，这个常量要跟着手动同步，没有自动化保证两者一致。
- ~~前端展示（`Step8Output.tsx`）目前只是把 `narrative` 当一段纯文本
  `<p>` 展示，没有额外排版~~ **已在 Part XII 解决**（拆成 `headline`/
  `details`/`footnote` 三个结构化字段，前端分别渲染）。
- 没有再单独做"选项 2"（LLM 二级总结）——这轮的"深刻"完全靠模板 + 更多
  bundle 字段的交叉引用做到，没有引入新的 LLM 自由文本层，符合 Part IX
  §9.3 定下的原则。

---

## Part XII. Summary 排版重新设计：倒金字塔结构 + 去掉 line 标题（2026-08-18，已实现）

用户对 Part XI 的反馈：`narrative` 是一整段没有结构的长文字，读到最后才
知道结论；而且 `formation_lag_months`/`cz_actual_config` 这类参数名/
track 名不该直接出现，"C&Z"/"HXZ" 也是简称——最后确认的方案：每张卡片
不再要"vs. C&Z"/"vs. HXZ"这种标题，headline 自己把比较对象说清楚
（"Compared with C&Z's independent replication of this paper, ..."）。

### 12.1 `DiagnosisSummary`/新增 `VsPaperSummary` 的字段改动

- **删除** `narrative: str`、**删除** `caveats: list[str]`
- **新增**（`headline: str`/`details: list[str]`/`footnote: str`）：
  - `headline`：一句话结论，永远第一个展示，自己交代比较对象（不需要
    外部标题/line label）
  - `details`：逐项细节，一条一个分歧点/维度，不再拼成一个长句
  - `footnote`：技术性备注（联合检验可用性等），弱化展示
- `per_switch_summary`/`joint_supported`/`dominant_switches` **保留不变**
  ——这些是结构化数据（前端拿来做徽章），不是文字内容，跟"narrative 里
  有没有重复文字"是两回事
- 新增 `ReplicationDiagnosisReport.vs_paper_summary: VsPaperSummary`
  （取代原来的 `vs_paper_narrative: str`）——单独一个小 model 而不是三个
  松散字段，因为这是报告级、不分 comparison line 的一个整体

### 12.2 `summary.py` 的改动

- `_build_cz_narrative` → `_build_cz_summary`，`_build_sensitivity_
  narrative` → `_build_sensitivity_summary`，两者都从返回单个字符串改成
  返回 `(headline, details, footnote)` 三元组
- `build_vs_paper_narrative` → `build_vs_paper_summary`，返回
  `VsPaperSummary` 而不是字符串
- headline 的措辞现在直接点名比较对象（"Compared with C&Z's independent
  replication..."/"Compared with the fully standardized HXZ protocol..."/
  "Compared with the paper's own reported result..."），不依赖外部标题

### 12.3 参数名/track 名可读化（这轮顺带做的，同一批改动里发现的真实 gap）

用户指出 `formation_lag_months`、`cz_actual_config` 这些是参数名/内部
track 名，不应该直接出现在面向读者的文字里。新增：

- `CONFIG_KEY_LABELS`：每个已知 config key → 可读短语（比如
  `formation_lag_months` → "the lag between signal formation and
  portfolio start"），`_readable_key` 对没收录的 key 兜底做下划线转
  空格的通用处理
- `TRACK_LABELS`：`cz_actual_config` → "C&Z's own independent
  replication"，`original_method` → "our reviewed implementation of the
  paper's method" 等
- `_readable_value`：专门处理 `universe_filters` 这种复杂值（原来会打印
  成 Python repr `[{'field': 'siccd', ...}]`，现在渲染成"siccd not
  between 6000-6999"这种可读文本）

`_build_cz_summary`/`_build_sensitivity_summary`/`build_vs_paper_summary`
里所有原来反引号包着的原始 key/track 名全部换成这几个 helper 的输出。

### 12.4 真实数据验证效果（`099f6e1136bd316c/comparison.json`，不是编的）

```
to_cz headline: "Compared with C&Z's independent replication of this
paper, the only differences are explained by paper ambiguity or C&Z's
own conventions, and none has a statistically significant effect."

to_hxz headline: "Compared with the fully standardized HXZ protocol,
our implementation's effect differs by 0.0059/month, confirmed by a
joint significance test (p=7.8e-05)."

vs_paper headline: "Compared with the paper's own reported result, our
reviewed implementation of the paper's method agrees in sign with it;
its magnitude is 2.11x larger."
```

`details`/`footnote` 分别核实过跟真实数字对得上（universe_filters/
formation_lag_months 两个 house_convention 分歧、96%/31%/-27% 的
Shapley 份额、2 个论文没提的默认字段），格式符合"headline 先行、
details 逐条、footnote 弱化"的倒金字塔结构。

### 12.5 明确的已知局限（这轮遗留）

- `headline`/`details` 文字里偶尔有轻微的语法重复（比如"this setting
  is one of the settings..."），是模板拼接的自然产物，没有再花时间打磨
  措辞，优先级低于结构本身。
- `render.py` 的 markdown 渲染（`diagnosis.md`）里 `details` 渲成
  `- ` bullet 列表，`footnote` 渲成斜体——没有像前端一样单独测试视觉
  效果，只验证过文本内容正确。

---

## Part XIII. 面向"完全不懂的人"的可读性追加（2026-08-18，已实现）

用户反馈：即使 Part XI 已经把 `formation_lag_months`/`cz_actual_config`
这类参数名换成了短语，一个完全不懂金融的人看到"the lag between signal
formation and portfolio start"、"siccd not between 6000-6999"这种表述
还是看不懂——"lag 是什么"、"siccd 6000-6999 是什么"都没有解释。这轮把
`CONFIG_KEY_LABELS`/universe filter 的翻译都改成"解释是什么 + 为什么
存在"，不是只换个说法。

### 13.1 `CONFIG_KEY_LABELS` 改成"解释性"而不是"换个词"

比如 `formation_lag_months`，Part XI 版本是"the lag between signal
formation and portfolio start"（只是把参数名翻成了英文短语，"lag"是
什么依然没解释）；这轮改成：

> "how long after picking which stocks go in a portfolio before that
> portfolio actually starts trading (a safety delay so the strategy
> can't accidentally use information before it was realistically
> available)"

`accounting_lag_months` 同理，从"how many months of lag before
accounting data is used"改成解释"为什么要等"：

> "how many months we wait after a company's fiscal year ends before
> using its accounting data (real investors can't see the numbers the
> instant the year ends)"

### 13.2 universe filter 的代码值（`siccd`/`shrcd`/`exchcd`）—— 精确查表，
不是通用解码器

新增 `_KNOWN_FILTER_DESCRIPTIONS`：`(field, op, value)` 三元组精确匹配到
一整句人话，只覆盖这个项目实际会产生的固定组合（论文里的 SIC 行业排除、
C&Z 自己的 shrcd/exchcd 房规），不是一个通用的 CRSP/Compustat 代码词典：

```python
("siccd", "not_between", (6000, 6999)): "excludes financial companies
  such as banks, insurers, and real estate firms (identified by SIC
  industry codes 6000-6999)"
("shrcd", "in", (10, 11, 12)): "includes only ordinary common shares
  (not REITs, ADRs, or other special share types)"
("exchcd", "in", (1, 2, 3)): "includes only stocks listed on the NYSE,
  AMEX, or Nasdaq exchanges"
```

没查到表里的字段/组合会退回到`_readable_field`（字段名转可读）+ 操作符
英文 + 数值本身拼出的**通用但没有具体业务解释**的兜底句子——不会显示未
翻译的原始代码，但也不会瞎编没见过的代码组合的金融含义（比如某篇新论文
自己定义的过滤字段）。

### 13.3 真实数据核实时发现并修复的语法 bug："we use excludes..."

`universe_filters` 的可读值本身已经是一个完整的动词从句（"excludes
financial companies..."），套进"we use {value}, C&Z uses {value}"这个
通用模板会拼出"we use excludes financial companies"这种破句。修法：
新增 `_CLAUSE_VALUED_KEYS`（目前只有 `universe_filters`）+
`_value_clause(key, value, ours=...)`——这类 key 用"our version
{clause}"/"C&Z's version {clause}"而不是"we use/uses {value}"；多条
filter 描述之间的连接词也从"; "改成" and "，让"C&Z's version A and B"
读起来是一整句话而不是两个分号隔开的碎片。

**真实数据验证效果**（`099f6e1136bd316c/comparison.json`）：

> "Which stocks are allowed into consideration at all: our version
> excludes financial companies such as banks, insurers, and real
> estate firms (identified by SIC industry codes 6000-6999), C&Z's
> version includes only ordinary common shares (not REITs, ADRs, or
> other special share types) and includes only stocks listed on the
> NYSE, AMEX, or Nasdaq exchanges -- ..."

### 13.4 明确的已知局限

- `_KNOWN_FILTER_DESCRIPTIONS` 只覆盖 3 个已知组合——新论文如果用了不同
  的 universe filter 字段/组合，会退回通用兜底句子（可读但不够具体），
  需要人工发现后补充这张表，不会自动生成新的金融领域解释。
- `_CLAUSE_VALUED_KEYS` 目前只有 `universe_filters`——如果以后有新的
  "值本身是完整从句"的 config key，需要记得把它加进这个集合，否则会
  重复"we use excludes..."这种语法错误。
- 5 处测试断言按新措辞更新（`weighting_rule`/`accounting_lag_months`/
  `universe_filters` 相关），`tests/test_replication_diagnosis.py`
  118 passed，更广套件 152 passed，没有新增回归。

### 13.5 用户追问"以后还有别的论文，硬编码表不可能覆盖所有情况，内容
应该能从 MethodSpec 拿"——已解决（2026-08-18，同一天追加）

这个反馈是对的，`_KNOWN_FILTER_DESCRIPTIONS` 那种按 `(field, op, value)`
精确查表的方式，天生不可能穷举以后所有论文自己的 universe filter 写法。
真正的解法：**论文自己的 universe 描述，MethodSpec 提取时已经存了**
（`spec.paper.universe.description`，一个 `SourcedValue[str]`，是论文
原文的自然语言描述，带证据引用）——这个字段对任何论文都存在（提取阶段
保证），不需要我们自己去"猜"某个 filter 代码组合是什么意思。

新增 `build_universe_description(spec)`（`bundle.py`，跟 `build_spec_
quality`/`build_menu_deviations` 同一个模式），把 `spec.paper.universe.
description.value` 塞进 bundle 的新顶层 key `universe_description`——
`src/steps/step5_backtest_runner/__init__.py` 调 `build_evidence_bundle`
时本来就传了真实 `spec`，所以这个字段在真实 pipeline 里会自动生效，不
依赖 step8 `diagnose()` 那个"`resolved_spec` 从来没被传过"的既有 gap
（那是 `field_evidence_detail` 工具的问题，这次没碰）。

`summary.py` 新增 `_universe_filters_clause(bundle, detail, ours)`：
- **我们这边**：优先用 `bundle["universe_description"]["text"]`（论文
  原文），生成"the paper describes its universe as: \"...\""——对任何
  论文都自动生效，不需要针对每篇论文单独维护规则
- **C&Z 那边**：改成一个**固定常量** `_CZ_HOUSE_UNIVERSE_DESCRIPTION`
  （不是查表）——因为 C&Z 的房规 universe（`shrcd in [10,11,12]` +
  `exchcd in [1,2,3]`）对每个 C&Z 因子都完全一样,不需要"扩展到新论文",
  这本来就是个不随论文变化的常量
- `_KNOWN_FILTER_DESCRIPTIONS`/`_readable_filter` 那套精确查表**降级为
  兜底**——只在没有 `spec`（`universe_description` 不可用）时才用，
  代码注释和文档都已更新说明这是"退路"不是"主路"

**真实数据验证**（用真实提取的论文原文,不是编的）：

> "Which stocks are allowed into consideration at all: the paper
> describes its universe as: \"We use all NYSE, Amex, and NASDAQ
> nonfinancial firms (excluding firms with four-digit SIC codes between
> 6000 and 6999) listed on the CRSP monthly stock return files and the
> Compustat annual industrial files\", C&Z's version is ordinary common
> stock listed on the NYSE, AMEX, or Nasdaq exchanges -- C&Z's own fixed
> cross-factor universe convention, applied identically to every C&Z
> factor regardless of what any individual paper's own universe
> description says -- ..."

新增测试：`TestUniverseDescription`（`build_universe_description` 单测,
`no_spec` / `available` 两种情况）+ `test_universe_filters_prefers_the_
papers_own_extracted_description`（验证优先用论文原文,C&Z 侧仍是固定
描述）。`tests/test_replication_diagnosis.py` 121 passed，更广套件
155 passed，零回归。

## Part XV. 两个用户追问：值本身也要翻译成大白话 + 别单独展示
per-switch/joint-gate（2026-08-18，同一天追加）

### 15.1 "we use vw, C&Z uses ew" 里的 `vw`/`ew` 还是没翻译

用户指出：`CONFIG_KEY_LABELS`（"whether bigger companies count for more
in the portfolio, or every stock counts equally"）解释的是**这个设置是
什么**，但后面接的 `we use {value}` 里 `{value}` 之前是 `_readable_
value` 直接 `str(value)`，也就是原始 menu token（`"vw"`/`"ew"`），根本
没翻译。用户要求：这类描述后面也要接上大白话的实际取值（比如
"value-weighted"），双方（我们 vs 对比对象）都要翻译。

`summary.py` 新增 `_VALUE_LABELS: dict[key, dict[raw_value, plain_label]]`
——只覆盖有固定 menu 的 key（`weighting_rule`/`breakpoint_source`/
`missing_action`/`return_combination_type`，menu 定义见
`src/steps/step3_codegen/registry.py`的`STANDARD`），例如
`{"vw": "value-weighted", "ew": "equal-weighted"}`。另加 `_quantile_
label`（`breakpoint_quantiles` 是个原始分组数,比如 `10` -> "10 groups
(deciles)"）和月份单位格式化（`accounting_lag_months`/`formation_lag_
months`：`6` -> "6 months"）。`_readable_value` 优先查这些表，查不到
（比如以后新增了 menu 之外的 key）才退回 `str(value)`——不会因为漏填
一个 key 而崩溃，只是那个 key 暂时还是显示原始值，直到补充。

修改后示例：
> "Whether bigger companies count for more in the portfolio, or every
> stock counts equally: we use value-weighted, C&Z uses equal-weighted
> -- is one of the settings C&Z always overrides..."

### 15.2 per-switch analysis / joint significance gate 不再单独展示，
折进 summary 正文

`DiagnosisSummary.per_switch_summary`/`joint_supported`/`dominant_
switches` 是从 LLM 已验证 claims 里提炼出来的（Part IX 设计），之前在
`render.py`/`Step8Output.tsx` 里各自渲染成独立的一行/一个 badge，跟同一
张卡片里 `headline`/`details`（Part XI 起改成直接从 bundle 算,不依赖
claims）看起来是两套并列的东西,内容却经常重叠,显得啰嗦。

新增 `_fold_claim_evidence_into_details(details, per_switch_summary,
joint_supported, dominant_switches)`（`summary.py`），在
`build_deterministic_summary` 里对每条 `DiagnosisSummary` 的 `details`
末尾追加最多 3 句话（各自条件非空才加）：
- `"LLM-reviewed per-setting significance: {配置项大白话} ({relation}), ...".`
- `"LLM-reviewed joint-significance conclusion: supported/not supported by the data."`
- `"LLM flagged as dominant driver(s): {配置项大白话}, ...".`

`DiagnosisSummary` 模型本身的三个字段**没有删**（`evidence_keys`/引用
审计还用得到,后端 API 也还照常返回),只是不再单独渲染——`render.py`
的 `_summary_section` 删掉了原来那三行 markdown（"Per-switch
significance:"/"Joint test:"/"Dominant switches:"），
`Step8Output.tsx` 的 `SummaryCard` 删掉了对应的 badge/段落。

测试更新：`test_findings_are_grouped_by_analysis_stage_and_summary_
section_is_rendered` 断言从旧的独立行改为断言这三句折进 `details` 的
新措辞。`tests/test_replication_diagnosis.py` 121 passed，更广套件
155 passed；前端 `npx tsc --noEmit` + `npx oxlint` 均干净。

### 15.3 用户追问："per switch analysis, joint significant gate 等等
为什么还在" —— 原来 `## Findings` 里按 analysis_stage 分组的原始 claim
列表还在（跟 15.2 折进 Summary 是两个不同的地方：15.2 改的是
`DiagnosisSummary` 卡片里的三个字段，这里指的是整份 markdown/前端里
`## Findings`/"Findings" 折叠区，按 `per_switch`/`joint_gate`/`vs_paper`/
`auxiliary`/`None` 分组、逐条渲染每个 claim 自己的 `deterministic_
sentence` + 引用证据）。第一轮只隐藏了 `per_switch`/`joint_gate` 两个
stage。用户追问："not only two stage sections, all sections except
summary"——即整个 Findings 折叠区（所有 stage）都不该再单独展示。

已解决：`render.py::render_markdown` 整段删掉 `## Findings` 循环（连带
`_STAGE_ORDER`/`_STAGE_HEADINGS`/`_CLAIM_TYPE_HEADINGS`/`_FINDINGS_
HIDDEN_STAGES` 这些只服务于该循环的常量一并删除)；`Step8Output.tsx`
删掉整个按 stage 分组的 `<details>` 折叠块、`unstaged`/`Other` 折叠块，
和只被它们使用的 `ClaimCard` 组件、`DiagnosisClaim` 类型、`STAGE_ORDER`/
`STAGE_LABELS`/`LINE_LABELS`/`lineLabel`。现在页面/`diagnosis.md` 只剩
两块：**Summary**（`SummaryCard`/`VsPaperCard`，直接从 bundle 算，Part
XI 起就不依赖 claims）和 **Rejected claims (audit)**（保留——这是验证
失败的审计记录，跟"重复展示已通过的证据"是两回事,不在这次"别单独展示
findings"的范围内）。

`report.claims`/`report_to_jsonable` 的 `rendered_sentence` 字段**没有
删**——`diagnosis.json`（后端 API 响应）依然带着完整 claims 列表和每条
的 `deterministic_sentence`,只是不再渲染成 UI/markdown 的一个独立区块,
供审计/未来其他消费者使用。

`deterministic_sentence`/`_RELATION_TEMPLATES`/`_line_label`/
`_switch_subject`/`_per_switch_subject` 这些"claim -> 句子"生成逻辑本身
没有删（`report_to_jsonable` 还在用),只是不再由 `render_markdown` 的
Findings 循环触发——相应测试（`test_part_viii_claim_types_render_
switch_and_line_into_the_sentence`、原 `test_figures_come_from_the_
bundle_and_sentence_from_the_relation`）改成直接调用 `deterministic_
sentence(claim, evidence)` 断言句子内容，不再通过 `render_markdown` 间接
验证。`tests/test_replication_diagnosis.py` 122 passed，更广套件
156 passed；前端 `npx tsc --noEmit` + `npx oxlint` 均干净。






