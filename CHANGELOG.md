# Changelog

## [Unreleased]

### Added

- **v1 `MethodSpec` 完全删除**（`src/infra/models/method_spec.py` 已不存在）。
  论文优先 schema（`PaperMethodSpec`/`MethodReview`/`ImplementationResolution`/
  `ResolvedMethodSpec`，`src/infra/models/paper_method_spec.py`）现在是仓库里
  唯一的 MethodSpec 模型。所有 `isinstance(spec, ResolvedMethodSpec)` 双分派
  分支都已收敛为单一路径：`registry.build_config`、`MetaCoder.
  generate_plugin`/`_build_prompt_from_resolved`、`script_generator.
  pick_signal_input_mode`/`generate_backtest_script`、`step4_validator.
  validate`、`step5_backtest_runner`（`_spec_factor_id` 等 4 个辅助函数简化为
  直接属性访问）、`step6_dual_track_controller` + `experiment_spec.py`、
  `RepairLoop`、`Pipeline.run_from_method_spec`/`_build_validation_slice`、
  `assemble_signal_master_table`、`backend/spec_parsing.py`、`app.py` 的
  MetaCoder/Backtest 页面 spec 选择器。
  **整体删除**（无 v2 等价物，且已确认无其他引用）：`SemanticExtractor`
  （`step1_extractor/__init__.py` 清空为占位说明）、`ReviewGate` +
  `resolution.py`（`apply_decisions`）+ `field_help.py` + `cz_suggest.py`
  （`step2_reviewer/__init__.py` 同样清空）、`field_contract.py`、
  `Pipeline.run_full_pipeline`/`PipelineStatus`/`MAX_REEXTRACT`、
  `backend/routers/methodspecs.py`、`backend/routers/evaluations.py`（连带
  `scripts/run_extraction_eval.py`）、`scripts/{extract_methodspecs,
  resolve_review_blocks,review_methodspecs,validate_methodspecs,
  run_real_asset_growth_experiment}.py`、`src/evaluation/helpers.py`
  （唯一还有用的 `load_signaldoc` 迁到了 `src/infra/reference/__init__.py`，
  它自己的 C&Z reference profile 逻辑的唯一消费者）。`backend/routers/
  sessions.py` 的 step1(extract)/step2(review/resolve) 端点整体删除——
  session 现在从 step3（脚本构建）开始，没有 session 内的抽取/评审 UI 流程了，
  只有独立的 `backend/routers/paper_methodspecs.py` API + app.py 的
  "Paper-First Workflow" 页面。
  **测试文件**：删除 ~18 个纯 v1 专属测试文件（`test_extractor.py`、
  `test_field_contract.py`、`test_formula_symbol_coverage.py`、
  `test_holding_period_derivation.py`、`test_llm_enum_false_positive_filter.py`、
  `test_meta_coder_prompt.py`、`test_method_spec_sign_validation.py`、
  `test_no_default_source.py`、`test_reextraction_loop.py`、
  `test_resolution.py`、`test_reviewer_silent_defaults.py`、
  `test_unsupported_fields.py`、`test_pipeline_status_artifacts.py`、
  `test_evaluations_api.py`）；5 个被 `_resolved_method_spec` 姊妹版本取代的
  e2e 测试文件重命名为规范名（`test_mvp_e2e.py`/
  `test_execute_data_path_override.py`/`test_bridge_track_e2e.py`/
  `test_accruals_e2e.py`/`test_real_wrds_samples_e2e.py`，v1 原版删除）；
  合并 `test_step_diagnostics.py`（原 step1/2 v1 专属类删除，step3/4 换成
  `asset_growth_resolved_spec()`，step5-8 本就与 spec 无关，原样保留）；
  修复 `test_experiment_replication_diagnosis_api.py`/`test_session_api.py`/
  `test_backend_api.py`/`test_signal_master_multisource.py`/
  `test_bridge_track_wiring.py`/`test_llm_normalized_mapping.py` 等混合内容
  文件里残留的 v1 fixture 构造；`tests/_spec_test_helpers.py` 的
  `asset_growth_resolved_spec()` 新增 `factor_id` 参数（多 session 测试要求
  同一经济学场景下有不同 factor_id 避免 RunRegistry 碰撞）。
  全量套件 483 passed / 18 skipped（较之前的 630 减少是因为删除了纯 v1
  专属测试，不是回归——每一步都验证过 0 failure），`ruff check --select
  F401,F821,F811` 全绿。Streamlit 应用烟雾测试通过。
  **已知未验证/未跟进的缺口（有意不做，明确告知用户）**：React 前端
  （`frontend/src/`）仍在调用已删除的 `/api/methodspecs/*`、
  `/api/evaluations/*`、`/api/sessions/{id}/steps/1/extract*`、
  `/api/sessions/{id}/steps/2/review*` 端点（`sessionApi.ts`、`steps.ts`、
  `BacktestExperimentsPage.tsx`、`PipelineE2EPage.tsx`、
  `SchemaReferencePage.tsx`、`SessionDetailPage.tsx`）——本轮完全没有触碰
  前端代码，这些调用点现在会 404。

