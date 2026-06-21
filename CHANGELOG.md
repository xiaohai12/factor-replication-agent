# Changelog

## [0.6.4] - 2026-06-21

### Changed
- `docs/architecture.md` (v7): Comprehensive update to align with actual codebase state:
  - §3 pipeline diagram made non-linear — added explicit feedback loop arrows (Sandbox→MetaCoder, Sandbox→ReviewGate, ReviewGate→Extractor, Attribution→ReviewGate)
  - Added §3.1 Feedback Loops table (was referenced by `src/pipeline.py` but absent from the document)
  - §4 module details: added §4.5 Adversarial Sandbox (full validation suite, not just future-function scan), §4.6 Plugin Registry, renumbered Data Layer and BacktestEngine; §4.4 MetaCoder now documents `repair_plugin()`
  - §5 file layout: updated to match actual `src/` structure (added sandbox, registry, controller, attribution, evidence, evaluation, pipeline.py, pdf_mapper.py, app.py, evidence/ output dir); fixed `data/method_specs/` subdirs (resolutions/ exists, impl_config/ does not); marked `data/local/` as not yet created
  - §6 end-to-end example: replaced non-existent `scripts/run_factor_backtest.py` with actual entry points (Streamlit dashboard + `Pipeline` class usage + real CLI scripts)
  - §7 DualTrackController: noted `HXZ_STANDARD_CONFIG` in `src/controller/__init__.py`
  - §9 Attribution: added anomaly detection thresholds (sign flip, >50% gap)
  - §10 replaced "Currently Deferred" stub list with accurate implementation status table (✅ implemented / 🚧 WIP / ⏳ not yet built)

## [0.6.3] - 2026-06-20

### Added
- `src/meta_coder/__init__.py`: Implemented `MetaCoder.generate_plugin()` — builds a structured prompt from the resolved MethodSpec (formula, data fields, timing, missing policy) and calls the configured LLM client to generate a signal plugin; also implemented `repair_plugin()` for bounded syntax-only repairs (max 3 attempts)
- `app.py`: New **MetaCoder** sidebar page — loads resolved MethodSpecs, shows approval gate with human-override checkbox for specs that passed human review but not full rules re-review, generates plugin code via LLM, runs AdversarialSandbox validation inline, supports auto-repair loop (up to 3 attempts), and saves plugins to `data/plugins/`
- `app.py`: Sidebar MetaCoder status now reflects plugin count from `data/plugins/`

### Changed
- `app.py`: Sidebar navigation now includes "MetaCoder" between single-paper and batch-evaluation pages
- `app.py`: "Apply All Resolutions" now marks `codegen_ready=true` and `review_status=approved` whenever there are no hard structural errors (missing formula, empty required_fields, etc.), regardless of remaining ambiguous_field metadata flags — the human's explicit approval action supersedes the rules re-review's field-level blocks
- `app.py`: MetaCoder approval gate is now strict (no force-approve bypass) since resolved JSONs are written with correct approval status

## [0.6.2] - 2026-06-20

### Added
- `app.py`: Single-paper upload flow now persists extracted PDF text to `data/paper_text_cache/<pdf_stem>.txt` for auditability and downstream reuse alongside the existing Streamlit session cache
- `app.py`: Single-paper workflow can now resume from a saved curated `*.methodspec.json` or an uploaded MethodSpec JSON, with optional paper-text cache selection for continuing LLM review after a restart
- `scripts/extract_methodspecs.py`: New CLI for extracting MethodSpecs from single PDFs or PDF directories, with batch support, provider/model selection, and JSON or text summaries
- `src/llm.py`: Added Claude Code CLI support, CLI binary auto-detection helpers, streaming callbacks for CLI-backed providers, and token-usage estimation helpers for Codex/Copilot/Claude responses
- `src/review_gate/__init__.py`: Added prompt-backed `review_with_llm()` flow that converts raw LLM audit JSON into structured `ReviewResult`
- `AGENTS.md`: Added explicit Streamlit startup instructions and port-selection guidance for local dashboard use

