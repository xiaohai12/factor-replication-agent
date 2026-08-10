# Changelog

## [Unreleased]

### Added

- **`review_method_spec_with_llm` (Step2 LLM-assisted review) 现在会把完整
  `MethodSpec` JSON 也发给 LLM**（此前只发送 9 个高影响字段的 snapshot +
  论文全文），让它能对 snapshot 之外的任意字段（`signal.formula`、
  `data.fields`、`sample.*`、`reported_results.metrics`、`portfolio.legs`
  等）通过既有的 `additional_findings` 机制提出问题。`field_assessments`
  （改 `EvidenceStatus`）的可用字段范围保持不变，仍只限那 9 个 snapshot
  字段——只是"提出新问题"的可见范围扩大了，"改状态"的权限边界没变，
  `additional_findings` 的 disposition 也依然被硬编码为
  `NEEDS_HUMAN_CONFIRMATION`，LLM 无法借此自我批准或绕过 D4 能力检查。
  同步更新了 `prompts/review_gate/llm_review.md`：明确"两层"输入契约，并
  新增一份"重点关注"清单（formula 公式步骤、`signal.estimation` 完整性、
  `data.fields` 语义正确性、三段 sample 期间一致性、`reported_results`
  主指标匹配、`portfolio.legs` 多空方向）引导 LLM 该往哪儿找问题。新增 2
  个测试（`tests/test_step2_reviewer_llm.py`）验证完整 spec 确实进了
  prompt，且 snapshot 之外的字段也能落地成一个可用的 finding。

- **Step4 (`AdversarialSandbox._check_executes`) 的执行冒烟测试，除了原有
  的 `compute_signal(df)` 调用，现在还会在切片本身已经长得像返回面板
  （有 `ret`/`me`/`exchcd`/`shrcd`/`siccd` 列，即 "crsp_only" 模式）时，
  额外尝试一次 `BacktestExecutor.run_with_config()`，把只有跑到 Step5 全量
  数据才会暴露的引擎生命周期问题（`filter_universe` 等）提前到 Step4 就
  看到**。刻意保持跟现有设计同一套"宽松"姿态：只有 40 个 permno 的薄切片
  完全可能因为样本太小（比如撑不起十分位断点）而让引擎抛异常，这不代表
  代码有 bug——所以引擎这一步的任何异常都只记成 `report.warnings`，从不
  让 `executes_ok`/`report.passed` 变成 `False`；只有切片本身不具备返回
  面板列（"compustat"/"multi_source" 模式的信号输入切片，没有 `ret`/`me`
  等列）时才完全跳过这次尝试，避免对每个非 CRSP 因子都产生毫无信息量的
  噪音警告。Step5 的全量真实执行依然是唯一会真正阻断（fail loud）的地方。
  新增 `tests/test_sandbox_validation.py::TestFullEngineSmokeTest`（3 个：
  正常薄切片跑通不报警、universe filter 解析到返回面板没有的列时引擎报错
  但只警告不失败、非返回面板形状的切片完全跳过这次尝试）。全量测试
  533 passed / 18 skipped，零回归。

- **`FilterSpec.accepted_unapplied`/`unapplied_reason`（universe filter 的
  "other" 逃生舱）+ `ResolvedMethodSpec.unsupported_universe_filters()` 把
  "这条 universe filter 解析出的物理列不在返回面板上"（例如一条
  Compustat-only 的 backfill-bias 筛选，引擎的 `filter_universe` 只能看到
  CRSP 返回面板自身的 8 列)从"跑到
  Step5 才 `ValueError` 崩溃"提前到"resolve 阶段的 `is_ready` 就直接
  block"，跟 `WeightingScheme.OTHER` 那类 D4 "论文说了但引擎不支持"字段
  同一个处理姿态：默认仍然阻塞,只有人显式登记
  `accepted_unapplied=True` + `unapplied_reason`（人工决定"这条限制先不
  应用"),才会放行——`registry.build_config` 把这类 filter 单独收进
  `config["unapplied_universe_filters"]`（record 用,永不参与
  `filter_universe`/引擎执行),从不静默丢弃。新增
  `RETURNS_PANEL_NATIVE_COLUMNS`（`src/infra/models/method_spec.py`,一个
  写死的、CRSP 返回面板列名的静态集合，不是数据层查询——真正的
  eligibility-panel 支持（把 Compustat 等其他源的列 join 到返回面板上再
  跑 filter）本次有意不做，见 CHANGELOG 决策讨论。
  新增测试：`tests/test_method_spec_contract.py::TestUnsupportedUniverseFilter`
  （3 个）、`tests/test_registry_resolved_method_spec.py::
  TestAcceptedUnappliedUniverseFilter`（3 个）。全量测试 539 passed / 18
  skipped，零回归。