- 黄金数值 e2e 测试迁移收尾（6/6 全部完成）：新增
  `tests/_spec_test_helpers.accruals_resolved_spec()`（Sloan 1996 accruals，
  6 个 SIGNAL_INPUT concept 映射到 comp_funda 的 act/lct/che/dlc/dp/at，
  与 v1 fixture 同样复用 asset_growth 的黄金数值/合成数据，`build_config`
  逐字段核对一致）+ `test_accruals_e2e_resolved_method_spec.py`（golden
  numbers 匹配 `rel=1e-9`）。发现 `test_real_wrds_samples_e2e.py` 其实
  **并未被跳过**——`data/local/validation_sample/` 真实样本数据本机已存在，
  之前误判为"依赖不存在的私有数据"；该文件只是 smoke test（不校验黄金数值，
  只断言 n_months>0/非 NaN），且只调用已双分派的
  `assemble_signal_master_table`/`registry.build_config`，属于低风险快速
  转换：新增 `test_real_wrds_samples_e2e_resolved_method_spec.py`（复用
  `asset_growth_resolved_spec()`，对真实 WRDS 样本 CSV 跑通)。
  全量套件 630 passed / 26 skipped，无回归。至此 6 个黄金数值 e2e 测试
  全部有了 `ResolvedMethodSpec` 姊妹版本（v1 原文件保留不动，双轨并存）。

- 黄金数值 e2e 测试迁移（4/6）：新增 `tests/_spec_test_helpers.
  asset_growth_resolved_spec()`——与 v1 committed fixture
  `cooper_gulen_schill_2008_asset_growth.resolved.methodspec.json` 经济学完全
  等价的 `ResolvedMethodSpec`（formation_month=6、年度调仓、6 个月会计滞后、
  vw、10 分位、long=最低/short=最高资产增长分位；`build_config` 解析出的
  config dict 逐字段核对与 v1 一致），复用同一个 `compute_signal` 插件
  （spec 无关代码）。新增 4 个 `*_resolved_method_spec.py` 姊妹测试文件：
  `test_mvp_e2e_resolved_method_spec.py`（通过 `Pipeline.run_from_method_spec`
  跑出与 `expected_metrics()` 完全一致的黄金数值，`rel=1e-9`）、
  `test_execute_data_path_override_resolved_method_spec.py`（`BacktestRunner.
  build_script`/`execute` 的数据路径覆盖机制）、
  `test_bridge_track_e2e_resolved_method_spec.py`（C&Z bridge track 真实
  subprocess 执行）、`test_step_diagnostics_resolved_method_spec.py`
  （`diagnostics.step3_diagnostics`/`step4_diagnostics`，均是 spec-agnostic
  下游对象，只需换 fixture）。全量套件 626 passed / 26 skipped，无回归。
  **未迁移**：`test_accruals_e2e.py`（不同因子/公式，需要一套新的多字段
  accruals fixture，本轮未做）、`test_real_wrds_samples_e2e.py`（依赖本机
  不存在的真实 WRDS 私有数据，当前本就是 skipped，无法在本地验证转换是否
  正确，未做）。`test_step_diagnostics.py` 的 step1/step2 诊断测试仍保留
  v1——`step1_diagnostics`/`ReviewGate` 用的是 v1 专属的 `ambiguous_fields`/
  评审概念，没有 v2 等价物。

