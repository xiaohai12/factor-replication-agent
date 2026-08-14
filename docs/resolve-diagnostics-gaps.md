# Resolve 阶段诊断盲区 -- 待讨论清单

状态：待讨论（2026-08-11 整理，尚未决定任何修复方案，尚未实施）

背景：从 `compustat_listing_history` 这个具体 case 一路排查下去，发现 `/resolve`
（`ResolvedMethodSpec.is_ready` 及其下游）目前有好几处"判断逻辑本身是对的，但
判断的原因对用户完全不可见"或者"判断逻辑本身就没覆盖到"的地方。这个文件把它们
分开列出来，逐条讨论要不要修、怎么修。

每一条的结构：**现状** / **代码位置** / **后果** / **可能的修法（未决定）**。

---

## 问题 1：`unsupported_universe_filters()` 算了但从没往外传

**现状**：`ResolvedMethodSpec.unsupported_universe_filters()` 会找出"已经解析到
物理列、但那一列不是引擎 `filter_universe` 认识的 native 列"的 universe filter
（比如解析到了某个 Compustat 专属列）。这个方法的结果只被用来算 `is_ready` 这一个
布尔值，具体是哪个 filter 造成的，从来没有被返回过。

**代码位置**：
- 判断逻辑：`src/infra/models/method_spec.py::ResolvedMethodSpec.
  unsupported_universe_filters()` / `_universe_filters_supported()`
- `/resolve` 端点返回值：`backend/routers/methodspecs.py::resolve()`，只返回
  `{resolution, is_ready, unmapped_concepts, llm_matched_concepts}`，没有这一项
- 前端展示：`frontend/src/pages/SessionDetailPage.tsx` 里 "This needs human
  resolution..." 那个卡片，只画 `findings.disposition==='blocked'`（现在是死代码）
  和 `unmapped_concepts`

**后果**：`is_ready=false` 且 `unmapped_concepts`/`findings` 都是空的时候，用户只能
看到一句通用兜底提示，不知道真正原因，也没有下一步能做什么。