- **`apply_human_value_patches` + `POST /api/methodspecs/patch-value`
  ——人工直接改字段的值（不只是改 evidence status）**。这是"human review
  能不能像 v1 一样推荐值/自己选值"这个讨论的落地：`_review/override` 只能
  改 `EvidenceStatus`（论文证据等级),改不了提取器写错的实际内容；这次新增
  的路径专门解决"提取器把值本身写错了"（比如论文写 annual，提取器写成
  quarterly）的情况。
  - `apply_human_value_patches(paper, patches, reason)` 只允许改
    `_high_impact_sourced_values(paper)` 已知的那个固定字段清单（含带下标
    的 `portfolio.sorts[i].breakpoints.basis`）——`field_path` 来自前端输入，
    故意不做"任意字符串按 `.`/`[i]` 解析成 getattr 链"这种通用反射，只在
    这张已知安全的字段表里查,不会被引导到任意属性。改完的字段
    `status` 会被标成 `clear`（人工确认过了),并在 `evidence[]` 里留一条
    "human correction: <reason>" 的记录。返回一份新的 `MethodSpec`,不改
    原对象。
  - 加了一层类型感知的强制转换（`_coerce_to_current_type`）：前端文本框
    永远只会传字符串,但有些高影响字段本身是 `int`（`timing.
    holding_period`)或 `Enum`（`signal.direction` 等),直接赋值不会做
    pydantic 校验,字符串会静默存进本该是 int/enum 的字段。现在会按当前
    值的类型尝试转换,转不了就直接报错（不猜)。
  - 前端：`SessionDetailPage.tsx` 的 review 面板里,"needs_human_
    confirmation"的字段现在除了 status 下拉框,还多了一个"改值"的文本
    框,点"Apply N value correction(s)"提交后会清空当前 `review`/
    `resolved` 状态（不再有 hash 自动检测陈旧了——2026-08-09 早些时候的
    改动——所以这里手动清空,提示用户重新跑一遍 review 作为替代信号）。
  - 新增 `tests/test_apply_human_value_patches.py`（9 个测试：改值 + 标记
    clear / 不改原对象 / 未知字段拒绝 / 带下标字段可改 / 一次改多个 /
    字符串转 int 成功与失败 / 字符串转 enum 成功与失败）。全量测试
    533 passed。
  - **同一天的跟进（复刻 v1 的字段说明 + 下拉选择体验）**：改值那个输入框
    现在会先查 `GET /api/methodspecs/schema`（`build_schema_reference()`
    直接从 `MethodSpec` pydantic 模型机械生成的字段参考,`SchemaReferencePage.tsx`
    也在用同一份数据,不是新写的接口）——如果这个字段是枚举类型
    （比如 `portfolio.weighting` 只能是 `vw`/`ew`/`other`，`signal.direction`
    只能是 `positive`/`negative`/`non_monotonic`/`unspecified`），改值的
    输入框会自动换成下拉选择（带"Other"逃生舱可以手打),而不是让人瞎猜
    枚举值怎么拼；同时每个字段上面会显示一行简短的字段说明
    （`_FIELD_NOTES` 里已经写好的 `description`，比如 weighting 会显示
    "How portfolio returns are weighted across constituent stocks."）。
    自由文本字段（`timing.formation_rule`/`universe.description` 这类）
    没有 `allowed_values`，照旧是文本框。前端新增 `sessionApi.
    getSchemaReference()`，纯读取现成端点，后端零改动。

### Removed

- **移除了 `MethodReview`/`ImplementationResolution`/`ResolvedMethodSpec` 的
  paper/review 哈希绑定陈旧检测（`paper_spec_hash`/`review_hash`/
  `_hashes_current`）**——用户明确要求，权衡过"会破坏一个已有测试覆盖的
  安全机制"之后仍然选择去掉。具体改动：
  - `MethodReview` 去掉 `paper_spec_hash` 字段和 `content_hash()` 方法；
    `ImplementationResolution` 去掉 `paper_spec_hash`/`review_hash` 字段；
    `ResolvedMethodSpec` 去掉 `_hashes_current()`，`is_ready` 不再校验这层
    陈旧性——现在只看 `review.is_blocked` / 所有 concept 是否已映射 /
    sort 维度是否在引擎能力范围内。
  - **`MethodSpec.content_hash()` 本身保留**——`app.py`/
    `src/steps/step3_codegen/__init__.py`/`src/steps/step5_backtest_runner/
    __init__.py` 还在用它做插件/脚本命名的确定性 ID，这跟"陈旧检测"是两
    件独立的事，没有一起删。
  - `review_method_spec`/`review_method_spec_with_llm`/
    `apply_human_status_overrides`/`build_implementation_resolution` 都不
    再往 `MethodReview`/`ImplementationResolution` 里塞 `paper_spec_hash`/
    `review_hash`。
  - 更新了 `tests/_spec_test_helpers.py`、
    `tests/test_meta_coder_resolved_method_spec.py`、
    `tests/test_registry_resolved_method_spec.py`、`tests/test_step2_reviewer.py`、
    `tests/test_method_spec_contract.py` 里所有构造
http://localhost:5173/pipeline    `MethodReview(...)`/`ImplementationResolution(...)` 时传的
    `paper_spec_hash`/`review_hash` 关键字参数；删掉了两个专门测这层陈旧
    检测的测试（`test_review_bound_to_current_paper_hash`、
    `test_not_ready_when_paper_hash_stale`）。全量测试 524 passed（526 -
    2 个被删的陈旧检测测试）。
  - **注意（已知副作用，用户已确认接受）**：现在如果在 review/resolve 跑
    完之后又改了 paper 的内容（比如重新提取、或者以后加的"人工改值"功能），
    系统**不会再自动检测到"review 已经过期"并拦住 `is_ready`**——需要人
    自己记得改完东西要重新跑一遍 review/resolve，没有自动兜底了。见
    `docs/decision-log.md` 2026-08-09 条目里权衡的完整记录。

