---
type: plan
status: active
project: factor-replication-agent
created: 2026-08-02
tags: [plan, multi-config, evidence, run-identity, llm-boundary]
---

# 计划 —— 多配置运行、证据持久化与 LLM 对比分析

目标：让**同一个冻结的 agent 信号**在多套受控 backtest 引擎配置下运行，把每次
run 的结果**以及它的确切配置**作为唯一、可审计的证据持久化下来，然后在已算好的
**确定性对比**之上，叠加一个**可选、仅做解释**的 LLM 层。

实现顺序从 config/run identity 开始，再进入证据持久化、实验矩阵、外部参考契约、
确定性诊断和可选 LLM 解释。这样避免在证据模型稳定前引入无法审计的归因结论。

与 [replication-diagnosis-design.md](replication-diagnosis-design.md) 的 Phase
A–E 及 §1.1 LLM 使用边界保持一致。

---

## 1. 不可妥协的设计红线

- **LLM 边界（设计 §1.1）**：LLM 绝不产出任何进入结论的数字或 pass/fail 阈值。
  所有 metric、gap、相关性、以及分类的输入都由确定性代码给出。LLM 只**解释**已算好
  的数值，标记为 `llm_assisted`，可人工复核，且绝不回写 MethodSpec 或 config。
- **可复现**：每个上报数字都必须在关闭 LLM 时可复现，并可追溯到不可变的
  config + 序列 artifact。
- **受控归因**：两次 run 的差异，只有在**恰好一个**目标组件改变、其余部分可证明
  完全相同时，才可归因（设计 §5.2 的 identification level）。

---

## 2. 已核实的现状缺陷

以下断言均已于 2026-08-02 对照代码确认。

| # | 缺陷 | 证据 |
|---|---|---|
| D1 | 脚本与收益 CSV 路径只按 `factor_id` 命名，不同 track/config **互相覆盖**。 | `build_script` 用 `results/{factor_id}.csv` 与 `{factor_id}_backtest.py` —— `src/steps/step5_backtest_runner/__init__.py` |
| D2 | `run_id` 在 `make_run_record` 中、**执行之后**才生成，且不含 `config_hash`；而唯一路径必须在 `build_script` **之前**就确定。 | `src/steps/step5_backtest_runner/__init__.py` |
| D3 | config override **不被菜单钳制**：`build_config` 直接 `config.update(overrides)`，任意未知 key / 非法值静默通过。 | `src/steps/step3_codegen/registry.py`（`if overrides: config.update(overrides)`） |
| D4 | `lag` override 对信号是 **no-op**：生成脚本烘焙的是 `accounting_lag_months = spec.accounting_lag_months or 6`，而非 `CONFIG[...]`。 | `src/steps/step3_codegen/script_generator.py` |
| D5 | "冻结同一信号"不成立：每个 track 跑**各自**的 repair loop，track-local `repair_plugin` 会改变 `code_hash`，污染 config 归因。 | `src/infra/repair.py`、`DualTrackController._run_track` |
| D6 | `EvidenceStore.save_run(run)` 只写 `metadata.json`；`return_series_path` / `signal_series_path` / `data_snapshot_hash` 从不填充；不拷贝 config/script/plugin/MethodSpec 内容。 | `src/infra/evidence/__init__.py`、`src/infra/models/run_record.py` |
| D7 | `SnapshotMetadata.hash` 默认空字符串；没有定义 hash 规则；且 FF-factor 数据可能来自 snapshot 之外的共享 fallback。 | `src/infra/data_layer/__init__.py`、`build_script` 的 FF fallback |
| D8 | 信号序列**根本没被输出**——脚本只写 LS 收益 CSV。 | `src/steps/step3_codegen/script_generator.py` |
| D9 | Pipeline 调用了 `diff_ablation(runs)`，却**丢弃**返回值（不持久化、不返回）。 | `src/pipeline.py` |

