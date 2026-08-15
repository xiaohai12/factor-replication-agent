# Step 3-8 展示内容重构计划

范围：运行详情页里 `StepOutputView` 对 step 3、4、5、6、7、8 的渲染内容。
已于 2026-08-14 与用户确认。

不在范围内：Runs 列表页（`RunsPage.tsx`）保持不变（factor / paper /
8 点进度条 / state / updated / delete）。Step 1-2 继续用 `MethodSpecBoard`。

## 设计原则（已确认）

1. **每个 step 分两层。** 一层是**主视图**，回答"这对复现结果说明了什么"
   （可引用的数字、identification level、caveat）；另一层是默认折叠的
   **Debug / provenance 区**，回答"机器是不是正常跑完的"（repair、哈希、
   provenance、原始 JSON）。两者不能混在一个平铺列表里。
2. **界面上出现的每个数字都必须来自某个确定性 artifact。** UI 本身不计算
   任何统计量，只格式化后端已经写好的东西。唯一允许的例外是纯粹的重排
   （比如把已持久化的收益序列做累计乘积），且必须标注为"仅用于展示的派生值"。
3. **LLM 措辞必须和数字明确分开。** step 8 的 claim 按设计不含数字，所以
   UI 必须把对应的确定性证据数值摆在措辞旁边，绝不能只显示一句没有数字支撑的话。
4. **兜底保留。** 任何没有专属展示的 step 仍然回退到现在的 `JsonTree` 原始结果。

## 现状（基线）

| Step | 目前渲染的内容 | 没被用上的后端数据 |
|---|---|---|
| 3 | 把 resolved config 摊平成一个 `MetricsTable`，加 plugin 代码、组装脚本 | `defaults_applied`（菜单 clamp 审计）、`substitutions`、`unapplied_universe_filters`、`sort_dims`、`repair_trace`、attempt 的 `diagnostics`（readiness/counters/flags）、`script_sha256` |
| 4 | 5 个布尔徽章 + errors | `passed`、`faithful_ok`、`warnings`、`technical_metrics`、step4 自己写的 repaired `plugin_ref`（代码被改了但完全看不出来） |
| 5 | 月度收益折线图 + metrics 表 | 累计净值曲线、`by_sample_period`、`coverage`/`microcap_share`、`runtime_provenance`、`repair_history`、其它 evidence 文件 |
| 6 | 多 track 叠加图 + 每个 track 一张 metrics 表（纵向堆叠） | 横向 track 对比表、`batch_invalidated` 及原因、`frozen_plugin_hash` 一致性、`is_bridge_track` |
| 7 | `overall_tag` 徽章、gap 瀑布图、每个 track 的 config diff | `paper_reported`、`derived.tracks.*.vs_paper`、`spec_quality`、`menu_deviations`、`bridge_comparison`、`publication_decay`、`robustness_summary` |
| 8 | `claim.text` 逐行文字 + rejected 原因 | 几乎所有其它字段：`overall_tag`、`evidence_keys` 对应的数值、`claim_type`/`relation`/`stage`/`identification_level`/`evidence_strength`/`reason_layer`，以及后端已经渲染好的 `diagnosis.md` |

## 各 step 的目标设计

### Step 3 — Codegen

主视图，按以下顺序：

1. **头部信息条**：`script_sha256`（缩短、可复制）、`code_hash`、
   `validation_status`、attempt diagnostics 里的 `readiness`。
