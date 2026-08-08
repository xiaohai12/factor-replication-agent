---
type: plan
status: discussion
project: factor-replication-agent
created: 2026-08-07
tags: [plan, methodspec, extraction, review, reproducibility]
---

# MethodSpec v2 计划

## 1. 目的

重新设计 `MethodSpec`，使其能够在保持项目受控实证边界的前提下，忠实且可审计地描述横截面股票因子论文方法。覆盖边界由研究范式界定，而非由因子知名度界定（见第 2 节）——不论论文研究的是广为人知的因子还是冷门的小众因子，只要采用横截面因子研究范式（formation-period 排序/回归 + holding-period 收益），均在范围内：

1. 提取论文原文表达的方法，不进行静默删除或替换；
2. 区分论文事实、歧义点、人工决策与引擎选择；
3. 保留足够的方法细节以支持代码生成、回测和比较；
4. 对当前引擎无法执行的方法进行如实表示，而不是假装已支持；
5. 在评审完成后，保证所有实证数值与可执行选择保持确定性。

本文档是讨论计划，不是已批准的架构决策。最终决策应在评审后记录到 `docs/decision-log.md`。

## 2. 范围

### 纳入范围

- 公司层面的横截面股票因子——不论是广为人知的因子还是冷门的小众因子，只要采用横截面因子研究范式（formation-period 排序/回归 + holding-period 收益）；
- 会计、市场、分析师、期权及其他已注册信号来源；
- 年度、季度、月度信号构建；
- 直接公式、递归公式、滚动估计和残差信号；
- 单变量排序、独立/序贯/条件多重排序，以及作为论文方法的 Fama-MacBeth 风格构造；
- 原始收益、价差、alpha 及其他论文报告的比较目标；
- 对当前标准化引擎不可执行方法的显式表示。

### v2 不纳入范围

- 覆盖所有资产类别的通用 schema；
- 时间序列交易策略、期货期限结构、外汇 carry 和宏观配置策略；
- 在回测引擎中实现多重排序或回归估计器；
- 允许生成的插件代码控制股票池、滞后、断点、加权或组合构建；
- 将 C&Z 视为真值，或向抽取阶段暴露 C&Z 工件。

schema 可以描述比引擎当前可执行能力更广的方法。schema 覆盖范围与引擎能力是有意分离的。

## 3. v1 中已验证的问题

### 3.1 抽取器输出被静默压缩

抽取提示词要求的嵌套对象比 Pydantic 模型实际存储更丰富。`MethodSpec.normalize_curated_schema` 仅保留了一个较小的可执行子集，并静默丢失了以下信息：

- 公式约定及有序 `calculation_steps`；
- 超出 citation 字符串之外的论文标题/文件/章节元数据；
- 对定义、经济直觉、方向、样本日期的证据；
- 形成日期规则、持有期、收益窗口和会计期间语义；
- 数据频率、收益频率、来源使用/细节和覆盖警告；
- 排序变量、排序角色、分组数量/类型及多种权重描述；
- 信号变量名和信号类别；
- 报告收益期限、主表位置及收益类型说明；
- 注释说明和扩展内容。

由于 Pydantic 默认忽略额外字段，提示词与模型的漂移可能在通过校验的同时导致信息消失。

### 3.2 单一对象混合了四种权威来源

当前模型同时包含以下内容：

- 论文声称的事实；
- 抽取歧义与证据质量；
- 人工评审状态与决策历史；
- 物理列、收益股票池、C&Z 关联、默认值与代码生成就绪状态。

这些字段的所有者和变更规则不同。将其混在一起会导致无法判断一个值来源于论文、评审者、数据目录还是引擎回退。

### 3.3 归一化会破坏论文原值

论文中不在菜单内的值会被转成 `other`，而原始字面值只有在并行 `unsupported_fields` 记录正确创建时才能保留。论文方法与引擎能力决策不应共享同一个枚举。

### 3.4 构造模型过于狭窄

当前 `PortfolioSortSpec` 只能表达“一个连续排序 + 一个断点总体”。它在结构上无法描述：

- 独立或序贯双重排序；
- 在规模、行业、交易所或其他条件组内排序；
- 类别型组合；
- 多个多/空腿；
- 滚动回归或 Fama-MacBeth 的构造细节。

仅将这些内容写入自由文本或 `ambiguous_fields`，会阻碍可靠评审、比较以及未来引擎支持。

### 3.5 报告结果类型约束不足

`spreads` 和 `t_stats` 既可接受列表也可接受任意字典，而单个 `main_spread` 又缺乏明确单位、频率、方向、样本、调整模型和表格标识。即使两个数值都被正确抽取，这也可能产生无效的论文/回测比较。

## 4. 设计原则

1. **论文事实不可变。** 评审可以标注或解析可执行选择，但不得改写“论文被记录为说了什么”。
2. **不允许静默丢失。** 抽取模型使用 `extra="forbid"`；提示词示例与生成的 JSON schema 必须一致。
3. **证据按字段归属。** 关键值应携带自身 citation，而不是依赖一个覆盖整段内容的总 citation。
4. **论文词汇与引擎菜单分离。** 不支持方法要按原样保留，只能在显式 resolution 中被阻断或映射。
5. **一项选择一个责任方。** 论文抽取、评审、物理映射和执行各自对应独立工件。
6. **不引入论文特化字段。** Beta、残差动量、组织资本等方法应复用通用的公式、估计、窗口和状态模型。
7. **比较语义必须类型化。** 仅当单位、期限、方向、样本和调整基准已知时，报告数值才可比较。
8. **引擎限制必须可见地失败。** 不支持的构造不能被静默钳制成单变量特征排序。

## 5. 拟议的工件边界