> **与已实现机制的区分（2026-08-02 补充）：** `build_config` 现在还有另一条**已经
> 实现**的输出——`config["substitutions"]`，记录 MethodSpec 级别"论文明确说了某个
> 值，但不在引擎菜单"的替换（如 `weighting="capped_vw"` → 记录原值并钳成 `vw`；见
> `MethodSpec.unsupported_fields`、决策记录 2026-08-02）。这和 D3 是**两个不同的轴**：
> D3 是"实验声明的 config override 未被校验"，处理的是**我们自己发起**的实验配置；
> `substitutions` 处理的是**论文原文**里引擎做不到的方案。Phase 0.1 重写 config 解析
> API 时，必须**保留并透传**这个已有的 `substitutions` 输出，不能被新的
> `resolved_diff`/`validation_errors` 覆盖或遗漏——两者应在 `resolved_config` 里并存，
> 分属不同字段。

---

## 3. 编码前必须拍板的两个决策

以下必须显式选择；下面的阶段都假设已有结论。

### 决策 1 —— run 身份语义

- **方案 A（推荐）：每次执行唯一 ID。** 每次 run 分配一个 `execution_id`
  （如 ULID）；同时存所有内容 hash（`config_hash`、`code_hash`、
  `method_spec_hash`、`data_snapshot_hash`）。重跑同一实验会生成**新目录**，
  不覆盖任何东西。最利于审计。
- **方案 B：内容寻址。** 目录 = 所有输入的 hash；相同输入复用同一目录，且**禁止
  改写**。"相同输入 ⇒ 相同输出"的自证最强，但对有意重跑的碰撞需要显式策略。

推荐：**以方案 A 为主键，内容 hash 作为字段存储**——审计友好，同时仍能通过比对
hash 识别"相同输入的重跑"。

### 决策 2 —— per-key stage taxonomy + resolved-diff 校验（取代二元分类）

**不要**把"整套 config"分成 `portfolio-only` / `signal-input` 两类——factorial
可能同时改 lag 和 weighting，`formation_month`/universe/rebalance 等还可能横跨
多个阶段。真正需要分类的是**每个 config key 影响哪个阶段**，可比性由**两次 run 的
resolved-config diff-set** 自动决定。

给每个 config key 一份 spec：

```text
ConfigKeySpec(
    key="accounting_lag_months",
    stage="signal_input",              # signal_input | portfolio | universe | sample | estimator
    affects=("signal_availability",),
    validator=...,                     # 类型/取值范围/菜单成员
)
```

`stage` 的 5 个取值本身还分属**两大类**（这一分类，而不是逐个 stage，才是归因规则的
真正依据）：

- **pre-signal**（`signal_input`）：在信号计算**之前**生效，会改变 realized 信号；
- **post-signal**（`portfolio` / `universe` / `sample` / `estimator`）：都在信号计算
  **之后**才生效——universe 过滤、sample 截断、estimator 选择和 portfolio 构造一样，
  不改变某个 permno-month 的信号取值，只改变它是否/如何被用于组合构造。

比较时按 resolved diff-set 判定 identification level（design §5.2 词表：
`controlled` / `harmonized` / `observational` / `unidentified`）：

- diff 只有一个 **post-signal** key（不论具体是 portfolio/universe/sample/estimator
  哪一个）→ `controlled`，且 realized 信号序列的 **semantic hash 必须相等**
  （见 A1.3）；
- diff 只有一个 **pre-signal**（`signal_input`）key → `controlled`，归因到该输入处理，
  信号序列**允许变化**，只断言 plugin `code_hash` 相等；
- diff 同一大类里有**多个** key（例如同时改 weighting 和 breakpoint_source，都是
  post-signal）→ `unidentified`（signal 不变的保证还在，但不能给单组件归因）；
- diff **跨 pre/post 两大类** → `unidentified`，且**失去** signal 不变的保证；
- override 后 resolved value **没变** → 拒绝这个 no-op experiment。

可比性断言随之由 diff-set 推出（而非"整套 config 属于哪类"）：`controlled` 的
post-signal 比较用 **semantic hash 相等**强制；`controlled` 的 pre-signal 比较只
断言 plugin `code_hash` 相等。

这个 per-key 校验会**当场抓住现存 bug**：`HXZ_STANDARD_CONFIG` 里
`breakpoint_quantiles` 是百分位**列表**，而引擎执行 `int(config["breakpoint_quantiles"])`
（且该概念早已换成 `ls_quantile` 计数）——强类型校验会直接拒绝，而不是让
`standardized_hxz` 带病运行（见 §10 即时修复项）。

**"family" 和 "identification level" 是两个不同的轴，不要混用同一列展示**：