### Changed
- `app.py`: Extractor UI now records and displays the saved paper-text cache path after upload, while keeping review/extraction on the same already-extracted text instead of re-running `pymupdf`
- `app.py`: LLM review and LLM-assisted resolution now reload paper text from the saved cache path before falling back to session memory, so saved artifacts survive Streamlit restarts
- `app.py`: When review starts from an extractor session that still has PDF bytes but no cached text in memory, reviewer now auto-extracts and re-caches paper text for non-Claude providers instead of forcing a manual re-upload
- `app.py`: Review artifact saving now serializes nested `EvidenceCitation` objects correctly, and the UI distinguishes review-execution failures from artifact-persistence failures
- `scripts/review_methodspecs.py`: LLM review mode now delegates to `ReviewGate.review_with_llm()` and supports the `claude` provider instead of hand-building review JSON prompts inline
- `src/extractor/__init__.py`: Extraction now loads prompts from `prompts/extractor/methodspec_extractor.md` when present, captures token usage, accepts optional PDF bytes, and first attempts direct rich-schema `MethodSpec.model_validate()` before falling back to the legacy flat-schema mapper
- `src/llm.py`: Codex and Copilot CLI execution moved to streaming `Popen` flows so the UI can surface incremental output while preserving JSON-mode parsing
- `src/llm.py` and `src/review_gate/__init__.py`: JSON-mode parsing now tolerates explanatory preambles before the first JSON object, and review results map legacy `patch_existing_json` remediation output to the current `resolve_existing_json` schema value
- `tests/test_extractor.py`: Relaxed evaluation summary assertion to accept either `80%` or `80.0%`

### Removed
- `data/method_specs/curated/`, `data/method_specs/reviewed/`, `data/method_specs/resolved/`, and `data/method_specs/resolutions/`: Removed the previous bulk curated/reviewed AssetGrowth-era artifacts from the working tree, leaving the new `cooper_gulen_schill_2008_asset_growth_vw.methodspec.json` curated sample and moving `AssetGrowth.methodspec.json` under `data/test_papers/`
- `tmp/assetgrowth_paper.txt` and `tmp/assetgrowth_review_input.txt`: Removed temporary review-input scratch files from the repo working tree

## [0.6.1] - 2026-06-20

### Added
- `scripts/review_methodspecs.py`: New `--backend llm` mode that can call configured CLI/API LLM backends (`codex`, `copilot`, or `openrouter`) for paper-aware MethodSpec review
- `scripts/review_methodspecs.py`: Local PDF text extraction for LLM review via `pdftotext -layout`, with `pymupdf` fallback when `pdftotext` is unavailable
- `scripts/review_methodspecs.py`: LLM review output now writes both structured `review_report.json` for downstream resolution tooling and human-readable `*.llm_review.md`

### Changed
- `scripts/review_methodspecs.py`: Added prompt/paper/backend CLI flags (`--prompt`, `--paper`, `--papers-dir`, `--provider`, `--model`) so a single command can trigger external CLI-backed review against the original paper

## [0.6.0] - 2026-06-20

### Added
- `AGENTS.md`: Canonical shared instruction file for Codex, Claude, Copilot, and other coding agents with compact project rules and model-selection guidance
- `scripts/validate_methodspecs.py`: Validates curated MethodSpecs against the current schema — reports missing required fields, type errors, and enum violations
- `scripts/review_methodspecs.py`: Runs curated MethodSpecs through Review Gate — produces per-factor `review_report.json` and `reviewed.methodspec.json` under `data/method_specs/reviewed/`
- `scripts/resolve_review_blocks.py`: Interactive CLI to resolve Review Gate blocked fields — reads a `review_report.json`, prompts field-by-field with smart suggestions (candidate values, field-specific option lists), writes a `resolution.json` and final `resolved.methodspec.json`
- `data/method_specs/reviewed/`: Reviewed MethodSpecs and review reports for 25+ factors (AB1998 suite, AnAngBaliCakici2013 volatility factors, Ball2016 profitability factors, BlitzHuijMartens residual momentum, EisfeldtPapanikolaou OMK, FrazzinPedersen BAB, KoHsuLi innovation factors, LohWarachka streak factors, MertonStrategicDefault suite)
- `data/method_specs/resolutions/AssetGrowth.resolution.json`: Resolution decisions for AssetGrowth blocked fields
- `data/method_specs/resolved/AssetGrowth.resolved.methodspec.json`: Final resolved MethodSpec for AssetGrowth, ready for codegen
- `docs/roadmap.md`: Full project roadmap covering MVP workflow, MethodSpec quality, meta-coder, backtest engine, and production data integration phases
- `ReviewGate._get_field_value()`: Best-effort dotted-path lookup with path-alias resolution for populating review context
- `FieldReviewNote`: Extended with `current_value`, `candidate_value`, `empirical_impact`, and `evidence` fields so resolvers have full context without re-reading the spec

