# Tools + LLM 重构方案（Tool Prelude 模式）

状态：**已确认，待实施**。讨论日期 2026-08-12。
相关：[decision-log.md](decision-log.md)、[architecture.md](architecture.md)、
[step1-step2-refactor-plan.md](step1-step2-refactor-plan.md)

## 0. 目标与核心判断

把每一个"有 LLM 参与"的步骤统一改造成 **确定性工具 + LLM** 的模式：

```
确定性工具全跑 → (工具说明书 + 工具 JSON 输出) 一起进 prompt → LLM 只做判断/生成
```

**这不是 function calling。** 因为我们通过 CLI（Codex / Copilot / Claude Code）
调用 LLM，模型无法在推理中途选择并调用工具。所以工具由 runner **预先全部执行**，
结果连同**工具说明书**一起作为 prompt 输入。称为 **Tool Prelude 模式**。

工具说明书必须进 prompt：因为 LLM 没有"选择"这一步，它需要被明确告知每个数字
是怎么算出来的、边界在哪、哪些不能当作 ground truth。

这个模式在 [spec_build.py](../src/steps/step2_reviewer/spec_build.py) 的
`_PRE_LLM_TOOLS` / `_run_pre_llm_tools()` 里已有雏形（2026-08-12 CHANGELOG）。
本次工作是**把它抽成通用基础设施，再推广到 step1 / step3 / step8**，而不是新建架构。

## 1. 已确认的设计决策

| # | 议题 | 决定 |
|---|---|---|
| 1 | 伪 tool call（LLM 在 JSON 输出里带 `tool_requests`，下一轮由 runner 执行） | **要**。第一轮默认全部工具跑满，后续轮次可由 LLM 追加请求 |
| 2 | 工具结果给 LLM 的形态 | **JSON payload**（不是自然语言 summary） |
| 3 | 执行分档 | 三档 `always` / `on_failure` / `opt_in`，按工具粒度配置 |
| 4 | Step1 工具范围 | **先只用现有能力**，不做新的 section parser |
| 5 | Step3 强制回喂一轮 | **撤销**（§4.2 详细讨论后推翻）：`missing_columns`/`dtype` 这类能明确判断
  "是bug"的信号，本来就该走现有失败判据（`report.errors` → `repair_plugin`），到不了"成功但要
  确认"这个状态；`nan_ratio`/覆盖数在薄验证切片上天然不好看、不代表代码有问题（step4 docstring
  自己就是这么设计的），LLM 无法据此可靠判断要不要改，勉强喂给它只会误伤正确代码。结论：**只在
  失败时 repair_plugin，成功就不管**，跟现有行为完全一致，不新增任何 LLM 调用。技术指标只进
  `tool_results` 供人工审计，不触发任何 LLM 决策 |
| 6a | `ReviewRound.error_log` 迁移 | **方案 A**：底层换成 `tool_results`，`error_log` 保留为渲染出来的 property |
| 6b | 工具结果持久化位置 | 统一进 [trace.py](../src/infra/trace.py) 事件流，**不进** EvidenceStore RunRecord，**不进** 任何 Pydantic 持久化模型 |
| 6c | prompt catalog 注入方式 | 沿用 `splice_schema_skeleton` 的 marker 机制，新增 `<!-- TOOLS:CATALOG:START/END -->`，**运行时渲染注册表里全部工具**，分「本轮已执行」（附 JSON 结果）和「可按需请求」（`opt_in`，只给名字+说明书，供 `tool_requests` 引用）两段 |
| 7 | 原生 tool use 后门 | **留**。同一套 `Tool` 定义在 provider 支持时可注册成真 function calling |

## 2. 通用抽象：`src/infra/tooling/`

只有一层概念——`Tool` 本身既是"说明书元信息"也是"可执行单元"（讨论后去掉了
`Tool` Protocol + `FunctionTool` 包装的两层设计，直接用一个具体 dataclass 包一个
函数）。`ToolContext` 是共享基类，每个 step 定义自己的子类扩展所需字段
（比如 `Step2ToolContext` 加 `spec_dict`），而不是塞一个大杂烩通用 context。

```python
# src/infra/tooling/types.py
CtxT = TypeVar("CtxT", bound="ToolContext")

@dataclass
class ToolContext:
    """共享基类；各 step 定义自己的子类，加自己需要的字段。"""
    results: dict[str, "ToolResult"] = field(default_factory=dict)
    prior_round_failed: bool = False   # 供 on_failure tier 判断

@dataclass
class ToolResult:
    name: str
    status: Literal["ok", "error", "skipped"]
    payload: dict = field(default_factory=dict)   # 给 LLM 的 JSON（决策 2）
    error: str | None = None
    truncated: bool = False

@dataclass
class Tool(Generic[CtxT]):
    name: str
    description: str          # 干什么 —— 进 prompt catalog
    produces: str             # 输出含义 + 局限 —— 进 prompt catalog
    fn: Callable[[CtxT], ToolResult]
    tier: Literal["always", "on_failure", "opt_in"] = "always"

    def run(self, ctx: CtxT) -> ToolResult:
        return self.fn(ctx)
```

没有 `depends_on`/拓扑排序：工具**按调用方传入的 list 顺序**依次跑（顺序由组装
`tools = [SCHEMA_VALIDATION_TOOL, ENGINE_MENU_TOOL, ...]` 时的书写顺序决定，
显式、无环、不需要通用依赖解析）。需要前置结果的工具自己去 `ctx.results` 查，
查不到就自己返回 `status="skipped"`——不把这个决策交给 runner：