- **family**（`portfolio_ablation` / `signal_input` / `reference_bridge` /
  `data_vintage`）是**声明的实验类型**，写在 `ExperimentSpec` 上，人读起来方便；
- **identification level**（design §5.2 的 `controlled` / `harmonized` /
  `observational` / `unidentified`）是**由 resolved-diff 自动算出**的归因等级。

两者不一定一致：一个声明为 `portfolio_ablation` 的实验，如果它的 resolved-diff
其实同时改了 post-signal 和 pre-signal 的 key（比如 `standardized_hxz` 同时改了
weighting 又改了 accounting_lag），它的 family 仍是 `portfolio_ablation`，但
identification level 只能是 `unidentified`。报告和对比表必须把这两栏分开列，
不能拿 family 名字代替真正算出来的 level。

---

## 4. 分阶段计划

### Phase 0 —— config 解析 + run 身份（正确的第一刀）

**不要**从天真的 `make_run_record` 改动开始。从这里开始。

- **0.1 统一的 config 解析/校验 API**（放在 `registry`）：以 `ConfigKeySpec`
  注册表为基础（决策 2），返回结构化结果—— `requested_overrides`、
  `resolved_config`、`resolved_diff`（相对 baseline）、`validation_errors`、
  `warnings`。对未知 key、非法值、no-op override **直接拒绝**，而不是静默钳制
  （修 D3）。一个名为 `vw_experiment` 的 run 绝不能静默跑成默认值。
- **0.2 按 per-key `stage` 把 signal-input config 路由进 loader**（修 D4）：
  生成脚本必须从 resolved 的 `CONFIG` 读取所有 `stage="signal_input"` 的 key
  （如 `accounting_lag_months`），而不是从单独烘焙的 `spec.*` 常量。路由规则由
  `ConfigKeySpec.stage` 驱动，而非硬编码。
- **0.3 `RunContext` / `RunIdentity`**：在 `build_script` **之前**完成
  `resolve config → 计算 config_hash → 分配 execution_id + run_dir`，让脚本和
  输出写进唯一的 per-run 工作区（修 D1、D2）。同时分配 **matrix/batch 身份**：
  `experiment_batch_id`、`frozen_plugin_hash`、`baseline_execution_id`、
  `attempt_id`，使"同一轮、共享同一冻结输入"的 run 可被表达；矩阵失效时旧 batch
  标 `invalidated`，不与新 run 混比。
- **0.4 plugin 冻结策略**（修 D5）：在实验矩阵启动**之前**修好并冻结 plugin；
  矩阵运行期间**禁止** track-local repair；若某 track 暴露了真正必须修的技术性
  formula 错误，则**使整个 batch 失效**（标 `invalidated`），重新冻结后从头重跑
  全部 config。最低要求：断言所有可比 run 共享同一个 `code_hash`。
- **0.5 冻结 runtime provenance**（补：脚本非封闭）：生成脚本运行时
  `from src.infra.backtest_engine import BacktestExecutor`，因此"script 字节相同"
  **证明不了**"执行逻辑相同"。每次 run 必须记录：`lifecycle_commit` + dirty-worktree
  状态、engine/loader/registry 的 source hash（或整个运行代码包 hash）、Python 与
  关键依赖版本、OS/arch、实际执行命令、schema/engine version、外部 FF factor 文件的
  路径/hash/版本。`RunRecord.lifecycle_commit` 字段已存在但从未填充，纳入本阶段。

完成标准：两套不同 config 产出两个不碰撞的 run 工作区；非法/no-op override 被拒；
lag override 可证明地改变了信号 availability；所有可比 run 共享同一 `code_hash`；
每次 run 带完整 runtime provenance 与 batch 身份。

### Phase A1 —— 完整且唯一的 run bundle

- **A1.1** 脚本输出信号序列为 `signal.parquet`（`[permno, yyyymm, signal]`，
  校验：排序、唯一键、schema）——修 D8。firm-month 数据可能很大，优先 Parquet
  而非 CSV。**明确捕获阶段**：`signal.parquet` 记录的是 `compute_signal` 输出、
  完成 key/schema 规范化**之后**、进入任何 universe filter / breakpoint / portfolio
  步骤**之前**的 realized signal（否则 portfolio-only 配置可能因捕获阶段不同而
  改变 signal artifact）。