```text
paper/PDF
    |
    v
PaperMethodSpec                 Step 1, immutable paper-first artifact
    |
    v
MethodReview                    Step 2 findings and append-only decisions
    |
    v
ImplementationResolution       human/catalog mappings and approved choices
    |
    v
ResolvedMethodSpec             deterministic aggregate/view for codegen
    |
    v
ExecutionConfig                fixed-menu engine input from registry
```

只有 `PaperMethodSpec`、`MethodReview` 和 `ImplementationResolution` 需要独立持久化。`ResolvedMethodSpec` 可以是一个经过校验的聚合视图，而不是第四份可变副本。

### 5.1 `PaperMethodSpec`

由 Step 1 负责。仅包含来源于论文的事实、规范化解释与证据。不得包含：

- 物理来源/列映射；
- 收益股票池默认值；
- C&Z 缩写或桥接标识；
- 评审状态或 resolution 日志；
- `codegen_ready`；
- 引擎替代或默认值。

### 5.2 `MethodReview`

由 Step 2 负责。引用精确的 `paper_spec_hash`，并包含：

- 确定性发现以及可选的 LLM 辅助发现；
- 歧义字段与证据质量分级；
- 基于能力矩阵识别的引擎不支持项；
- 阻断路径与修复建议；
- 仅追加的人类 resolution 记录；
- 重新抽取尝试历史；
- 由未解决发现推导出的评审状态。

LLM 可以提出发现或候选解释，但不能批准实证选择，也不能移除确定性阻断。

### 5.3 `ImplementationResolution`

由人工评审与确定性 catalog 解析共同负责。包含：

- 论文概念到已注册 source/column 的映射；
- 选定的 returns universe；
- 对论文未明示但高影响字段的显式约定；
- 对“论文表述清晰但引擎不支持”方法的显式替代；
- 如 C&Z acronym/manifest identity 之类的参考关联；
- 决策依据，以及指向评审条目的证据/引用。

### 5.4 `ResolvedMethodSpec`

前述工件的校验后聚合体。就绪状态由以下条件推导：

- 论文 hash 匹配；
- 不存在未解决的阻断性发现；
- 所有必需物理映射均已注册；
- 所有执行所需选择均已解析；
- 当前引擎能力版本支持该构造。

不得持久化可任意修改的 `codegen_ready` 布尔值。

### 5.5 `ExecutionConfig`

现有 registry 仍是进入标准化引擎的唯一边界。它接收已就绪的 `ResolvedMethodSpec`，产出固定菜单值，并记录每一项默认/替代。引擎绝不直接读取 `PaperMethodSpec`。

## 6. PaperMethodSpec Schema 定稿

设计原则：**一个概念只有一个表达通道**；枚举成员不编码可从数据推导的信息；
物理映射、引擎默认值、参考关联一律不出现在本层。

以下按 Pydantic 形态给出，字段名即最终实现名。

### 6.0 通用构件

```python
class EvidenceStatus(str, Enum):
    CLEAR       = "clear"        # 正文明确陈述，quote 可被自动字符串校验
    TABLE_ONLY  = "table_only"   # 数字来自表格，无正文 quote，需人工核对（常态）
    INFERRED    = "inferred"     # LLM 依据领域惯例推断，论文未直接说明
    CONFLICTING = "conflicting"  # 论文内部前后矛盾
    UNSPECIFIED = "unspecified"  # 论文完全未提及


class TableRef(BaseModel):
    table: str          # "Table 3"
    row: str = ""       # "L-H spread"
    column: str = ""    # "FF3 alpha"


class EvidenceCitation(BaseModel):
    location: str                       # "Section 3.2" / "p.18"
    quote: str = ""                     # 原文逐字摘录（TABLE_ONLY 时为空）
    table_ref: TableRef | None = None   # 表格来源时填写
    interpretation: str = ""            # 该引用如何支持取值；不得规定引擎应做什么


class SourcedValue[T](BaseModel):
    """所有关键取值的统一包装：值 + 证据 + 证据质量。"""
    value: T | None = None
    evidence: list[EvidenceCitation] = []
    status: EvidenceStatus = EvidenceStatus.UNSPECIFIED
```

> **枚举精简（相对 v1）**：删除 `SINGLE` 与 `WEAK_OR_CONFLICTING`。
> "只有一处证据" 由 `len(evidence) == 1` 表达，不需要单独枚举成员；
> `WEAK_OR_CONFLICTING` 与 `CONFLICTING` 语义重叠。新增 `TABLE_ONLY`（见 D5）。
> Step2 审批矩阵相应从 6×2 收缩为 5×2。

### 6.1 顶层结构

```python
class PaperMethodSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")   # 静默丢失字段的根治手段

    schema_version: Literal["methodspec.v2"]
    factor_id: str            # sha256(paper.document_id + "::" + target_name)[:16]
    target_name: str          # 论文内该目标的名称，如 "asset_growth"

    paper: PaperRef
    signal: SignalSpec
    data: DataSpec
    sample: SampleSpec
    timing: TimingSpec
    universe: UniverseSpec
    portfolio: PortfolioSpec
    reported_results: ReportedResults
    notes: str = ""           # 抽取器的自由备注，不参与任何判定
```

一个 spec = 一个可独立执行且可独立比较的目标（D6）。

```python
class PaperRef(BaseModel):
    document_id: str          # 论文文件的稳定标识（文件哈希或 DOI）
    title: str
    citation: str
    publication_year: int | None = None
```

### 6.2 信号与公式