```python
@dataclass
class Step2ToolContext(ToolContext):
    spec_dict: dict = field(default_factory=dict)

def _schema_validation_fn(ctx: Step2ToolContext) -> ToolResult:
    spec, report = _schema_validation_tool(ctx.spec_dict)   # 复用现有逻辑
    ctx.results["_parsed_spec"] = spec   # 供后续工具（如 engine_menu）读取真正的 MethodSpec
    return ToolResult(
        name="schema_validation",
        status="ok" if spec else "error",
        payload={"report": report},
    )

SCHEMA_VALIDATION_TOOL = Tool(
    name="schema_validation",
    description="Pydantic 结构校验 MethodSpec",
    produces="校验通过与否 + 错误列表。局限：只查结构，不查经验参数合理性",
    fn=_schema_validation_fn,
)

def _engine_menu_fn(ctx: Step2ToolContext) -> ToolResult:
    spec = ctx.results.get("_parsed_spec")
    if spec is None:
        return ToolResult(name="engine_menu_and_capability", status="skipped",
                           error="requires a validated MethodSpec (schema_validation must run first)")
    ...
```

### `ToolPolicy`

```python
@dataclass
class ToolPolicy:
    enable: set[str] | None = None      # None = 按 tier 默认
    disable: frozenset[str] = frozenset()
    max_payload_chars: int = 4000       # 单工具输出上限
    allow_llm_requests: bool = True     # 决策 1 的开关
```

`ToolPolicy()`（默认构造）= 第一轮全部 `always` 工具跑满 —— 保证所有现有调用点零改动。

### `ToolRunner`

```python
class ToolRunner:
    def run_all(
        self,
        tools: list[Tool[CtxT]],
        ctx: CtxT,
        policy: ToolPolicy,
        tracer: PipelineTracer | None = None,   # 未传则不记录（问题3）
    ) -> list[ToolResult]: ...
```

- **失败隔离**：任何工具抛异常 → `status="error"`，绝不 crash pipeline
- **预算**：`max_payload_chars` 字段先保留但**暂不启用**（截断逻辑推迟为后续优化项，
  `truncated` 目前恒为 `False`）
- **顺序**：按 list 顺序依次跑，无依赖解析（见上）
- **分档**：`always` 总跑；`on_failure` 只在 `ctx.prior_round_failed` 时跑；
  `opt_in` 只在 `policy.enable` 点名或 LLM 通过 `tool_requests` 请求时跑
- **全部结果写 trace**（决策 6b，`tracer` 可选，传了才记），每条一个 `TraceEvent`，
  `detail` 里带 `step / round / name / status / payload_hash`

**`prior_round_failed` 的职责划分（Q4）**：`ToolRunner` 只消费调用方算好的
`ctx.prior_round_failed` 布尔值，自己完全不判断"什么算失败"——因为不同 step
判定失败的方式不一样（step2 是 schema 校验没过，step3 是 sandbox/execution 报错），
这个判断属于各 step 自己的循环代码，不属于通用基础设施：

```python
ctx = Step3ToolContext(plugin=plugin, spec=spec)
for round_num in range(1, max_rounds + 1):
    ctx.prior_round_failed = (round_num > 1 and last_validation_report.status != "passed")
    results = runner.run_all(tools, ctx, policy)   # runner 只读这个标志，不参与计算
    ...
```

### `tests/test_tooling.py` 覆盖清单

- 工具异常被隔离，不传播，标记 `status="error"`
- 一个工具读 `ctx.results` 里前置工具的结果，前置没跑/没成功时自己返回 `skipped`
  （验证"无依赖解析、由工具自己判断"这个设计）
- `disable` 生效（两段 catalog 都不出现该工具）
- `opt_in` 工具默认不跑；`tool_requests` 点名后才跑
- `tool_requests` 请求了未注册的名字 → 忽略 + 下一轮 catalog 提示"未知工具名"
- `on_failure` 工具依据调用方传入的 `ctx.prior_round_failed` 决定跑不跑
- `tracer=None` 时不报错；传了 tracer 会收到对应事件
- catalog splice：marker 存在/不存在两种情况；"已执行"段 vs "可请求"段内容正确

### Prompt 渲染

catalog 必须让 LLM 知道**全部**已注册工具的存在（否则它无法通过 `tool_requests`
请求 `opt_in` 工具），但只有「本轮已执行」的工具才有 JSON 结果可看。因此 catalog
分两段，由共享 renderer 产出：

```markdown
<!-- TOOLS:CATALOG:START -->
## TOOL CATALOG

### 本轮已执行（结果见下方 TOOL RESULTS）
- schema_validation: Pydantic 结构校验 MethodSpec。局限：只查结构...

### 可按需请求（在 tool_requests 里写工具名，下一轮执行）
- keyword_locate: 按关键词定位论文原文片段。局限：只做子串匹配，非语义搜索
<!-- TOOLS:CATALOG:END -->

## TOOL RESULTS (round N)  ← 仅「本轮已执行」工具的 JSON payload
```

`disable` 掉的工具两段都不出现。LLM 请求了一个不在注册表里的名字——**忽略，
下一轮 catalog 里追加一行「未知工具名：xxx」提示**，不中断循环。

`splice` 行为照抄 [`splice_schema_skeleton`](../src/infra/models/schema_render.py)：
纯 `find`/切片替换，marker 缺失就原样返回文本，不强制要求存在、不报错。

## 3. 通用循环

把 step2 的 review 循环和 step3 的 repair 循环合并成一个形态：

```
for round in 1..N:
    results = ToolRunner.run_all(tools, ctx, policy)   # 第 1 轮全跑
    if converged(results): break
    output = llm(catalog + results + prev_output)
    ctx.update(output)
    if output.tool_requests and policy.allow_llm_requests:
        tools += resolve(output.tool_requests)          # 决策 1
```