- **A1.2** 填充 `RunRecord`：`return_series_path`、`signal_series_path`、
  `config_hash`、`code_hash`、`method_spec_hash`、`data_snapshot_hash`，以及
  Phase 0 的 runtime provenance 与 batch 身份字段。
- **A1.3 两种 hash 分离，不要直接 hash Parquet 文件**：文件字节受 writer 版本 /
  metadata / compression / row-group layout 影响，内容相同也可能字节不同。定义：
  - `artifact_sha256` —— 文件完整性；
  - `series_semantic_hash` —— 规范化内容一致性：①只取定义列 ②固定 dtype
    ③固定缺失值表示 ④按主键排序 ⑤拒绝重复主键 ⑥规范化浮点表示 ⑦对规范化后的
    行内容取 hash。决策 2 的"信号序列相等"断言用的是 **semantic hash**。
- **A1.4** 定义 **snapshot hash** 规则（修 D7）：基于**本次 run 实际消费的输入
  manifest**（每个打开的文件记 `logical_role` / `resolved_path` / `content_hash` /
  `size` / `schema` / `source_version`），而不是 hash 整个 snapshot 目录——这样既
  不纳入无关文件，也能捕获 snapshot 外的 FF fallback。正式成功 run **禁止**空
  snapshot hash；开发运行最多允许 `status=non_reproducible`。
- **A1.5** 保存 **中间产物**（不只 signal + 最终 returns + metrics，否则只能证明
  "结果不同"、无法定位"差异在哪产生"）：

  ```text
  signal.parquet
  breakpoints.parquet
  assignments.parquet
  portfolio_returns.parquet
  returns.parquet
  diagnostics.json          # coverage / eligibility / microcap share …
  ```

  assignments 可能很大：提供 **configurable evidence level**——pilot 与 bridge run
  保存完整中间证据，bulk run 可精简。
- **A1.6** 扩展 `EvidenceStore`，改为接收显式 **artifact bundle**（修 D6），
  而不只是一个 `RunRecord`：

  ```text
  save_run(
      run_record,
      artifacts=RunArtifacts(
          resolved_config, methodspec, plugin, script,
          signal_path, breakpoints_path, assignments_path,
          portfolio_returns_path, return_path, metrics_path,
          diagnostics_path, logs_path,
      ),
  )
  ```

  要求：原子写入（先 staging 再 rename）；`RunRecord` 中的 path 指向 evidence
  root **内部**的 canonical artifact，并以 **evidence-root 相对路径**存储；记录
  每个 artifact 的 `artifact_sha256`；写入中途失败不得留下"success metadata +
  缺文件"；**失败的 run 也要持久化** config、script、logs。

完成标准：两套 config 的 artifact 永不碰撞；每个 metric 都能追溯到不可变、带
semantic+artifact hash 的 config + 序列 + 中间产物 + runtime provenance；失败 run
也保留完整证据。

### Phase A2 —— 命名实验矩阵

- 用能覆盖**全部实验输入**的显式模型（不只是 `config_overrides`——bridge 与
  data-vintage 实验还会改变信号 artifact / snapshot / reference version /
  harmonization 契约）：

  ```text
  ExperimentSpec(
      name="canonical_v1",
      family="portfolio_ablation",     # portfolio_ablation | signal_input | reference_bridge | data_vintage
      baseline_ref=...,
      config_overrides={...},
      signal_input_ref=None,           # bridge：换成 C&Z 信号
      snapshot_ref=None,               # data_vintage：换快照
      expected_diff={...},             # 预期 diff-set，与实际 resolved-diff 交叉校验
  )
  ```

  这样到 bridge/data 阶段不必再次扩 API。
