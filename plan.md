# Data Layer 重新设计 Plan(CRSP-centric DataSource Registry + DataLayer 门面)

状态:**Round 1(§1–§6, P1–P5)已全部完成(2026-08-01)**。注册表成为唯一真相源、
catalog 派生、CRSP/Compustat/IBES 全迁、B 组快照式路径已删除、golden numbers 逐位不变。
Round 2(§7–§12, Agent onboarding)仍为 doc-only,待另起一轮。本文件保留为实施蓝图 +
沿革记录。

一句话总纲:
> 用 `DataSource Registry + DataLayer` 统一数据输入,**以 CRSP `permno` 为唯一证券身份骨架**。
> Round 1 只做确定性的基础设施重构;Agent 自动 onboarding 未知数据源(Round 2)在
> Round 1 稳定后另起一轮。

分工:**DataSource Registry** 解决"数据是什么、如何链接";**DataLayer** 解决"如何统一
加载";**CRSP** 解决"所有证券最终用什么身份和收益骨架"。

---

## 0. 本 plan 分两轮(边界画死)

| | 内容 | 性质 | 何时做 |
|---|---|---|---|
| **Round 1** | §1–§6:CRSP-centric Registry + DataLayer 门面 + 迁 CRSP/Compustat/IBES + 全部 fail-loud + 主键重复失败 + 旧路径当 oracle 逐位比 golden-number(含 B 组合并,带闸门) | 确定性、可 golden-number 验收 | **现在** |
| **Round 2** | §7–§12:Agent 发现未知源 → 用户给 path → 自动生成 SourceSpec 草稿 → 确认关键经验规则(含 link coverage/ambiguity 审核)→ 注册 → 继续流水线 | LLM 驱动、天然无法完全自动化 | **Round 1 全绿之后** |

**为什么切开**:Round 1 是纯基础设施,风险可控;Round 2 是一个 LLM 功能(读用户数据、
推断映射、生成草稿)。在一个还没稳定的重构之上盖 agent 会两头不稳。

---

# ========== Round 1(现在做)==========

## 1. 背景与目标

要解决的痛点:
1. **returns 和 signal 入口不统一**:`BacktestExecutor.load_data()` 直接调自由函数
   `build_crsp_monthly_panel_ciz`,两侧各走各的,没有门面。
2. **数据源元数据与读取逻辑分散**:元数据在 `catalog.py`,行为在 `__init__.py` 散装函数。
3. **快照式和声明式存在两套信号装配路径**(见 §3 B/D 组)。
4. **新增数据源要改多个地方**。
5. **缺失数据源可能被静默跳过**。

目标架构:
```
MethodSpec
    ↓
DataLayer
    ↓
DataSource Registry
    ├─ CRSP  (returns backbone + CRSP-based signal)
    ├─ Compustat Annual   (signal, SourceSpec)
    ├─ Compustat Quarterly (signal, SourceSpec)
    ├─ IBES               (signal, SourceSpec)
    └─ 后续注册的数据源
```

### 1.1 CRSP-centric backbone(顶层原则,非实现细节)
> **CRSP-centric backbone**:Round 1 以 CRSP `permno` 为唯一证券身份标准,以 CRSP monthly
> panel 为 returns / universe / month backbone。所有非 CRSP signal source 注册时必须声明
> 经过审核的 point-in-time CRSP link policy,并在进入 signal plugin 前标准化为
> `[permno, time_avail_m, ...]`。无法可靠映射到 CRSP 的数据源只能保持 experimental,
> **不得进入正式复制结果**。

```
CRSP monthly backbone
[permno, yyyymm, ret, me, exchcd, shrcd, siccd]
        ↑
        ├─ Compustat: gvkey → CCM → permno
        ├─ IBES:      ticker → IBES/CRSP link → permno
        ├─ 13F:       CUSIP → CRSP historical names → permno   (Round 2)
        └─ New source: native key → approved PIT link → permno
```

---

## 2. 已确认的设计决策

