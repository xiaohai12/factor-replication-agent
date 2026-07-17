# Streamlit Dashboard Redesign Plan

## TL;DR
重新设计 Streamlit，对齐 architecture.md 的完整 pipeline，支持 E2E 运行、每步单独 eval、trace/log 追踪。Dual-Track UI 先搭好但 disabled（_run_track 是 stub）。

## Ground Truth 数据源
**不使用 SignalDoc。** 使用 `data/test_method_specs/` 下的 26 个人工准备的 MethodSpec 作为 ground truth：

- `AB1998_AQ`, `AB1998_AR`, `AB1998_CAPX`, `AB1998_EQ`, `AB1998_ETR`, `AB1998_GM`, `AB1998_INV`, `AB1998_LF`, `AB1998_SA`
- `AnAngBaliCakici2013_DCVOL`, `DPVOL`, `DPVOL_minus_DCVOL`
- `AssetGrowth`
- `Ball2016_ACC`, `RMWCbOP`, `RMWOP`
- `BlitzHuijMartens_ResidualMomentum`
- `EisfeldtPapanikolaou2013_OMK`
- `FrazziniPedersen2014_BAB_US_Equity`
- `HirshleiferHsuLi2012_EMI1_PatentsRDC`, `EMI2_CitationsRD`
- `LohWarachka2011_StreakSURPQuintile`, `StreakSign`
- `Valta_StrategicDefault_ConvertibleDebt`, `SecuredDebt_LowZ`, `Shareholders_LowZ`

路径：`data/test_method_specs/*.methodspec.json`

---

## Proposed Navigation (7 pages)

```
Sidebar:
  1. 🔄 Pipeline — End to End
  2. 📄 Extractor
  3. 🔍 Review & Resolve
  4. 🧬 MetaCoder
  5. 📊 Backtest & Experiments
  6. 🔬 Attribution
  7. 📋 Trace & Logs
```

---

## Page 1: Pipeline — End to End

**目的：** 一键跑完全流程（PDF → Backtest），带进度条和 stage-by-stage 展开。

```
┌──────────────────────────────────────────────────────────────┐
│ Pipeline — End to End                                         │
├──────────────────────────────────────────────────────────────┤
│ Input: [Upload PDF] or [Select existing MethodSpec]          │
│ [▶ Run Full Pipeline]                                         │
│                                                               │
│ Progress: ████████░░░░ Stage 4/7 — MetaCoder                 │
│                                                               │
│ ┌─ Stage Outputs (expandable) ────────────────────────────┐  │
│ │ ✅ 1. Extract      → 42 fields, 3 ambiguous             │  │
│ │ ✅ 2. Review       → revision_required, 2 blocked        │  │
│ │ ✅ 3. Resolve      → codegen_ready: true                 │  │
│ │ 🔄 4. MetaCoder   → generating compute_signal()...      │  │
│ │ ⏳ 5. Sandbox      → pending                             │  │
│ │ ⏳ 6. Backtest     → pending                             │  │
│ │ ⏳ 7. Attribution  → pending                             │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                               │
│ Feedback Loop Status:                                         │
│   Backtrack: 0/3 | Repair attempts: 0/3                      │
│                                                               │
│ [Expand] Final Results: mean=0.45%, t=2.31                   │
└──────────────────────────────────────────────────────────────┘
```

**每步 Eval 面板：** 每个 stage 展开后显示该步骤的诊断：
- Extract: field_coverage, ambiguity_rate, extraction_time
- Review: disposition, blocked_fields list, codegen_ready
- MetaCoder: code_hash, hooks generated, token usage
- Sandbox: syntax/schema/leak/reproducibility pass/fail
- Backtest: signal coverage, portfolio balance, metrics
- Attribution: gap decomposition, anomaly flags

---

## Page 2: Extractor

**目的：** 从 PDF 提取 MethodSpec，并与 ground truth（test/ 下的人工 MethodSpec）逐字段对比。

**功能：**
- 上传 PDF → 提取 draft MethodSpec
- 提取完成后，自动匹配对应 ground truth（按 factor_id 在 `data/test_method_specs/` 中查找）
- 逐字段对比 extracted vs ground truth