step2 的 3 轮 review、step3 的 3 次 repair、step8 的 claim 校验都是这个循环的实例，
只是 `tools` 与 `converged` 不同。

## 4. 各步骤工具清单（全部复用现有函数）

### Step 1 — 抽取（详细讨论后的结论，见 §4.1）

| 工具 | 复用 | 是否采用 |
|---|---|---|
| `schema_skeleton` | `splice_schema_skeleton` | 采用，但是**占位型 tool**（payload 不重复渲染 JSON，只指向第5节示例），第5节的 splice 机制本身不变 |
| ~~`pdf_text`~~ | ~~`CodexCLIClient._pdf_to_text`~~ | **不成立**：`paper_text` 在 `extract()` 之前已由离线脚本 `scripts/convert_papers_to_md.py` 转好；`pdf_bytes` 走的是 client 内部机制，不是可复用的独立函数 |
| ~~`keyword_locate`~~ | 关键词命中片段提取 | **暂不加**（讨论后决定，见 §4.1） |

## 4.1 Step 1 详细讨论结论

- **Step1 架构上是严格单次 LLM 调用**（`MethodSpecExtractor` 类和模块 docstring
  明确写"a single LLM call, nothing else"，正确性工作全部在 Step2）。因此
  Step1 的 tools+LLM 改造是**纯前置（prelude-only，无轮次）**：不加循环、
  不加 `tool_requests` 字段——没有"下一轮"去执行它，加了也是摆设，还会违背
  已经写进代码注释的设计原则。
- **`pdf_text` 工具不成立**：核实后发现 `paper_text` 到达 `extract()` 时已经是
  离线脚本预先转换好的 markdown（[scripts/convert_papers_to_md.py](../scripts/convert_papers_to_md.py)
  用 pymupdf4llm），`extract()` 内部不需要也不做 PDF 抽取；`pdf_bytes` 那条路径
  是原生支持 PDF 的 client（Codex/Claude）内部处理，不是我们能拿出来复用的
  独立确定性函数。
- **`schema_skeleton` 讨论后决定包成 Tool**（推翻了最初"它是静态模板不该算
  tool"的判断，为了跨 step catalog 一致性）。为避免和第5节"Required JSON
  Shape"示例重复渲染同一份 JSON（浪费 token），设计为占位型 Tool：

  ```python
  def _schema_skeleton_fn(ctx: Step1ToolContext) -> ToolResult:
      return ToolResult(
          name="schema_skeleton", status="ok",
          payload={"note": "完整内容见第5节 Required JSON Shape 示例，此处不重复"},
      )

  SCHEMA_SKELETON_TOOL = Tool(
      name="schema_skeleton",
      description="MethodSpec 的 JSON 骨架结构（从 Pydantic 模型自动生成）",
      produces="完整骨架内嵌在第5节示例里，跟当前论文内容无关，是结构约束不是分析结果",
      fn=_schema_skeleton_fn,
      tier="always",
  )
  ```

  第5节的 `splice_schema_skeleton` 嵌入机制本身**不变**，仍是唯一信息源。
- **`keyword_locate`（关键词命中定位）讨论后决定暂不加**：设计过（固定关键词
  列表按 [src/infra/models/method_spec.py](../src/infra/models/method_spec.py)
  的枚举值系统性生成，命中结果必须真正塞进这唯一一次 LLM 调用的 prompt 才有
  意义，否则等于白跑），但决定先不实现——**Step1 目前实质上没有新增任何真正
  分析论文内容的工具**，只有 `schema_skeleton` 这个占位型 tool 走 catalog 统一
  格式。如果之后有需要，`keyword_locate` 的设计（关键词按 schema 枚举系统性
  生成、每关键词限流几条代表性片段、结果进 TOOL RESULTS）已经讨论过，可以
  随时捡回来实现。

**红线**：step1 的任何工具**不得**触碰 `data/osap/SignalDoc.csv`。

### Step 2 — 审查

| 工具 | 复用 | tier |
|---|---|---|
| `schema_validation` | 现有 `_schema_validation_tool` | always |
| `engine_menu_and_capability` | 现有 `_engine_menu_and_capability_tool` → `review_method_spec` | always |

`physical_mapping`（`build_implementation_resolution`）/ `data_source_catalog`
（`catalog.source_of_column`）**不进 review 循环**——见 §5 问题1：这两个服务于
spec 定稿之后的 mapping 解析阶段，在 review 循环里提前跑会让 LLM 看到可能作废
的结果。它们仍然存在，只是不是这个循环的工具（未来如果 `build_implementation_
resolution` 内部的 LLM-fallback 也要接入 tooling，是另一个 `ToolContext`）。

## 5. Step 2 迁移细节（第一个动手迁移的 step，其余 step 待各自详细讨论后续写）

- **`Step2ToolContext`**：只加 `spec_dict: dict`。两个现有工具原样包成 `Tool`
  实例，`_schema_validation_fn` 把解析出的 `MethodSpec` 存进
  `ctx.results["_parsed_spec"]`，`_engine_menu_fn` 读它，读不到就自己
  `status="skipped"`（无 `depends_on`，见 §2）。
- **`error_log` 兼容性已用 [tests/test_step2_reviewer_llm.py](../tests/test_step2_reviewer_llm.py)
  验证**：现有断言只有 `== ""` / `!= ""` / 子串匹配（如 `"formation_month" in
  error_log`），**不检查 `[tag]` 精确格式**，只要 property 把 `tool_results` 里
  `payload["report"]`（Pydantic 报错原文 / findings 文本）拼接起来即可，迁移
  风险低。