```python
class SignalCategory(str, Enum):
    CONTINUOUS  = "continuous"   # 连续特征（绝大多数）
    CATEGORICAL = "categorical"  # 类别/分组标签
    INDICATOR   = "indicator"    # 0/1 事件哑变量
    ESTIMATED   = "estimated"    # 需回归/滚动估计（beta、残差动量）


class SignalDirection(str, Enum):
    POSITIVE      = "positive"       # 高信号 → 高收益
    NEGATIVE      = "negative"       # 高信号 → 低收益
    NON_MONOTONIC = "non_monotonic"
    UNSPECIFIED   = "unspecified"


class CalculationStep(BaseModel):
    step_id: str                     # spec 内唯一，如 "s1"
    description: str                 # 人和 LLM 都能读的自然语言步骤
    expression: str = ""             # 可选的表达式；符号须解析到 input/constant/前序 step
    status: EvidenceStatus = EvidenceStatus.UNSPECIFIED
    evidence: list[EvidenceCitation] = []


class FormulaSpec(BaseModel):
    paper_expression: str = ""       # 论文原文写的公式（LaTeX 或纯文本）
    steps: list[CalculationStep] = []  # 有序步骤（D3）
    inputs: list[str] = []           # 引用 data.fields[].concept_id
    constants: dict[str, float] = {}
    output_concept: str = ""         # 最终输出的概念名
    evidence: list[EvidenceCitation] = []


class SignalSpec(BaseModel):
    definition: SourcedValue[str]
    economic_intuition: SourcedValue[str]
    direction: SourcedValue[SignalDirection]
    category: SignalCategory = SignalCategory.CONTINUOUS
    formula: FormulaSpec
    estimation: EstimationSpec | None = None   # category == ESTIMATED 时必填
```

> **相对 v1 的关键变化**：删除 `FormulaSpec.expression`（"给 codegen 用的表达式"）。
> 该字段与 `paper_expression` 的归属边界模糊——它既不是论文事实也不是评审决议。
> v2 中 codegen 直接消费 `steps`，规范化表达式若确有需要，由 `ImplementationResolution`
> 生成并记录，不混在论文层。

### 6.3 估计与窗口

```python
class TimeUnit(str, Enum):
    DAY = "day"; MONTH = "month"; QUARTER = "quarter"; YEAR = "year"


class WindowAnchor(str, Enum):
    FORMATION_DATE    = "formation_date"
    FISCAL_PERIOD_END = "fiscal_period_end"
    REPORT_DATE       = "report_date"
    OBSERVATION_DATE  = "observation_date"


class WindowSpec(BaseModel):
    start_offset: int          # 相对 anchor 的偏移（负数表示过去）
    end_offset: int
    unit: TimeUnit
    anchor: WindowAnchor
    is_expanding: bool = False # False = rolling


class EstimationMethod(str, Enum):
    TIME_SERIES_REGRESSION    = "time_series_regression"
    CROSS_SECTIONAL_REGRESSION = "cross_sectional_regression"
    ROLLING_STATISTIC         = "rolling_statistic"
    RESIDUALIZATION           = "residualization"
    OTHER                     = "other"


class EstimationSpec(BaseModel):
    method: EstimationMethod
    model_expression: str = ""            # 如 "r_i - rf = a + b*MKT + s*SMB + h*HML + e"
    estimation_window: WindowSpec
    measurement_window: WindowSpec | None = None   # 估计后取哪一段作为信号
    minimum_observations: int | None = None
    residual_definition: str = ""
    evidence: list[EvidenceCitation] = []
```

一个 `EstimationSpec` 覆盖 rolling beta、特质波动率、残差动量、Fama-MacBeth 系数等，
无需为每个因子新增字段。

### 6.4 数据需求

```python
class FieldRole(str, Enum):
    SIGNAL_INPUT     = "signal_input"
    UNIVERSE_FILTER  = "universe_filter"
    WEIGHTING_INPUT  = "weighting_input"
    BENCHMARK_INPUT  = "benchmark_input"
    ESTIMATION_INPUT = "estimation_input"


class RequiredField(BaseModel):
    concept_id: str            # spec 内唯一，公式与过滤器都引用它
    paper_name: str            # 论文里的叫法，如 "total assets"
    description: str = ""
    paper_source_hint: str = ""  # 论文说的数据集，如 "Compustat annual"
    roles: list[FieldRole]       # 取代 v1 的 is_signal_input: bool
    evidence: list[EvidenceCitation] = []


class DataSpec(BaseModel):
    signal_frequency: SourcedValue[TimeUnit]
    return_frequency: SourcedValue[TimeUnit]
    sources: list[SourcedValue[str]] = []    # 论文声称的数据集名
    fields: list[RequiredField] = []
    coverage_notes: list[str] = []           # 论文自述的覆盖缺口
```

> **`normalized_mapping` 已移出**：物理 source/column 属于 `ImplementationResolution`，
> 不是论文事实。这是 v1 权威混合最严重的一处。

### 6.5 样本期（三个期间独立）

```python
class Period(BaseModel):
    start_year: int | None = None
    end_year: int | None = None
    start_month: int | None = None
    end_month: int | None = None
    evidence: list[EvidenceCitation] = []
    status: EvidenceStatus = EvidenceStatus.UNSPECIFIED


class SampleSpec(BaseModel):
    data_coverage: Period      # 原始数据覆盖期
    formation: Period          # 可执行的形成/策略样本期
    reported_returns: Period   # 论文报告收益的样本期
```

v1 把三者压成 `sample_start_year` / `sample_end_year` 两个 int，
导致 "论文用了 1962 起的数据但只报告 1968 起的收益" 这类信息无处安放。

### 6.6 时序

```python
class LagBasis(str, Enum):
    FIXED_CALENDAR_LAG = "fixed_calendar_lag"   # 如 "财年结束后 6 个月"
    REPORT_DATE        = "report_date"          # 实际公告日
    POINT_IN_TIME      = "point_in_time"


class DataAvailability(BaseModel):
    lag_value: int | None = None
    lag_unit: TimeUnit = TimeUnit.MONTH
    anchor: WindowAnchor = WindowAnchor.FISCAL_PERIOD_END
    basis: LagBasis = LagBasis.FIXED_CALENDAR_LAG
    evidence: list[EvidenceCitation] = []


class TimingSpec(BaseModel):
    formation_rule: SourcedValue[str]              # "每年 6 月末" / "每月末"
    rebalance_frequency: SourcedValue[TimeUnit]
    holding_period: SourcedValue[int]              # 单位同 rebalance_frequency
    return_window: WindowSpec | None = None        # 持有期收益窗口
    data_availability: DataAvailability
```