- **① CRSP-centric**(见 §1.1):permno 是唯一身份;CRSP monthly panel 是 returns/universe/
  month 骨架;非 CRSP 源必须声明 PIT link,标准化成 `[permno, time_avail_m, ...]` 才进 plugin。
- **② 单一真相源 = 注册表**:`catalog.py` 的派生视图(`signal_sources()`/`concept_map()`/
  `source_of_column()`/`RETURNS_UNIVERSES`)改成从 DataSource 注册表**派生**,不再手写 dict。
- **③ 声明式配置为主(SourceSpec),class 仅限特例**:
  - 普通 CSV/Parquet 源 = 一条 **`SourceSpec` 声明**,由通用 `SignalSource` 从配置构造;
  - 只有 CRSP CIZ 这类需要多文件组合 / 特殊字段推导(exchcd/shrcd)/ delisting 合并的
    才写**自定义 class**。
  - 理由:更少代码、更易 review、更难让 LLM 藏 bug —— 与 "declarative / clamp-to-menu" 一致。
- **④ CRSP 是双角色**:CRSP 既是 **returns backbone**,也是 **signal 源**(动量/短期反转/市值
  等直接用 CRSP 的 ret/prc/me 当信号输入)。DataLayer 必须能以两种角色调用 CRSP,
  **不能只有单一 `returns` role**。
- **⑤ 全迁**:CRSP-CIZ / Compustat 年+季 / IBES / link 表 全部迁入新体系。
- **⑥ 不做向后兼容**:老自由函数**全部删除**(不留薄壳);所有调用方同步改。
- **⑦ 缺文件 / 缺字段 / 缺 link table 一律直接报错**,绝不静默跳过。
- **⑧ 主键重复默认失败,不自动去重**(见下方边界)。
- **⑨ raw_filters 只作用于原始输入**(raw CSV),不作用于已清洗的 snapshot parquet。
- **⑩ returns 是特例**:CRSP returns backbone 走自定义 class,**不进** §7–§8 的
  "给 path 自动 onboarding" 闭环。

**⑧ 主键重复的边界(重要,避免误伤合法清洗)**:
- **禁止**:对**意外**出现的重复主键**静默去重**(取第一条、悄悄丢行、把一对多链接扩张
  成重复信号行)。
- **允许**:**声明过且经 review 的**清洗/tie-break(如 Compustat `indfmt=="INDL"`、
  CCM `primary_filter=linkprim=="P"`)——这是显式规则,不是静默去重。
- 判定点:清洗 + 链接**之后**,最终 `[permno, time_avail_m]` 若**仍然**非唯一 → **报错**。

---

## 3. 现状盘点(`src/infra/data_layer/__init__.py`)

### A. 通用注册 / 字典
- `FieldEntry` + `DataDictionary` — reviewer 用 `normalize_fields()`(读 `catalog.concept_map()`)。
- `SnapshotMetadata` + `SnapshotManager` — 快照目录登记。用户:backend/state.py、
  test_mvp_e2e、test_accruals_e2e。**保留**(与 DataSource 正交,见 §4.6)。

### B. 旧「快照式」信号主表机制(与 D 组重复)
- `CCMLinker`、`TimeAvailComputer`、`DataLayer.get_signal_master_table()` / `get_snapshot_data()`。
  用户:pipeline `_build_validation_slice`、生成脚本 compustat 模式、mvp/accruals e2e。

### C. Returns 面板(CIZ)
- `_ciz_shrcd`、`build_crsp_monthly_panel_ciz`、`load_daily_msf_ciz`。
  用户:`backtest_engine.load_data`、test_real_wrds_csv_loaders、生成脚本 multi_source 模式。

### D. 新「声明式」信号源机制(与 B 组重复)
- `SIGNAL_SOURCES`/`LINK_TABLES`、`link_to_permno`、`_load_link_tables`、
  `_read_raw_link_table_csv`、`_resolve_lag`、`_filter_raw_indfmt_indl`、
  `_filter_raw_ibes_statsumu`、`_read_raw_source_csv`、`_load_source_frame`、
  `signal_input_sources`、`assemble_signal_master_table(_from_sources)`。
  用户:test_signal_master_multisource、生成脚本(`signal_input_sources` bake 进脚本)。