2. **一张完整的 config 表格，按引擎自身阶段分组，逐行标注来源。** 不再是
   单一摊平的 `MetricsTable`，也不再把 substitution/default 拆成独立卡片：
   同一张表里，每一行除了 `config_key` 和最终解析值之外，还带一个来源徽章
   （论文原样 / 评审批准的替代 substitution / 引擎兜底 default，两者都可能
   同时出现在同一行，因为它们是两条独立运作的记录线，见下）——
   substitution 行额外显示 `paper_value → engine_value` 和批准理由（amber
   样式）；default 行显示 `paper_value`（`ev()` 得到的原始论文值，genuinely
   unspecified 时就是字面 `"unspecified"`）和兜底理由（灰色样式，不抢眼）。
   这两个字段都已在 `src/steps/step3_codegen/registry.py` 里补上（2026-08-14
   完成，`tests/test_registry_resolved_method_spec.py`/`test_method_spec_contract.py`/
   `test_replication_diagnosis.py` 均仍通过）：
   - `defaults_applied` 补了 `paper_value`。
   - `substitutions` 补了 `config_key`（因为 `substitutions.field` 是人工填写的
     MethodSpec 路径写法，如 `"portfolio.weighting"`，和 config 表格的行名
     `weighting_rule` 对不上；新增 `SUBSTITUTION_FIELD_PATH_TO_CONFIG_KEY`
     做最佳匹配，未匹配上时 `config_key` 为 `None` —— 前端必须把这类
     substitution 单独列出来，不能静默丢弃，因为 `field_path` 是自由文本，
     这份映射表不可能穷尽）。
   分组：
   - 信号输入：`accounting_lag_months`、`signal_max_staleness_months`、`missing_action`
   - Universe：`universe_filters`、`unapplied_universe_filters`、`apply_delisting_returns`、`returns_table`/`returns_layout`
   - 组合构建：`breakpoint_source`、`breakpoint_quantiles`、`weighting_rule`、`rebalance_frequency`、`holding_period_months`、`long_leg`/`short_leg`、`long_portfolios`/`short_portfolios`、`formation_month`(+`_explicit`)、`sort_dims`
   - 样本：`sample_start_year`、`sample_end_year`、`publication_year`
   - 估计方法：`return_basis`、`return_combination_type`、`estimator`
   `unapplied_universe_filters`（`concept_id | op | value | reason`）作为
   Universe 分组里单独一段，因为它描述的是完全没被应用的过滤条件，不是某个
   config_key 的取值来源。**未能匹配到任何 config_key 的 substitution**
   （`config_key: null`）放在表格最下方单独一段，标注"未能自动对应到具体
   config 项"，同样附上 `field`/`paper_value`/`engine_value`/`reason`。
3. **`compute_signal` 代码**（不变）和**组装后的脚本**（不变，但默认折叠——
   内容很长且大部分是样板代码）。

Debug 区：`repair_trace`、attempt 的 `diagnostics.counters`/`flags`、原始 config JSON。

### Step 4 — Validator

主视图：

1. **总体结论徽章**由 `passed` 驱动，然后是各项检查徽章（`syntax_ok`、
   `schema_ok`、`no_future_leak`、`reproducible`、`executes_ok`、
   `faithful_ok`）。当 LLM faithfulness 检查没有实际运行时，`faithful_ok`
   必须标注为"skipped"而不是显示为绿色通过，避免"没跑的检查看起来像通过了"。
2. **技术指标表**，来自 `technical_metrics`：`n_permno`、`n_months`、
   `nan_ratio`（格式化为百分比，超过阈值时用 warning 样式）、`dtype`、
   `missing_columns`（列表，非空时用 destructive 样式）。
3. **Errors**（destructive）和 **warnings**（灰色）分开两个列表——目前
   warnings 是被完全丢弃的。
4. **Repair 提示**：当 step4 的 attempt 记录了自己的 `plugin_ref`、且和
   step3 的不一样时，显示一条横幅"validation 修复了插件代码 —— step5 将
   执行修复后的代码"，并提供一个可展开的 diff 对比 step3 和 step4 的代码。
   这是目前 step 4 里最令人困惑、且完全静默的一个缺口。

Debug 区：`validated_script_sha256`、原始 report JSON。

### Step 5 — Backtest run

主视图：

1. **收益图加一个累计净值切换开关**——月度（现状）vs. 累计增长曲线（从
   同一份 `return_series.csv` 派生，仅用于展示）。
2. **核心指标做成卡片**，而不是通用表格：`mean_return`、`t_stat`、
   `sharpe_ratio`、`alpha_capm`、`alpha_ff3`、`alpha_ff5`、`n_months`。
