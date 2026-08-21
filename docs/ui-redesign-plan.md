# UI 重新设计方案

**状态：** 设计已确认，尚未实施。
**目标：** 把现在 9 个各自为政的页面收敛成一条主干（Session/Run），并补上三块缺失
能力：单步独立测试、tool + token 可观测性、data / MethodSpec 字段级说明。

相关文档：[architecture.md](architecture.md)、[tools-plus-llm-plan.md](tools-plus-llm-plan.md)、
[multi-config-evidence-plan.md](multi-config-evidence-plan.md)。

---

## 1. 现状问题

现有 9 个页面（`frontend/src/pages/`）里有 5 个是「同一件事的不同入口」：

| 页面 | 问题 |
|---|---|
| `ExtractorPage` | 只是 step1，和 session 的 step1 各写一遍 |
| `ReviewResolvePage` | 只是 step2，同上 |
| `PipelineE2EPage` | step3–7 的第二套跑法，和 session 重复 |
| `BacktestExperimentsPage` | step6 的第三套入口，且脱离 session 上下文 |
| `TraceLogsPage` | 只渲染 `TraceEvent` 的 `stage/event/detail`，没有 tool / token 结构 |
| `SessionsPage` / `SessionDetailPage` | **保留**，是唯一有完整审计链的入口 |
| `SchemaReferencePage` / `DataCatalogPage` | 保留概念，重写为可反查的字典 |

后果：同一步骤的 UI 行为在多处漂移；单步测试只能通过「非 session 页面」做，产物不
进 session 的审计链；跑完之后看不出哪些下游步骤已经过时。

## 2. 新信息架构（4 个区）

| 区 | 路由 | 取代 |
|---|---|---|
| **Runs**（会话中心） | `/runs`、`/runs/:id/step/:n` | Sessions + Extractor + Review + Pipeline + Backtest |
| **Telemetry**（可观测） | `/telemetry`、`/runs/:id/telemetry` | Trace Logs（重写） |
| **Reference**（字典） | `/ref/data`、`/ref/methodspec` | Data Catalog + Schema（重写） |
| **Settings** | `/settings` | 侧栏底部的 provider/model 选择器 |

**删除页面：** `ExtractorPage`、`ReviewResolvePage`、`PipelineE2EPage`、
`BacktestExperimentsPage`、`TraceLogsPage`。

**保留并复用的组件：** `MethodSpecBoard`、`MethodSpecViewer`、`CodeView`、`DiffView`、
`JsonTree`、`JobLogPanel`、`StepOutputView`、`MultiTrackChart`、`ReturnChart`、
`GapWaterfallChart`、`MetricsTable`、`StepStepper`。它们全部改为在 Runs 区内按 step
号挂载，不再各自绑定一个页面。

## 2.1 `/runs` 列表页细节

- **列：** factor_id / paper / 8 格进度点（复用 `StepStepper` 缩略版，完成/失败/未跑
  三态）/ 状态（运行中/完成/失败/归档）/ 最后更新时间 / tokens（先留空占位，待
  telemetry 汇总接入后再填）。
- **筛选/排序：** 第一版只做全量列表 + 搜索框（按 factor_id/paper 模糊匹配）。按状态
  筛选、按时间排序留到后续迭代。
- **新建 run：** 沿用现有 session 创建流程（选/上传 paper + 填 factor_id），只是套进
  新的页面壳，不重新设计创建流程本身。
- **归档 / 删除：** 不做归档功能，只保留删除（二次确认弹窗）。对应现有
  `DELETE /api/sessions/{id}`（硬删）。`POST /api/sessions/{id}/archive` 的软删除
  能力不在 UI 上暴露。
- **实时更新：** 不做 SSE 自动刷新，运行中的 run 靠手动刷新页面看最新进度/状态。
- **Fork 血缘标记：** 由 `Fork run`（见 §3）产生的新 run，在列表行上标注
  `↳ fork of #<run_id>`，点击可跳转到源 run；后端需要在 run 记录里存
  `forked_from: {run_id, step}`。
- **分页：** 先不做分页/虚拟滚动，等 run 数量真的多了再补。
- **行内展开看 tool 调用：** 每行左侧一个展开箭头，点击就地展开子区域（不跳转到
  telemetry 详情页），按 step 分组列出这次 run 每一步用过的 tool：
  - 每个 tool 一张卡片：`name` / `tier`（always/on_failure/opt_in）/ `status`，卡片
    本身默认折叠，点击展开完整 JSON payload（即 4.2 节 `telemetry.jsonl` 里
    `kind: "tool_call"` 的记录）。
  - 这个展开区是 `/runs/:id/telemetry` 详情页（LLM 调用时间线、跨 step 聚合）的
    轻量子集，只覆盖「这个 run 用了哪些 tool、输出是什么」这一个高频查看场景，
    不需要为了看 tool 输出而离开列表页。