**Eval 面板（核心）：**
- field_coverage: 提取了多少字段 / ground truth 总字段数
- field_accuracy: 逐字段匹配率（exact match + semantic match）
- ambiguity_rate: 标注为 unspecified/inferred 的字段占比
- 字段对比表格：

```
┌─────────────────────────────────────────────────────────────┐
│ Field           │ Extracted        │ Ground Truth   │ Match │
│ formula         │ (at-at_lag)/at   │ (at-at_lag)/at │ ✅    │
│ formation_month │ 6                │ 6              │ ✅    │
│ breakpoint_src  │ unspecified      │ full_sample    │ ❌    │
│ weighting       │ vw               │ vw             │ ✅    │
│ lag             │ inferred: 4      │ 6              │ ❌    │
└─────────────────────────────────────────────────────────────┘
```

- 批量模式：跑全部 test/ 下的 factor，汇总 accuracy

---

## Page 3: Review & Resolve

**目的：** 对 extracted/curated MethodSpec 做审查和 resolution，结果与 ground truth 对比验证 resolution 是否正确。

**输入：** 选择 `curated/` 或上传 draft MethodSpec

**3 个 Tab：**

### Tab: Review
- [▶ Run LLM Review]
- 显示 disposition, blocked_fields, codegen_ready
- Field-by-field review notes table

### Tab: Resolution
- 逐字段 resolution 交互：
  - `[field_path]` current: "unspecified"
  - Candidate: "6" (from LLM suggestion)
  - [Accept] [Override: ___] [Skip]
- [Apply All Resolutions]

### Tab: Eval
**与 ground truth 对比 resolution 质量：**
- 从 `data/test_method_specs/` 加载同名 ground truth
- Resolution accuracy: 对于每个 resolved 字段，新值是否 == ground truth 值？
- 指标：
  - resolution_accuracy: 正确 resolve 的字段 / 总 resolve 字段
  - high_impact_accuracy: 高影响字段的 resolution 正确率
  - over_resolution_rate: resolve 了但 ground truth 说不需要改的
  - under_resolution_rate: 应该 resolve 但没有的

