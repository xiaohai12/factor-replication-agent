# Step 6（`MultiTrackController`）—— 当前设计与待讨论问题

范围：`src/steps/step6_dual_track_controller/__init__.py` +
`experiment_spec.py`。只读梳理，尚未改动代码。

## 1. 它是什么

一个多轨道批次编排器。给定一个已验证的 `PluginRecord`（一份
`compute_signal`）+ 一份已 resolve 的 `MethodSpec`，对每一个 config
override（"轨道"）跑一次 Step 5（build script -> execute），最后写出一份
聚合的 `comparison.json`。核心不变量：跨轨道只有 config 变化，代码永不变
——这样任何实证差异都能归因到某个配置开关上。

## 2. 两个入口，一套执行实现

- `run_experiment(plugin, spec, plan: ExperimentPlan, snapshot_id)` ——
  遗留的 Python 构造入口。现在只是一个薄适配器：`_plan_to_matrix` 把
  `run_standardized` / `ablation_switches` / `factorial_switches` 转成
  resolved 的 `ExperimentSpec` 列表。
- `run_from_matrix(plugin, spec, matrix, snapshot_id, run_baseline=True)`
  —— 声明式入口，读取 `experiments/<factor_id>.experiments.yaml`。

两者共用同一套实现：批次/plugin 冻结记账、`comparison.json` 写出、
bridge 轨道处理。

## 3. 轨道类型

| 轨道 | 来源 |
|---|---|
| `original_method` | 无 override 的基线（由 `run_baseline` 控制是否跑） |
| `standardized_hxz` | 整包 `HXZ_STANDARD_CONFIG` override（手工策展，非自动推导） |
| `ablation_*` | 单开关翻转，走 `_ABLATION_SWITCH_TO_CONFIG_KEY` |
| `factorial_*` | 对 n 个开关做 {baseline 值, HXZ 值} 的 2^n 笛卡尔积，去掉全 baseline 角，并按名字去重 |
| bridge 轨道 | `signal_input_ref: "cz_bridge[:factor_id]"`，由 `_run_bridge_track` 处理 |
| sweep | 仅 yaml 路径，`_expand_sweep` 做笛卡尔展开 |

`HXZ_STANDARD_CONFIG` 与 step2 的 `SENSIBLE_DEFAULTS` 是两个不同概念：
step2 是给论文没提到的字段填入字段级惯例（保持对论文的忠实）；step6 的
标准则是故意把论文覆盖成统一的"房屋标准"。两者可以合理地不一致（例如
rebalance 一个是 annual，一个是 monthly）。

## 4. 声明式矩阵的校验哲学（`experiment_spec.py`）

- `family` / `identification_level` / `resolved_diff` 一律派生，绝不允许
  在 yaml 里手写。恰好 1 个 resolved-config key 不同 -> `controlled`；
  0 个或 >1 个 -> `unidentified` / 拒绝。
- 整个文件在 load 时通过 `registry.build_config` 校验（未知 key /
  菜单外取值都会 raise）。一条坏实验会让整个文件加载失败。
- no-op 实验（resolved config 与 baseline 完全相同）在 load 时被拒绝。
- 若给出 `expected_diff`，会与真实 diff 交叉核对——专门捕捉"菜单 clamp
  悄悄抵消了我的 override"这类 bug。
- `experiment_spec_hash` —— 声明矩阵本身的内容哈希，被视为运行可复现
  身份的一部分。
- 明确记录为未实现：`baseline_ref` 链式基线、`snapshot_ref` 数据
  vintage 解析——这些会被记录并跳过（`skipped_experiments`），而不是
  静默丢弃。

## 5. Auto-freeze（Phase 0.6）—— `_run_tracks_with_freeze`

1. Pass 1：所有轨道跑一遍，允许修复（`self.repair_loop`）。
2. 检查每个成功轨道的 code_hash 是否仍等于该批次最初冻结的 plugin
   哈希。