- **A2.1 实验矩阵的声明/存储层（目前完全缺失，必须先补）**：现状是
  `ExperimentPlan` 只在 Python 代码里硬编码构造
  （`pipeline.py` 的 `ExperimentPlan(factor_id=factor_id)`、测试代码里直接构造），
  Streamlit 面板上的 override 控件（`ov_nq`/`ov_bp`/`ov_wt`/…）是一次性手动调试，
  不进证据链、不可版本化。改为**每个因子一份实验矩阵文件**，与 MethodSpec 同级：

  ```text
  experiments/<factor_id>.experiments.yaml
  ```

  ```yaml
  factor_id: cooper_gulen_schill_2008_asset_growth
  baseline: original_method        # 隐式 ExperimentSpec，config_overrides={}
  experiments:
    - name: standardized_hxz
      config_overrides: {breakpoint_source: nyse, weighting_rule: vw, ls_quantile: 0.1,
                          rebalance_frequency: monthly}
    - name: ablation_weighting_ew
      config_overrides: {weighting_rule: ew}
    - name: ablation_lag_12
      config_overrides: {accounting_lag_months: 12}
    - name: bridge_cz_signal
      signal_input_ref: "cz:AssetGrowth"
      config_overrides: {}
  sweep:                            # 可选：声明式 grid，自动展开成多个 ExperimentSpec
    - keys: [weighting_rule, breakpoint_source]
      values: {weighting_rule: [ew, vw], breakpoint_source: [nyse, full_sample]}
  ```

  要点：
  - **`family` 不手写**：loader 对每条 `config_overrides` 过一遍 `ConfigKeySpec`，
    从 resolved-diff **自动算出** family 归属和 identification level（修正
    "手写 family 和实际 diff 对不上"的问题，见决策 2 末尾说明）；
  - **加载即校验**：整份 yaml 一次性过 `ConfigKeySpec` 注册表，未知 key / 非法值 /
    no-op override 在解析阶段就整份拒绝，不必等某个 run 跑到一半才报错；
  - **`sweep` 自动展开**：声明 key×value 网格，代码做笛卡尔积展开成若干
    `ExperimentSpec`，真正落地 factorial（不再是现在这种只存开关名、没有取值网格的
    `factorial_switches: list[str]`）；
  - **矩阵文件本身是证据**：对它算 `experiment_spec_hash`，存进每条
    RunRecord/batch——"这一批声明要跑什么"本身是可复现输入的一部分；
  - Streamlit UI 改为**编辑/触发**这份文件，而不是 ad hoc 控件状态。
- 同一轮里把已声明但从未执行的 `factorial_switches` 也实现掉，不要留两套半成品接口。
- 按决策 2 用**实际 resolved-diff** 推可比性断言并与 `expected_diff` 交叉校验
  （不符即拒绝，避免"名字说改 weighting、实际改了别的"）。
- batch 语义：一个 `experiment_batch_id` 下所有 run 共享 `frozen_plugin_hash`；
  任一 track 触发失效 → 整 batch 标 `invalidated`，新旧不混比。

### Phase B —— 外部证据契约与版本治理（显式独立阶段）

（从原 C/D 里拆出来——reference adapter 是"外部证据契约 + 版本治理"，不应和
comparison 实现混在一起。）

- factor→C&Z manifest schema；
- 把 SignalDoc 解析成规范化的 reference profile；
- 下载/版本化 C&Z firm-level 信号 + LS 收益；
- 实现信号/收益 adapter，带单位/符号/hash 与 reference version 元数据。

完成标准：AssetGrowth 的 reference 信号与收益序列能通过稳定契约加载，且**不进入**
提取或代码生成。

### Phase C/D —— 确定性对比 + bridge 实验

（仅在 A1/A2/B 产出稳定、带 hash 的证据之后。）

- 确定性**对比 bundle**：跨 config 的 metrics 表、resolved-config diff、pairwise
  gap（收益 / t-stat 差）、每对比较的 identification level——**无 LLM**。
- **bridge 实验（E2）**：C&Z 信号 × 我们引擎，与 agent run 同一 config，用以分离
  信号实现 vs portfolio 效应。
- matched-sample 的信号 + 收益对比；对存在差异的设置做两端 OAT；对交互做条件
  factorial；每条推断的贡献都记录 **identification level**。
- 持久化 report 并**从 Pipeline 返回**（修 D9）；不再丢弃 `diff_ablation` 的结果。
- 版本化复现/判定阈值。
- **"vs 论文/C&Z 发布值"对比必须挂替换 caveat**：任何因子的 `resolved_config`
  含非空 `substitutions`（见 §2 补充说明），其与论文报告数字或 C&Z 发布收益的
  `observational` 对比，都必须显式标注"该字段被替换为引擎默认值"，不得报告为
  单纯的复现失败或成功。**跨 config 的内部对比不受影响**——替换是该因子所有
  run 的共同起点，不进入任何两个 run 之间的 diff。