### Changed
- `CLAUDE.md` and `.github/copilot-instructions.md`: Converted to thin compatibility wrappers that point agents to `AGENTS.md`
- `src/models/method_spec.py`: `PatchLogEntry` renamed to `ResolutionLogEntry` (terminology shift: "resolve" not "patch")
- `src/models/method_spec.py`: `RemediationMode.PATCH_EXISTING_JSON` renamed to `RemediationMode.RESOLVE_EXISTING_JSON`
- `src/models/method_spec.py`: `SignalSpec.sign` and `MethodSpec.sign` changed from `int = 1` to `Optional[int] = None` — unspecified sign is now explicitly nullable rather than defaulting to positive
- `src/models/method_spec.py`: `PortfolioSpec.implied_factor_direction`, `ReturnCalculationSpec.input_return`, `ReportedResultsSpec.comparison_policy`, `spreads`, and `t_stats` types widened to `T | dict[str, Any]` to tolerate structured LLM output without validation errors
- `src/models/method_spec.py`: Added `normalize_curated_schema` `model_validator` to coerce legacy curated JSON into the current schema on load
- `src/review_gate/__init__.py`: `ReviewGate.review()` now populates full field context (current value, candidate value, empirical impact, evidence) in each `FieldReviewNote`
- `src/review_gate/__init__.py`: `ReviewResult.remediation_mode` default updated to `resolve_existing_json`
- `src/models/__init__.py`: Exports `ResolutionLogEntry` instead of `PatchLogEntry`
- `docs/architecture.md`: Updated to reflect current module boundaries and MVP workflow

## [0.5.4] - 2025-05-28

### Added
- `data/gold_standard/paper_selection_rationale.md`: Records why the 10-paper annotation set was chosen, the extraction-difficulty coverage dimensions, and a recommended drop order if reducing scope
- `src/llm.py`: Model selection support — Codex CLI now uses `-m` flag for model (gpt-5.5, gpt-5.4); Copilot CLI supports claude-opus-4-6, claude-sonnet-4-6, gpt-5.4
- `app.py`: Model selector dropdown in sidebar — dynamically shows available models based on selected provider
- `src/models/method_spec.py`: `reported_return_spread` and `reported_t_stat` fields on MethodSpec — stores paper's reported long-short return and t-stat for Attribution comparison
- `src/extractor/__init__.py`: Extraction schema now extracts `reported_return_spread` and `reported_t_stat` from paper text in a single LLM call
- `data/gold_standard/gold_standard.csv`: Human-annotated ground truth CSV template (24 fields) with AssetGrowth example row
- `data/gold_standard/README.md`: Field documentation and annotation guidelines for gold standard
- `scripts/csv_to_gold_standard.py`: Converter from flat CSV annotations to nested JSON matching MethodSpec schema
- `data/gold_standard/gold_standard.csv`: Added `return_type`, `data_frequency`, `annotator_notes` columns (now 27 fields)
- `data/gold_standard/gold_standard.csv`: Added `_source` columns for each substantive field — annotators can record where in the paper each value was found
- `data/gold_standard/README.md`: Added "Where to Find" column to field documentation table

### Changed
- `data/gold_standard/paper_selection_rationale.md`: Reordered the printable 10-paper list by annotation priority (High/Medium/Low) from highest to lowest
- `data/gold_standard/paper_selection_rationale.md`: Added a printable full-name list for all 10 selected papers (author-year-title) to support annotation logging and reporting
- `src/llm.py`: `CodexCLIClient` default model changed from "default" to "gpt-5.4"
- `src/llm.py`: `CopilotCLIClient` default model changed from "opus" to "claude-opus-4-6" (full name)
- `src/llm.py`: `CodexCLIClient._create()` now ignores caller's model param (e.g. hardcoded "gpt-4o") and always uses the configured default model
- `app.py`: Both `create_llm_client` calls now pass selected model

## [0.5.3] - 2025-05-28

