# Changelog

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
- **MethodSpec** 重构为嵌套结构（`signal.*`, `portfolio.*`, `extraction_sources`, structured `ambiguous_fields`），匹配 architecture.md Section 4.2 YAML schema
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