滞后仍只在 DataLayer 实现，绝不进入生成的信号代码（硬约束不变）。

### 6.7 股票池与缺失处理

```python
class FilterSpec(BaseModel):
    concept_id: str          # 引用 data.fields[].concept_id
    op: FilterOp
    value: Any = None
    evidence: list[EvidenceCitation] = []


class UniverseSpec(BaseModel):
    description: SourcedValue[str]
    filters: list[FilterSpec] = []


class MissingStage(str, Enum):
    INPUT     = "input"       # 原始字段缺失
    SIGNAL    = "signal"      # 信号计算结果缺失
    PORTFOLIO = "portfolio"   # 组合构建阶段


class TransformStage(str, Enum):
    BEFORE_SIGNAL = "before_signal"
    AFTER_SIGNAL  = "after_signal"


class MissingPolicy(BaseModel):
    stage: MissingStage
    action: SourcedValue[str]        # 论文原话，不钳制到引擎枚举
    threshold: float | None = None


class TransformSpec(BaseModel):
    """缩尾/截断等变换。v1 错误地把 winsorize 塞进 missing_policy。"""
    kind: Literal["winsorize", "truncate", "standardize", "rank", "log", "other"]
    stage: TransformStage
    bounds: tuple[float, float] | None = None
    evidence: list[EvidenceCitation] = []
```

`UniverseSpec` 只用 `filters` 一个通道表达样本限制——不再有 v1 的
`portfolio.filter` 自由文本与 `universe_filters` 并存的双通道。

### 6.8 组合构建

```python
class ConstructionType(str, Enum):
    CHARACTERISTIC_SORT = "characteristic_sort"
    FAMA_MACBETH        = "fama_macbeth"
    DIRECT_PORTFOLIO    = "direct_portfolio"
    OTHER               = "other"


class SortRole(str, Enum):
    TARGET       = "target"        # 被研究的因子本身
    CONTROL      = "control"       # 如 size，用于隔离
    CONDITIONING = "conditioning"  # 条件排序的分组变量


class SortMode(str, Enum):
    INDEPENDENT  = "independent"   # FF 式独立双排
    SEQUENTIAL   = "sequential"    # 先 A 后 B
    WITHIN_GROUP = "within_group"


class GroupType(str, Enum):
    QUANTILE    = "quantile"
    CATEGORICAL = "categorical"
    THRESHOLD   = "threshold"


class BreakpointSpec(BaseModel):
    population: SourcedValue[str]   # "NYSE only" / "full sample"；论文原话
    values: list[float] = []        # 显式分位点，如 [0.33, 0.66]


class SortDimension(BaseModel):
    sort_id: str
    concept_id: str                 # 排序变量，引用 data.fields
    role: SortRole
    order: int                      # 1, 2, 3...（多维排序的先后）
    mode: SortMode
    group_type: GroupType
    group_count: int | None = None
    breakpoints: BreakpointSpec
    condition_on_sort_id: str | None = None
    evidence: list[EvidenceCitation] = []


class PortfolioLeg(BaseModel):
    leg_id: str
    side: Literal["long", "short"]
    selector: dict[str, Any]        # {sort_id: group_index}，多维时多个键
    evidence: list[EvidenceCitation] = []


class PortfolioSpec(BaseModel):
    construction_type: SourcedValue[ConstructionType]
    sorts: list[SortDimension]                     # 取代 v1 单个 sort 对象
    legs: list[PortfolioLeg]                       # 取代 long_leg/short_leg 枚举
    weighting: SourcedValue[str]                   # 论文原话，不钳制
    return_combination: SourcedValue[str]          # 论文原话，不钳制
    missing_policies: list[MissingPolicy] = []
    transforms: list[TransformSpec] = []
```

初期引擎能力支持 `len(sorts) <= 3` 且全部 `group_type == QUANTILE`（D4）；
超出者由能力矩阵显式拒绝，但论文结构在此层完整保留。

### 6.9 报告结果

```python
class Estimand(str, Enum):
    MEAN_RETURN = "mean_return"
    SPREAD      = "spread"
    ALPHA       = "alpha"
    COEFFICIENT = "coefficient"
    SHARPE      = "sharpe"
    OTHER       = "other"


class AdjustmentModel(str, Enum):
    """必须与引擎输出名一一对应（D5）。"""
    RAW  = "raw"
    CAPM = "capm"
    FF3  = "ff3"
    FF5  = "ff5"
    FF6  = "ff6"
    OTHER = "other"      # 引擎不产出 → Step7 标记为不可自动对比


class Unit(str, Enum):
    DECIMAL = "decimal"; PERCENT = "percent"; BASIS_POINTS = "basis_points"


class MetricStatistic(BaseModel):
    kind: Literal["t_stat", "standard_error", "p_value"]
    value: float


class ReportedMetric(BaseModel):
    metric_id: str
    label: str                      # 论文里的说法
    estimand: Estimand
    adjustment_model: AdjustmentModel
    estimate: float
    unit: Unit
    frequency: TimeUnit             # 月度/年度
    statistic: MetricStatistic | None = None
    sample_period: Period
    evidence: list[EvidenceCitation]   # 必填；TABLE_ONLY 时用 table_ref
    status: EvidenceStatus


class ReportedResults(BaseModel):
    primary_metric_id: str
    metrics: list[ReportedMetric] = Field(max_length=4)   # primary + 至多 3 个 secondary
```