- **`SpecBuildOutcome.tool_results` 存最后一轮**，语义与 `outcome.spec` /
  `outcome.review` 一致（"最终状态"）；完整历史仍在 `outcome.history[i].
  tool_results` 里。例：2 轮收敛时 `outcome.tool_results == outcome.history[1].
  tool_results`（第2轮两个工具都 `status="ok"`），而 `outcome.history[0].
  tool_results` 里 `engine_menu_and_capability` 是 `skipped`（第1轮 schema 没过）。
- **循环骨架与 opt_in/`tool_requests` 管线在所有 step 保持一致**：即使 step2
  当前没有注册任何 `opt_in` 工具，LLM 输出 JSON schema 仍从一开始就带可选字段
  `tool_requests: list[str] = []`，循环体统一走
  `results = runner.run_all(tools, ctx, policy)` → 渲染 catalog+results → 调 LLM →
  解析 `tool_requests` → 下一轮按需追加工具。step2 因为注册表为空，任何
  `tool_requests` 都会落进"未知工具名"分支（良性，不需要为 step2 特殊处理）。
  不会出现"step2 是阉割版、step3 才是完整版"的不一致。

### Step 2 prompt 迁移（[prompts/review_gate/llm_review.md](../prompts/review_gate/llm_review.md)）

- **第 0 节整体替换为自动渲染**：现状是手写的 `[schema_validation]`/
  `[engine_menu_and_capability_findings]` 说明文字，跟"工具说明书从 `Tool.
  description`/`produces` 自动生成"是重复的两套信息源，容易像
  `splice_schema_skeleton` 要解决的"文档漂移"问题一样跟着代码走偏。第 0 节改成
  `<!-- TOOLS:CATALOG:START/END -->`，由 catalog renderer 动态产出；以后加工具
  只需要写 `Tool(description=..., produces=...)`，prompt 自动同步，不再手改这
  一节。
- **第 6 节输出 JSON 现在就加 `tool_requests` 空字段**（跟"循环骨架在所有 step
  保持一致"呼应，不等 step3 才加）：

  ```json
  {
    "spec": { ... },
    "field_assessments": [...],
    "value_corrections": [...],
    "evidence_assessments": [...],
    "additional_findings": [...],
    "tool_requests": []
  }
  ```

  解析时用 `.get("tool_requests", [])` 兜底——现有 `_FakeLlmClient` 测试返回的
  payload 都没有这个字段，不受影响。step2 目前没有任何 `opt_in` 工具可请求，
  这个字段对 LLM 是摆设，但保持跨 step 格式一致。
- **`llm_notes`（`value_corrections`/`additional_findings`）与 `tool_results`
  是两条独立信息线，不混在一起**：前者是"LLM 对自己改动的解释"，后者是
  "确定性工具的报告"。`SpecBuildOutcome.llm_notes` 不变，新增
  `SpecBuildOutcome.tool_results` 与之并列，互不覆盖。

### Step 3 — 生成

| 工具 | 复用 | 是否采用 |
|---|---|---|
| ~~`config_menu_snapshot`~~ | ~~`registry.build_config`~~ | **不做**（讨论后决定，见下）：LLM 结构性地只能写 `compute_signal`，无法触碰 portfolio construction/weighting/breakpoints 那部分代码（那是配置拼接，不是代码生成），真正能防的只是"隐性冲突"（比如公式内部悄悄处理了缺失值，跟引擎后续基于 `missing_action` 的处理产生不一致），场景边缘、性价比不够，暂不做。风险维持现状：`prompts/meta_coder/signal_plugin_system.md` 的文字规则 + `AdversarialSandbox` 的可疑模式扫描是现有两道防线，不做这个工具不引入新风险，只是不多一层预防 |
| `column_mapping` | `resolution.concept_mapping` | 采用，从 `_build_prompt_from_resolved()` 里手写的箭头文本（`at → df["at"]`）迁移成独立 `Tool`，payload 走 JSON。[tests/test_meta_coder_resolved_method_spec.py](../tests/test_meta_coder_resolved_method_spec.py) 里断言精确箭头文本格式的用例需要同步改成断言 JSON payload，讨论后确认可以改测试 |
| `build_script` | `script_generator.generate_backtest_script` / `BacktestRunner.build_script` | 采用 |
| `sandbox_validate` | `AdversarialSandbox.validate`，扩展后**同时**承载技术指标（见 §4.2） | 采用 |

**结构性说明**：代码还没生成时无法跑 build/sandbox，所以 step3 的 tools+LLM 实质是
把 [repair.py](../src/infra/repair.py) 的循环显式化，**行为跟现有 `RepairLoop` 完全
一致**——只在失败时 `repair_plugin`，成功就不管，不新增任何 LLM 调用（§4.2 详细
推翻了最初"成功也强制回喂一轮"的设想）。

**红线**：`sandbox_validate` 的技术指标 payload 白名单化 ——
只允许 `nan_ratio` / `n_permno` / `n_months` / `missing_columns` / `dtype` 一类字段，
任何 return/alpha/t-stat/Sharpe 一律不进 payload。这些指标只供人工审计，不触发任何
LLM 决策（见 §4.2）。

## 4.2 Step 3 详细讨论结论

### `smoke_run` 并入 `sandbox_validate`，不是独立工具

原方案把 `smoke_run`（技术指标）和 `sandbox_validate`（pass/fail 校验）列成两个
独立工具，各自要跑一次 `compute_signal`。讨论后发现现有
[AdversarialSandbox.validate()](../src/steps/step4_validator/__init__.py) 的
执行 smoke test 已经在子进程里跑了一次 `compute_signal`，只是目前只产出
pass/fail + 文字消息（`report.errors`/`report.warnings`），**没有把 NaN 比例、
permno 数量这类数字结构化地提取出来**。

**关键判断（类比 step2）**：`AdversarialSandbox.validate()` 物理上住在
[step4_validator/](../src/steps/step4_validator/) —— 这是一个独立、被
`Pipeline` 和 `DualTrackController` 共用的 step（见 [AGENTS.md](../AGENTS.md)
模块表），不是 step3 私有代码。但这不妨碍把它**注册成 step3 工具列表里的一个
`Tool`**——跟 step2 把物理上住在 `review.py` 的 `review_method_spec` 包成
`Tool` 是同一个模式：`Tool` 只是"把一次调用包上说明书"，不代表要把底层函数
搬进调用方的目录。

`smoke_run` 不再是独立工具，**并入 `sandbox_validate`**，复用同一次
`compute_signal` 执行，避免多跑一次：
1. `_EXECUTE_DRIVER`（[step4_validator/__init__.py](../src/steps/step4_validator/__init__.py)）
   的子进程 driver 在算完 `compute_signal` 后，顺手计算白名单技术指标，写进
   它已经返回的 JSON（原有 pass/fail/empty/engine_error 判断逻辑不变）
2. `ValidationReport` 新增字段 `technical_metrics: dict`（白名单字段），
   `report.errors`/`report.warnings` 的语义和现有测试断言不受影响（纯加字段）
3. step3 注册的 `sandbox_validate` `Tool.fn` 调用
   `AdversarialSandbox.validate(...)`，`ToolResult.payload` 只摘取
   `report.technical_metrics`（白名单），不摘 `errors`/`warnings` 里可能夹带的
   其他信息进 payload

### "成功也强制回喂一轮"（原决策5）讨论后撤销

推翻过程（完整推理见对话记录，这里只记结论）：

1. 最初设想"即使 `sandbox_validate` 通过，也多打一次 LLM 调用，让它看技术
   指标决定要不要自我修正"（方案甲），代价是成功路径多花一次 LLM 调用。
2. 但审视每个候选指标能否支撑"要不要改"的判断：
   - `missing_columns`（引用不存在的列）：**会在执行时直接抛异常**，已经
     被现有的 `report.errors` 判定为失败，走的是**现有**失败分支，根本到不了
     "成功但要确认"这个状态
   - `dtype` 异常（比如 signal 列输出成字符串而非数值，但不抛异常）：现在
     没人检查，但只要真的要检测，最自然的做法是**直接把它加进
     `report.errors`，变成一个新的确定性失败条件**，而不是发明"成功确认轮"
   - `nan_ratio`/`n_permno`/`n_months`：[step4_validator 的 docstring](../src/steps/step4_validator/__init__.py)
     明确写着验证切片故意很薄，"even with entirely correct code" 也会显得
     退化——LLM 没有基准去判断这些数字对薄切片而言算不算异常，勉强喂给它做
     决策依据只会**误伤正确代码**
3. **结论**：两个真正"确定性、能明确判断是bug"的信号（`missing_columns`、
   `dtype`）本来就该走**现有**的 `report.errors → repair_plugin` 失败分支——
   `repair_plugin(plugin, errors: list[str])` 本身就是通用字符串列表接口，
   `dtype` 检查只要加进 `report.errors`，**自动**复用现有失败-修复循环，不需要
   任何新代码路径。剩下唯一"没法可靠判断"的指标（NaN比例/覆盖数）本来就不该
   触发决策。
4. **最终行为**：`RepairLoop` 完全不变——只在失败时 `repair_plugin`，
   成功就定稿，不新增任何 LLM 调用。`technical_metrics`（含 `dtype` 检测结果）
   只是 `sandbox_validate` 这个 `Tool` payload 的一部分，供人工审计/调试参考。
   Step3 事实上没有新增循环，唯一实质改动是给 `validate()` 加一条 `dtype`
   确定性检查。

### Step 8 — 诊断（**完整重新设计**，见 §4.3）

step8 从"只讲配置敏感度"重新设计为**分层归因**——复现不上的原因分成三大类，
每类各自的证据现在有的已经在算但被丢弃，有的完全没算，新增/找回后才能讲清楚。

**红线不变**：LLM 输出仍只能引用 `evidence_keys` 白名单，不许含数字，
由 [render.py](../src/steps/step8_diagnosis/render.py) 重新插入所有数字；
不许用因果措辞（"caused by"/"drives"），因为只有观察性/OAT证据，断不了因果。

## 4.3 Step 8 详细讨论结论：完整重新设计

### 问题框架：复现差距的三层来源

```
论文原文
   ↓  ① 抽取/理解层：我们有没有读懂论文？