### Phase E —— 可选 LLM 解释（最后做）

- **只**消费已持久化、带 hash 的诊断 report。
- **不**新建一套平行的顶层 `DiffExplanation` 模型；把 LLM 叙述作为
  `ReplicationDiagnosisReport` 上的**可选附属字段**。
- LLM 契约（替代天真的"断言不含数字"守卫）：
  - LLM 输出**结构化 narrative fragment**；每条 claim 必须引用确定性 bundle 中的
    `evidence_key`；
  - 数字由**确定性 renderer** 从 bundle 插入，不由 LLM 书写；
  - **每种 claim type 定义允许引用的 evidence schema**，而不只是检查 `evidence_key`
    存在——例如"信号实现接近"这类 claim 必须同时具备 matched-sample signal
    correlation、rank agreement、sign disagreement、coverage overlap 才允许，
    组合收益接近**不**足以支撑；"显著"只能在确定性统计检验 + 阈值通过时使用；
  - 分类标记为 `llm_assisted_proposal`，绝不作为自动 empirical 结论；人工确认后的
    分类另存，且绝不回写 config/MethodSpec。

完成标准：确定性 report 的 hash 在 LLM 开/关时**完全相同**；LLM 仅额外增加一份
`llm_assisted` 叙述。

---

## 5. 为什么不先做原版 2.1 + 2.2

`run_id` 在 `make_run_record`（执行后）生成，无法命名执行前的 script/output 路径；
而 `{factor}_{track}_{config_hash}_{code}` 在有意重跑时仍会碰撞。先提交那种形态，
会固化一套 Phase 0/A1 必须立刻推翻的 run-identity API。Phase 0（config 校验 +
`RunContext` + per-execution 唯一目录 + plugin 冻结）才是最小且正确的第一刀；
artifact persistence 建立在它之上。

---

## 6. 测试计划（集成优先）

fake-runner 测试抓不到真实的路径覆盖。至少补充：

- 真实 `BacktestRunner`：两套 config ⇒ script / metrics / return / signal 路径
  各不相同；
- 相同 track+config 连跑两次 ⇒ 仍不覆盖（按决策 1）；
- 未知 / 非法 override ⇒ 被拒绝；
- track name 含 `../` 或路径字符 ⇒ 不能逃出 run 目录；
- 所有可比 `portfolio_ablation` run 共享同一 `code_hash`；
- lag override 可证明地改变信号 availability（信号序列不同）；
- 每个 artifact 记录的 hash 与文件内容一致；
- `EvidenceStore` 写入中途失败不留下"success metadata + 缺文件"半成品；
- 失败 run 同样持久化 config、script、logs；
- Pipeline 持久化并返回 step-7 report；
- 确定性 report hash 在 LLM 关 vs 开时完全一致。

---

## 7. 仓库强制 workflow

- 每个阶段的每次改动都更新 `CHANGELOG.md`。
- 在 `docs/decision-log.md` 记录重大决策：
  - run 身份语义 + matrix/batch 身份（决策 1）；
  - **per-key stage taxonomy + resolved-diff 校验**（决策 2，取代二元分类）；
  - runtime provenance + semantic hash + signal 捕获阶段；
  - plugin 冻结 / batch 失效策略；
  - LLM 分类边界（`llm_assisted_proposal`、claim-type→evidence-schema 契约）。
- 优先做定向读取和窄测试；绝不 `git add .`。

---

## 8. 顺序总览

1. 锁定**决策 1 与 2**。
2. **Phase 0** —— typed config resolution + effective-diff 校验 + signal-input
   路由 + `RunContext`/batch 身份 + frozen runtime provenance + plugin 冻结。
3. **Phase A1** —— signal/中间产物 artifact + semantic/artifact hash + 完整
   provenance + 原子 EvidenceStore ingest。
4. **Phase A2** —— `ExperimentSpec` 命名矩阵 + factorial + batch 语义。
5. **Phase B** —— 外部证据契约与版本治理（C&Z manifest / adapter）。
6. **Phase C/D** —— 确定性对比 + bridge + 持久化并返回 report。
7. **Phase E** —— 在带 hash 的 report 之上做可选 LLM 解释。

---