Step7 仅在 `estimand` / `adjustment_model` / `unit` / `frequency` 四项全部兼容时
才进行确定性对比；否则输出 "不可自动对比" 并说明原因。

### 6.10 字段审计：v1 → v2

**移出 PaperMethodSpec（不是论文事实，权威归属错误）**

| v1 字段 | 去向 | 理由 |
|---|---|---|
| `data.normalized_mapping` | `ImplementationResolution` | 物理 source/column 是目录解析结果 |
| `returns_source` | `ImplementationResolution` | 收益股票池是实现选择，非论文事实 |
| `cz_acronym` | `ImplementationResolution` | 参考关联；留在抽取层还有 C&Z 泄漏风险 |
| `ambiguous_fields` | `MethodReview` | 评审发现 |
| `unsupported_fields` | `MethodReview` | 由能力矩阵推导 |
| `review_status` / `remediation_mode` | `MethodReview` | 评审状态 |
| `resolution_log` | `ImplementationResolution` | 决议历史 |
| `reextraction_attempts` | `MethodReview` | 流程计数 |

**直接删除（冗余或可推导）**

| v1 字段 | 删除理由 |
|---|---|
| `codegen_ready` | 可由 hash 匹配 + 无未决阻断 + 映射齐全推导；布尔标志可被绕过 |
| `FormulaSpec.expression` | 与 `paper_expression` 归属边界模糊；v2 由 `steps` 承担 |
| `portfolio.weighting_scheme` | 与 `portfolio.weighting` 完全重复（实际 artifact 中两者并存） |
| `portfolio.implied_factor_direction` | 与 `legs` + `signal.direction` 三重表达同一件事 |
| `portfolio.breakpoints.*` | 与 `portfolio.sort.*` 的 `quantiles`/`ls_quantile` 重复 |
| `portfolio.filter`（自由文本） | 与 `universe.filters` 双通道 |
| `reported_results.return_type` | 由 `ReportedMetric.estimand` 类型化取代 |
| `reported_results.spreads` / `t_stats` | 多态 list-或-dict，无单位无期限；由 `metrics[]` 取代 |
| `reported_results.main_spread` / `main_t_stat` | 由 `primary_metric_id` 指向取代 |
| `EvidenceSource.SINGLE` | 可由 `len(evidence) == 1` 推导 |
| `EvidenceSource.WEAK_OR_CONFLICTING` | 与 `CONFLICTING` 语义重叠 |
| `RequiredFieldSpec.is_signal_input` | 二值不足以表达多用途；由 `roles` 列表取代 |
| 各枚举的 `OTHER` 兼 "跑引擎默认值" 语义 | `OTHER` 只表示论文取值，替代决策由 registry 单点记录 |

**新增（v1 缺失，已验证会导致信息丢失）**

| 新字段 | 解决的问题 |
|---|---|
| `paper.document_id` | 论文文件的稳定标识，`factor_id` 哈希的输入 |
| `signal.category` | 区分连续/类别/指示/估计类信号，决定是否需要 `estimation` |
| `signal.formula.steps[]` | 多步公式无处安放（v1 挤在一个字符串里） |
| `signal.estimation` (`EstimationSpec`) | rolling beta / 残差动量 / IVOL 在 v1 完全无法表达 |
| `WindowSpec` | 估计窗口与测量窗口的区分 |
| `sample.data_coverage` / `formation` / `reported_returns` | 三个期间在 v1 被压成两个 int |
| `timing.holding_period` / `return_window` | v1 只有 `formation_month` + `rebalance_frequency` |
| `timing.data_availability.basis` | 固定日历滞后 vs 实际公告日，直接影响前视偏差 |
| `portfolio.sorts[]`（多维） | v1 结构上无法表达双排（D4） |
| `portfolio.legs[]` | v1 的 `LegSide` 枚举无法表达多维排序下的腿定位 |
| `TransformSpec` | winsorize 在 v1 被错误塞进 `missing_policy` |
| `MissingPolicy.stage` | v1 未区分输入/信号/组合三个阶段的缺失处理 |
| `ReportedMetric.adjustment_model` | v1 无法区分 raw / CAPM / FF3 alpha |
| `ReportedMetric.sample_period` | 不同指标可能来自不同样本期 |
| `EvidenceCitation.table_ref` | 表格数字无法引用正文（~80% 的数字，见 D5） |
| `EvidenceStatus.TABLE_ONLY` | 同上 |
| `data.coverage_notes` | 论文自述的数据缺口 |

**净效果**：顶层字段从 v1 的 24 个降到 11 个（其余按语义归入嵌套对象），
删除 13 个冗余字段，新增 16 个此前会静默丢失的字段。

### 6.11 其余三个工件