### Added
- `src/llm.py`: `CopilotCLIClient` — uses VS Code's bundled Copilot CLI binary via subprocess with your GitHub Copilot subscription; supports LLM mode (tools disabled) and agent mode (tools enabled)
- `app.py`: LLM Provider selector in sidebar — choose between codex, copilot, or openrouter at runtime
- `src/extractor/__init__.py`: `extract_batch()` method — extracts all factors from the same paper in a single LLM call (saves tokens and API calls for multi-factor papers)
- `src/extractor/__init__.py`: `RateLimitExhausted` exception — raised immediately on rate limit so caller can checkpoint and stop (no retry, since quota recovery takes hours)
- `app.py`: Checkpoint/resume system for batch evaluation — saves progress after each paper to `data/eval_history/_checkpoint.json`; on next run, skips already-completed papers
- `app.py`: "Clear Checkpoint" button to start fresh

### Changed
- `app.py`: Batch evaluation uses `extract_batch()` — one LLM call per paper instead of one per factor
- `app.py`: On rate limit, stops gracefully with saved progress instead of retrying
- `app.py`: Paper selection adds "First N PDFs" mode with slider (e.g., first 30, 50 papers)

## [0.5.2] - 2025-05-27

### Added
- `scripts/convert_papers_to_md.py`: PDF→Markdown conversion script using pymupdf4llm (preserves headings, tables, equations); outputs to `data/papers_md/`
- `src/evaluation/helpers.py`: `extract_pdf_text()` now prefers pre-converted MD files from `data/papers_md/`, falls back to PyMuPDF extraction
- `src/extractor/__init__.py`: LLM extraction now requires `reasons` field — a dict mapping each extracted field to the verbatim quote from the paper supporting that value
- `src/extractor/__init__.py`: `ExtractionResult.reasons` field stores per-field citations from LLM output
- `src/evaluation/helpers.py`: New shared module with evaluation utilities (no pytest dependency) — used by both `app.py` and tests

### Changed
- `app.py`: Per-Factor Results table columns renamed from "Expected"/"Actual" to "Ground Truth"/"Extracted", added "Reason" column showing paper citations
- `app.py`: Imports evaluation utilities from `src.evaluation.helpers` instead of `tests.test_extractor` (fixes Streamlit import error)
- `src/evaluation/helpers.py`: `build_field_details()` now accepts optional `reasons` dict and includes reason in each field detail
- `tests/test_extractor.py`: Refactored to import shared utilities from `src.evaluation.helpers` instead of duplicating code

## [0.5.1] - 2025-05-25

### Changed
- `src/pdf_mapper.py`: Complete rewrite — replaced complex author-based matching with simple Paper title matching from SignalDoc.csv (55/56 PDFs → 67 factors mapped)

### Added
- `tests/test_pdf_mapper.py`: Comprehensive test suite for pdf_mapper (33 tests) — covers normalization, title loading, integration with real data, cache behavior, edge cases, and known mapping spot checks

## [0.5.0] - 2025-05-25

### Added
- `src/pdf_mapper.py`: New content-based PDF-to-factor mapping utility — reads first page of each PDF via PyMuPDF, matches author last names against SignalDoc entries using word-boundary regex, year matching, and confidence scoring
- `src/pdf_mapper.py`: Caching system (`.pdf_factor_map_cache.json`) to avoid re-scanning unchanged PDFs
- `src/pdf_mapper.py`: `build_pdf_factor_map()`, `get_factor_to_pdf()`, `invalidate_cache()` public API

### Changed
- `tests/test_extractor.py`: Replaced hardcoded `PDF_FACTOR_MAP` dict with dynamic mapping via `src.pdf_mapper.build_pdf_factor_map()` — works with any PDF filenames

### Fixed
- `scripts/download_papers.py`: Rewrote CrossRef search to use all author last names + journal keywords (instead of just first author + partial description), with scored result validation (threshold 0.5) to avoid matching wrong papers
- `scripts/download_papers.py`: Added `_validate_crossref_item()` scoring (author match 40%, year 30%, journal 20%, title presence 10%) to rank and filter search results
- `scripts/download_papers.py`: Added post-download `validate_pdf_content()` that checks PDF contains expected author names in raw text

### Added
- `scripts/download_papers.py`: `--force` flag to re-download papers even if file already exists
- `scripts/download_papers.py`: `--revalidate` mode to check all existing PDFs contain expected author names without downloading
- `scripts/download_papers.py`: Logs DOI found for each paper during download; reports invalid PDFs to `data/papers/invalid_pdfs.txt`