## 9. 端到端示例：Asset Growth（Cooper–Gulen–Schill 2008）

以仓库现成的 pilot 因子走一遍，展示"输入一篇论文 → 得到什么"。

> 数字说明：标 **[参考]** 的取自 [replication-diagnosis-design.md](replication-diagnosis-design.md)
> §12（论文/C&Z release 的真实数字）；标 **[示意]** 的是产物**形态**的占位值，
> 真实数值取决于所用数据快照，不是复现结论。

### 9.1 输入

- **论文 PDF**：Cooper, Gulen & Schill (2008), *Asset Growth and the
  Cross-Section of Stock Returns*。
- 仅论文原文进入 Step 1；`SignalDoc.csv` 绝不进入提取（避免泄漏）。

### 9.2 Step 1–2：提取 + 审阅后的 MethodSpec（关键字段）

```yaml
factor_id: cooper_gulen_schill_2008_asset_growth
signal.formula: (at - at_lag12) / at_lag12       # 年度总资产增长率
sign: -1                                          # 高增长 → 低预期收益
signal.timing: {formation_month: 6, holding_period: 12, accounting_lag: 6}
portfolio: {breakpoint_source: nyse, ls_quantile: 0.1, weighting: vw, long_leg: low, short_leg: high}
reported_results: {main_spread≈0.0105, main_t_stat≈5.04, sample: 1968–2002}   # [参考] VW year-1 raw monthly
```

### 9.3 冻结信号 + 声明实验矩阵（Phase 0/A2）

plugin 先修好并**冻结**（同一 `code_hash`），随后按 `experiments/<factor_id>.experiments.yaml`
（见 A2.1）声明的矩阵运行：

```yaml
factor_id: cooper_gulen_schill_2008_asset_growth
baseline: original_method
experiments:
  - name: standardized_hxz
    config_overrides: {breakpoint_source: nyse, weighting_rule: vw, ls_quantile: 0.1,
                        rebalance_frequency: monthly}
  - name: ablation_weighting_ew
    config_overrides: {weighting_rule: ew}
  - name: ablation_lag_12
    config_overrides: {accounting_lag_months: 12}
  - name: bridge_cz_signal
    signal_input_ref: "cz:AssetGrowth"
    config_overrides: {}
```

`family` 与 identification level **不手写**，由 loader 对每条 `config_overrides`
过一遍 `ConfigKeySpec` 后从 resolved-diff 自动算出（见 §9.5）：
`ablation_weighting_ew` 的 diff 只有 1 个 post-signal key → `controlled`，信号序列
semantic hash 须相等；`ablation_lag_12` 的 diff 只有 1 个 pre-signal（`signal_input`）
key → `controlled`，信号允许变，只断言 plugin `code_hash` 相等；`standardized_hxz`
同时改了 weighting/breakpoint/rebalance 等**多个** post-signal key → `unidentified`。

### 9.4 每个 run 产出的证据 bundle（Phase A1）

```text
evidence/cooper_gulen_schill_2008_asset_growth/<execution_id>/
├── metadata.json          # RunRecord：execution_id + 全部内容 hash + path
├── provenance.json        # lifecycle_commit/dirty、engine source hash、py/deps 版本…（0.5）
├── resolved_config.json
├── methodspec.json
├── plugin.py
├── backtest.py
├── signal.parquet         # [permno, yyyymm, signal]（修 D8，A1.1 定义的捕获阶段）
├── breakpoints.parquet    # pilot/bridge 保存完整中间证据（A1.5）
├── assignments.parquet
├── portfolio_returns.parquet
├── returns.parquet        # 月度 long/short/LS
├── diagnostics.json       # coverage / eligibility / microcap share
├── metrics.json
└── logs.txt
```

每条 metric 都能回溯到不可变、带 hash 的 config + 序列 + 中间产物 + runtime
provenance；失败 run 也留 config/script/logs。

### 9.5 确定性对比 bundle（Phase C，无 LLM）

代码算出的跨 config 表（数值 **[示意]**，形态为真）。`family` 是声明值，
`identification level` 是从 resolved-diff **自动算出**——两栏分开列，不混用
（§3 决策 2 末尾说明过为什么不能合并）：