- `src/pipeline.py`/`src/infra/data_layer/sources.py` 双分派收尾：
  `Pipeline.run_from_method_spec`/`_build_validation_slice` 的 `spec` 类型
  加宽为 `MethodSpec | ResolvedMethodSpec`（本就只调用已双分派的
  `MetaCoder.generate_plugin`/`RepairLoop`/`BacktestRunner.*`，唯一的真实
  v1 专属读取是 `_build_validation_slice` 里的
  `spec.data.normalized_mapping`，现按 isinstance 分派到
  `resolution.concept_mapping`）。`assemble_signal_master_table` 新增
  ResolvedMethodSpec 分支（复用 `script_generator.
  signal_input_sources_from_resolved` + `registry.build_config` 取
  `accounting_lag_months`，而不是 v1 的 `signal_input_sources`/
  `spec.accounting_lag_months`）。新增
  `tests/test_signal_master_multisource.py::
  test_master_table_dispatches_on_resolved_method_spec`（复用已有的
  synthetic `test_papers_v1` 数据）。`tests/_spec_test_helpers.py` 的
  `minimal_resolved_spec` 新增 `concept_source`/`concept_column` 参数。
  全量套件 619 passed / 26 skipped，无回归。
  **`Pipeline.run_full_pipeline`（含 `SemanticExtractor`/`ReviewGate` 的
  完整 v1 提取-评审循环）、`src/evaluation/diagnostics.py` 的
  `step1_diagnostics`（依赖 v1 专属的 `ambiguous_fields`/
  `reextraction_attempts`）、`src/evaluation/helpers.py`（提取准确率评估，
  整体对标 v1 `SemanticExtractor`）、`scripts/*.py`（extract/review/
  resolve/validate 系列 CLI，均是 v1 工作流专属工具，没有 v2 版本）判定为
  没有 v2 等价概念、有意保留 v1，直到 v1 整体删除或未来单独做"v2 版
  CLI/诊断"功能——不在本轮"迁移消费者"范围内。

- 测试 fixture 迁移第一批(11 个文件改用 `ResolvedMethodSpec`)：新增
  `tests/_spec_test_helpers.py`（`minimal_resolved_spec(factor_id, weighting,
  breakpoint_source)` 通用最小 fixture + `spec_factor_id(spec)` 双分派辅助函数，
  供只把 `MethodSpec(...)` 当成"随便一个合法 spec"的测试文件复用）。已转换：
  `test_batch_invalidation.py`、`test_dual_track_controller.py`、
  `test_experiment_matrix.py`、`test_experiment_plan_matrix_merge.py`、
  `test_run_from_matrix.py`、`test_run_identity.py`、
  `test_sandbox_validation.py`、`test_repair_loop.py`、
  `test_script_generator_bridge_mode.py`、
  `test_script_generator_lag_override.py`、
  `test_config_override_validation.py`。这些测试所覆盖的模块
  （DualTrackController/RepairLoop/registry.build_config/BacktestRunner/
  AdversarialSandbox/script_generator）本就已双分派，转换只是把 fixture 换掉、
  FakeRunner 里的 `spec.factor_id` 换成 `spec_factor_id(spec)`，逻辑不变。
  全量套件仍是 618 passed / 26 skipped，无回归。
  **未转换**（有意保留 v1，原因各不相同）：约 18 个文件直接测试 v1 专属组件
  （`SemanticExtractor`/`ReviewGate`/`apply_decisions`/v1 `field_contract`/
  签名校验/持有期推导/reextraction loop 等），没有 v2 对应概念，只能在
  v1 整体删除时一并处理；另外一小撮（`test_accruals_e2e.py`、
  `test_execute_data_path_override.py`、`test_step_diagnostics.py`、
  `test_bridge_track_e2e.py`、`test_mvp_e2e.py`、
  `test_real_wrds_samples_e2e.py`）用的是**已提交的真实黄金数值 fixture**
  （`tests/fixtures/method_specs/*.resolved.methodspec.json`）跑
  `Pipeline`/真实经济数据端到端对账，换成等价的 v2 fixture 需要重新构造并
  核实相同的黄金数值——风险较高，本轮未做，留给后续单独处理。

