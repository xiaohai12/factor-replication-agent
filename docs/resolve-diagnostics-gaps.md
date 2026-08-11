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