```python
class Disposition(str, Enum):
    AUTO_APPROVE              = "auto_approve"
    APPROVE_WITH_DEFAULT      = "approve_with_default"
    NEEDS_LLM_REVIEW          = "needs_llm_review"
    NEEDS_HUMAN_CONFIRMATION  = "needs_human_confirmation"
    BLOCKED                   = "blocked"


class Finding(BaseModel):
    field_path: str                  # 点分路径，如 "portfolio.sorts[0].breakpoints"
    kind: Literal["ambiguous", "unsupported", "missing_mapping", "inconsistent"]
    reason: str
    empirical_impact: Literal["high", "low"]
    disposition: Disposition
    paper_value: Any = None          # unsupported 时保留论文原值
    evidence: list[EvidenceCitation] = []


class MethodReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["methodreview.v2"]
    factor_id: str
    paper_spec_hash: str             # 绑定；论文 spec 变更即失效
    capability_version: str          # 评审时的引擎能力矩阵版本
    findings: list[Finding] = []
    status_overrides: dict[str, EvidenceStatus] = {}   # 人工覆盖 LLM 打标（D2）
    reextraction_attempts: int = 0

    @property
    def is_blocked(self) -> bool:
        return any(f.disposition == Disposition.BLOCKED for f in self.findings)


class ResolutionEntry(BaseModel):
    field_path: str
    expected_old_value: Any          # 不匹配则拒绝应用，防止基于陈旧视图决策
    new_value: Any
    reason: str
    reviewer: str
    resolved_at: datetime


class ImplementationResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["resolution.v2"]
    factor_id: str
    paper_spec_hash: str
    review_hash: str

    # 物理映射（从 PaperMethodSpec 移出）
    concept_mapping: dict[str, SourceColumn]   # concept_id -> {source, column}
    returns_source: str                        # 已注册的收益股票池名

    # 参考关联（从 PaperMethodSpec 移出）
    cz_acronym: str | None = None

    # 显式决议（仅追加）
    entries: list[ResolutionEntry] = []
    approved_substitutions: list[Substitution] = []   # 论文清晰但引擎不支持时的显式替代


class ResolvedMethodSpec(BaseModel):
    """实时重建的聚合视图（D1），不作为输入持久化。"""

    paper: PaperMethodSpec
    review: MethodReview
    resolution: ImplementationResolution

    @property
    def is_ready(self) -> bool:
        """取代 v1 的 codegen_ready 布尔标志——推导而非声明。"""
        return (
            self.review.paper_spec_hash == self.paper.content_hash()
            and not self.review.is_blocked
            and self._all_concepts_mapped()
            and self._construction_within_capability()
        )
```


## 7. 引擎能力契约

引入独立于 schema 枚举的、带版本的能力注册表。初始能力应声明引擎支持：

- 一个连续特征排序；
- 全样本或 NYSE 断点总体；
- 等权/市值加权；
- 当前固定的 return-combination 菜单；
- 已注册的股票池过滤操作；
- 当前已支持的信号可得性与再平衡路径。

应显式拒绝（而非钳制）以下情况：

- 多维和类别型组合构建；
- Fama-MacBeth 或自定义回归型组合估计器；
- 自定义加权公式；
- 不支持的重叠持有期构建；
- 没有已注册 PIT source 的 point-in-time 时序。

`other` 可以保留为论文方法取值，但绝不能表示“运行引擎默认值”。必须有单独记录的实现决策。

## 8. 校验规则

### Step 1 schema 校验

- 拒绝未知字段；
- 要求公式步骤、字段、排序、腿和指标 ID 唯一；
- 要求每个公式符号都能解析到 input、constant 或前序步骤；
- 要求每个 filter/sort/weighting/estimation 概念都引用已声明的字段角色；
- 除规范化排序外，保持 JSON 往返在字节语义上不丢失；
- 当论文被记录为 clear 时，要求高影响字段附带证据。

### Step 2 确定性评审

- 将“论文未说明”与“证据冲突”分开标记；
- 检查 timing、sample、holding 与 return-window 一致性；
- 在不预设 high-minus-low 的前提下检查 sort/leg/direction 一致性；
- 通过能力注册表识别不支持方法；
- 对高影响推断选择要求显式人工决策；
- 校验每条 resolution 路径都存在，且预期旧值匹配；
- 当 `paper_spec_hash` 变化时使评审决策失效。

### Resolution 就绪性

- 每个可执行字段都有已注册的物理映射；
- 不存在未解决的高影响阻断；
- 每个不支持的可执行方法都必须被阻断，或链接到显式批准的替代/替代轨道；
- 论文值与实现值保持可分离检查；
- 任何 readiness 标志都不能覆盖这些检查。

## 9. 迁移计划

不要求兼容旧 fixtures、生成的 run 工件或已保存会话。它们应以明确的 schema-version 提示失败，并重新生成。源码层迁移仍需增量推进，以保持主分支可测试。

### Phase A：冻结 v2 契约

1. 增加 v2 Pydantic 模型与规范化 JSON/hash 方法。
2. 将 schema 词汇与引擎能力词汇分离。
3. 增加严格校验与无损往返的契约测试。
4. 增加具有代表性的 schema 用例：
  - 简单会计比率；
  - 滚动残差信号；
  - 序贯双重排序；
  - Fama-MacBeth 结果；
  - 不支持的自定义加权。
5. 在这些测试定义清晰边界前，不改动 pipeline 消费方。

### Phase B：迁移抽取

1. 让抽取提示词在结构上与 `PaperMethodSpec` 完全一致。
2. 在可行处从模型元数据生成提示词 schema 片段。
3. 移除 `normalize_curated_schema` 和历史字段别名。
4. 停止 Step 1 填充物理 `normalized_mapping` 值。
5. 只持久化不可变论文工件与抽取诊断信息。

### Phase C：迁移评审与 resolution

1. 将 `ReviewGate` 改为返回 `MethodReview`，而非原地修改 MethodSpec。
2. 更新高影响字段路径与字段帮助元数据。
3. 构建确定性的引擎能力发现项。
4. 将物理 catalog 映射和 returns-universe 选择迁入 `ImplementationResolution`。
5. 让 resolution 日志只追加，并绑定到论文工件 hash。
6. 通过推导得到 readiness，而不是把 `codegen_ready` 回写到 Step 1 输出。

### Phase D：迁移代码生成与执行

1. 让 MetaCoder 与 `registry.build_config` 仅接受就绪聚合体。
2. 从 implementation mappings 解析插件输入，而不是用论文 source hints。
3. 在插件生成前硬阻断不支持的构造类型。
4. 保留现有“仅公式插件”与 DataLayer 滞后边界。
5. 在 run provenance 中存储 paper、review、resolution、config 和代码 hash。

### Phase E：迁移比较与评估