- Phase D 收尾 + 新增论文优先(paper-first)工作流的独立 UI/API 面：
  - `backend/spec_parsing.py`（新增）：`parse_spec(raw_dict)`/`spec_factor_id(spec)`
    共享双分派辅助函数（按 payload 形状——`{paper, review, resolution}` 三个顶层键
    即视为 `ResolvedMethodSpec`，否则走扁平 v1 `MethodSpec`）。接入
    `backend/routers/backtest.py`/`codegen.py`/`experiments.py`
    三个路由（原先都是 `MethodSpec.model_validate(req.spec)` 直接构造，现在都走
    `parse_spec`），下游调用的 `MetaCoder.generate_plugin`/`BacktestRunner.
    build_script`/`AdversarialSandbox.validate`/`DualTrackController.run_experiment`
    本就已双分派，无需改动。新增 `tests/test_backend_spec_parsing.py`（2 个测试）。
  - `backend/routers/methodspecs.py` 与 `app.py` 的既有 Extractor/Review & Resolve
    页面判定为纯 v1 专属工作流（`ReviewStatus.APPROVED`/`codegen_ready` 字段、
    `ReviewGate`/`apply_decisions`，v2 没有对应概念），不做双分派改造，
    保持原样不动。
  - 新增独立的论文优先工作流（不与 v1 工作流共享文件/端点，双方永不冲突）：
    - `src/steps/step1_extractor/paper_extractor.py` 新增 `PaperExtractor` 类
      （沿用 `SemanticExtractor` 的 LLM 调用/重试/PDF 附件逻辑，但产出
      `PaperMethodSpec`）。
    - 新增后端路由 `backend/routers/paper_methodspecs.py`：
      `POST /api/paper-methodspecs/extract`（LLM job）、`/extract-pdf`、
      `POST /api/paper-methodspecs/review`（同步，调用
      `review_paper_method_spec`）、`POST /api/paper-methodspecs/resolve`
      （同步，调用 `build_implementation_resolution` 并组装
      `ResolvedMethodSpec`，返回 `is_ready`）、`GET /{stage}`、
      `GET /{stage}/{factor_id}`（stage ∈ drafts/reviews/resolutions/resolved）。
      产物落在 `runs/method_specs/paper_{drafts,reviews,resolutions,resolved}/`
      （`backend/state.py` 新增对应目录常量 + `build_paper_extractor`），
      与 v1 的 `unreviewed/reviewed/resolutions/resolved` 完全分开。已在
      `backend/main.py` 注册。新增 `tests/test_backend_paper_methodspecs_api.py`
      （2 个测试，review+resolve 全流程走 TestClient，无 LLM 调用）。
    - `app.py` 新增第 8 个侧边栏页面 "Paper-First Workflow"（Extract/Review/
      Resolve 三个 tab，直接调用上述模块而非走 HTTP，与其余页面的既有架构
      一致）。同时把 MetaCoder 与 Backtest & Experiments 两个既有页面的
      MethodSpec 选择器扩展为可加载 `paper_resolved/` 下的 `ResolvedMethodSpec`
      文件（新增 `_load_any_spec`/`_spec_factor_id`/`_spec_codegen_ready`/
      `_spec_stable_hash` 模块级辅助函数，按 isinstance 分派；v1 专属字段
      `review_status`/`codegen_ready`/`model_copy` 强制审批的写法只在
      v1 分支保留）。
  - 全量套件 618 passed / 26 skipped，无回归；Streamlit 应用启动烟雾测试通过
    （无导入期报错）。

- 新增 `docs/methodspec-v2-plan.md`：一份处于讨论阶段的计划，用于分离
	论文事实、评审决策、实现映射与引擎配置；同时定义了拟议的横截面因子覆盖范围、
	严格 schema 契约、类型化报告指标、不支持方法策略、迁移阶段、测试要求，
	以及实施前必须完成定案的决策事项。