3. **分样本期拆解**，来自 `by_sample_period`（存在时才显示）：一个小表格，
   行是 `insamp` / `between` / `postpub`——这正是 step 7 里
   `publication_decay` 的原始素材，在 step 5 就先看到能让后面那部分容易理解得多。
4. **Coverage 信息条**：`coverage`、`microcap_share`。

Debug 区：`runtime_provenance`（`dirty_worktree` 为 true 时标红、
`engine_source_hash`、`interpreter_version`）、`code_hash`/`config_hash`/
`data_snapshot_hash`、`repair_history`，以及该次 run 的可下载 evidence
文件列表（`GET /api/evidence/{factor_id}/{run_id}` 已经返回 `files`）。

### Step 6 — Multi-track controller

主视图：

1. **Batch 状态条放最前面**：`experiment_batch_id`、track 数量、
   `batch_invalidated`（+ `batch_invalidation_reason`）为 true 时用
   destructive 横幅展示，以及 `frozen_plugin_hash` 一致性指示（所有非
   bridge track 共享同一个 hash → 绿色；否则红色）。Bridge track 按设计
   被排除在这个一致性检查之外，必须明确标注说明。
2. **横向 track 对比表**，替换掉现在纵向堆叠的每 track 一张表：行 =
   track，列 = `mean_return`、`t_stat`、`sharpe_ratio`、`alpha_ff3`、
   `n_months`、`coverage`、`status`。基准 track（通常是
   `original_method`）固定放第一行；bridge track 加明确徽章；t-stat 那一列
   额外显示相对基准的差值。
3. **叠加图**（现有 `MultiTrackChart`），移到表格下方。

Debug 区：每个 track 的 `repair_history`、各自的哈希、原始 run record。

### Step 7 — Replication diff

主视图，按引用频率从高到低排序：

1. **结论**：`overall_tag` + `baseline_track`，以及 `paper_reported` 头部
   信息（`return_type`、`main_spread`、`main_t_stat`）。
2. **Paper vs Tracks 对照表**（新增，目前缺失的最重要的一张表），来自
   `derived.tracks.*.vs_paper`：行 = track，列为论文 spread、track spread、
   `spread_delta`、`abs_spread_ratio`、`sign_agrees`、论文 t 值、track t
   值、`t_stat_delta`、`t_stat_comparable`、`significance_agrees`。当
   `t_stat_comparable == false` 时必须把 t-stat 相关列显示为灰态，而不是
   继续显示一个具有误导性的差值。
3. **Gap 分解**：保留 `GapWaterfallChart`，但补上 `available`/`reason` 的
   空态、`explained_fraction`、`residual`、`identification_level`，以及
   目前被丢掉的 `interaction_caveat` 文字——这条 caveat 缺失会让分解结果
   显得比实际更可信。
4. **五张证据卡片**放进一个可折叠的网格里，每张各自渲染自己的
   `available`/`reason` 空态，而不是直接消失不见：
   - `robustness_summary`：`n_ablation_tracks`、`t_stat_range`、`sign_flips`、`significance_flips`、`robust`
   - `publication_decay`：每个 track 的 `insamp_t_stat` / `postpub_t_stat` / `decayed`
   - `bridge_comparison`：`bridge_track`、`own_track`、`bridge_reproduces_paper`、`own_reproduces_paper`、`signal_implementation_agreement`
   - `spec_quality`：`weak_fields` 表格（`field_path | reason | disposition`）
   - `menu_deviations`：`unsupported_paper_fields` + `clamped_by_track`
5. **Config diff**（现有 `DiffView`，按 track 对）移到最下方，并标注
   `changed_stages` / `identification_level`。

每张卡片都要显示自己的 `identification_level` 徽章，因为这决定了这个数字
在论文写作里能不能被描述成因果关系。

Debug 区：原始 `comparison.json`（`JsonTree`），以及一个 `evidence_keys`
的扁平 key → value 查找框，同时也作为 step 8 的取数入口。