### Added

- **`build_implementation_resolution` 接上了已经写好但从没接线的 LLM 概念匹配
  兜底（`DataDictionary.normalize_fields_with_llm`）**。此前 `/resolve` 只跑
  确定性别名/子串匹配（`normalize_fields`），一个 paper concept 只要没在
  catalog 别名表里精确/子串命中就直接判定 unmapped——即使 LLM 兜底匹配器
  (`normalize_fields_with_llm`，连同硬校验、`tests/test_llm_normalized_
  mapping.py`) 早就写好了，只是没有任何生产代码调用它。现在：
  1. `build_implementation_resolution(...)` 新增可选 `llm_client=None` 参数：
     `None`（默认）行为完全不变，纯确定性；传入 client 时，对确定性匹配
     仍解析不出来的 concept 再跑一次 LLM 兜底（LLM 的每个选择依旧要通过
     `normalize_fields_with_llm` 自带的硬校验——source/column 必须是真实
     已注册的，选不出来的直接丢弃，不会静默瞎猜）。
  2. `ImplementationResolution` 新增 `llm_matched_concepts: list[str]` 字段，
     记录"只有 LLM 兜底才解析出来"的 concept（跟确定性解析的做区分，方便
     人工重点复核），`/resolve` 响应体和 session event 日志都带上这个列表。
  3. `POST /api/methodspecs/resolve` 新增可选 `llm_provider`/`llm_model`：
     不传（默认）完全不建 LLM client，行为跟以前一模一样；传了才会在
     确定性匹配失败时多尝试一次。`SessionDetailPage.tsx` 的 Resolve 按钮
     现在总是带上侧边栏选的 provider/model（反正只有真的有解析不出来的
     concept 时才会真的触发 LLM 调用），并在结果里高亮"LLM 匹配的 concept，
     请重点复核"。
  - **提醒：这解决的是"论文写法 vs 目录别名对不上"这一类（比如论文写
    "book equity"，目录里叫 `ceq`）**，不解决 `compustat_listing_duration`
    这种"目录里根本没有任何列能代表这个概念，因为它本质是需要计算的衍生量"
    的情况——LLM 面对这种情况应该、也会正确地返回"匹配不上"，这是
    `docs/known-gaps-paper-first-v2.md` gap #3 里描述的问题，需要单独的
    "衍生 filter 能力"设计（还没开始做）。
  - 新增 `tests/test_implementation_resolution_llm.py`（3 个测试：无
    llm_client 时行为不变 / 合法 LLM 匹配被记录进 `llm_matched_concepts` /
    LLM 提议一个没注册过的 source-column 时照样被丢弃、保持 unmapped）。

- **Session Step2 现在有 LLM-backed review 和人工字段决议 UI 了**。之前的
  gap：`src/steps/step2_reviewer/review.py` 的 `review_method_spec()` 是纯
  规则检查（D2 evidence-status matrix + D4 engine-capability menu），文档里
  自己写着"an optional LLM-assisted discovery pass ... is deferred to a
  later iteration"；同时 `SessionDetailPage.tsx` 的 Step2 面板只能跑这个
  规则版 review，且明确写着"this step has no manual field-editing UI yet"。
  旧版 `PipelineE2EPage.tsx` 里看起来有 LLM review 按钮和逐字段决议表单，
  但那套 `/api/methodspecs/review/llm` 端点和 `ReviewResult`/`spec` 请求体
  属于 2026-08-07 已经删除的 v1 `backend/routers/methodspecs.py`，实际上
  是死代码（会直接 422），不是一个可用的替代方案。
  现在补上（新增 `review_method_spec_with_llm()` / `apply_human_status_overrides()`，
  两者跟 `review_method_spec()` 共享同一个 `_compute_findings()` helper，
  `DISPOSITION_MATRIX` 仍然是唯一决定 disposition 的地方）：
  1. `POST /api/methodspecs/review/llm`（异步 job，同 `/extract` 模式）：
     用 `prompts/review_gate/llm_review.md` 让 LLM 重新读一遍论文原文，
     只能对已提取的高影响 `SourcedValue` 字段提出 `EvidenceStatus` 重新判定
     （写进 `MethodReview.status_overrides`），或者提出新的
     `kind="inconsistent"` finding——但新 finding 永远被强制成
     `NEEDS_HUMAN_CONFIRMATION`，LLM 自己没有批准/拦截的权力；D4 engine-
     capability 检查完全不受 LLM 影响。
  2. `POST /api/methodspecs/review/override`（同步，不调 LLM）：人工直接
     给某个 D2 字段指定"我确认论文其实写清楚了"这类修正后的
     `EvidenceStatus`，同样只是喂给 `DISPOSITION_MATRIX` 重新算，不是让人
     直接写 disposition。
  3. `_extract_job` 现在把 `paper_text` 一起塞进 job 结果（之前只有
     `spec`/`error`/`raw_llm_output`/`token_usage`），因为 LLM review 需要
     原始论文文本；`MethodSpecWorkflowState`（`lib/methodSpecStore.ts`）新增
     `paperText`/`reviewSource` 字段做 sessionStorage 持久化。
  4. `SessionDetailPage.tsx` 的 Step2 面板：新增"Run LLM-backed review"
     按钮（跟规则版并列，用 source badge 区分是 rules/llm/human 产出的）；
     每条 `disposition=needs_human_confirmation` 且 `kind!="unsupported"`
     的 finding 旁边现在有一个 `EvidenceStatus` 下拉框，选完点"Apply N
     human override(s)"调用上面的 `/review/override`。
  - **已知局限，没有在这次改动里处理**：`MethodReview.is_blocked`/
    `ResolvedMethodSpec.is_ready` 目前只看 `Disposition.BLOCKED`（D4），
    `NEEDS_HUMAN_CONFIRMATION`（D2）本身并不会让 `is_ready` 变 false——这
    是重构前就有的既存行为（`test_step2_reviewer.py` 里显式断言了
    `not review.is_blocked`），所以这次新增的人工 override 面板改的是
    finding 本身是否存在/其 evidence_status 是否准确，而不会让 Resolve
    按钮从"不可用"变"可用"。真正会拦住 Resolve 的只有 D4 unsupported 项
    （引擎能力menu之外的选择），这类项本来就不允许被覆盖。
  - 新增 `tests/test_step2_reviewer_llm.py`（5 个测试，覆盖 LLM 只能重判
    它被给到的字段 / 不能碰 D4 blocked / additional finding 强制
    needs_human_confirmation / 人工 override 不调 LLM 也能重算 disposition）。