- 引擎新增双排序执行能力：`BacktestExecutor` 新增 `compute_breakpoints_multi`/
  `assign_portfolios_multi`/`compute_portfolio_returns_multi`/
  `combine_portfolio_returns_multi`（`src/infra/backtest_engine/__init__.py`），
  由 `form_portfolios`/`compute_portfolio_returns`/`combine_portfolio_returns`
  在 `config["sort_dims"]` 恰好 2 维时分发，单维路径代码与行为完全不变。这是对
  2026-07-24"精简引擎到单一 vanilla 路径"决定的部分反转（仅恢复双排序，
  Fama-MacBeth/overlapping/discrete/microcap 均不恢复），详见
  `docs/decision-log.md` 2026-08-07 条目。新增 `tests/test_double_sort_engine.py`
  （7 个测试，手算验证 2x2 独立双排序的断点/分组/组合收益）。同时把
  `MAX_SUPPORTED_SORT_DIMENSIONS` 从计划里的 3 改为 2（与引擎真实能力一致，
  避免 schema 层放行引擎实际跑不动的构造）。全量套件 594 passed / 26 skipped，
  无回归。**尚未接入** `registry.build_config`/`MetaCoder`/
  `step6_dual_track_controller`——推导 `config["sort_dims"]` 仍是待办工作
  （见 `docs/methodspec-v2-plan.md` 迁移 Phase D）。

- Phase D 第一块：`registry.build_config` 改为双分派（`spec: MethodSpec |
  ResolvedMethodSpec`），新增 `_build_config_from_resolved` 从 `ResolvedMethodSpec`
  （paper+review+resolution）推导出与 v1 完全相同的 config dict 形状，
  `BacktestExecutor` 不用改。覆盖单排序与双排序两种情况：`sort_dims` 里 `target`
  维度固定映射到引擎的字面 `"signal"` 列（论文自己的信号，由
  `compute_signal()` 产出），非 target 维度（如 size）才走物理列解析
  （`ImplementationResolution.concept_mapping`）——这是接线时发现的一个关键点，
  最初实现搞混了会导致断点算在不存在的列上。`PortfolioLeg.selector` 的
  0-based 分组号转换成引擎的 1-based 桶号。`TimingSpec` 补了一个此前遗漏的
  结构化字段 `formation_month`（v1 有 `formation_month: int`，v2 之前只有自由文本
  `formation_rule`，会导致年度信号对齐逻辑拿不到月份）。新增
  `tests/test_registry_resolved_method_spec.py`（6 个测试，含单排序/双排序两条
  真实端到端 `BacktestExecutor.run_with_config()` 跑通）。全量套件 600 passed /
  26 skipped，无回归。仍未接入 `MetaCoder`/`script_generator`/`step6`/backend/
  `app.py`——这些还在直接构造 v1 `MethodSpec` 并调用 `build_config(v1_spec, ...)`，
  走的是保留不变的 v1 分支。

- `MetaCoder.generate_plugin`/`_build_prompt` 同样改为双分派：
  `_build_prompt_from_resolved` 从 `ResolvedMethodSpec` 读 `signal.formula.steps`
  （取代 v1 单一 `formula.expression`）、`timing.formation_month`/
  `rebalance_frequency`、按 `stage=="signal"` 过滤的 `missing_policies` 条目，
  物理列通过 `resolution.concept_mapping` 解析（取代 v1 的
  `data.normalized_mapping`）。就绪判断用 `resolved.is_ready`，取代 v1 的
  `review_status=="approved" and codegen_ready`。新增
  `tests/test_meta_coder_resolved_method_spec.py`（3 个测试，用假 LLM 客户端跑
  `generate_plugin`）。全量套件 603 passed / 26 skipped，无回归。v1 分支/
  `method_spec.py` 仍保留，等 script_generator/step4-6/backend/app.py 全部
  迁移完才一起删除（用户已确认最终要删掉 v1，不是长期保留）。

- `script_generator.py` 同样双分派：`pick_signal_input_mode`/新增
  `signal_input_sources_from_resolved` 从 `resolution.concept_mapping` 按
  `FieldRole.SIGNAL_INPUT` 分组物理列（取代 v1 的 `data_layer.
  signal_input_sources`/`resolved_sources()`）；`generate_backtest_script`
  的 `factor_id`/`factor_name`/`paper_ref` 模板变量按 `isinstance` 分支取值。
  新增 `tests/test_script_generator_resolved_method_spec.py`（5 个测试）。
  全量套件 608 passed / 26 skipped，无回归。