### Changed
- `app.py`: Replaced tabs with left sidebar navigation (pipeline steps); batch eval page now renders independently without `st.stop()` interference
- `app.py`: Batch Evaluation page — added multi-select paper picker (radio: "All PDFs" / "Select specific PDFs"), progress status text, and explicit "Run Evaluation" button
- `app.py`: Fixed `use_container_width` deprecation; progress now shows "3/60 done — processing X.pdf → FactorID ..."
- `app.py`: Added "Evaluation History" page — reports auto-saved to `data/eval_history/` after each batch run; browse, view full details, download, or delete past reports from the sidebar
- `app.py`: Added per-field accuracy summary table in batch eval results
- `src/extractor/__init__.py`: `evaluate_extraction()` now treats unspecified/None/N/A ground truth as correct (no penalty)
- `tests/test_extractor.py`: `_build_field_details()` also treats unspecified ground truth as correct
- `tests/test_extractor.py`: Complete redesign — removed all mock LLM tests, replaced with real LLM (codex CLI) + real PDF extraction + SignalDoc.csv ground truth evaluation pipeline
- `FACTOR_PDF_MAP` now maps 80+ SignalDoc factors to 33 actual PDFs in `data/papers/`, generated by matching SignalDoc Authors+Year to PDF filenames
- Added `FactorEvalResult` and `EvalReport` dataclasses for structured evaluation output (JSON + text summary)
- Added `TestRealExtraction` class: parametrized tests using real PDFs + real LLM calls
- Added `TestFullEvaluation` class: full eval suite producing `data/eval_output/` reports
- Added `TestEvaluationLogic` class: unit tests for evaluation helpers (no LLM needed)
- Added `run_evaluation()` standalone function for programmatic/CLI evaluation
- Eval output: `data/eval_output/extraction_eval_report.json` + `extraction_eval_summary.txt`
- Restructured mapping to `PDF_FACTOR_MAP` (PDF → factor list) as primary, with `FACTOR_TO_PDF` reverse lookup; `test_full_eval_report` iterates by PDF to avoid redundant reads
- `SemanticExtractor` docstring clarified: one paper may define multiple factors; each extract() call produces exactly one MethodSpec for one factor_id

### Added
- Expanded eval fields: `formula_keywords` (Compustat/CRSP variable keyword matching from Detailed Definition), `sample_start_year`, `sample_end_year`, `rebalance_frequency` (derived from Portfolio Period), `accounting_lag` (derived from Start Month)
- Scoring system: `PASS_THRESHOLD=80`, `_compute_score()`, `FactorEvalResult.score`/`.passed`, `EvalReport.passed_count`/`.failed_count`/`.pass_rate`/`.avg_score`/`.compute_aggregates()`
- `_extract_formula_keywords()` helper with `_KNOWN_VARIABLES` set for Compustat/CRSP variable detection
- `SemanticExtractor._values_match()` now supports `field_key="formula_keywords"` for partial-credit keyword matching (>=50% threshold)
- `app.py`: Added "Batch Evaluation" tab — select individual PDF or run all, progress bar, aggregate metrics (avg score, pass rate), per-factor expandable results with field detail tables, JSON report download

## [0.4.0] - 2025-05-25

### Changed
- `src/extractor/__init__.py`：`required_fields` 从简单字符串列表改为结构化格式 `[{field, source, description}]`，LLM 直接从 paper 提取数据源（不再假设只有 Compustat/CRSP），解析后自动填充 `SignalSpec.field_sources`

### Removed
- `src/extractor/__init__.py`：删除 `_get_data_fields_context()` 及 user template 中的 data_fields 占位符，LLM 自行从 paper 识别数据源和字段名
- `tests/test_extractor.py`：删除 `TestDataFieldsContext` 测试类（对应方法已移除）

### Fixed
- `src/extractor/__init__.py`：Rules 中 stock_weight 说明补充 "capped_vw" 选项

