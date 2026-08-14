# MethodSpec 信息重复审查(讨论记录,2026-08-13)

本文记录一次针对 `MethodSpec`/`MethodReview`/`ImplementationResolution` schema
(`src/infra/models/method_spec.py`)是否存在冗余信息的讨论,基于一份真实样本
(`runs/method_specs/resolved/099f6e1136bd316c.resolved.json`,Cooper/Gulen/
Schill 2008 asset growth)逐条核对。仅为讨论/审查记录,**尚未执行**下面标注为
"待处理"的项;已执行的项已注明。

## 结论

`MethodSpec` 整体不算过度冗余——大量"每个字段自带 evidence[]"的重复是
`docs/methodspec-v2-plan.md` 设计原则3("证据按字段归属")故意付出的成本,
换来的是可审计性,不应简化。但审查中发现 4 处具体重复点,严重程度和处理
优先级不同,分类如下。

## 1. 已修复:前端 schema 分组把 4 个模块塞进一个 "Top-level" 桶

- **位置:** `frontend/src/pages/SchemaReferencePage.tsx` 的 `sectionOf`/
  `SECTION_ORDER`/`SECTION_LABEL`。
- **问题:** 硬编码只认 `data`/`signal`/`portfolio`/`reported_results` 四个
  前缀,`paper`/`sample`/`timing`/`universe` 全部落入兜底的 `"other"`
  ("Top-level")分组,注释本身也过时(写着只对应 4 个模块,实际 `MethodSpec`
  顶层有 8 个)。后端 `GET /api/methodspecs/schema`
  (`src/infra/models/schema_reference.py::_walk_model`)其实遍历了完整
  `MethodSpec`,字段说明本身没有缺失,只是前端分组展示时揉在了一起。
- **状态:** **已修复**(本次会话内完成)。`sectionOf`/`SECTION_ORDER`/
  `SECTION_LABEL` 改为列出全部 8 个真实顶层模块
  (`paper`/`signal`/`data`/`sample`/`timing`/`universe`/`portfolio`/
  `reported_results`),`other` 只兜底 `factor_id`/`target_name`/`notes`/
  `schema_version` 这类真正的裸顶层字段。

## 2. 待处理(建议优先做,风险最低):`review.all_high_impact_fields` ⊇ `review.findings`

- **位置:** `MethodReview.findings` / `MethodReview.all_high_impact_fields`
  (`src/infra/models/method_spec.py`),由
  `src/steps/step2_reviewer/review.py` 的 `_compute_findings`/
  `_all_high_impact_field_findings` 各自构建。
- **问题:** 两者都由同一个 `high_impact_sourced_values(paper)` 遍历生成,
  `all_high_impact_fields` 是"每个高影响字段都给一条 Finding(含
  auto_approve)"的超集,`findings` 是"需要人工关注的子集"——**内容完全
  重叠的那部分(disposition != auto_approve 的条目)在两个字段里逐字重复
  存储**。代码里有注释说明这是故意的("purely additive"),但完全可以在
  读取时从 `all_high_impact_fields` 按 `disposition` 过滤算出
  `findings`,不需要物理存两份。
- **建议:** 把 `findings` 改成从 `all_high_impact_fields` 派生的只读
  属性/方法,而不是独立持久化字段。执行前需要确认:
  - 是否有前端/测试依赖 `findings` 作为 JSON 里独立存在的 key(而不是
    "可以从 all_high_impact_fields 计算出来");
  - `_compute_findings` 里 `missing_mapping`/`unsupported` 类 Finding(如
    `_missing_mapping_findings`、sort 数量超限)是否也被
    `all_high_impact_fields` 覆盖到——如果没有,派生逻辑需要把这些也
    并进去,不能简单等价成一次 filter。

## 3. 待处理:`signal.formula.evidence`(顶层)与 `signal.formula.steps[].evidence`

- **位置:** `FormulaSpec.evidence` vs `CalculationStep.evidence`
  (`src/infra/models/method_spec.py`)。
- **问题:** 确认 `formula.evidence`(FormulaSpec 顶层这份)在 `src/` 里
  **没有任何 codegen/校验逻辑读取**;唯一消费者是
  `frontend/src/components/MethodSpecBoard.tsx#L177`,把它当"Formula"
  这一行的展示证据,与逐步展示的 `steps[].evidence` 并列。对目前唯一的
  真实样本(单步公式)来说,这是在要求 LLM 提取时多引一条 quote,却没有
  任何下游逻辑依赖它——是四处重复点里"最纯粹"的一个:没有消费者,也没有
  `docs/methodspec-v2-plan.md`/`docs/decision-log.md` 记录为什么 FormulaSpec
  需要独立于 steps 之外的证据。
- **建议:** 考虑弱化或去掉 `FormulaSpec.evidence` 的强制性(例如只要求
  `steps` 里至少一个 step 有 evidence),减少提取负担;若要保留,需要
  补一条设计原则说明它和 step 级证据的分工(例如"formula.evidence 只
  用于多步公式的整体归属,单步公式应省略")。

## 3b. 已修复:`schema_reference.py::_walk_model` 把孙子字段拍平进父节点的 `sub_fields`

审查 `signal` 部分时用户发现 Schema Reference 页面展开树不对,排查确认是一个
真实的递归 bug,和上面的"信息重复"性质不同——不是 schema 本身重复,是**渲染
该 schema 的代码算错了字段的父子层级**。

- **位置:** `src/infra/models/schema_reference.py::_walk_model` 的
  composite(`BaseModel` 嵌 `BaseModel`)分支。
- **问题:** `_composite_entry(path, list(nested.keys()))` 在递归调用之后才读
  `nested.keys()`,而递归本身会把孙子/曾孙字段路径也写进同一个 `nested`
  字典,导致父节点的 `sub_fields` 把孙子字段错误地当成了直接子字段。实测
  `signal.formula.sub_fields` 之前有 11 项(应有 6 项),`signal.estimation.
  sub_fields` 之前有 17 项(应有 7 项)。前端展开树时孙子字段会作为兄弟节点
  重复出现、层级不对。
- **状态:** **已修复**。改为在递归前用 `unwrapped.model_fields` 直接算出真正
  的直接子字段路径列表。验证:`test_schema_reference.py`(9 passed)+ 全量
  套件(518 passed,32 failed/5 errors 均为环境缺 `pyarrow`/`yaml`,与本次
  改动无关)。

## 4. 已知技术债,暂不处理(有明确决策记录,不建议现在推翻)

- **位置:** `paper.data.fields[].source_table`/`source_column` vs
  `resolution.concept_mapping`。
- **状态:** 2026-08-13 当天的决策
  (`docs/decision-log.md` "`RequiredField` 获得 `source_table`/
  `source_column`"条目)明确记录了这是应用户要求做出的取舍,并自己写明
  "两套物理映射机制并存,未来如果想彻底统一需要再评估"。`build_
  implementation_resolution` 现在优先直接读 `source_table`/`source_column`,
  只有未设置/`other`的字段才退回字符串匹配,所以运行时不是两套逻辑打架,
  只是 schema 里两个字段代表同一个事实。**不建议在这份记录之后立刻推翻**;
  留作已知债务,等两者出现实际 drift 或有新证据支持统一时再评估。

## 下一步

第 2、3 项待用户确认后再动手实现(参见上方"建议"小节的前置检查项)。