- `step4_validator`：`AdversarialSandbox.validate` 的 `spec` 参数本来就没在
  方法体内被读取过，只放宽类型注解为 `MethodSpec | ResolvedMethodSpec`。
  `step5_backtest_runner`：新增 `_spec_factor_id`/`_spec_paper_ref`/
  `_spec_stable_hash`/`_spec_paper_reported` 四个双分派辅助函数，`build_script`/
  `write_comparison_summary`/`make_run_record`/`make_failed_run_record` 都
  改用它们取代直接访问 `spec.factor_id`/`spec.paper_ref`/`spec.stable_hash()`/
  `spec.reported_results`；`ResolvedMethodSpec` 的 `ReportedResults`（D5 的
  primary+secondary 类型化指标）被拍平成和 v1 相同的
  `{return_type, spreads, t_stats, main_spread, main_t_stat}` 形状，供
  `step7_replication_diff.bundle.build_evidence_bundle` 直接消费不用改。新增
  `tests/test_step5_backtest_runner_resolved_method_spec.py`（3 个测试）。
  全量套件 611 passed / 26 skipped，无回归。

- `step6_dual_track_controller`：新增 `_spec_factor_id` 辅助函数，`run_experiment`/
  `_plan_to_matrix`/`run_from_matrix`/`_run_bridge_track`/`_get_ablation_override`
  等方法的 `spec` 参数类型全部放宽为 `MethodSpec | ResolvedMethodSpec`（这些方法
  本身只把 `spec` 转手传给已双分派的 `build_config`/`runner.build_script`，唯一
  需要改的是 3 处直接读 `spec.factor_id` 的地方）。`experiment_spec.py` 的
  `build_experiment_spec`/`load_experiment_matrix` 同样放宽。`RepairLoop`
  （`src/infra/repair.py`）的 `build_validate_repair`/`execute_with_repair` 也
  放宽类型（同理，只是转手传递）。新增
  `tests/test_step6_dual_track_resolved_method_spec.py`（3 个测试）。全量套件
  614 passed / 26 skipped，无回归。

### Decisions Approved

- **D4（不支持执行策略）** 已定案：
  - 第一阶段支持双排序（2维）和基础三维排序
  - 更复杂的方法（Fama-MacBeth、自定义权重）在 `original_method` 上硬阻断
  - 允许单排序近似轨道，并行报告透明化gap
  - 基于 Fama-French 数据库标准做法和现有数据集统计（16.7% 需要多维排序）
- **D6（论文目标粒度）** 已定案：每个可独立执行的目标一个 MethodSpec，共享 `paper_ref`；信号内部组合仍是单 MethodSpec
- **D1（ResolvedMethodSpec 形态）** 已定案：实时重建（paper+review → 内存合并），同时写审计快照到 `runs/resolved/` 供调试；快照是输出产物，不作为输入读取
- **D2（evidence-status 归属）** 已定案：两层（LLM 打标 + 人工可覆盖）；v2 要求 Step1 每个字段必须有 `evidence_status` + 原文引用；审批矩阵维持现有逻辑，人工仅在"不确定 + 高影响"时介入
- **D5（报告指标粒度）** 已定案：`primary`（必填结构化）+ `secondary`（≤3个可选）；`metric_type` 枚举绑定引擎输出名；引擎没有的指标用 `other` 标记；`source` 支持 `clear`（原文 quote）和 `table_only`（table/row/column 定位）两种 evidence_status，后者是常态，走人工核实路径
- **D3（公式中间表示）** 已定案：选结构化文本步骤（不引入 AST）；`FormulaSpec` 扩展为有序步骤列表；用正则提取变量名做轻量符号验证；Step4 沙箱执行是主要验证手段
- **D7（稳定标识符）** 已定案：`factor_id = sha256(paper_ref + "::" + target_name)[:16]`，确定性生成无需人工维护；ablation/多 track 通过 `run_config` 区分，不影响 factor_id
- **D8（迁移切换策略）** 已定案：一次切换，旧 artifacts 直接作废重生；不维护 v1/v2 并行路径；旧 schema_version 报错提示重新生成

### Changed

- `docs/methodspec-v2-plan.md` §6 从概念草案改写为定稿级 schema：给出 `PaperMethodSpec` /
  `MethodReview` / `ImplementationResolution` / `ResolvedMethodSpec` 四个工件的完整
  Pydantic 形态，并新增 §6.10 字段审计（v1 → v2 的移出 8 项、删除 13 项、新增 16 项）。