### Added
- `README.md`：添加 "Key Enums Explained" 子章节（WeightingRule / EvidenceSource / EmpiricalImpact 用途说明 + pipeline 关联）
- `README.md`：添加 "What a Good MethodSpec Looks Like" 章节（BM factor 完整示例 + 评判标准 + 常见错误）
- `src/models/method_spec.py`：为所有 class 和 enum 添加详细 docstring（含 SignalDoc 统计数据、示例、pipeline 角色说明）
- `app.py`：Streamlit dashboard，PDF-first 流程（上传 PDF → 自动匹配 SignalDoc factor → 提取 → ground truth 对比）
- `src/llm.py`：LLM client 抽象层，支持 Codex CLI（默认 model 5.5）和 OpenRouter 两种后端
- `streamlit>=1.30`, `pymupdf>=1.24` 加入 pyproject.toml dependencies
- `match_factor_from_text()` 自动从 PDF 文本匹配 SignalDoc factor（基于 author names + year + keywords）
- 移除 sidebar factor selector，改为 PDF 上传驱动的自动识别 + 手动确认
- Semantic Extractor 完整实现：paper-first LLM extraction pipeline (`_call_llm_extract`, `_build_method_spec_from_llm`)
- Extraction system prompt (`EXTRACTION_SYSTEM_PROMPT`) 和 user template，结构化 JSON 输出
- `_get_data_fields_context()` 提供 data dictionary context 给 LLM
- `_parse_enum()` 安全 enum 解析（大小写不敏感 + fallback）
- `_values_match()` fuzzy 比对用于 evaluation
- Ambiguity auto-tagging：LLM 返回 "unspecified" 字段自动标记为 `AmbiguousField`
- `tests/test_extractor.py`：22 个单元测试覆盖 MethodSpec 构建、enum 解析、evaluation metrics、端到端提取、data dictionary context
- `TestSignalDocGroundTruth`：7 个集成测试使用真实 SignalDoc.csv 作为 ground truth，验证 evaluation pipeline（BM perfect score、negative sign factors、batch pilot、imperfect detection、全量 parse）

### Changed
- `src/models/method_spec.py`：每个 Enum class 新增 `choices(allow_unspecified)` classmethod，返回 schema 可选值字符串；model class 的 `EXTRACTION_SCHEMA` 直接引用 enum 的 `choices()` 而非内联拼接
- `src/models/method_spec.py`：每个 model class 新增 `EXTRACTION_SCHEMA: ClassVar[dict]` 类变量，定义该 class 在 LLM 提取 prompt 中对应的 schema 字段和可选值
- `src/extractor/__init__.py`：`_build_extraction_schema()` 改为从各 class 的 `EXTRACTION_SCHEMA` 组合，不再手写 schema 描述
- `src/extractor/__init__.py`：将 EXTRACTION_SYSTEM_PROMPT 中的硬编码 JSON schema 重构为 `EXTRACTION_SCHEMA_FIELDS` 字典 + `_build_schema_json_block()` 函数，从 model enum 类自动生成 schema 描述
- **LLM output schema 重构**：对齐 SignalDoc.csv 字段结构
  - `weighting` → `stock_weight` (ew/vw)
  - `breakpoint_quantiles` → `ls_quantile` (float: 0.1=decile, 0.2=quintile, 0.3=tercile)
  - 新增 `filter` (stock-level filters, e.g. abs(prc)>5, exchcd%in%c(1,2))
  - 新增 `cat_form` (continuous/discrete)
  - 新增 `sign` (+1/-1 预测方向)
  - 新增 `detailed_definition` (文字描述 formula)
  - 新增 `sample_start_year` / `sample_end_year`
- `MethodSpec` model 新增字段：`detailed_definition`, `cat_form`, `sign`, `sample_start_year`, `sample_end_year`
- `PortfolioSpec` 新增 `filter` 字段；`BreakpointSpec` 新增 `ls_quantile`
- `EXTRACTION_SYSTEM_PROMPT` 重写：新增 sign/ls_quantile/filter/cat_form 解释和提取指导
- `_build_method_spec_from_llm()` 支持 `stock_weight`、`ls_quantile`→quantiles 转换、`filter` 解析
- `evaluate_extraction()` core_fields 扩展为 8 个核心字段，field_map 支持所有 SignalDoc 字段
- `_parse_signaldoc_row()` (app.py + tests) 新增 `sign`, `ls_quantile`, `filter`, `cat_form` 解析
- `TestExtractEndToEnd`: 替换 mock LLM 为真实 codex CLI 调用，5 个 E2E 测试验证完整提取流程
- `_build_method_spec_from_llm()`: 添加 `_safe_int()` 处理 LLM 返回 "unspecified" 或非数字字段
- `app.py` 结果页面重构：LLM 提取结果与 SignalDoc ground truth 左右并排显示，取消 tabs 布局