### E. 补充 / 尽力而为因子源
- `load_crsp_index_factors`、`load_liquidity_factors`、`load_institutional_ownership_13f`、
  `load_ibes_recommendation_detail`、`load_ibes_unadjusted_actual`。用户:仅 test_real_wrds_csv_loaders。
  **E 组延后**(不进 Round 1;暂原样保留,不影响 returns/signal 统一)。

> B 组和 D 组是**两套并行做同一件事**(拼信号主表)的机制。Round 1 采用**渐进式彻底合并**
> (§5,带闸门):最终只留**一个公开 DataLayer API**。

---

## 4. 目标架构

### 4.1 文件布局
```
src/infra/data_layer/
  sources.py     ← 新增:DataSource 基类 + SourceSpec + CrspLinkSpec + 具体源/配置 + 注册表(唯一真相源)
  catalog.py     ← 改为从 sources 注册表【派生】所有查询视图
  __init__.py    ← DataLayer 门面(public API);保留 DataDictionary / SnapshotManager 等
```
依赖单向无环:`sources.py ← catalog.py ← __init__.py`。sources 必须自包含。

### 4.2 SourceSpec(声明式配置,普通 CSV/Parquet 源)
```python
@dataclass
class SourceSpec:
    name: str
    snapshot_table: str              # 冻结 snapshot 中的表名
    raw_file: str | None             # data/local/<csv>;None = 仅从 snapshot 读

    physical_columns: set[str]
    concept_columns: dict[str, str]  # 论文概念别名 -> 物理列

    source_key: str                  # 源自己的原生 id 列
    observation_date: str            # 观测/可得日期列
    availability_policy: str | int   # lag(月)或规则名(如 "accounting_lag_months")
    crsp_link: CrspLinkSpec          # PIT 链接到 permno(见 4.3)

    frequency: str                   # monthly/quarterly/annual —— 供 §6 对齐检查
    raw_filters: dict[str, Any] | None = None   # 仅作用于 raw 输入(§2⑨),如 {"indfmt":"INDL"}
```

### 4.3 CrspLinkSpec(PIT 链接规则)
```python
@dataclass
class CrspLinkSpec:
    native_key: str                  # 源侧 id;permno-keyed 源填 "permno"
    link_table: str | None           # link 表名;permno-keyed 源填 None

    link_native_key: str | None = None
    link_permno_column: str = "permno"

    link_date: str | None = None     # 在哪个日期判断 link 有效
    valid_from: str | None = None    # 有效期起(如 namedt / linkdt)
    valid_to: str | None = None      # 有效期止(如 nameendt / linkenddt)

    valid_filters: dict[str, list] | None = None    # 数据质量过滤(如 CCM linktype/linkprim)
    primary_filter: dict[str, Any] | None = None    # 一对多 tie-break(如 linkprim=="P")
```
已含 `permno` 的源:`CrspLinkSpec(native_key="permno", link_table=None)`。

### 4.4 DataSource 抽象 + 通用/特例实现
```python
class DataSource(ABC):
    name: str; role: str             # "returns" | "signal"(CRSP 两者皆可,见 §2④)
    @abstractmethod
    def load(self, data_dir, columns, ctx) -> pd.DataFrame: ...

class SignalSource(DataSource):      # 通用;从 SourceSpec 构造
    # 基类统一执行:
    #   读必要字段 -> clean()(仅 raw 时套 raw_filters) -> PIT link_to_permno(记审计指标)
    #   -> 算 time_avail_m -> 验证字段/唯一键(§2⑧) -> 返回 [permno, time_avail_m, *cols]
    # 子类通常只覆盖:clean() / 特殊读取 / 特殊 link / 特殊 availability 规则

class ReturnsUniverse(DataSource):   # 自定义 class(CRSP CIZ)
    universe_aliases: list[str]      # ["us_equity_crsp"] -> RETURNS_UNIVERSES 派生
    # load() -> [permno, yyyymm, ret, me, exchcd, shrcd, siccd, dlret]
```
CRSP 同时以 returns backbone 和 signal 源两种角色被 DataLayer 调用(§2④)。避免在
`DataLayer` 里写越来越长的 `if source == ...` 分支。