- **上面那版的两个跟进修正（同一天）**：
  1. **`paper_text` 现在持久化到磁盘，不再只活在 sessionStorage/job 结果
     里**。之前 `paper_text` 只塞进内存态的 job 结果和前端
     `MethodSpecWorkflowState.paperText`（sessionStorage），对已经提取过
     的旧 spec（sessionStorage 被清过，或 job 早就过了
     `JOB_TTL_SECONDS` 过期）完全找不回来，LLM review 会直接报"No paper
     text available"。现在 `_extract_job`（`backend/routers/
     methodspecs.py`）复用 `backend/routers/papers.py` 已有的
     `data/paper_text_cache/{document_id}.txt` 缓存约定，把 paper_text
     按 `document_id` 落盘；前端新增 `sessionApi.getPaperText(documentId)`
     调用既有的 `GET /api/papers/{paper_id}`，在点"Run review"时如果
     `state.paperText` 没有，先按 `paper.paper.document_id` 去查这个缓存，
     查到就用、查不到才真正退化成规则版。
  2. **Step2 面板的"规则版"/"LLM 版"两个按钮合并成一个"Run review"**。
     因为 `review_method_spec_with_llm()` 内部本来就是通过共享的
     `_compute_findings()` 把 D2/D4 规则检查跑一遍（LLM 只是在这基础上
     叠加 evidence_status 修正），所以 LLM 版本身就是规则版的超集，两个
     并列按钮容易让人以为要"二选一"（这是 v1 `review_with_llm` 的设计：
     LLM 版恒定合并规则版结果，不作为平行选项）。现在只有一个"Run
     review"：paper_text 能拿到（无论是当次提取自带的还是上面缓存查到
     的）就跑 LLM 版，拿不到才 fallback 成同步的规则版并照常展示结果，
     不再要求用户自己二选一。

### Fixed

- **`portfolio.missing_policies[].action` 也改成真正的 Enum**
  （`MissingActionScheme(str, Enum)`: `drop`/`other`，跟之前 `weighting`
  的 `WeightingScheme` 完全同一套模式）。根因：这个字段之前是纯
  `SourcedValue[str]`，`review.py` 里从来没有对它做过 D4 引擎能力检查（不像
  `weighting`/`return_combination` 早就有），所以论文原话式的自由文本
  （实测真实提取结果是 `"Require nonzero total assets in both input years."`
  这种完整句子）会一路静默流到 `registry.build_config`，被 `_track_clamp`
  悄悄替换成默认值 `"drop"`，全程没有任何可见的拦截点。现在：(1) 模型层
  加了 `MissingActionScheme` 枚举，`other` 是逃生舱（同
  `WeightingScheme.OTHER`/`ConstructionType.OTHER` 模式，论文原话仍保留在
  `evidence[]` 引用里）；(2) `review.py` 新增 `ENGINE_MISSING_ACTION_MENU`
  + D4 检查，任何不是 `drop` 的值现在会在 review 阶段就 `blocked`；(3)
  `extractor.py` 的 `normalize_engine_vocabulary()` 新增
  `_normalize_missing_action()`（关键词匹配 `drop`/`exclud`/`remov`/
  `require`/`omit`/`discard`，命中则归一化成 `"drop"`，否则归一化成
  `"other"`——因为字段现在是真枚举，任意自由文本会在 `MethodSpec.
  model_validate()` 时直接校验失败，而不只是像以前那样留到 review 才拦截）；
  (4) 提取 prompt 新增 §1.7c，明确要求 LLM 对"排除/丢弃类"的缺失值处理写
  `drop`，其余写 `other`。新增 4 个测试（`tests/test_step1_extractor.py`
  2 个 + `tests/test_step2_reviewer.py` 2 个）。全量测试 505 passed/18
  skipped（501+4 新增）。

- **真实 400 bug：step3 报 `concept_id 'total_assets_t_minus_1' has no
  physical column mapping`**。根因是 LLM 提取时把 `signal.formula.steps[]`
  里用到的 lag 变量名（比如 `total_assets_t_minus_1`/`_2`，只是公式内部的
  临时命名）直接当成 `universe.filters[].concept_id` 写了进去，但这两个
  名字从未在 `data.fields` 里注册过——`ImplementationResolution.
  concept_mapping` 只从 `data.fields`（+ universe.filters 自身，用裸
  `{"field": concept_id}` shim）匹配物理列，一个连 `data.fields` 都没有的
  filter concept 永远不可能解析成功，此前完全没在 review 阶段拦截，直到
  step3 `build_config` 才报错，而且报错信息完全看不出是"提取时把公式内部
  变量误当成 filter concept"这个根因。
  修了两处：(1) `src/steps/step2_reviewer/review.py` 的 `_capability_findings`
  新增一条 D4 检查：任何 `universe.filters[].concept_id` 若不在
  `data.fields[].concept_id` 里，直接 `kind="unsupported"`,
  `disposition=BLOCKED`，在 review 阶段就挡住，不再等到 step3 才炸出一个
  莫名其妙的 400（`docs/known-gaps-paper-first-v2.md` gap #3 的其中一种情形，
  现已修复其中"lag 变量名当 filter concept"这个子问题）。(2)
  `prompts/extractor/method_spec_extractor.md` 新增 §1.8b，明确告诉 LLM：
  `universe.filters[].concept_id` 必须也是一个真正的 `data.fields` 条目，
  绝不能直接借用公式步骤里的 lag 后缀变量名。新增 2 个回归测试
  （`tests/test_step2_reviewer.py`）。全量测试 501 passed/18 skipped
  （499+2 新增）。已用真实触发这个 bug 的 draft 直接对 `/api/methodspecs/
  review` 发请求验证：现在正确返回 3 条 blocked finding，而不是悄悄放行到
  step3 才报错。

### Changed

- **Session step1/2 页面布局改为单列（Events → 步骤内容 → Result），且 step1 已提取过时直接内联展示 `MethodSpecBoard`**。
  之前 step1/2 和 step3-8 共用同一套两栏 request/result 网格，`MethodSpecBoard`
  内容偏长偏密，两栏挤在一半宽度里很局促；且 step1 若已经提取过，只显示一行
  "Already extracted... 去 Step 2"提示，看不到实际提取结果，得跳到 step2 才
  能看。现在 step1/2 改成单列：`Events` 卡片在最上面（extract/review job 的
  进度是这两步最先要看的），中间是该步骤自己的卡片（extract 面板 / review+
  resolve 面板），下面是 `Result` 卡片；step3-8 的两栏布局完全不变（把两个
  Events 卡片实例提成一个共享的 `eventsCard` JSX 变量，避免两个分支各写一份
  再走样）。同时 step1 只要 `state.paper` 已经存在（之前提取过），就直接在
  同一张卡片里内联渲染 `MethodSpecBoard`（而不是仅一行文字提示），再提取会
  覆盖它。`npm run build`/`npm run lint` 均干净，浏览器手动验证过单列顺序，
  全量后端测试 499 passed/18 skipped 不受影响（纯前端改动）。

- **Step2 review 面板重做**：去掉 review 之前就一直显示的完整
  `MethodSpecBoard`（未 review 的 spec 没必要占地方），"Run review"/
  "Resolve to a codegen-ready MethodSpec" 两个按钮 pending 时改成
  "Reviewing…"/"Resolving…" 文字（之前 sync 请求没有任何进度反馈，看起来像
  卡住了——实测 `/api/methodspecs/review` 对真实 spec 只要 ~25ms，纯前端缺反馈
  问题，不是后端慢）。findings 列表改成每条一个带 disposition 徽章
  （blocked 红色/其余 outline）的卡片，field_path 加粗、reason 单独一行，
  比之前一整行纯文字更容易一眼看出"review 之后哪些字段被标记了"。
  `MethodSpecBoard.tsx` 里 "Breakpoint population" 表头改名
  "Breakpoint basis"（对应 v1 时代就用的术语，`portfolio.sorts[].
  breakpoints.population` 字段名本身不改）。
  另外说明一下 `portfolio.missing_policies[].action` 的问题：这个字段本来就
  设计成自由文本（`SourcedValue[str]`），存的是论文原话（比如实测真实提取
  结果是 `"Require nonzero total assets in both input years."` 这种完整
  句子），不是 `drop` 这种规范 token——这是有意为之，`MethodSpecBoard` 显示
  整句话是对的。`registry.build_config` 会在生成 engine 配置时把它 clamp 成
  `drop`/`unspecified` 两个菜单值之一，但那只影响最终 resolved config，不
  影响这里展示的原始论文原话，两者不冲突。
### Fixed

- **Session 里 step1/2 现在完成后会变色并自动跳转下一步，且 step1/step2 页面不再是同一个面板**。
  之前两个问题都在：(1) `MethodSpecWorkflowPanel` 不管 URL 是 `steps/1` 还是
  `steps/2` 都渲染同一整套 extract+review+resolve UI，两页看起来一模一样；
  (2) step1/2 的完成状态只存在 `sessionStorage`（`methodSpecStore`），从不
  写回 session manifest 的 step attempts，所以 `StepStepper` 的颜色徽章永远
  是 `not_started`，且没有任何步骤（包括 3-8）在成功后自动跳到下一步。
  现在：`MethodSpecWorkflowPanel` 按 `step` 拆成两个真正不同的视图——step1
  只有"上传 PDF /抽取"，抽取成功后立刻跳到 step2；step2 若还没有
  `state.paper` 则显示"还没抽取，去 Step 1"提示，否则显示 review + resolve，
  resolve 成功（`is_ready`）后立刻跳到 step3。`SessionDetailPage` 新增
  `specState`（把 `MethodSpecWorkflowPanel` 的 sessionStorage 状态提升到父
  组件），传给 `StepStepper` 做 step1/2 的颜色覆盖（`specStepStatus`：
  `paper` 存在 -> success；`review` 存在但被 block -> blocked；`review` 存在
  未 block -> running；`resolved` 存在 -> success）。同时给 step3-8 的
  `runMutation`/job 完成也补上了自动跳转（新增 `isFailureResult()`
  辅助函数——不是"HTTP 调用没抛异常就算成功"，而是识别 `passed`/`is_ready`/
  `success`/`status` 里任何明确的失败标记，没有才跳转，避免把 step4
  validate 的 `passed:false` 之类误判成成功后跳走）。`npm run build`/
  `npm run lint` 均干净，浏览器手动验证 step1/step2 渲染的内容确实不同，
  且从 step1 抽取成功会自动进入 step2。全量后端测试 499 passed/18 skipped
  不受影响（纯前端改动）。

- **React 的 Extractor / Review & Resolve 不再是失效的 sidebar 占位项，且不再错误地依附于 session step1/2。** 新增独立 `/extract` 与 `/review` 页面：Extractor 支持 PDF、document id、target factor、全局 LLM provider/model、SSE job progress、结构化 MethodSpec preview，并把成功结果直接带到 review；Review & Resolve 从后端持久化的 `runs/method_specs/{unreviewed,reviewed,...}` 生命周期加载 draft/review，展示 deterministic findings、blocked 状态和 implementation resolution。Sidebar 现在可直接进入两个页面；新 session 和 session 列表从真正属于 session 的 Step 3 开始，stepper 隐藏已从 session backend 删除的 Step 1/2，旧的 `/sessions/:id/steps/{1,2}` URL 分别重定向到独立页面。修复了此前“独立 MethodSpec API，却用 sessionStorage + session id 模拟 step1/2”的 UI/架构错位。

- **（同日，用户要求撤回上一条的重定向部分）Step1/2 重新并入 session 详情页**。
  上一条改动把 `/sessions/:id/steps/{1,2}` 重定向去独立的 `/extract`/`/review`
  页面、并把 stepper 过滤成只显示 Step 3 起——用户明确要求改回去。撤销了
  `App.tsx` 里那两条 `<Navigate>` 重定向路由（`/sessions/:sessionId/steps/:step`
  这条通用路由现在会正常匹配 step=1/2，交给 `SessionDetailPage`）和
  `StepStepper.tsx` 的 `.filter((def) => def.step >= 3)`，恢复显示全部 8 步。
  `SessionDetailPage.tsx` 里原有的 `MethodSpecWorkflowPanel`（`step === 1 ||
  step === 2` 时渲染，调用独立的 `/api/methodspecs/*` 生命周期端点）本来就没被
  删掉，只是路由绕过了它——所以这次是纯撤销路由/stepper 改动，没有恢复任何
  逻辑代码。独立的 `/extract`、`/review` 页面本身保留未删，仍在 sidebar 里，
  只是 session 内的 step1/2 不再重定向过去。`npm run build`/`npm run lint`
  均干净，浏览器手动验证 `/sessions/{id}/steps/1` 重新在 session 详情页内
  渲染 Extract 面板。

- **`GET /api/methodspecs/schema` 重新实现，`SchemaReferencePage.tsx` 恢复可用**。
  该端点属于已删除的 v1 `backend/routers/methodspecs.py`，v2 迁移时从未补建
  v2 等价物；今天早些时候把 `paper_methodspecs.py` 重命名为 `methodspecs.py`
  后，前端这个调用从"路由完全不存在"变成命中新路由的 `/{stage}` catch-all
  （`stage="schema"`），依然是 404（"Unknown stage 'schema'"），最终表现
  不变但排查路径变了。新增 `src/infra/models/schema_reference.py::
  build_schema_reference()`，直接从 `MethodSpec` 模型机械生成
  `{fields: {dotted_path: {...}}, json_schema}`（复用 `schema_render.py`
  "从模型元数据生成，而不是手写文档" 的思路），`allowed_values`/`example`/
  `sub_fields`（复合对象的直接子字段路径）/`list_item_fields`（list 字段
  项本身的字段名）全部机械推导；`description`/`usage`/`engine_consumed`
  这三项无法从类型标注推导，来自模块内一份按 dotted path 索引的精选表
  （对照 `registry.py::_build_config_from_resolved` 逐项核实哪些字段真正
  进了 engine 的 resolved config，未在表里的字段默认 `engine_consumed=
  False`）；`origin` 固定为 `"llm"`（`MethodSpec` 现在只是 Step1 抽取产物，
  不再像 v1 那样混有 review/resolution 状态）。新增
  `@router.get("/schema")`（注册在 `backend/routers/methodspecs.py` 的
  `/{stage}` catch-all之前，避免被吞掉）。
  过程中发现并修复一个真实的检测 bug：Pydantic v2 会把 `SourcedValue[T]`
  具体化成一个真正的类（而非 `typing._GenericAlias`），`typing.get_origin()`
  对它返回 `None`——之前用这个检测的写法会把 `portfolio.weighting`
  这类字段误判成普通嵌套 BaseModel，把 `allowed_values` 埋进
  `portfolio.weighting.value` 子字段里，而不是直接挂在 `portfolio.weighting`
  本身。改用 `__pydantic_generic_metadata__` 检测后确认正确（
  `schema_render.py` 里同样的检测写法凑巧没受影响，因为它的用途下两种
  渲染结果碰巧一致，未改动那个文件）。新增
  `tests/test_schema_reference.py`（8 tests，含专门覆盖这个检测 bug 的
  回归测试）。全量测试 499 passed/18 skipped，前端页面已在浏览器里手动
  验证渲染正常（description/usage/allowed values/engine-consumed badge/
  has-fields 全部正确显示）。

- **`MethodSpecBoard.tsx` 重写以匹配当前 paper-first `MethodSpec` schema**
  （之前整个组件还是按已删除的 v1 扁平 schema 写的：`spec.factor_name`/
  `spec.review_status`/`spec.codegen_ready`/`spec.ambiguous_fields`/
  `spec.paper_ref`/`spec.sign`/`signal.timing.*`/`portfolio.sort.*`/
  `portfolio.weighting`（裸字符串）/`reported_results.return_calculation.*`
  这些字段路径在当前 schema 里根本不存在，导致 Session 详情页 step1
  "2. Review" 里展示的 MethodSpecBoard 几乎全是"—"）。现在按
  `src/infra/models/method_spec.py` 的真实嵌套结构重写：`paper`（citation/
  publication_year）、`signal`（definition/economic_intuition/direction/
  formula.steps[]/estimation，均为 `SourcedValue` 展示 value+evidence+
  status）、`timing`（formation_rule/formation_month/rebalance_frequency/
  holding_period/data_availability）、`sample`（三段独立采样区间）、
  `universe`（description + filters[] 表格）、`portfolio`
  （construction_type/weighting/return_combination + sorts[]/legs[]/
  missing_policies[]/transforms[] 表格）、`data.fields[]`、
  `reported_results.metrics[]`。`Field` 组件现在能直接接收一个
  `SourcedValue`-形状的对象并自动拆出 value/evidence/status，不用每处调用
  都手动 `.value`/`.evidence`。`npm run build`/`npm run lint` 均干净。
  **未动**（已有文档记录的、独立的、超出本次范围的已知问题）：
  `PipelineE2EPage.tsx`/`SchemaReferencePage.tsx` 仍直接调用已删除的 v1
  `/api/methodspecs/{extract,schema}` 端点（`SchemaReferencePage` 现在会命中
  新路由的 `/{stage}` catch-all，返回 404 "Unknown stage 'schema'"——同样是
  404，只是错误信息变了，行为本质没变）；这两个页面在 2026-08-07/08-08 就已
  被记录为独立的遗留页面，需要单独的一次性工作（重建 `field_help.py` 的 v2
  等价物/迁移 Pipeline E2E 页面的提取调用），不在本次"schema 与展示不匹配"
  修复范围内，需要用户单独确认是否要做。

### Changed

- **移除代码/文件/路由里纯粹为了区分已删除 v1 而加的 `paper_`/`Paper` 前缀**
  （v1 `MethodSpec` 已在 2026-08-07 完全删除，这个前缀失去存在意义）。
  文件：`src/infra/models/paper_method_spec.py`→`method_spec.py`、
  `src/steps/step1_extractor/paper_extractor.py`→`extractor.py`、
  `src/steps/step2_reviewer/paper_review.py`→`review.py`、
  `backend/routers/paper_methodspecs.py`→`methodspecs.py`、
  `prompts/extractor/paper_method_spec_extractor.md`→`method_spec_extractor.md`，
  以及对应的 4 个测试文件。符号：`PaperMethodSpec`→`MethodSpec`、
  `PaperExtractor`→`MethodSpecExtractor`、`PaperExtractionResult`→
  `ExtractionResult`、`build_paper_method_spec`→`build_method_spec`、
  `review_paper_method_spec`→`review_method_spec`、`build_paper_extractor`→
  `build_extractor`（均用 IDE rename 保证全部引用同步）。API 路由
  `/api/paper-methodspecs/*`→`/api/methodspecs/*`（v1 的同名路由已删除，
  路径空出）。前端 `paperFirstStore.ts`→`methodSpecStore.ts`，
  `PaperFirstState`/`getPaperFirstState`/`setPaperFirstState`/
  `PaperFirstPanel`→`MethodSpecWorkflowState`/
  `getMethodSpecWorkflowState`/`setMethodSpecWorkflowState`/
  `MethodSpecWorkflowPanel`。**明确保留不动**（这些 `paper`/`Paper` 是真实
  领域词，不是版本消歧前缀）：`PaperRef` 类、`MethodSpec.paper`/
  `paper_ref`/`paper_name`/`paper_expression`/`paper_source_hint` 等字段、
  `data/papers/`、`paper_text_cache`、"paper-first" 这个研究设计名称本身
  （README/AGENTS.md/docs 里的用法）、CHANGELOG 历史条目与
  `docs/decision-log.md`/`docs/methodspec-v2-plan.md`（按现有约定，历史记录
  保留写作时的真实名称，不回填重命名）。全量测试 491 passed/18 skipped，
  `npm run build`/`npm run lint`（frontend）均干净。

### Fixed

- **`portfolio.weighting` 从自由字符串改为真正的 Enum**
  （`WeightingScheme(str, Enum)`: `vw`/`ew`/`other`，`src/infra/models/
  method_spec.py`）。根因见下一条 CHANGELOG：`schema_render.py` 只会给真正
  的 Python `Enum` 字段自动把允许值拼进 prompt，`weighting` 之前是纯
  `SourcedValue[str]`，完全吃不到这个机制。现在改成 Enum 后，prompt 的
  schema skeleton 会自动显示 `"vw | ew | other"`，不再需要单靠 prompt 里
  一句话提醒。`other` 是逃生舱（同 `ConstructionType.OTHER` 的既有模式）：
  论文真实描述的自由文本仍保留在该字段的 `evidence[]` 引用里，只是分类
  `.value` 被约束到菜单内。`return_combination` 保持 `SourcedValue[str]`
  不变（其自由文本形态远比 weighting 多样，枚举化会丢信息，本次未改）。
  联动修复：`normalize_engine_vocabulary()`（extractor.py）现在把无法识别
  的 weighting 自由文本映射到 `"other"` 而不是原样保留（否则会在
  Pydantic 校验时直接报错，而不是像以前那样留到 review 阶段才拦截）；
  `review_method_spec`（review.py）的 D4 weighting 检查改用
  `getattr(weighting, "value", weighting)` 兼容"直接属性赋值绕过校验"的
  测试写法（Pydantic v2 attribute assignment 默认不校验/不强制转换）。
  更新了 2 个受影响的测试。全量测试 491 passed/18 skipped。

- **`pytest tests/` 不再污染真实 `runs/` 目录**。`test_session_api.py`/
  `test_backend_api.py`/`test_experiment_replication_diagnosis_api.py`/
  `test_backend_paper_methodspecs_api.py` 都在模块顶层 `from backend.main
  import app`，而 `backend.state.RUNS_DIR` 只在 import 时解析一次
  `FACTOR_AGENT_RUNS_DIR` 环境变量——之前完全没有任何 conftest 兜底，一次全量
  `pytest tests/` 实测在真实 `runs/` 下留下了 114 个 session/evidence/
  method_specs/backtest_scripts 杂散文件。新增 `tests/conftest.py`，在
  collection 阶段（早于任何测试模块 import）把 `FACTOR_AGENT_RUNS_DIR`
  默认设为 `.runs_scratch`（复用已有的 gitignored 手动 live-test 约定）。
  已清理本次误产生的全部 114 个文件（未触碰用户真实的 session/工作数据）。

- **提取 prompt 现在直接告诉 LLM `weighting`/`return_combination` 的规范 token**
  （`prompts/extractor/paper_method_spec_extractor.md` 新增 §1.7b）。根因
  更深：`schema_render.py` 会自动把真正的 Python `Enum` 字段的允许值拼成
  `"vw | ew"` 这种提示塞入 prompt 的 schema skeleton，但 `PortfolioSpec.
  weighting`/`return_combination` 在模型里是普通 `SourcedValue[str]`（故意不用
  enum，保留记录引擎不支持的自由文本的能力），所以这个自动机制对这两个字段
  完全不生效——prompt 里之前没有任何一句话告诉 LLM 常见情况下应该写哪个
  规范 token，这才是 gap #1 的更深层根因。新增 §1.7b 明确要求：匹配
  vw/ew/extreme_group_spread/average_leg_spread/single_signal_portfolio_
  return/full_portfolio_return 时必须写精确 token，真正不匹配时才写自由
  文本。与上一条 CHANGELOG 里 `normalize_engine_vocabulary()` 的事后归一化
  互补（事前预防 + 事后容错两道防线），不相互取代。已验证
  `tests/test_step1_extractor_paper_spec.py`（15 passed）不受影响。

- **Step1 extractor 现在会归一化 `portfolio.weighting`/`portfolio.
  return_combination` 的自由文本到 engine 菜单 token**
  （`src/steps/step1_extractor/paper_extractor.py::normalize_engine_vocabulary`，
  在 `build_paper_method_spec` 里、`PaperMethodSpec.model_validate` 之前调用）。
  修复 `docs/known-gaps-paper-first-v2.md` gap #1：之前 LLM 提取常把
  `weighting` 写成 `"value-weighted"`/`"equally weighted"` 这类自然语言而不是
  `vw`/`ew`，`return_combination` 写成整句话而不是
  `extreme_group_spread`/`average_leg_spread` 等 token。这不仅让 Step2 review
  的 D4 引擎能力检查永久 `blocked`（此前没有任何 resolution 步骤能解开），
  一旦有人手动放行，`registry.build_config`/`_clamp_with_provenance` 还会把
  这个不在菜单里的值**静默 clamp 成默认值**（`vw`/`extreme_group_spread`），
  这是真实的正确性 bug，不只是体验问题。归一化只做已知同义词的精确映射
  （如 `"value-weighted"→"vw"`、同时出现 long/short 措辞→
  `extreme_group_spread`），无法识别的文本原样保留，review 仍会照常拦截，
  不会静默猜测经验参数。新增 7 个测试
  （`tests/test_step1_extractor_paper_spec.py::TestEngineVocabularyNormalization`）。
  全量测试 491 passed/18 skipped，无回归。

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