- 新增 `src/infra/models/method_spec_v2.py`：Phase A 契约冻结实现，落地计划 §6 的
  `PaperMethodSpec` / `MethodReview` / `ImplementationResolution` / `ResolvedMethodSpec`
  四个 Pydantic 模型，含 `content_hash()`（D1 陈旧检测）、`make_factor_id()`（D7 确定性
  ID）、`DISPOSITION_MATRIX`（D2 五档证据矩阵）与 `ResolvedMethodSpec.is_ready`（取代
  v1 `codegen_ready` 布尔标志的推导式就绪判断）。尚未接入 `src/steps/*` 任何消费方
  （按计划 §9 Phase A 要求，先冻结契约再迁移消费方）。
- 新增 `tests/test_method_spec_v2_contract.py`（29 个测试）：`extra="forbid"` 拒绝
  未知字段、无损往返、`factor_id`/`content_hash` 稳定性、四个代表性 schema 场景
  （简单会计比率单排序 / 滚动残差估计信号 / 序贯双重排序 / 显式记录的不支持自定义
  加权替代）、`DISPOSITION_MATRIX` 形状、以及 `ResolvedMethodSpec.is_ready` 的五种
  失效路径。全量套件 567 passed / 26 skipped，无回归。
- Phase B：新增 `src/infra/models/schema_render_v2.py`（从 `PaperMethodSpec` 模型
  字段直接生成 JSON schema 骨架，杜绝 v1 那种"提示词比模型更丰富"的漂移问题）、
  `prompts/extractor/methodspec_extractor_v2.md`（v2 抽取提示词，schema 骨架块由
  `schema_render_v2` 在加载时拼接生成，不手工维护）、`src/steps/step1_extractor/v2.py`
  （`build_paper_method_spec` 直接用 `PaperMethodSpec.model_validate()` 校验 LLM 输出，
  无需 `normalize_curated_schema` 式的展平层；`factor_id`/`schema_version` 由流水线
  计算，不取信 LLM 填写）。新增 `tests/test_step1_extractor_v2.py`（13 个测试）。
  全量套件 575 passed / 26 skipped，无回归。**尚未接入** `src.pipeline` / v1
  `SemanticExtractor`——Step2/Step3 仍消费 v1 `MethodSpec`，真正切换要等 Phase C/D
  完成后一次性进行（避免中途破坏可测试的主分支）。
- Phase C：新增 `src/steps/step2_reviewer/v2.py`（`review_paper_method_spec`：
  D2 证据状态矩阵 + D4 引擎能力矩阵两条独立判定路径产出 `MethodReview`；能力菜单
  `ENGINE_WEIGHTING_MENU`/`ENGINE_RETURN_COMBINATION_MENU` 与 schema 词汇分离，
  论文即使清晰陈述了不支持的方法，也照样 `kind="unsupported"` + `BLOCKED`）、
  `src/steps/step2_reviewer/resolution_v2.py`（`build_implementation_resolution`
  复用既有 `DataDictionary.normalize_fields()` 目录匹配器，未解析的 concept 直接
  从 `concept_mapping` 中省略，绝不静默猜测）。同时修正 Phase A 的一个疏漏：
  `ResolvedMethodSpec._hashes_current` 此前只校验 `paper_spec_hash`，未校验
  `resolution.review_hash` 是否对应 review 的当前内容——新增 `MethodReview.
  content_hash()` 并补上这层校验，使 D1 的陈旧检测在 paper→review→resolution
  三层之间完整闭合。新增 `tests/test_step2_reviewer_v2.py`（12 个测试）。全量
  套件 587 passed / 26 skipped，无回归。仍未接入 `src.pipeline`。

### Renamed

- 去掉上面三条 Phase A/B/C 文件名里的 `_v2` 后缀（`schema_version` 里的
  `"methodspec.v2"` 等字面量保留，那是持久化数据的版本标识，不算代码命名）：
  `method_spec_v2.py` → `paper_method_spec.py`、`schema_render_v2.py` →
  `schema_render.py`、`step1_extractor/v2.py` → `step1_extractor/
  paper_extractor.py`、`step2_reviewer/v2.py` → `step2_reviewer/paper_review.py`、
  `step2_reviewer/resolution_v2.py` → `step2_reviewer/
  implementation_resolution.py`、`prompts/extractor/methodspec_extractor_v2.md`
  → `prompts/extractor/paper_method_spec_extractor.md`，以及对应的三个测试文件。
  重命名后全量套件重新验证 587 passed / 26 skipped。