**可能的修法（未决定）**：
- `/resolve` 返回值加 `unsupported_universe_filters: string[]`
- 前端把这个列表渲染出来，并说明"解析到了 `<列>`，但引擎目前只支持 `<native 列
  清单>`"
- 给 `FilterSpec.accepted_unapplied`/`unapplied_reason` 配一个实际的写入路径
  （目前这两个字段在整个 `backend/`/`frontend/` 里零引用，只存在于 Pydantic 模型
  本身——没有任何 API/UI 能设置它们）

---

## 问题 2：`_construction_within_capability()` 连诊断方法都没有

**现状**：`is_ready` 的第三个条件——sort 维度是否超过
`MAX_SUPPORTED_SORT_DIMENSIONS`（=2）、每个 sort 的 `group_type` 是否都是
`quantile`——只返回一个 bool，**没有对应的"哪个 sort 不满足"列表方法**，比问题 1
更彻底地黑箱。

**代码位置**：`src/infra/models/method_spec.py::ResolvedMethodSpec.
_construction_within_capability()`

**后果**：论文用了三重排序，或者用了非分位数分组（比如按行业分组），`is_ready`
会是 `false`，用户看到的跟问题 1 一模一样的通用提示，完全不知道是排序结构的问题。

**可能的修法（未决定）**：
- 加一个 `unsupported_construction_reasons() -> list[str]`（或类似命名）
  返回具体原因（"3 个 sort 维度，超过引擎支持的 2 个"/"sort 'xxx' 用了
  categorical 分组，引擎只支持 quantile"）
- 同样接进 `/resolve` 返回值 + 前端展示

### 讨论结论（2026-08-12，最终版）

`is_ready` 不再检查构造能力——`_construction_within_capability()` 整个删除。
全部改为**非阻塞的自动降级 + 统一通知**，理由/机制见下。

**核心统一原则**（本次讨论的最终共识，取代所有中间过程提到的
`Substitution`/按维度人工批准等方案——那些都不用了）：

> 所有 backtest engine 实际读取的字段，只要值不在引擎支持的菜单里，一律走
> **同一个** clamp+记录+通知函数，不区分"这个字段需不需要 OTHER 枚举"、
> "值是不是自由文本"——`categorical`/`day`/`within_group`/字面 `"other"`
> 对这个机制来说是同一种情况：值不在 `allowed` 集合里，clamp 成默认值，
> `defaults_applied` 记一条，生成一条 `disposition=NEEDS_HUMAN_CONFIRMATION`
> 的 Finding（不阻塞 `is_ready`，只是让人工能看见"这里用了默认值，为什么"）。
> `paper_value` 直接用该值自身的字符串（`"categorical"`/`"within_group"` 等
> 本身已可读）；只有值恰好是字面 `"other"` 时才额外查
> `SourcedValue.unsupported_value` 补充论文原文自由文本。

**一张统一登记表**（`review.py`/`registry.py` 共用同一份，避免两边字段清单漂移
不一致）：

| 字段 | 允许集合 | 默认值 |
|---|---|---|
| `portfolio.weighting` | `{vw, ew}` | `vw` |
| `portfolio.return_combination`（升级为真正 Enum + `OTHER`） | `{extreme_group_spread, average_leg_spread, single_signal_portfolio_return, full_portfolio_return}` | `extreme_group_spread` |
| `portfolio.sorts[].breakpoints.basis` | `{full_sample, nyse}` | `nyse` |
| `portfolio.missing_policies[].action` | `{drop}` | `drop` |
| `portfolio.sorts[].group_type`（加 `OTHER`，保留 `categorical`/`threshold`，包一层 `SourcedValue`） | `{quantile}` | `quantile` |
| `portfolio.sorts[].mode`（加 `OTHER`；`within_group` 原样透传给引擎，引擎侧 fail-loud，不在 `build_config` 层默认成 sequential） | `{independent, sequential}` | `independent` |
| `timing.rebalance_frequency`（现在是裸 dict `.get()`，漏了 `TimeUnit.DAY`，改成走统一函数） | `{annual, quarterly, monthly}` | `monthly` |
| `timing.data_availability.lag_unit`（现在虽然记了 `defaults_applied`，但理由写成"unspecified"是假的——论文其实说了"day"，只是换算不了，需要修成准确归因） | `{month, quarter, year}` | `month`（换算比例不变） |
| sort 维度数（`len(portfolio.sorts)`，结构性，非枚举） | `<= MAX_SUPPORTED_SORT_DIMENSIONS`（=2） | 保留 target + 按 `order` 排前面的非 target 维度，多余的砍掉 |

**关键澄清**：`TimeUnit`/`SortMode` 本身**不需要**因为这次改动加 `OTHER`——
`day`/`within_group` 都是完整、具体、有名字的已知值，不是"论文写了归类不了的
自由文本"；只有 `WeightingScheme`/`BreakpointBasis`/`MissingActionScheme`/
`ConstructionType`/新升级的 `return_combination`/`group_type` 这几个字段的
`OTHER` 成员才是为了在 Step1/2 抽取时给 LLM 一个"这段论文原文分类不进已知选项"
时可写的兜底——`OTHER` 要不要加是抽取时的问题，跟"引擎执行时怎么处理不支持的
值"这次讨论的统一 clamp 机制是两件独立的事，不要混着决定。

**已排除的候选方案**（讨论过程中提出过，最终没采用，避免以后重新提）：
- 按维度单独记一条 `Substitution` + `approved_by` 人工批准——太重，`is_ready`
  不需要为构造能力卡人工审批，自动降级+事后可见就够了。
- 把 sort 维度数超限也需要人工批准才能继续——不需要，跟其余字段一样自动裁剪。

**尚待实现，未写代码**：
1. `GroupType`/新 `ReturnCombinationScheme` 加 `OTHER`；两个字段包 `SourcedValue`
2. `review.py`：新增统一登记表 + 无条件通知检查（不依赖 `EvidenceStatus`，
   `value` 不在允许集合就必定生成 Finding）；`_high_impact_sourced_values`
   补上新纳入的字段
3. `registry.py`：`rebalance_frequency`/`lag_unit`/`sort.mode`/sort 维度数
   四处改用统一 clamp 函数；`sort.mode=within_group` 原样透传，引擎侧新增
   fail-loud 检查（`assign_portfolios_multi` 收到未实现的 mode 时报错，不
   静默当 sequential 处理）
4. 前端：新 Finding 的 `canPatch` 判断 + 下拉框默认预填引擎实际会用的值
5. `docs/decision-log.md` 新条目（部分恢复 D4 的可见性，但不阻塞——跟
   2026-08-10 的决定不冲突，只是补上当时缺失的"通知"层）
6. **`prompts/review_gate/llm_review.md` 更新**（`return_combination`/
   `group_type`/`sort.mode` 的 `OTHER` 分类是 LLM 在 Step2 review loop 里
   自己判断、自己填 `unsupported_value` 的，不是任何确定性代码算出来的——
   2026-08-10 起 `normalize_engine_vocabulary` 等确定性归一化函数已被删除，
   分类工作全部在 LLM 手里。三处要同步改：(a) 第 1 节 item 5 的
   "`unsupported_value` only present on ..." 字段清单加上新字段；
   (b) 开头 "pay extra attention" 高影响字段清单同步加；(c) 第 3 节
   "Classifying weighting/construction_type/..." 逐字段加新的分类规则文字
   （`return_combination` 的 4 个 token 分别是什么意思、`group_type` 的
   `quantile`/`categorical`/`threshold`/`other` 怎么区分）。`schema_render.py`
   的 `splice_schema_skeleton` 只会自动把新枚举的合法取值列出来，**不会**
   自动生成判断规则，第 3 节的文字必须手写。
7. 测试：现有手动构造 `SortDimension`/`PortfolioSpec` 的地方，`group_type`/
   `return_combination` 字段类型变了要跟着改

### 实现前复查（2026-08-12）：两点补充决定

**A. 同一字段最多一条 Finding，`value=="other"` 优先，替代 D2 检查**——
`_evidence_status_finding`（D2，只看 `EvidenceStatus`）和这次新加的"无条件
通知"检查（只看 `value` 是否等于 `"other"`）是两条独立判断，同一个字段
（如 `weighting`）如果同时满足"`status=inferred`"和"`value=="other"`"，
会重复生成两条 Finding，前端会画出两张卡片、两个绑定同一个
`valuePatchDrafts[fieldPath]` 的下拉框，冗余且容易误导。**已决定**：
`value=="other"` 时，跳过该字段的 D2 evidence-status 检查，只生成新的
"unsupported menu value"Finding（不管 `status` 是什么）；只有
`value!="other"` 时才走原来的 D2 逻辑。实现时 `_compute_findings` 需要
按字段做一次"新检查优先"的短路，而不是简单地把两个列表 `extend` 在一起。

**B. sort 维度裁剪的 tie-break**——`SortDimension.order` 没有唯一性校验，
两个非 target 维度 `order` 相同时，"按 order 排序保留"依赖 Python 排序的
稳定性（即隐式依赖原始列表顺序）。**已决定**：`order` 相同时按 `sort_id`
字母序作为 tie-breaker，显式写进 `_clamp_sort_dims` 的排序 key，不依赖
隐式的列表顺序。

（顺手记录，不在这次范围内：`registry.py`/`KNOWN_CONFIG_KEYS` 目前不含
`sort_dims`，意味着 caller 现在也没法通过 `config_overrides` 覆盖它——
这是既有行为，跟这次改动无关，不需要处理。）

### 状态：已实现（2026-08-12）

代码改动见 `CHANGELOG.md` 同日条目、`docs/decision-log.md` 同日条目
（"部分恢复 D4 的可见性"）。全量测试 548 passed / 18 skipped，前端
`npm run build` 干净。

---

## 问题 3：Filter 的"值编码"跟物理列不匹配（`docs/known-gaps-paper-first-v2.md`
gap #2，历史遗留，至今未修）

**现状**：即便 filter 的 `concept_id` 被正确解析到了引擎认识的物理列，`value`
本身可能还是论文原文的措辞（比如 `["NYSE", "Amex", "NASDAQ"]`），而不是那一列
真实的物理编码（`exchcd` 是数字 1/2/3）。

**代码位置**：
- 值直接透传，无校验：`src/steps/step3_codegen/registry.py::build_config()`
  拼 `universe_filters` 那一段，`f.value` 原样放进去
- 实际执行：`BacktestExecutor.apply_universe_filters`
  （`src/infra/backtest_engine/__init__.py`）

**后果**：**resolve 阶段完全测不出来，`is_ready` 会是 `true`，看起来一切正常。**
`series.isin(["NYSE", "Amex", "NASDAQ"])` 对一个整数列永远是 `False`——filter
悄无声息地把整个 universe 筛成空的。这个空面板会一路往下传（`filter_universe`
→ 0 行 → `apply_signal_holding_period` 退化成没有 CRSP 列的裸 frame），**最后在
好几步之后的 `compute_breakpoints` 冒出一个完全不相关的报错**："config
['breakpoint_source']=='nyse' requires an 'exchcd' column ... but the loaded
returns panel has none"——但 `exchcd` 明明是有的，只是被空面板级联坑了。

**后果严重程度**：比问题 1/2 更麻烦——不是"卡住不让走"，而是"悄悄跑出错误结果，
或者在几步之后报一个不相关的错"。

**可能的修法（未决定）**：
- 一个"按 concept 建标签 -> 物理编码"的映射表（类比已有的
  `CIZ_EXCHCD_MAP`），接进 resolve/`build_config`
- 至少在 build/validate 时做一个"filter 的 value 是否跟列的实际值域有交集"的
  快速检查（哪怕不做完整翻译，先做 fail-loud）

### 讨论结论（2026-08-12，已实现）

**跟问题 1 的 `derivation`/LLM codegen 机制是两回事，不复用**：讨论中发现
"值编码不匹配"（这个问题的例子）根本不需要"计算出一个新值"——物理列
（`exchcd`）本身就是对的，只是 **filter 自己的 `value`（比较目标）需要翻译**，
是纯静态查表，不需要生成代码/跑沙盒。问题 1 的 `derivation` 更适合"真的需要
逐行计算"的场景（如"上市满 2 年"），但那类底层列通常不在 native 列里，会先被
问题 1 的 `unsupported` Finding 拦下来，走 `accepted_unapplied`，根本走不到
执行阶段。

**范围**：只做 `exchcd`（交易所）、`shrcd`（股票类型）——`siccd`（行业分类）
排除在外，行业排除通常是 SIC **区间**（如 financials=6000-6999），跟单值标签
映射形状不一样，需要一张行业->区间表，更容易出错，值得单独讨论。

**为什么不让 LLM 生成这份映射**：`exchcd`/`shrcd` 的编码含义是 **WRDS/CRSP
数据源自己的约定**，论文原文通常不会解释这一点，LLM 只能凭训练数据里的常识
去猜，没有论文证据能验证对不对——跟"论文这段话该归类成 vw 还是 ew"这种能从
论文文本验证的判断不是一回事。而且这份映射是"每个物理列注册一次，永久对所有
论文复用"的一次性成本，不是"每篇论文都要猜一次"，手工注册比 LLM 每次猜测更
安全也更省事。

**实现**：
- `FILTER_VALUE_ENCODINGS: dict[str, dict[str, int]]`（`src/infra/models/
  method_spec.py`，紧挨着 `RETURNS_PANEL_NATIVE_COLUMNS`）：`exchcd`/`shrcd`
  两个物理列的"论文措辞（小写）-> 物理编码"映射。
- `registry._translate_filter_value(column, value)`：`universe_filters`
  构造时对每个 filter 的 value 做一次翻译——查到就换成编码，已经是数字的
  原样保留，列没有注册映射的原样保留；**字符串查不到对应编码时直接
  `ValueError`**（不悄悄放过，避免重演"全筛空+几步后报不相关的错"这个真实
  事故）。
- 测试：`tests/test_registry_resolved_method_spec.py::
  TestUniverseFilterValueEncodingTranslation`（5：正常翻译、大小写不敏感、
  已是数字直接透传、未注册词汇 fail-loud、无映射列直接透传）。全量测试
  553 passed / 18 skipped（较问题 2 完成时 +5，零回归）。

---

## 问题 4：LLM 兜底匹配到"技术上支持、语义上错误"的列

**现状**：`/resolve` 传了 `llm_provider` 时，未解析的 concept 会走 LLM 兜底
（`DataDictionary.normalize_fields_with_llm()`）。LLM 的猜测只会做"这个
source/column 是否真实存在于目录里"的硬校验，不做语义校验。如果它把
`compustat_listing_history` 猜配到 `exchcd` 这种 native 列，`unsupported_
universe_filters()` 不会拦（因为 exchcd 技术上是引擎支持的），`is_ready=true`，
resolve"成功"，只留下一条软提醒 `llm_matched_concepts`。

**代码位置**：
- `src/steps/step2_reviewer/implementation_resolution.py::
  build_implementation_resolution()`（`llm_matched_concepts` 的计算）
- `src/infra/data_layer/__init__.py::_llm_match_unresolved_fields()`（硬校验逻辑）

**后果**：跟问题 3 性质类似（错的东西被当成对的跑下去），只是"错列"而不是
"对列错值"；因为列存在、类型也大概率兼容（都是可比较的数字/字符串），往往不会
在 Step3/Step4 报错，会一路跑到底、产出语义上错误但"技术上跑通"的回测结果。

**可能的修法（未决定）**：
- `llm_matched_concepts` 目前只是展示性的软提醒——要不要改成阻塞性的
  `NEEDS_HUMAN_CONFIRMATION`，逼着人工在继续之前显式确认/拒绝每一条 LLM 猜配？
- 或者在 LLM 匹配 prompt 里加一步"你的匹配理由"，展示出来辅助人工判断（而不是
  只显示 concept_id 本身）

---

## 汇总表

| # | 触发条件 | 挡不挡 `is_ready` | 现在有没有暴露原因 |
|---|---|---|---|
| 1 | concept 解析到列，但不是 native 列 | 挡（`is_ready=false`） | ❌ 没有 |
| 2 | sort 维度超限 / 非 quantile 分组 | 挡（`is_ready=false`） | ❌ 完全没有诊断方法 |
| 3 | filter 的 value 编码跟物理列不匹配 | **不挡**，`is_ready=true` | ❌ 完全没有，要等好几步后才报不相关的错 |
| 4 | LLM 猜配到语义错误但技术上支持的列 | **不挡**，`is_ready=true` | 只有软提醒 `llm_matched_concepts` |

（另有已知但性质不同、暂不在此列表讨论范围内：`missing_mapping` finding 已经
在 review 阶段暴露且已接线，`unmapped_concepts` 已经在 `/resolve` 返回值和前端
里正确展示。）

---

## 讨论顺序建议

问题 1、2 是同一类（"判断对了但没告诉用户"），改起来风险低、工作量小，可以先做。
问题 3、4 是同一类（"判断错了/没判断，静默产出错误结果"），风险更高、需要更谨慎
的设计（尤其问题 3 涉及给每个 concept 建值编码映射表，长期维护成本要考虑），
建议后讨论。

---

## 讨论结论（2026-08-12，进行中）

### 问题 1 的暴露方式：Finding 机制，但计算时机放在 `/resolve`

沿用现有 `Finding`/`Disposition` 机制（跟 9 个 high-impact 字段、`missing_mapping`
同一套模型和 UI 渲染语言），但**不塞进 `review_method_spec(paper)`**——那个函数只
吃 `paper`，拿不到 `concept_mapping`，没法判断"这个 concept 解析到的列是不是原生
列"。改为在 `/resolve` 端点里，用已经算出来的 `resolution.concept_mapping` 构造
这些 `Finding`（复用已有的 `kind="unsupported"` literal，这是 D4 被移除后留下的
空位，正好够用），作为返回体新增的 `resolution_findings` 字段返回；前端在 Resolve
卡片里用跟 Review 卡片相同的样式渲染，`canPatch` 排除这个 kind（`field_path` 带
数组下标，现有 `apply_value_patches` 处理不了）。

LLM review loop 不受影响、不加拦截——它可以像处理其他 high-impact 字段一样，自己
在重写 spec 时判断并设置某条 filter 的 `accepted_unapplied`/`unapplied_reason`；
这条 Finding 只客观反映"这个 filter 现在是否处于不受支持状态"，不关心是谁设的
`accepted_unapplied`，人工在 resolve 结果里看到后自行判断认不认可（认可就不用管，
不认可就重新触发一轮 review 或手改 spec）。不新增专门的写入端点。

### 问题 1、3 根源合并：`concept_mapping` 缺一层"derivation"

讨论中发现问题 1（filter 解析到了列但引擎不认识）和问题 3（filter 的 value 编码
跟物理列不匹配）根源相同：`ImplementationResolution.concept_mapping` 目前只是
`concept_id -> SourceColumn{source, column}` 的哑二元组，中间完全没有"怎么从这个
物理列算出/编码出这个 concept 语义值"这一层，reviewer 也就只能审"这一列存不存
在"，审不了"转换对不对"。

拟议方向：给 concept 解析加一个类似 `SignalSpec.formula`（`FormulaSpec` +
`CalculationStep`）的 **derivation** 结构——同样是"分步骤记录"的模式，reviewer
审 steps 描述，Step3 视情况生成一小段确定性代码（多数情况就是一个 dict 映射或
简单表达式，不需要 LLM），Step4 冒烟测试验证。

两个具体例子（草案，字段命名未定）：

```python
# 例 1: listing_exchange -- 论文写 "NYSE/Amex/NASDAQ"，底层是 exchcd 数字编码
ConceptDerivation(
    concept_id="listing_exchange",
    underlying=SourceColumn(source="crsp_msf", column="exchcd"),
    paper_expression='"NYSE"/"Amex"/"NASDAQ" -> exchcd 1/2/3',
    steps=[
        CalculationStep(
            step_id="map_label_to_code",
            description="Map paper's exchange label to CRSP numeric exchcd",
            expression='{"NYSE": 1, "Amex": 2, "NASDAQ": 3}',
            status=EvidenceStatus.CLEAR,
        ),
    ],
    output_encoding={"NYSE": 1, "Amex": 2, "NASDAQ": 3},
)