### 4.5 DataLayer 门面
```python
class DataLayer:
    def load_returns(self, universe_name) -> panel       # load_data 调这个
    def load_signal_master(self, by_source, lag) -> table
    def get_source(self, name) -> DataSource             # reviewer 校验用
```
`BacktestExecutor.load_data()`:
```python
if data is not None: return data
return DataLayer(self.data_path).load_returns(config["returns_universe"])
```

### 4.6 SnapshotManager 保留(与 DataSource 正交)
- DataSource 定义"数据是什么、怎么标准化";Snapshot 定义"本次实验用哪一份冻结数据"。
- 长期理想:`Raw → DataSource ingest → 冻结 immutable snapshot → DataLayer → Backtest`。
- 本轮不建完整 ingest 平台,但**正式回测应优先消费 snapshot**,避免每次重新解释大 CSV。

### 4.7 实现边界:不每次 load 都物理膨胀成大表
"CRSP-centric" ≠ 每次 load 都和完整 CRSP 月度大表物理合并。实际流程:
```
外部 source → PIT identifier link → 稀疏事件表 [permno, time_avail_m, fields]
    → 计算 signal → [permno, yyyymm, signal] → backtest engine → CRSP monthly backbone
```
既以 permno 为统一身份,又不让每个 source load 扩张成巨大证券月度面板。

### 4.8 顺手修掉的不一致
CRSP-CIZ 文件路径现在两条路读的位置不同(returns 侧 `<dir>/`,signal 侧 `<dir>/local/`)。
统一到 CRSP 源一处定义后消失。

---

## 5. 旧、新信号装配路径:渐进式彻底合并(Q1 = a,带闸门)
1. 先迁 returns。
2. 再迁声明式 signal source(D 组 → SourceSpec/class)。
3. 新 DataLayer 支持现有 snapshot parquet(§4.6)。
4. **比较新旧 Compustat 路径的行级输出**:`permno` / `time_avail_m` / link coverage /
   golden-number 逐位比对。
5. 一致后**删除旧独立入口**(B 组);旧实现短期作 **test oracle**。
6. 最终只保留**一个公开 DataLayer API**。

**闸门(降低 golden-number 风险)**:
- 合并放在 **Round 1 最后阶段(P4)**;前面 P1–P3(returns + 声明式 signal 统一)先独立跑绿。
- P4 严格用旧快照路径当 oracle,mvp/accruals golden number **逐位一致**才算过。
- **Fallback**:若 P4 风险过高/对不齐,P1–P3 仍是可交付独立成果,P4 可单拆一轮。

---

## 6. 多数据源对齐(Round 1 范围)
当前按精确 `[permno, time_avail_m]` 月份合并,适合单源 / 同频同可得月份。
**暂不支持** annual+monthly / quarterly+daily / 需要 carry-forward 的公式。

**关键**:Round 1 不实现通用 as-of join,但 **reviewer/codegen 必须 BLOCK 不支持的组合**
(靠 SourceSpec.frequency 检测),不能在明知对齐错误时继续跑。以后再加 `event_aligned` /
`asof_available` / 最大 stale months / carry-forward policy(Round 2+)。

---

## 6b. MethodSpec 影响:Round 1 不动,Round 2 只加一个可选字段
MethodSpec 描述"论文说了什么"(concept → source → column),registry/DataLayer 描述
"已注册源怎么加载"——两层分开。