### Removed
- `app.py`: 移除 mock LLM 选项和 `_build_mock_response()` 函数，Streamlit 现在仅使用真实 codex CLI 提取

## [0.3.0] - 2026-05-24

### Added
- `scripts/download_papers.py`：从 Semantic Scholar 下载 SignalDoc.csv 中引用的论文 PDF（open-access），下载不到的记录到 `data/papers/missing.txt`
- `README.md`：项目概述、架构图、目录结构、数据源表、设计决策、引用格式
- `src/evaluation/` 模块：`Evaluator` 类实现三层评估（extraction vs SignalDoc、signal vs C&Z firm-level、portfolio vs C&Z LS returns）
- `TimeAvailComputer` 类：Data Layer 中统一处理 `time_avail_m` point-in-time 可用日期
- `DataLayer.get_signal_master_table()` 方法：构建 [permno, time_avail_m] 面板供 plugin 使用
- `MetaCoder.load_few_shot_examples()` 方法：从 OSAP Predictors/ 加载 few-shot 示例代码
- Meta-Coder 新增 `reference_code_path` 参数和 `PLUGIN_OUTPUT_COLS` schema 定义

### Changed
- **Semantic Extractor** 文档明确：SignalDoc.csv 不作为输入（避免信息泄漏），仅用于 post-hoc evaluation
- **Meta-Coder** 重写：明确 plugin 输出格式为 `[permno, yyyymm, signal]`；lag 由 Data Layer 处理（time_avail_m），plugin 只做 formula computation
- **Data Layer** 新增 `TimeAvailComputer`，`DataLayer` facade 增加 `time_avail` 和 `get_signal_master_table`

## [0.2.0] - 2026-05-24

### Changed
- **MethodSpec** 重构为嵌套结构（`signal.*`, `portfolio.*`, `extraction_sources`, structured `ambiguous_fields`），匹配 docs/architecture.md Section 4.2 YAML schema
- **Semantic Extractor** 改为 multi-source triangulation 策略（C&Z → OSAP → paper fill-in → ambiguity tagging），新增 `ExtractionMetrics` 评估
- **Review Gate** 新增 Review Decision Matrix（evidence × impact 分类）、`Disposition` 枚举、LLM Reviewer picky 策略、sensible defaults、structured `FieldReviewNote`
- **Pipeline** 新增完整 feedback loop / backtrack 逻辑（Sandbox→Meta-Coder repair, Sandbox→Review empirical, Review→Extractor, Attribution→Review anomaly），max backtrack depth=3
- **BacktestEngine** `_build_config` 适配新 MethodSpec 属性名
- **DualTrackController** HXZ config 和 ablation map 更新字段名，新增 `universe` ablation switch

### Added
- `src/data_layer/` 模块：DataDictionary（字段注册表）、SnapshotManager（versioned data pulls）、CCMLinker（point-in-time CRSP-Compustat linking）、DataLayer facade
- `PipelineStatus` dataclass 跟踪 factor 执行状态和 backtrack 计数
- MethodSpec 新增 `FieldSource`、`SignalTiming`、`MissingPolicy`、`SignalSpec`、`PortfolioSpec`、`BreakpointSpec`、`ExtractionSource`、`AmbiguousField` 子模型
- Review Gate 新增 `classify_disposition()` 函数实现决策矩阵
- Extractor 新增 `evaluate_extraction()` 方法对标 C&Z ground truth

### Fixed
- `factor_spec.py` 修复 `Optional` import 位置错误

## [0.1.0] - 2026-05-20

### Added
- 项目基本框架搭建
- 核心数据模型：`MethodSpec`、`FactorSpec`、`PluginRecord`、`RunRecord`
- Semantic Extractor 模块（接口定义）
- Review Gate 模块（基础验证逻辑）
- Controlled Meta-Coder 模块（接口定义）
- Adversarial Sandbox 模块（语法检查、schema 检查、forbidden pattern 扫描）
- Plugin Registry 模块（增删查改）
- Controlled Backtesting Lifecycle Engine 模块（接口定义）
- Dual-Track + Factorial Controller 模块（original/standardized/ablation track）
- Evidence Store + Run Registry 模块（JSON 持久化）
- Factorial Attribution Layer 模块（ablation 归因框架）
- Pipeline orchestrator 串联全流程
- `pyproject.toml` 项目配置
- `.github/copilot-instructions.md` agent 指令（强制每次修改更新 changelog）