1. 通过 `primary_metric_id` 选择论文目标。
2. 以确定性方式归一化单位与方向。
3. 将论文值、评审核释、实现选择和实际引擎值作为独立比较列输出。
4. 在确定性证据包中展示默认值、替代项和不支持方法。
5. 更新抽取评估，仅对论文字段评分，不把 C&Z 答案导入抽取阶段。

### Phase F：迁移 API 与 UI

1. 后端 endpoint 返回分离的 paper/review/resolution 工件。
2. 更新 session 引用，并清晰拒绝旧工件版本。
3. 将 MethodSpec UI 拆分为论文证据、评审发现和实现映射视图。
4. 展示多重排序、估计窗口和类型化报告指标。
5. 清晰区分 unsupported 与 unresolved 状态。
6. 将 paper schema 和 engine capability 作为独立参考页面/区块暴露。

### Phase G：清理与文档

1. 将测试构建器和必要 fixtures 重写为 v2 形态。
2. 在所有消费方迁移后，删除历史扁平属性、别名和 normalizer 路径。
3. 更新架构与 replication-diagnosis 文档。
4. 将获批的方法学决策记录到 decision log。
5. 仅在模块归属或硬约束变化时更新 `AGENTS.md`。

## 10. 测试策略

### 契约测试

- 提示词骨架可通过 `PaperMethodSpec` 校验；
- 未知提示词字段会触发校验失败；
- 模型 dump/validate 往返不丢失任何值或证据；
- paper hash 不遗漏论文事实，也不包含评审决策；
- 多重排序和滚动估计示例保持可表示。

### 评审测试

- 论文未说明、歧义、矛盾和能力不支持是彼此独立的发现类型；
- 人工决策不能修改 `PaperMethodSpec`；
- 论文 hash 变更后，过期 resolution 必须失败；
- 不支持的论文取值必须原样保留；
- 未注册信号来源必须保持硬阻断。

### 执行测试

- 仅就绪聚合体可进入 MetaCoder；
- 语义一致时，当前简单因子应生成不变的引擎配置；
- 多重排序/回归构造在代码生成前被阻断；
- 滞后逻辑不得进入生成的插件代码；
- config provenance 记录 paper/resolution/engine 差异。

### 比较测试

- percent/decimal/basis-point 的归一化是显式的；
- raw return 不得在无警告/阻断时直接与 alpha 比较；
- 相反价差方向必须显式对齐，而不是猜测；
- 论文样本与回测样本不一致时应保持可见；
- 每个确定性比较值都要有 evidence key。

### 集成测试

- Extract -> Review -> Resolve -> Codegen -> Validate -> Backtest；
- 使用 v2 工件恢复 backend session；
- frontend 生产构建；
- 一个简单因子和一个有意设置为不支持的复杂论文目标。

## 11. 发布与失败策略

- 用 `schema_version="methodspec.v2"` 标记工件。
- 以明确“需重新生成”的消息拒绝 v1 工件；不要通过宽松兼容加载器重新解释它们。
- 不迁移生成的 `runs/`；按项目定义它们是可丢弃的。
- 仅当其 v2 paper/review/resolution 工件可独立评审时，才替换已提交 fixtures。
- 每个实现阶段保持窄而可执行；不要把 schema 重写与新组合估计器实现捆绑。

## 12. 拟议完成标准

当满足以下条件时，v2 迁移视为完成：

1. 抽取提示词与 Pydantic schema 具备机器测试验证的一致性；
2. 不存在可被静默忽略的抽取字段；
3. 论文事实在评审和执行过程中保持不变；
4. 每个可执行选择都可追溯到论文证据或人工决策；
5. paper 工件中不包含 source mappings 和 C&Z identities；
6. 当前引擎可通过新边界执行受支持的简单因子；
7. 多重排序与回归类论文可被忠实表示，并在不支持执行时清晰阻断；
8. Step 7 使用类型化且兼容的论文指标进行比较，并报告不兼容；
9. API、session 和 UI 界面将三类权威来源分离展示；
10. 聚焦测试集与全仓库测试均通过。

## 13. 实施前需确定的决策

以下问题应在编码 Phase A 前讨论并定案。

### D1. 工件形态

`ResolvedMethodSpec` 应作为完整快照持久化，还是每次加载都由不可变的 paper/review/resolution 工件重建？

**初步建议：** 重建并可选缓存；三份源工件保持权威地位。

**已定案（2026-08-07）：** 实时重建 + 审计快照。
- Step3 执行时：读 `paper.json` + `review.json` → 内存合并 → 驱动 codegen，不从磁盘读 resolved
- 同时将本次用的 resolved 写到 `runs/resolved/<timestamp>_<factor>.json` 作为审计快照（供调试和 diff 用）
- 快照是**输出产物**，不是输入；没有代码从这里读回去，因此不存在过期/失效问题

### D2. Evidence-status 归属

`clear/inferred/conflicting` 应存于 Step 1 输出，还是仅存在于 Step 2？

**初步建议：** Step 1 记录抽取层证据评估，Step 2 以独立命名记录权威评审结论。

**已定案（2026-08-07）：** 选 C — 两层，维持现有矩阵逻辑，加强 Step1 强制性。
- LLM（Step1）为每个字段打 `evidence_status` + 原文引用；不能只填值不打标（v2 schema 强制）
- Step2 矩阵维持：`CLEAR` → 自动过；`INFERRED/CONFLICTING` + `HIGH impact` → 人工介入
- 人工只在"LLM 不确定 + 高影响"时介入，其余自动处理
- Step2 人工可显式覆盖 `evidence_status`，须附理由记入 `resolution_log`

### D3. 公式中间表示

有序计算步骤应继续采用“结构化文本 + 表达式”，还是改用受限表达式 AST？