- **Round 1:MethodSpec 零改动**。`data.normalized_mapping` / `returns_universe` /
  `resolved_sources()` / `accounting_lag_months` / `portfolio.universe_filters` 全部不变。
  frequency 是**源的属性**(SourceSpec.frequency),reviewer 去 registry 查,不进 MethodSpec。
  - **唯一约束**:`method_spec.py` 依赖 `catalog` 的查询函数
    (`resolve_concept`/`signal_sources`/`concept_map`/`source_of_column`)——catalog 改成从
    registry 派生后,**这几个函数的签名必须保持不变**,MethodSpec 才零改动。
  - **判定信号**:如果 Round 1 真的逼你改 MethodSpec,说明抽象边界漏了(加载细节渗进了论文
    事实模型),要停下来重想,而不是顺手改 spec。
- **Round 2:加一个可选、向后兼容的字段** —— normalized_mapping 条目上的
  `"status": "unregistered"`(见 §7),让 reviewer 设 `UNKNOWN_DATA_SOURCE` +
  `codegen_ready=false`。老 spec 没这个字段照样 validate。

---

## Round 1 分阶段实施(每阶段跑全测,green 才进下一步)—— **全部完成 ✅**

- **P0 ✅**:确认 §2 决策。
- **P1 ✅**:`sources.py` 骨架 —— `DataSource`/`SourceSpec`/`CrspLinkSpec`/`SignalSource`/
  `ReturnsUniverse` + 注册表 + `register`。导入无副作用(门面方法推迟到 P2)。
- **P2 ✅**:迁 CRSP(returns + signal 双角色,§2④)+ daily;`load_data` 改走门面;删 C 组;
  改 test_real_wrds_csv_loaders。
- **P3 ✅**:迁 Compustat/IBES(SourceSpec + CrspLinkSpec)/ link 表;`catalog.py` 改派生
  (逐字节兼容);删 D 组;reviewer 无需改;改 test_signal_master_multisource + test_data_sources。
- **P4(带闸门,§5)✅**:动手前先做只读等价核验(B/D 两路径逐字节一致),裁决 ghost-permno=
  保留;合并 B 组(快照式)+ pipeline + 生成脚本 compustat 模式(并入 multi_source loader);
  mvp/accruals e2e 逐位比 golden-number 通过;B 组彻底删除。
- **P5 ✅**:清死代码;更新 `AGENTS.md` Module Map / `docs/architecture.md` /
  `docs/roadmap.md` / `docs/decision-log.md` / `CHANGELOG.md` / repo memory。

每个 P 验收:`.venv/bin/python3 -m pytest tests/ -q` 全绿,`ruff check src/` 干净,
golden-number e2e(mvp/accruals)数值不变。**生成脚本(subprocess)必须实际跑一次验证**。

---

# ========== Round 2(Round 1 稳定后)==========

## 7. Agent 发现未知数据源
```
Agent 读论文 → 识别用到的数据源 → 查 Registry
    ├─ 已注册：正常进入 MethodSpec
    ├─ 可能是已有来源别名：请求确认映射
    └─ 真正新来源：生成 onboarding request,阻断 codegen
```
未知源**不能**:默认成 Compustat / 猜一个现有 source / 自动选替代数据 / 直接生成 plugin /
缺数据时假装完成复制。MethodSpec 保留论文事实:
```json
{ "concept": "institutional_ownership", "source": "thomson_reuters_13f",
  "column": null, "status": "unregistered" }
```
Reviewer 设 `UNKNOWN_DATA_SOURCE` + `codegen_ready=false`。

## 8. 用户给 path 后自动生成 DataSource(默认产出 SourceSpec,不产出任意代码)
用户提供 `data/local/new_source.csv`,系统:
1. **安全读 schema + 少量样本**(仅表头 + 脱敏少量行;严禁把评估 ground-truth 混入,
   遵守 AGENTS.md 的 SignalDoc 隔离)。
2. 按论文需要匹配字段。3. 识别证券标识符。4. 识别 observation/publication date。
5. 推断频率 + 候选唯一键。6. 推荐 CRSP link table。
7. **生成 `SourceSpec` 草稿**(默认;只有 CRSP 级别特例才 escalate 给人写 class —— §2③)。
8. 生成 contract tests(§12)。9. 展示未确定的经验规则 + link 审核(见下)。10. 用户确认后注册。
11. 重跑 Step 2 reviewer。