### Step 8 — Diagnosis

决定（用户已确认）：**直接渲染后端的 `diagnosis.md`** 作为主视图，让 UI
和论文写作共用同一套措辞/数字来源（`src/steps/step8_diagnosis/render.py`）。

主视图：

1. `status` 横幅（固定为 `llm_assisted_proposal`）+ `overall_tag` +
   `llm_model` + `generated_at`。
2. **渲染后的 `diagnosis.md`**（markdown → HTML，只读），里面已经包含
   结论、paper-vs-tracks 表、gap 表，以及每条 claim 对应的确定性句子 +
   证据引用 + identification level。
3. **Rejected claims 审计区**单独保留、用 destructive 样式（它在
   `diagnosis.json` 里；`render.py` 是否已经把它渲染进 markdown 需要先
   核实，避免重复展示）。

明确放弃：现在这版裸的 `claim.text` 列表。

需要先补的后端缺口：`diagnosis.md` 已经写盘、job result 里也返回了它的
路径，但**目前没有任何接口返回它的内容**（`backend/routers/diagnosis.py`
只暴露 `diagnosis.json`）。需要新增
`GET /api/sessions/{session_id}/steps/8/diagnosis.md`，返回
`{"content": str}`（或 `text/markdown`），读取 job 写入的同一个路径。

Debug 区：原始 `diagnosis.json`（`JsonTree`）。

## 需要新增的共享组件

| 组件 | 用于 | 作用 |
|---|---|---|
| `StepSection` | 全部 | 带标题、可选折叠状态的区块，统一主视图/Debug 区的分层结构 |
| `EvidenceCard` | 7 | 统一渲染 `{available, reason, identification_level, …}` 结构，含统一空态和 level 徽章 |
| `TrackComparisonTable` | 6、7 | 行 = track、列 = 指标，基准置顶，带 bridge/invalidated 徽章 |
| `KeyValueTable` | 3、4、5、7 | 分组的 label/value 展示，支持逐行 warn/destructive 样式 |
| `MarkdownView` | 8 | 经过消毒处理的 markdown 渲染器（不透传原始 HTML） |
| `ProvenancePanel` | 5、6 | 哈希 + runtime provenance + repair history，始终默认折叠 |

`StepOutputView.tsx` 现在已经约 250 行，这次改动之后无法维持单文件；
拆成 `frontend/src/components/steps/Step{3..8}Output.tsx`，
`StepOutputView` 简化为一个分发器加 `JsonTree` 兜底。

## 实施顺序

1. 后端：新增 `diagnosis.md` 内容接口（这是唯一需要的后端改动）。
2. 拆分 `StepOutputView` 为各 step 组件 + 新增 `StepSection`、
   `KeyValueTable`（暂不改变行为）。
3. Step 8（`MarkdownView`）—— 正确性收益最大、改动面最小。
4. Step 7（`EvidenceCard`、paper-vs-tracks 表、五张证据卡片、caveat）。
5. Step 6（`TrackComparisonTable`、batch 状态条）—— 复用 step 7 的表格组件。
6. Step 4（技术指标、warnings、repair 提示横幅）。
7. Step 5（累计净值切换、分样本期表、`ProvenancePanel`）。
8. Step 3（分组配置、菜单偏差面板）。

## 待确认的开放问题

- `render.py` 生成的 markdown 是否已经包含 rejected-claims 审计？如果是，
  step 8 就不再单独渲染这部分，避免重复。
- Step 6 的横向对比表基准 track，应该用 `derived.baseline_track`（只有
  step 7 跑完之后才知道）还是固定优先 `original_method`？倾向后者，
  这样 step 7 还没跑时 step 6 也能正常工作。
- Step 3 的 tool results（`column_mapping`）目前只是被渲染进 LLM
  prompt，并没有持久化，所以现在没法展示。要不要落盘（需要一个新的
  `tool_results.json` artifact）是一个独立的决定，不在本次范围内。