**初步建议：** 先采用有序类型化步骤和受限表达式语法；在真实因子明确需要前，不设计完整 DSL。
**已定案（2026-08-07）：** 选 A — 结构化文本步骤，不引入 AST。
- `FormulaSpec` 从两个字符串扩展为有序步骤列表：`[{step, description, expression?, evidence_status}]`
- ~70% 的简单因子 LLM 可以准确拆解步骤；~25% 复杂因子步骤标 `inferred` 走人工核查；~5% 难因子（rolling beta 等）由人工补写步骤
- 轻量符号验证：用正则从 `expression` 提取变量名，检查是否在数据源注册表里（替代 AST 静态分析）
- 不引入完整 DSL；Step4 沙箱执行是主要验证手段，优于 AST 静态分析
### D4. 不支持执行策略

评审者是否可以显式批准标准引擎近似方案，还是每个不支持构造都必须在 `original_method` 轨道保持不可执行？

**初步建议：** 保持 `original_method` 阻断；允许单独命名的近似/消融轨道，并显式记录替代项。

**已定案（2026-08-07）：** 
- **第一阶段支持双排序**（Size × Factor 等2维组合，独立或以第0维为条件的序贯排序）
- 原因：Fama-French 数据库标准做法，Hirshleifer 因子（现有数据集的16.7%）需要此功能，工作量小（~50-100行代码）
- 策略：不支持的更复杂方法（Fama-MacBeth回归、自定义权重、3维及以上排序等）仍在 `original_method` 上硬阻断，允许用单排序近似轨道
- 影响：降低对用户的"不支持"冲击，同时保持透明性（双排序版本和单排序近似版本并行报告）
- **引擎侧已实施（2026-08-07 同日）：** `BacktestExecutor` 新增 `compute_breakpoints_multi`/
  `assign_portfolios_multi`/`compute_portfolio_returns_multi`/`combine_portfolio_returns_multi`，
  仅在 `config["sort_dims"]` 恰好 2 维时触发，单维路径完全不受影响。`MAX_SUPPORTED_SORT_DIMENSIONS`
  相应设为 2（而非最初设想的 3），与引擎真实能力保持一致，避免 `ResolvedMethodSpec.is_ready`
  对引擎实际跑不动的构造放行。详见 `docs/decision-log.md` 2026-08-07 条目。

### D5. 报告指标粒度

是否应将每个表格单元都建为 `ReportedMetric`，还是仅覆盖主目标和直接相关比较目标？

**初步建议：** 主目标 + 一小组具名辅助指标；这是方法规范，不是完整表格转录格式。

**已定案（2026-08-07）：**
- `primary`（必填，结构化）+ `secondary`（可选列表，≤3个）
- `metric_type` 枚举 = backtest 引擎固定输出名（在 `field_contract.py` 维护对照表）
- 论文报告了引擎没有的指标 → `metric_type = "other"` + `label`，Step7 标记为"无法自动对比"
- 每个数字必须有 `source`，支持两种形式：
  - 正文有描述 → `evidence_status = "clear"`，`quote` = 原文字符串（Step2 自动验证）
  - 表格数字 → `evidence_status = "table_only"`，`quote = null`，填 `table/row/column` 定位，走人工核实路径
- `table_only` 是常态（~80% 数字来自表格），不是例外；Step7 报告中明确标注来源类型
- `secondary` 不强制枚举类型，保持提取简单

### D6. 论文目标粒度

当同一论文有多个定义或构造时，应共用一个含变体的 spec，还是每个目标一个 spec？

**初步建议：** 每个可独立执行/比较的目标使用一个 spec，并通过共同论文标识关联。

**已定案（2026-08-07）：** 选 B — 每个可独立执行的目标一个 MethodSpec，共享 `paper_ref`。
- 信号内部组合（sub-signal合并）仍是一个 MethodSpec（`compute_signal` 内处理）
- 多因子配置/线性组合策略超出横截面因子 scope
- 理由：符合论文独立报告惯例，独立管理/执行/对比，一个目标的修复不影响其他目标

### D7. 稳定标识符

哪些 ID 必须跨重抽取保持稳定：field concept IDs、formula-step IDs、sort IDs、metric IDs、target IDs？

**初步建议：** target 与 concept IDs 作为经评审的稳定 ID；step/sort/metric IDs 在可行时于 paper spec 内保持确定性。

**已定案（2026-08-07）：**
- `factor_id = sha256(paper_ref + "::" + target_name)[:16]`，确定性生成，不需要人工维护
- 同论文同目标 → 相同 ID（ablation / 多 track 能对应同一因子）
- 重提取同因子 → ID 不变，但用户打算全量重跑，旧结果自然作废
- 步骤 ID / sort ID / metric ID 不要求跨重提取稳定，提取时生成即可
- 实验条件（有无 reviewer 等）由 `run_config` / `track_type` 区分，不影响 `factor_id`

### D8. 迁移切换策略

实现应在并行 v1/v2 endpoints 后进行，还是采用一次分支级切换？

**初步建议：** 并行实现模型和契约测试，然后做一次协调的消费方切换；不运行双实证路径。

**已定案（2026-08-07）：** 选 B — 一次切换，旧 artifacts 直接作废重生。
- `runs/` 目录 gitignored，可随时删除；现有 4 个 MethodSpec 量小，无需兼容层
- 旧 fixtures 遇到 v2 schema 直接报错（`schema_version` 不匹配），提示重新生成
- 不维护 v1/v2 并行代码路径；按计划§9 迁移阶段逐步推进，保持主分支可测试

## 14. 建议讨论顺序

1. 确认范围与四类工件权威来源。
2. 先决策 D4，因为不支持方法策略决定研究主张边界。
3. 决策目标粒度与类型化报告结果语义。
4. 对照代表性论文评审信号/公式/估计表达能力。
5. 评审组合多重排序表示方案。
6. 决策 evidence-status 归属与 resolution 语义。
7. 批准迁移/切换策略后，再最终确定实施任务。