接口:
```python
draft = DataLayer.onboard_source(path=..., paper_source=..., required_concepts=...)
# -> SourceDraft(source_spec, field_mapping, inferred_schema, unresolved_decisions, validation_report)
DataLayer.approve_source(draft)
```

**onboarding 草稿必须向用户展示 link 审核**:原始 identifier / 推荐 CRSP link table /
在哪个日期判断 link 有效 / validity window / 一对多选择规则 / link coverage /
unmatched 与 ambiguous 数量。示例:
```
Source:             Thomson Reuters 13F
Native identifier:  CUSIP
Proposed CRSP link: CRSP historical names
Link evaluation:    filing_date
Validity columns:   namedt / nameendt
Matched rows:       87.4%
Ambiguous rows:     126
Status:             Requires confirmation
```
**必须阻塞**的情况:没有可用 CRSP link / 只有当前 identifier 映射没历史有效期 /
存在未解决一对多 / 不知用 observation 还是 publication date / link coverage 低于确认阈值。

## 9. 优先声明配置,而非任意代码
普通源优先生成 `SourceSpec`(§4.2);通用 DataSource 从配置构造。只有多文件组合 /
特殊字段推导 / delisting 合并 才生成自定义 class。更易验证,也降低 LLM 生成任意数据处理
代码的风险。

## 10. 必须由用户确认的经验规则(Agent 可推荐,不可静默决定)
CRSP link table 选择 / 用报告期末 vs 发布日 vs filing date / 固定 lag / 重复保留规则 /
样本过滤 / 是否允许 carry-forward / 是否可用替代源 / 是否适合正式回测。
- 若数据已含 `permno + yyyymm`:大部分自动,用户主要确认字段映射。
- 若是 CUSIP/13F 等复杂源:必须确认 point-in-time link 和 publication date。

## 11. 新数据源状态机 + 可复现性
`production_ready = False` 默认;满足以下才可 True:字段完整 / identifier 可 PIT 映射 /
availability date 明确 / 重复规则明确 / contract tests 通过 / 用户批准经验规则。
否则保留 experimental,**不得进入正式复制结果**。
> **可复现性**:已注册 SourceSpec 之后被改(改 filter/lag/link)会静默改变历史结果 ——
> 注册项应带版本/哈希,或写进 evidence,保证"某次实验用哪版 source 定义"可追溯。

## 12. 每个新源的 contract test(自动生成,防"假绿")
文件可读 / 请求字段存在 / 类型可转换 / identifier 能链到 `permno` / `time_avail_m` 正确 /
主键无意外重复 / 缺文件-字段-link 明确失败 / 无未来信息泄漏。
> 期望值尽量来自确定性推断或用户确认,别让 LLM 生成能自我通过的空测试。

**每次链接必产生审计指标**(记进 evidence,不静默):
```
input_rows / matched_rows / unmatched_rows / match_rate /
ambiguous_rows / rows_removed_by_link_filters / unique_native_ids / unique_permnos
```
不能静默:取第一条 link / 用当前 CUSIP 映射历史 / 丢大量 unmatched rows /
把一对多链接扩张成重复信号行。

---

## 13. 风险
- **生成脚本(subprocess)**:改公开 API 名会直接让 e2e 生成脚本执行失败 —— 每阶段必须
  实际跑生成脚本,不能只跑单测。
- **golden-number 漂移**:P4 合并快照路径时 mvp/accruals 数值有风险 —— 逐位比对 + 闸门 Fallback。
- **循环导入**:守住 sources ← catalog ← __init__ 单向依赖。
- **CRSP 双角色遗漏**:迁移时必须保留"CRSP 作为 signal 源"的路径(§2④),否则漏掉一大类
  直接用 CRSP 列的因子。
- **一次改太多**:严格 P1→P5 小步,每步全绿再进。
- **Round 2 安全**:onboarding 读用户数据 + LLM 推断,须遵守泄漏隔离、默认只出声明式
  SourceSpec、测试防假绿、link 审核阻塞。