MethodSpec（论文说了什么）
   ↓  ② 表达层：引擎能不能忠实表达论文的方法？
实际跑的 config（引擎实际做了什么）
   ↓  ③ 配置敏感度层：不同配置选择带来多大差异？
跑出来的数
   ↓ vs 论文报告的数 ← 差距
```

| 层 | 问题 | 证据来源 | 现状（已查证，与最初判断不同） |
|---|---|---|---|
| **①spec_quality** | 论文没写清楚，我们只能猜 | `review_method_spec(paper: MethodSpec) -> MethodReview` | **不需要任何新持久化**——这是个纯函数，`spec.paper`（`ResolvedMethodSpec` 的一部分）本来就是 `write_comparison_summary`/`build_evidence_bundle` 的调用参数，现场重新调用 `review_method_spec(spec.paper)` 即可 |
| **②engine_fidelity** | 论文写清楚了，但引擎表达不了，被夹到默认值 | `unsupported_value`（`spec.paper.*` 里）+ `defaults_applied`（`registry.build_config` 算的） | **两边都不需要新持久化**：`unsupported_value` 同样从已在手边的 `spec.paper` 直接读；`defaults_applied` 早已内嵌在 `build_config()` 返回的 config dict 里，而 `tracks_summary[track]["config"] = build_config(...)`（[step6_dual_track_controller](../src/steps/step6_dual_track_controller/__init__.py#L470)）已经原样把它写进了 `comparison.json`——之前判断"算了但丢了"是错的（搜索范围只查了 `src/infra/**`，漏看了 `src/steps/step6_dual_track_controller`） |
| **③config_sensitivity** | 都能表达，不同配置选择造成多少差异 | `config_diff` + `gap_decomposition`（OAT） | 已有 |

**修正后的结论**：①②两层**不需要碰任何持久化 schema**（`RunRecord`/`comparison.json`
的核心结构不用动）——只需要在 `bundle.py` 新增两个函数
`build_spec_quality(spec)` / `build_menu_deviations(spec, tracks)`，从**已经在调用
现场的 `spec` 参数** + **已经在 `tracks` dict 里的 `defaults_applied`** 组装出来。

### 三个新增的深层诊断类型（讨论后确定要做，见对话记录里的能力盘点）

在①②③之外，探查了现有 pipeline 已经算出来、但从没喂给 Step8 的三类证据：

**1. `signal_reproducibility`（信号本身能不能复现，基于 bridge track）**

已有 **bridge track** 机制（`signal_input_ref: "cz_bridge[:factor_id]"`，
[step6_dual_track_controller](../src/steps/step6_dual_track_controller/__init__.py)）：
把 C&Z 的参考信号跑过**跟我们的 track 完全相同的下游配置**，`RunRecord.
is_bridge_track=True` 标记。这构成天然的对照：

- bridge 复现了论文、我们的 track 没有 → 问题出在**信号构造代码本身**（LLM 生成的
  `compute_signal` 跟 C&Z 理解不同），不是配置/引擎的问题
- 两条都没复现 → 问题更可能在下游/数据，不在信号
- 两条都复现了 → 信号和配置都没问题

新增 `bundle.py` 函数 `build_bridge_comparison(tracks_dict)`：找到
`is_bridge_track=True` 的 track 和它对应的常规 track，各自的 `vs_paper.
sign_agrees` 拿出来比较，产出 `signal_implementation_agreement: "both_reproduce"
| "only_bridge" | "only_own" | "neither"`。**没有注册 bridge track 的因子，这条
证据不可用**（跟 `gap_decomposition` 在没有 ablation track 时不可用是同一个模式，
复用 `evidence_limitation` claim type 处理"证据不存在"的情况）。

**需要小量持久化改动**（查证后的修正）：`write_comparison_summary`
组装 `tracks_summary` 时现在只塑了 `{"config":..., "metrics":...}`，**没把
已经存在的 `RunRecord.is_bridge_track` 塑进去**——这不是模型 schema 变化，
只是往已有的 dict 里加一行 `"is_bridge_track": r.is_bridge_track`，工作量很小。

**2. `publication_decay`（发表后衰减）**

`by_sample_period`（[backtest_engine](../src/infra/backtest_engine/__init__.py)）
已经在算 `insamp`/`between`/`postpub` 三段独立指标（配置了
`sample_start_year`/`sample_end_year`/`publication_year` 时），但从没喂给
Step8。这是 McLean-Pontiff 那条经典线——"样本内显著，发表后消失"。

新增 `bundle.py` 函数 `build_publication_decay(tracks_dict)`，对每条有
`by_sample_period` 的 track 产出 `insamp_t_stat`/`postpub_t_stat`/`decayed`
（样本内显著、发表后不显著）。**只在配置了发表年份分段时可用**，同样走
`evidence_limitation` 兜底。
**需要真正的 schema 新增**（查证后发现）：`by_sample_period` 虽然已由
[backtest_engine](../src/infra/backtest_engine/__init__.py) 算出，但
[RunMetrics](../src/infra/models/run_record.py#L11)（Pydantic 模型）**根本没有
这个字段**——它会在塑进 `RunMetrics(...)` 时被静默丢弃。这是①②都不需要的
那种真正需要新增 Pydantic 字段的地方：`RunMetrics` 加
`by_sample_period: dict | None = None`。
**3. `implementation_robustness`（实现敏感度/鲁棒性）**

OAT 矩阵（`run_from_matrix`）已经产出多条 ablation track 各自的 t-stat，但
现在只喂给 `gap_decomposition`（逐开关贡献），**没有算一个"整体鲁棒不鲁棒"的
汇总判断**。新增 `bundle.py` 函数 `build_robustness_summary(tracks_dict)`：
算 ablation track 间 t-stat 的极差、有几条符号翻转、有几条跨越显著性阈值，
产出 `robust: true/false`（无符号翻转且无显著性翻转才算 robust）。

### `reason_layer`：claim 现在要标注属于哪一层

现有 `DiagnosisClaim` 不区分"这句话在讲哪类原因"，全部混在一个 `claims` 列表
里。新增字段：

```python
class DiagnosisClaim:
    ...
    reason_layer: Literal[
        "spec_quality",           # ①
        "engine_fidelity",        # ②
        "signal_fidelity",        # 新：bridge track 信号复现
        "config_sensitivity",     # ③（含现有的 sign_agreement/magnitude_gap/
                                   #    significance/config_divergence/gap_attribution
                                   #    以及新增的 implementation_robustness）
        "temporal_pattern",       # 新：publication_decay，跟"我们复现得好不好"
                                   # 是正交的，是论文因子本身的时间性质
    ]
```

新增的 3 个 claim_type（`signal_reproducibility`/`publication_decay`/
`implementation_robustness`）各自的 `CLAIM_EVIDENCE_REQUIREMENTS`/
`CLAIM_RELATIONS`/`render.py` 模板，遵循现有 6 个 claim_type 完全相同的模式
（[src/infra/models/diagnosis.py](../src/infra/models/diagnosis.py)）——**这是
唯一需要你后续再确认的细节**：新 claim_type 的具体 relation 取值（比如
`signal_reproducibility` 用 `"reproduces"`/`"diverges"`）我先按现有命名风格
拟了一版，写代码前可以再核对。

### 循环：重试 + `tool_requests`

```
round 1: 工具全跑（三层证据 always tier）→ catalog + JSON payload → LLM 产出 claims
         validate_claims() 逐条校验（现有校验器 + reason_layer 一致性检查）
             ↓
         有被拒的 claim？
             是 → round 2：把拒绝原因喂回去，只重写被拒的那几条（有界，最多1次）
             否 → 定稿
```

`tool_requests`（opt_in）：三层证据都是**摘要**（比如 `spec_quality` 只列弱字段
名+状态，不摆每个字段完整的论文原文引用）。新增 opt_in 工具
`field_evidence_detail`——LLM 觉得某个字段需要看完整证据引用才能判断严重程度时，
输出 `tool_requests: ["field_evidence_detail:portfolio.weighting"]`，下一轮把
`SourcedValue.evidence[]` 的完整内容喂给它。

### 工具注册：Step8 的"工具"绝大多数是占位型，真正的计算发生在 Step7

**关键结构性事实**：除了 `field_evidence_detail`，其余所有证据（`spec_quality`/
`menu_deviations`/`bridge_comparison`/`publication_decay`/`robustness_summary`/
`config_diff`/`gap_decomposition`/`track_vs_paper`）的计算本身都发生在**Step7**
的 `build_evidence_bundle()`，写进 `comparison.json`。**Step8 的 `diagnose()`
只是读取现成的 bundle，不实际执行任何计算**——跟 Step1 的 `schema_skeleton`
是同一种情况（`Tool.fn` 是"从已经算好的地方取值"的占位，不是"现算"）。

```python
@dataclass
class Step8ToolContext(ToolContext):
    bundle: dict                              # 解析后的 comparison.json
    resolved_spec: ResolvedMethodSpec | None = None  # 仅 field_evidence_detail 需要

def _spec_quality_fn(ctx: Step8ToolContext) -> ToolResult:
    section = ctx.bundle.get("spec_quality")
    if section is None:
        return ToolResult("spec_quality", "skipped", error="bundle 里没有 spec_quality（旧版 comparison.json）")
    return ToolResult("spec_quality", "ok", payload=section)

SPEC_QUALITY_TOOL = Tool(
    name="spec_quality", tier="always",
    description="论文里哪些字段证据不足（unspecified/inferred/conflicting）",
    produces="字段名+证据状态摘要，不代表这些字段一定错，只代表'这是我们猜的'",
    fn=_spec_quality_fn,
)
```

同样模式（`tier="always"`，`fn` 都是 `ctx.bundle.get(...)` 取值）注册：
`menu_deviations` / `bridge_comparison` / `publication_decay` /
`robustness_summary` / `config_diff` / `gap_decomposition` / `track_vs_paper`。
每个 `bundle.get(...)` 返回 `None` 时（旧版 `comparison.json` 没有这个字段，
或该证据本来就不适用，如没注册 bridge track）一律 `status="skipped"`，不报错。

`field_evidence_detail` 是唯一**真正现场计算**的 opt_in 工具，需要访问完整
`ResolvedMethodSpec`（不只是 bundle 摘要）来读 `SourcedValue.evidence[]`：

```python
def _field_evidence_detail_fn(ctx: Step8ToolContext, field_path: str) -> ToolResult:
    if ctx.resolved_spec is None:
        return ToolResult("field_evidence_detail", "skipped", error="no resolved_spec supplied")
    ...  # 现场从 resolved_spec 里按 field_path 取 SourcedValue.evidence[]
```

**`diagnose()` 签名新增一个可选参数**：`resolved_spec: ResolvedMethodSpec | None
= None`——没传时 `field_evidence_detail` 这个工具不可用（LLM 请求它会落进
"未知工具名/工具不可用"分支），不影响其余证据正常工作。

### 暂不做

**信号值层面的横截面相关性**（我们的 signal 排序 vs C&Z 的 signal 排序，
Spearman/rank IC）——现在完全没有这层计算，`signal_series_path` 虽然存了两边的
信号，但没有比较逻辑。这个能提供比"收益差多少"更直接的"实现分歧有多大"量化，
但需要新写一整层计算（不是"找回丢弃的数据"这种低成本改动），本次不做，记录
在案供以后考虑。

## 6. 向后兼容策略

**Golden number 零风险**：[test_accruals_e2e.py](../tests/test_accruals_e2e.py)、
[test_mvp_e2e.py](../tests/test_mvp_e2e.py)、[test_bridge_track_e2e.py](../tests/test_bridge_track_e2e.py)、
[test_real_wrds_samples_e2e.py](../tests/test_real_wrds_samples_e2e.py)
全部从 `tests/fixtures/` 的已提交 MethodSpec + plugin 出发，**一次 LLM 都不调**。

### 入参：只做加法

所有 LLM 入口新增一个可选参数 `tool_policy: ToolPolicy | None = None`（默认全跑）。
现有 8 个非测试调用点一行不改即可运行：

- [app.py](../app.py#L828) / [backend/routers/methodspecs.py](../backend/routers/methodspecs.py#L94) — `extract`
- [app.py](../app.py#L832) / [backend/routers/methodspecs.py](../backend/routers/methodspecs.py#L136) — `build_reviewed_method_spec`
- [app.py](../app.py#L908) / [backend/routers/methodspecs.py](../backend/routers/methodspecs.py#L322) — `build_implementation_resolution`
- [app.py](../app.py#L351) / [backend/routers/codegen.py](../backend/routers/codegen.py#L33) — `generate_plugin`
- [backend/routers/diagnosis.py](../backend/routers/diagnosis.py#L63) / [scripts/analyze_comparison.py](../scripts/analyze_comparison.py#L82) — `diagnose`

### 返回类型：按是否持久化分三类

| 类型 | 持久化 | 处理 |
|---|---|---|
| `ExtractionResult`（dataclass） | 否 | **加字段** `tool_results: list[ToolResult]` |
| `SpecBuildOutcome` / `ReviewRound`（dataclass） | 否 | **加字段** `tool_results`；`error_log` 降级为渲染 property（决策 6a） |
| `PluginRecord`（Pydantic，落 `runs/` 与 `tests/fixtures/`） | 是 | **不动**。工具结果走 trace 侧信道，与现有 `_token_usage` 同路数 |
| `ReplicationDiagnosisReport`（Pydantic，`schema_version=2`，落 `diagnosis.json`） | 是 | **不动** |

`comparison.json` 的核心结构（`tracks`/`derived`/`config_diff`/`gap_decomposition`）
不碰；**执行阶段更正**：Step8 重设计新增的顶层字段（`spec_quality`/
`menu_deviations`/`bridge_comparison`/`publication_decay`/`robustness_summary`）
是纯加法，不破坏现有消费方，但按项目惯例 `COMPARISON_SCHEMA_VERSION` 从 2 bump
到 3。

### `ReviewRound.error_log` 迁移（决策 6a）

```python
@dataclass
class ReviewRound:
    round_num: int
    tool_results: list[ToolResult] = field(default_factory=list)
    ...
    @property
    def error_log(self) -> str:
        """从 tool_results 渲染出的旧格式标签块文本，保留给 UI 与既有测试。"""
```

保留理由：`error_log` 是目前唯一能让人一眼看懂"这轮 LLM 到底看到了什么"的调试字段，
且 [tests/test_step2_reviewer_llm.py](../tests/test_step2_reviewer_llm.py) 有 19 处调用依赖它。

## 7. 实施顺序

1. `src/infra/tooling/`：`Tool` / `ToolResult` / `ToolPolicy` / `ToolRunner` / catalog renderer + 单元测试
2. trace 集成：`ToolRunner` 写 `TraceEvent`（决策 6b）
3. **Step 2 先迁移**（已有雏形，风险最低）：`_PRE_LLM_TOOLS` → 新接口，`error_log` 转 property，
   prompt 加 `TOOLS:CATALOG` marker。全部现有 step2 测试必须绿
4. Step 1 迁移（工具最简单）
5. Step 3 迁移：`sandbox_validate` 包含技术指标白名单 + `dtype` 检查并入现有失败判据（不新增循环，见 §4.2）
6. Step 8 重新设计（见 §4.3，工作量比最初判断小——多数证据零新持久化）：
   a. `bundle.py` 新增 `build_spec_quality(spec)`（现场调用 `review_method_spec(spec.paper)`）
      和 `build_menu_deviations(spec, tracks)`（读已存在的 `unsupported_value`/
      `defaults_applied`）——**均不改任何 schema**
   b. 新增 `bundle.py` 函数：`build_bridge_comparison`（需要 `write_comparison_summary`
      的 `tracks_summary` 补一行 `is_bridge_track`，小改动）/ `build_publication_decay`
      （需要 `RunMetrics` 加 `by_sample_period` 字段，真正的 schema 新增）/
      `build_robustness_summary`（零新增，读现有 `metrics.t_stat`）
   c. `DiagnosisClaim` 加 `reason_layer` 字段；`diagnosis.py` 加 3 个新 claim_type 及其
      `CLAIM_EVIDENCE_REQUIREMENTS`/`CLAIM_RELATIONS`；`render.py` 加对应模板
   d. `diagnose()` 加有界重试循环（被拒 claim 重写，最多1次）
   e. 新增 opt_in 工具 `field_evidence_detail` + `tool_requests` 解析
7. 伪 tool call（决策 1）：`tool_requests` 字段 + `resolve()` + `allow_llm_requests` 开关
8. 原生 tool use 后门（决策 7）：`Tool` → OpenAI tool schema 的适配器，仅在 provider 支持时启用

每一步单独提交，每步跑对应窄测试；1/3/6 步后跑一次 `pytest tests/`（跨模块共享 schema 行为）。

## 8. 不可破的红线汇总

- step1 的任何工具不得触碰 `data/osap/SignalDoc.csv`
- 工具只能"报告"，不能替 LLM 决定经验参数；菜单外的值仍由 `registry.build_config` clamp
- step3 的 `sandbox_validate` 技术指标 payload 只允许白名单字段（`nan_ratio`/`n_permno`/
  `n_months`/`missing_columns`/`dtype`），绝不回喂任何绩效数字；这些指标只供人工
  审计，**不触发任何 LLM 决策**（“成功也强制回喂一轮”的方案讨论后已撤销，见 §4.2）
- step8 的 LLM 输出仍受 `evidence_keys` 白名单 + 禁数字约束，不许用因果措辞
- step8 的 `signal_reproducibility`/`publication_decay`/`implementation_robustness`
  证据不可用时（没注册 bridge track / 没配置发表年份分段）必须走 `evidence_limitation`
  兵底，不得编造证据
- 不得为了塞工具结果而修改任何持久化 Pydantic 模型的 schema（**例外**：`RunMetrics`
  新增 `by_sample_period` 字段——查证后 `MethodReview`/`unsupported_value`/
  `defaults_applied` 实际都不需要碰 schema，唯一真正需要新增字段的是这一处，
  因为 `by_sample_period` 现在会在构造 `RunMetrics` 时被静默丢弃，这是本来就该
  保存却一直被丢弃的既有计算结果，不是"工具运行结果"）
