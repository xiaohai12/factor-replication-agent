# Changelog

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