| 实验 | 加权 | LS 月均 | t-stat | vs original Δ | family | identification level |
|---|---|---|---|---|---|---|
| original_method | VW | 1.05% | 5.0 | — | baseline | — |
| ablation_weighting_ew | EW | 1.68% | 7.9 | +0.63% | portfolio_ablation | `controlled`（diff 仅 1 个 post-signal key） |
| standardized_hxz | VW | 0.90% | 4.6 | −0.15% | portfolio_ablation | `unidentified`（diff 含多个 post-signal key，须逐项拆） |
| ablation_lag_12 | VW | 0.98% | 4.7 | −0.07% | signal_input | `controlled`（diff 仅 1 个 pre-signal key，信号允许变） |
| bridge_cz_signal | VW | 1.02% | 4.9 | −0.03% | reference_bridge | `harmonized`（隔离信号实现差异，数据未必逐字节对齐） |

同时附**外部参考**（下载/摘录，非我们跑）：

- **[参考]** SignalDoc 论文 EW：1.73%，t≈8.45；论文 VW：≈1.05%，t≈5.04。
- **[参考]** C&Z release（1952–2024）：op/EW deciles LS ≈0.905%；VW deciles ≈0.374%。
  identification level = `observational`。

### 9.6 可选 LLM 解释输出（Phase E）

LLM **只**消费 §9.5 的确定性 bundle，输出结构化叙述 + 提案分类。**每条 claim 受
claim-type→evidence-schema 约束**：只有 bundle 里具备该 claim 允许引用的证据字段
时才成立（不只是"evidence_key 存在"）。注意下面的措辞都**未越权**——不写"显著"
（除非确定性检验+阈值通过）、不从组合收益接近推断"信号实现接近"（那需要
matched-sample 的 signal correlation/rank/coverage，本 bundle 尚无）：

```json
{
  "source": "llm_assisted_proposal",
  "input_bundle_hash": "…",
  "narrative": [
    {"claim": "EW 相对 VW 的利差更大；该结果与规模权重的影响一致。",
     "claim_type": "delta_direction",
     "evidence_key": "delta.ablation_weighting_ew.ls_mean"},
    {"claim": "bridge 与 original 的组合收益接近；能否称信号实现接近，需 signal-level 证据（本 bundle 尚无）。",
     "claim_type": "return_proximity_only",
     "evidence_key": "gap.bridge_cz_signal.vs_original"}
  ],
  "classifications": [
    {"target": "original_vs_ew", "label": "config_driven"},
    {"target": "agent_vs_cz", "label": "return_proximity_pending_signal_metrics"}
  ]
}
```

数字由确定性 renderer 从 bundle 插入，LLM 不书写数值；分类是 `proposal`，人工确认后
另存，**绝不**回写 config/MethodSpec。要把 `agent_vs_cz` 升级为真正的
`signal_agreement`，必须先有 Phase B/D 的 matched-sample signal correlation、rank
agreement、sign disagreement、coverage overlap。

### 9.7 关键性质

关掉 LLM，§9.2–§9.5 的所有数字与对比 bundle 的 hash **完全不变**；LLM 只多产一份
`llm_assisted` 叙述。这就是"LLM 帮助解释，但不控制任何实证结论"的落地形态。

---

## 10. 即时修复（独立于 plan，现在就坏）

> 与分阶段计划解耦：以下是当前代码的存量 bug，应尽快单独修，并补真实运行测试。

- **`HXZ_STANDARD_CONFIG["breakpoint_quantiles"]` 类型/概念错误**：它是百分位
  **列表** `[10,…,90]`，而引擎执行 `int(config["breakpoint_quantiles"])`
  （[backtest_engine](../src/infra/backtest_engine/__init__.py) 第 736/795 行），
  且该 knob 早已换成 `ls_quantile`（float 计数，见 CHANGELOG）。因此
  `standardized_hxz` track 在真实运行时很可能直接崩。
- **测试缺口**：`test_dual_track_controller` 用 fake runner，跑不到引擎那行
  `int()`，所以没抓到。补一个**真实 `BacktestRunner`** 的 `standardized_hxz`
  冒烟测试。
- 修法与决策 2 一致：把 `breakpoint_quantiles` 从 `HXZ_STANDARD_CONFIG` 移除或改为
  正确的 `ls_quantile`，并由 `ConfigKeySpec` 校验器保证类型/取值合法。