## 3. Runs：一个 `StepWorkbench` 专做单步测试（不做自动 E2E）

核心抽象：**8 个步骤共用同一个组件**，只由 step 号参数化。这个页面的定位是**单步独立
测试**——没有「一键跑完整流程」的自动化按钮；要跑完整 8 步，就在这个页面里逐步手动
点 `Run step`，一步跑完看结果，再手动进下一步。这样每一步的产物都经过人眼确认，
不会被自动串联流程悄悄带过去。

```
┌ 顶栏: factor_id · paper · [Fork run] ────────────────────────────┐
├ Step Rail (1..8, 状态点: ok / stale / failed / not-run) ─────────┤
│ ┌── Input ──────┐ ┌── Action ─────┐ ┌── Output ────────────┐  │
│ │ 来源:          │ │ provider/model │ │ 由 step 决定：        │  │
│ │ ○ 上一步产物   │ │ [▶ Run step]   │ │  1/2 MethodSpecBoard │  │
│ │ ● 其他 run     │ │ [↻ Re-run]     │ │  3/4 CodeView        │  │
│ │ ○ fixture      │ └────────────────┘ │  5/6 图表 + Metrics  │  │
│ │ ○ 手动 JSON    │ ┌ Telemetry ─────┐ │  7 GapWaterfall      │  │
│ │ [查看 diff]    │ │ 3 LLM · 12.4k tok│ │  8 DiagnosisClaims   │  │
│ └───────────────┘ │ 7 tools · 4.2s   │ │ [Diff vs 上次]       │  │
│                   └──────────────────┘ └──────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

Input 面板的「来源」解决单步测试和端到端两种用法，不需要额外页面：

- **单步测试**（主要用法）：来源 = **其他 run 的上一步产物**（默认，不限 factor_id，
  下拉列出所有 run 并支持搜索）/ `tests/fixtures/` / 手动 JSON → 点 `Run step`，
  不必重跑前置步骤。
- **完整流程**：来源 = 上一步产物，从 step1 开始逐步手动点 `Run step`，一步步走到
  step8。没有自动串联按钮。
- **对比实验**：`Fork run` 从第 N 步复制出一条新 run，改参数再跑，天然形成 A/B。
  Step 6 的实验矩阵（多轨 / OAT / declarative matrix）**融入 Step 6 的 Output 面板**，
  不再单独开页面。

### 3.1 输入来源（`input_source`）

```jsonc
{"kind": "previous_step"}                                    // 顺序手动跑完整流程时用
{"kind": "other_run", "run_id": "...", "step": 2}            // 单步测试默认，run_id 不限 factor_id
{"kind": "fixture", "path": "tests/fixtures/..."}
{"kind": "inline", "payload": { /* ... */ }}
```

非 `previous_step` 的来源必须在 step 记录里留痕（`input_provenance`），否则审计链断裂。
UI 上对应一个显眼的「借用输入」徽标。若被借用的源 run 之后被硬删除，不做悬空引用
警告——当前 run 的该步产物已经落盘，无需重新读源。

### 3.2 Stale 传播

第 N 步重跑后，N+1..8 立即标记为 `stale`（产物仍在，但输入哈希已变）。这是审计链在
UI 上的表达，也是现在最缺的一环——目前跑完之后看不出哪些下游结果已经不对应当前输入。

### 3.3 单步执行与失败展示

- **Action 栏只有两个按钮**：`Run step`（当前步未跑过）/ `Re-run`（当前步已有产物，
  用当前 Input 栏配置重新跑一次）。没有自动跑多步的按钮。
- **失败展示：** Output 面板直接整块原样显示错误堆栈 / 校验失败输出（不做「一句话
  摘要 + 展开」的分层加工），保持和后端报错信息一致，便于直接拿去定位问题。
- **失败后的操作：** 允许直接在 Input 栏修改输入来源或参数，然后 `Re-run`；也可以
  不改动、原样 `Re-run`（应对网络超时等瞬时故障）。
- **多步依赖：** 由于没有自动串联，某一步失败不会影响别的步骤的状态——你只需要在
  失败的这一步修好、重跑，再手动切到下一个 step 号继续。Step Rail 上的 `stale` 状态
  （见 3.2）已经足够提示「下游步骤对应的输入已经变了，需要重新跑」。

## 4. Telemetry：tool 调用 + token 用量

### 4.1 现状缺口

- [src/infra/llm.py](../src/infra/llm.py) 的 `extract_usage()` 已经能拿到
  `prompt_tokens` / `completion_tokens` / `total_tokens`，但只在 step1 的 job result
  里返回一次，其余调用的 usage 被丢弃。
- CLI provider（Codex / Copilot）走 `_estimate_tokens`（≈4 字符/token），带
  `estimated: True` 标记。
- [src/infra/trace.py](../src/infra/trace.py) 的 `TraceEvent` 只有
  `timestamp/stage/event/detail/level`，没有结构化 usage，也没有 tool 概念。

### 4.2 统一事件流

[tools-plus-llm-plan.md](tools-plus-llm-plan.md) 的 D6b 已决定 tool 结果落 trace。这里
把 **LLM 调用也纳入同一条流**，并落到 session 目录：

```
runs/sessions/{session_id}/telemetry.jsonl
```

每行：

```jsonc
{
  "seq": 42, "ts": "...", "step": 2,
  "kind": "llm_call" | "tool_call",
  "name": "review_loop_round2" | "schema_validation",
  "status": "ok" | "failed" | "skipped",
  "duration_ms": 1834,
  "tokens": {"prompt": 8123, "completion": 942, "total": 9065, "estimated": false},
  "model": "...", "provider": "...",
  "tier": "always" | "on_failure" | "opt_in",   // tool_call
  "requested_by_llm": false,                     // tool_requests 触发的
  "attempt": 1,
  "payload_ref": "...",                          // 大 payload 落盘后的引用
  "error": null
}
```

### 4.3 UI 视图

1. **Timeline**：单次 run 的甘特条，LLM 调用与 tool 调用按 step 分道，直观看出哪一步
   慢、哪一步 retry 了。
2. **LLM Calls 表**：step / 用途 / model / prompt / completion / total / `~估算` 标记 /
   展开查看 prompt + response。
3. **Tool Calls 表**：name / tier / status / 是否由 LLM 的 `tool_requests` 触发 /
   payload JSON。
4. **聚合条**：`本次 run: 14 次 LLM · 86k tokens · 23 次 tool`，加按 step 的堆叠柱。
   全局 `/telemetry` 做跨 run 汇总（哪个 factor 最贵、review loop 平均几轮收敛）。

**硬性要求：** CLI provider 的 token 是估算值，UI 必须显式打 `~估算` 标签，且聚合时
估算与实测分列统计——否则这个数字会被误当成实测写进论文。

## 5. Reference：两个可反查的字典

不做静态文档页，做可搜索、可 deep-link 的字典。

### 5.1 `/ref/data`

数据来自现成的 `signal_sources_view()` / `data_catalog_view()` /
`returns_universes_view()`（[src/infra/data_layer/sources.py](../src/infra/data_layer/sources.py)）。

- 左：source 树（CRSP returns universe / Compustat / IBES / CCM link）。
- 右：columns 列表 —— concept 别名、单位、**lag 在哪里施加**、覆盖年份、缺失率。
- 顶部反查搜索：输入 "book equity" → concept → `source.column`。

### 5.2 `/ref/methodspec`

按 8 个字段组（Identity / Signal / Data / Timing / Universe / Portfolio / Results /
Notes）折叠展示，每个 field 显示：

- 类型、枚举可选值、Pydantic `description`；
- 是否是 `SourcedValue`（需要 evidence + `EvidenceStatus`）；
- **引擎是否真正支持** —— 菜单外的值会被 `registry.build_config` clamp 成菜单默认值。
  这一点必须在 UI 上标红，是本项目最容易踩的坑；
- 哪一步写它 / 哪一步读它。

`MethodSpecBoard` 里每个字段的 `?` 图标 deep-link 到这里的锚点，让编辑与文档联动。

## 6. 需要的后端改动

### 6.1 端点统一（前置条件）

当前三套风格并存，前端无法用一个组件跑 8 步：

| 步骤 | 现在 |
|---|---|
| 1, 2 | `/api/methodspecs/extract`、`/api/methodspecs/review-loop` … |
| 3, 4, 5 | `/api/sessions/{id}/steps/{n}/...` |
| 6, 7, 8 | `/api/{session_id}/steps/{n}/...`（缺 `sessions` 段） |

统一为：

```
POST /api/sessions/{id}/steps/{n}/run     body: {input_source, overrides}
GET  /api/sessions/{id}/steps/{n}          已有
```

旧端点在过渡期保留为薄适配层，前端切换完成后删除。

### 6.2 新增

- `GET /api/sessions/{id}/telemetry`（+ SSE 增量推送）
- `POST /api/sessions/{id}/fork?from_step=N`
- `llm.py` 每次调用写一条 `llm_call` 事件（现在 usage 拿到了却丢掉）
- `ToolRunner` 落地时同步写 `tool_call` 事件

## 7. 实施顺序

1. 后端端点统一 + telemetry 事件流（`llm_call` 先行，`tool_call` 随 `ToolRunner` 落地）。
2. 前端 Runs 区：`StepWorkbench` + Step Rail + input source + stale 传播。
3. Telemetry 区。
4. Reference 区（两个字典）+ `MethodSpecBoard` deep-link。
5. 删除 5 个旧页面及其路由/导航项。

## 8. 暂不做

- 页面内直接编辑 `sources.py` 注册新 DataSource（按 AGENTS.md 硬约束，必须人工注册）。
- Telemetry 的成本（$）估算 —— CLI provider 无法拿到真实计费口径，先只报 token。