# 例 2: compustat_listing_history -- 论文写 "上市满 2 年"，底层是 ipodate
ConceptDerivation(
    concept_id="compustat_listing_history",
    underlying=SourceColumn(source="comp_names", column="ipodate"),
    paper_expression="listing duration >= 2 years",
    steps=[
        CalculationStep(
            step_id="compute_duration",
            description="formation_date - ipodate, in years",
            expression="(formation_date - ipodate).days / 365.25",
        ),
        CalculationStep(
            step_id="apply_threshold",
            description="keep rows where duration >= 2",
            expression="duration >= 2",
        ),
    ],
)
```

这样一来：
- 问题 1：人工看到的不再是"unsupported"这个二元黑箱标签，而是"底层列 + 转换
  步骤"，转换逻辑本身可能没问题，只是引擎还没接这张表——两件事分开判断。
- 问题 3：`output_encoding`/steps 显式把"论文措辞 → 物理编码"的映射写出来，
  `build_config` 直接用这个映射转换 `FilterSpec.value`，而不是把论文原文
  （如 `["NYSE","Amex","NASDAQ"]`）直接透传给 `.isin()`。

**尚未决定**：`ConceptDerivation` 具体挂在 `MethodSpec` 的哪个位置（`RequiredField`
上加一个可选字段？还是 `ImplementationResolution.concept_mapping` 的 value 从
`SourceColumn` 换成一个更丰富的结构？）、是否所有 concept 都要有 derivation 还是
只有 universe filter concept 需要、以及这算不算一次 schema breaking change（需要
迁移已有的 `runs/`/`tests/fixtures/` 数据）。下一步继续讨论这些细节。

### 位置已定：`derivation` 归属 `paper`，跟 `SignalSpec.formula` 同构

推翻上面"挂在 `ImplementationResolution`"的候选方案。关键理由：用户明确了 derivation
将来也要像 `compute_signal` 一样被生成代码，而 `compute_signal` 现有的生成流程
（`MetaCoder._build_prompt_from_resolved`，见 `src/steps/step3_codegen/__init__.py`）
读的是 **`paper.signal.formula`**（`paper_expression`/`steps`，`inputs` 引用抽象
`concept_id`，不是物理列）+ **`resolution.concept_mapping`**（`concept_id` → 物理
列），两者在 Step3 才结合生成代码。`FormulaSpec` 之所以能在 Step2 review 阶段被
完整审查，正是因为它完全不依赖物理列信息。

Derivation 要复用同一个模式，所以：

- `paper` 侧：`FilterSpec` 新增 `derivation: FormulaSpec | None = None`（直接复用
  `FormulaSpec`/`CalculationStep`，不新建 `ConceptDerivation` 类型）。`derivation.
  inputs` 引用抽象 `concept_id`（如 `["ipodate"]`），逻辑本身在 Step2 review 时
  就能被人工/LLM 完整审查，不需要等 resolve 之后。
- `resolution` 侧：`concept_mapping` **完全不变**，还是纯粹的 `concept_id ->
  SourceColumn{source, column}`，职责单一，不承载任何转换逻辑。
- **Step3 codegen**：新增一个跟 `_build_prompt_from_resolved` 平行的函数（读
  `filt.derivation` + `resolution.concept_mapping[concept_id]`），生成一段类似
  `compute_signal` 的确定性代码，Step4 沙盒冒烟测试验证。

**是否所有 derivation 都走 LLM**：已决定——**只要 `FilterSpec.derivation` 非空，
一律走跟 `compute_signal` 相同的 LLM codegen + Step4 验证路径**，不区分"纯静态
映射表"和"需要计算"两种情况、不设特例分支。理由：跟 `compute_signal` 现有行为
一致（哪怕公式简单也一样走 LLM+沙盒），避免自造一套"简单/复杂"分类规则带来新的
判断出错风险；代价是纯映射类 derivation 也要多付出一次 LLM 调用+沙盒验证的开销，
这个代价被认为可接受。

**仍待讨论**：
- 是否所有 concept（不只 universe filter，也包括 signal input concept）都可能需要
  `derivation`，还是这次只给 `FilterSpec` 加。
- 这算不算 schema breaking change，`runs/`/`tests/fixtures/` 里已有的 MethodSpec
  数据要不要迁移（新增字段默认 `None`，理论上向后兼容，但需要验证）。
- Step3 新增的 filter-derivation 生成函数具体怎么复用/拆分 `MetaCoder` 现有代码
  （新方法？还是完全独立的类）。

### 三点全部拍板（2026-08-12）

1. **范围**：这次只给 `FilterSpec` 加 `derivation`，不推广到 `RequiredField`/其余
   四种 `FieldRole`（`weighting_input`/`benchmark_input`/`estimation_input` 目前都是
   直接读原始列，没有"论文措辞需要转换"这个模式，没有具体 case 支撑现在就扩大范围）。

2. **不是 breaking change，`schema_version` 不升版本**：`MethodSpec`/`FilterSpec`
   都是 `extra="forbid"`（只禁止未知字段，不要求已知字段必须出现），新增
   `derivation: FormulaSpec | None = None` 带默认值，旧的 `.methodspec.json`
   （包括 `tests/fixtures/method_specs/` 下 4 个）原样能被 `model_validate()` 读入，
   不需要迁移任何既有数据。`schema_version` 保持 `"methodspec.v2"` 不变——`docs/
   methodspec_schema_notes.md`（repo memory）记录过同类先例：`TimingSpec.
   formation_month` 当初也是作为可选字段加进来，没有因此升版本。
   `content_hash()` 的输出值会变（新字段被序列化进摘要），但项目已在 2026-08-09
   移除了 paper/review/resolution 的 hash 绑定校验，且现有测试都是相对比较
   （`spec.content_hash() == reloaded.content_hash()`），不受影响。
   需要跟着更新的是**文档性内容**，不是 schema 版本号：
   - `src/infra/models/schema_reference.py` 的 `FIELD_USAGE` 加一条
     `"universe.filters[].derivation"` 的 usage 说明（给前端 schema 参考页用）。
   - LLM 相关 prompt（`prompts/review_gate/llm_review.md` 的 schema skeleton 是
     自动从 Pydantic 模型 splice 出来的，字段本身自动可见；但很可能需要额外补一段
     "什么时候该填 derivation、什么时候不用"的 prose 指引，类似 2026-08-08 给
     `weighting`/`return_combination` 补的 §1.7b 那种手写规则，因为"要不要写
     derivation"不是模型类型能自解释的判断）。

3. **Step3 复用方式**：方式 A——在现有 `MetaCoder` 类里加新方法
   （`generate_filter_derivation_plugin()` + 对应的 prompt 构造函数），复用同一个
   `llm_client`/`_strip_code_fences`/repair 基础设施；新增一份独立的 system prompt
   文件（如 `prompts/meta_coder/filter_derivation_plugin_system.md`），因为现有
   `METACODER_SYSTEM_PROMPT` 里"只能算 signal 公式、不能碰 universe"的边界规则对
   filter derivation 场景是矛盾的，需要单独一份。模块级 docstring 的措辞也要跟着更新
   （从"Generate factor signal plugins"改成同时涵盖 filter derivation）。

下一步：开始实现（`FilterSpec.derivation` 字段 + Step3 新方法 + 问题 1 的
`resolution_findings` Finding），实现完再回头讨论问题 2。