3. 如果有轨道漂移（某次修复改变了其代码）：选择第一个漂移轨道（按
   `track_specs` 顺序）所使用的 plugin，把整个批次重跑一遍，全部对齐到
   这个重新冻结的 plugin，且禁止修复（`_frozen_repair_loop`，底层是
   `_NoRepairMetaCoder`，其 `llm_client = None`——`RepairLoop` 正是检查
   这个属性来决定是否尝试修复）。这一轮要么收敛，要么某轨道直接判定
   失败——绝不会出现"成功但仍然漂移"的情况。
4. 由 `max_refreeze_attempts`（默认 1）限界。
5. 当 `len(track_specs) <= 1` 时永不触发 refreeze——一致性是跨轨道属性，
   单轨道没有对比对象。

实际后果：在默认 `max_refreeze_attempts=1` 下，`batch_invalidated=True`
只有在调用方显式传 `max_refreeze_attempts=0` 时才会触发。

## 6. Bridge 轨道 —— `_run_bridge_track`

计算一个 C&Z 参考信号，落盘为 parquet，通过
`build_script(..., precomputed_signal_path=...)` 注入——完全绕过 agent
自己的 `compute_signal`，但复用完全相同的下游 config 与引擎。这样可以把
"信号实现差异"和"组合构建差异"分离开。若没有注册对应 bridge ->
返回 `None`，记入 `skipped`，不算失败。不走 `RepairLoop`（外部提供的
信号没什么可让 LLM 修的）。`code_hash = "cz_bridge:<factor_id>"`，
`is_bridge_track=True`，在 `_finalize_batch` 的"跨轨道代码一致性"检查
中被排除。

## 7. `_finalize_batch`

给每个 `RunRecord` 打上 `experiment_batch_id` / `frozen_plugin_hash` /
`batch_invalidated` / `batch_invalidation_reason`。构建 `tracks_summary`
（每条轨道的 resolved config + metrics + `is_bridge_track`）。通过
`runner.write_comparison_summary` 写出 `comparison.json`，包含
`safe_diff_ablation(runs)` 与批次元信息。可选调用 step8 诊断器
（best-effort，失败也绝不影响已落盘的实证产物）。

## 8. 待讨论问题

1. **命名（已改）** —— `DualTrackController` / `step6_dual_track_controller`
   已经不再是"双轨"了，实际是一个 N 轨道矩阵执行器。**已重命名为
   `MultiTrackController`**（类名，通过 rename symbol 完成，模块目录名
   `step6_dual_track_controller` 暂保留，因为改目录名涉及导入路径，
   影响面更大，未随此次改动一并处理）。
2. **两个入口的长期归宿** —— `ExperimentPlan` 已经是薄适配器，是否应该
   降级为测试夹具，只保留 yaml 矩阵作为生产路径？
3. **refreeze 的仲裁方式是否武断** —— "选第一个漂移轨道的 plugin"作为
   新冻结代码，在多个轨道各自漂移到不同代码时缺乏方法论依据。是否应该
   改成：任何漂移都直接判批次失败，交由人工复核，而不是自动选一个
   "赢家"？
4. **`batch_invalidated` 事实上是死代码路径** —— 默认参数下永远不会
   触发（除非调用方传 `max_refreeze_attempts=0`，而目前没有调用方这样
   传）。要不要让它变得可达，还是干脆承认它目前只是文档/保险机制？
5. **skipped 实验的可见性** —— `snapshot_ref` 和非 `cz_bridge` 的
   `signal_input_ref` 条目只会进入 `skipped_experiments`，绝不会让批次
   失败。如果矩阵声明了 10 个实验但只跑了 4 个，是否应该更醒目地
   报警（例如设置警告/失败阈值），而不是安静地记一个列表？

## 下一步

从以上任选一点深入讨论，之后再考虑代码改动。