```
┌──────────────────────────────────────────────────────────────┐
│ Resolution Eval vs Ground Truth                               │
├──────────────────────────────────────────────────────────────┤
│ Factor: cooper_gulen_schill_2008_asset_growth                │
│                                                               │
│ Resolution accuracy:  6/8 (75%)                              │
│ High-impact accuracy: 3/4 (75%)                              │
│                                                               │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Field            │ Resolved To │ Ground Truth │ Correct  │ │
│ │ breakpoint_src   │ full_sample │ full_sample  │ ✅       │ │
│ │ weighting        │ vw          │ vw           │ ✅       │ │
│ │ accounting_lag   │ 4           │ 6            │ ❌       │ │
│ │ missing_action   │ drop        │ drop         │ ✅       │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## Page 4: MetaCoder (现有，保留)

保持现有功能（steps 1-8: load spec → hook detect → generate → sandbox → script gen）。

**新增 Eval 面板：**
- Code quality: AST node count, function count, line count
- Hook coverage: which hooks generated vs which needed (_detect_hooks 预测)
- 与 ground truth plugin 对比（如 `data/osap/Predictors/` 有对应 reference code）：
  - Formula equivalence check (语义级)
  - Output shape match (same columns, compatible signal)

---

## Page 5: Backtest & Experiments

**3 个 Tab：**

### Tab: Single Run (现有 Backtest 页面)
Select plugin + spec → run → metrics + charts

### Tab: Dual-Track (暂 disabled)
Run same plugin with:
- original_method config
- standardized_hxz config
Side-by-side: metrics comparison table + overlay chart

### Tab: Ablation
Pick switches to vary:
- ☑ breakpoint_source (nyse ↔ full_sample)
- ☑ weighting (vw ↔ ew)
- ☐ lag (4m ↔ 6m)
- ☐ universe (with/without financials)
[Run Ablation Set]
Results table: switch × metric matrix

**Eval（all tabs）：**
- Signal coverage: % of CRSP universe with valid signal
- Portfolio balance: stocks per decile distribution
- Microcap share per portfolio
- Time-series stability: rolling 5yr t-stat

---

## Page 6: Attribution

```
┌──────────────────────────────────────────────────────────────┐
│ Attribution — Implementation Gap Decomposition                │
├──────────────────────────────────────────────────────────────┤
│ Select factor: [cooper_gulen_schill_2008_asset_growth ▼]     │
│ Load runs from evidence store                                 │
│                                                               │
│ [Run Ablation Attribution]                                    │
│                                                               │
│ Summary:                                                      │
│   original t-stat: 3.12  |  standardized t-stat: 2.45        │
│   Total gap: 0.67  |  Explained: 89%                         │
│                                                               │
│ Contribution Breakdown:                                       │
│   ┌─────────────────────────────┐                            │
│   │ ██████████ Universe   35%   │                            │
│   │ ███████    Breakpoint 25%   │                            │
│   │ █████      Weighting  18%   │                            │
│   │ ███        Lag        11%   │                            │
│   │ █          Missing     3%   │                            │
│   │            Residual    8%   │                            │
│   └─────────────────────────────┘                            │
│                                                               │
│ ⚠ Anomaly: None detected                                     │
│   (triggers re-review if t-stat flips or gap > 50%)          │
│                                                               │
│ [Download Attribution Report]                                 │
│                                                               │
│ ── Eval ──                                                   │
│ Cross-factor attribution consistency check                    │
│ Which switches matter most across all evaluated factors       │
└──────────────────────────────────────────────────────────────┘
```

---

## Page 7: Trace & Logs

**3 个 Tab：**

### Tab: Run Registry
Filter: [Factor ▼] [Status ▼] [Date range]
```
│ run_id  │ factor_id │ track    │ status  │ t-stat │
│ abc123  │ asset_gro │ original │ success │ 3.12   │
│ def456  │ asset_gro │ hxz_std  │ success │ 2.45   │
│ ghi789  │ beta      │ original │ failed  │ —      │
```

### Tab: Evidence Browser
Tree: evidence/{factor_id}/{run_id}/
- metadata.json
- return_series.csv
- signal.csv
- config.json
[View] [Download] for each artifact

### Tab: Pipeline Trace
Timeline per factor:
```
09:01 ─ Extract started
09:03 ─ Extract done (42 fields)
09:03 ─ Review started
09:05 ─ Review: revision_required
09:05 ─ Resolution applied (4 fields)
09:06 ─ MetaCoder: generating...
09:08 ─ Sandbox: FAILED (future leak)
09:08 ─ Repair attempt 1/3
09:09 ─ Sandbox: PASSED
09:10 ─ Backtest: running
09:15 ─ Done. t-stat=3.12
```

---

## Per-Step Eval 指标汇总

| Step | Eval 指标 | Ground Truth 来源 |
|---|---|---|
| Extract | field_coverage, field_accuracy, ambiguity_rate | `data/test_method_specs/*.methodspec.json` |
| Review | disposition, blocked_fields, requires_human | 审查 ground truth spec 时不应该 block 正确字段 |
| Resolve | resolution_accuracy, high_impact_accuracy | ground truth 的字段值 |
| MetaCoder | syntax pass, hook coverage, token efficiency | OSAP reference (optional) |
| Sandbox | pass rate (4 checks), repair success rate | binary pass/fail |
| Backtest | signal coverage, portfolio balance, metric stability | 已知因子的 published t-stat (from paper) |
| Attribution | explained_fraction, residual, anomaly rate | — |

---

## 实现依赖

| 依赖 | 状态 | 影响 |
|---|---|---|
| `DualTrackController._run_track()` | Stub | Dual-Track tab disabled |
| `data/local/msf.parquet` | 未有 | E2E backtest 步骤跳过 |
| `src/trace.py` (新文件, ~30行) | 待创建 | Pipeline Trace tab 需要 |

## 文件变更

- `app.py` — 重写导航 + 新增 4 个 page (E2E, Review&Resolve, Attribution, Trace)
- `src/trace.py` — 新建 PipelineTracer (~30行)
- `src/pipeline.py` — 注入可选 tracer 参数
