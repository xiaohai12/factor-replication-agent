---
type: reference
tags: [factor-replication, chen-zimmermann, open-source-asset-pricing, data]
updated: 2026-05-24
---

# Chen-Zimmermann Open Source Asset Pricing — 资源参考

**GitHub repo:** `OpenSourceAP/CrossSection`（GPL-2.0）
**网站:** https://www.openassetpricing.com
**论文:** Chen & Zimmermann (2021), "Open Source Cross-Sectional Asset Pricing"

本文件记录 C&Z 提供的代码、数据和 metadata 的完整结构，以及它们与 [[architecture]] 各模块的对应关系。C&Z 在因子可复现性诊断中的方法论角色、实验矩阵和原因分类见
[replication-diagnosis-design.md](replication-diagnosis-design.md)。

---

## 1. SignalDoc.csv — 结构化因子 metadata

每行一个 predictor（212 个），是冻结 paper-only MethodSpec 后使用的
post-hoc evaluation reference，绝不作为 Semantic Extractor 的输入。关键字段：

| 字段 | 含义 | 对应 MethodSpec 字段 |
|---|---|---|
| `Acronym` | signal 简称 (如 `BM`, `Accruals`) | `factor_id` |
| `Authors`, `Year`, `Journal` | 原始论文信息 | `paper_ref` |
| `LongDescription` | 因子名称 | `factor_name` |
| `Detailed Definition` | **完整信号构造逻辑**（含公式、Compustat 字段名、edge case 处理） | `signal.formula`, `data.required_fields[].field` |
| `Predictability in OP` | 原文预测能力：`1_clear`, `2_likely`, `3_not-pred` | pilot factor 筛选 |
| `Signal Rep Quality` | C&Z 复现质量：`1_good`, `2_fair`, `3_poor` | extraction 难度评估 |
| `Cat.Form` | signal 形式：continuous / discrete / binary | signal 处理方式 |
| `Cat.Data` | 数据来源类型：Accounting, Market, Analyst | 数据集 mapping |
| `Cat.Economic` | 经济分类：accruals, investment, profitability | topic 归类 |
| `SampleStartYear`, `SampleEndYear` | 原文样本期 | 回测区间参考 |
| `Sign` | long-short 方向 (+1 / -1) | `portfolio.long_leg` |
| `Return`, `T-Stat` | 原文报告的月均收益和 t-stat | benchmark 比对 |
| `Stock Weight` | EW / VW | `portfolio.weighting` |
| `LS Quantile` | 分位数 (如 0.1 = decile) | `portfolio.sort.ls_quantile` |
| `Quantile Filter` | breakpoint filter (如 NYSE) | `portfolio.breakpoints.source` |
| `Portfolio Period` | holding period（月） | derived from `signal.timing.rebalance_frequency` (annual=12/quarterly=3/monthly=1) via `MethodSpec.holding_period_months` -- no longer a separate stored field |
| `Start Month` | formation month (如 6 = June) | `signal.timing.formation_month` |
| `Filter` | 额外筛选条件 (如 `abs(prc)>5`) | universe filter |
| `Notes` | 复现说明、与原文差异 | `ambiguous_fields` 参考 |
| `Key Table in OP`, `Test in OP` | 原文对标表格和检验方法 | citation, 回测方法 |
| `GScholarCites202509` | Google Scholar 引用数 | 因子重要性排序 |

**项目用途：** SignalDoc.csv 不作为 Semantic Extractor 的输入（避免信息泄漏），而是作为**事后提取评估参考**。LLM 仅从论文原文提取 MethodSpec，冻结后再与 SignalDoc.csv 逐字段比对，量化 extraction accuracy。C&Z 是独立人工复现，不是唯一真值；差异分类（论文模糊 / LLM 误读 / C&Z 自行补充 / 合理分歧）本身是论文的分析素材。

---

## 2. Signal 构造代码 — `Signals/pyCode/`

```
Signals/pyCode/
├── master.py                  ← 主控脚本
├── config.py                  ← 全局配置 (MAX_ROWS_DL, TIMEOUT)
├── 01_DownloadData.py         ← 从 WRDS 下载原始数据
├── 02_CreatePredictors.py     ← 批量生成所有 predictor signals
├── 03_CreatePlacebos.py       ← 生成 placebo signals（对照组）
├── SignalMasterTable.py       ← 合并所有 signals 到统一 panel
├── DataDownloads/             ← WRDS 数据下载脚本
├── PrepScripts/               ← 数据预处理（含 time_avail_m 计算）
├── Predictors/                ← 195 个 predictor 文件，每因子一个 .py
│   ├── 00_map.yaml            ← predictor 索引
│   ├── Accruals.py
│   ├── BM.py
│   ├── Mom12m.py
│   └── ZZ1_*.py               ← 多因子合并文件
├── Placebos/                  ← placebo test
├── StataComparison/           ← Stata 对比验证
├── utils/                     ← 工具函数 (含 save_predictor)
├── prep1_run_on_wrds.sh       ← WRDS 服务器预处理
└── prep2_dl_from_wrds.sh      ← 从 WRDS 下载结果
```

### Predictor 文件的统一代码模式

每个 predictor .py 文件遵循统一模式：

```python
# 1. 加载预处理好的中间 parquet（不直接连 WRDS）
m_compustat = pd.read_parquet("../pyData/Intermediate/m_aCompustat.parquet")
signal_master = pd.read_parquet("../pyData/Intermediate/SignalMasterTable.parquet")

# 2. Merge：用 [permno, time_avail_m] 合并 Compustat 和 CRSP
df = pd.merge(m_compustat, signal_master, on=["permno", "time_avail_m"], how="right")

# 3. Lag：用 groupby + shift 构造滞后变量
df["me_lag6"] = df.groupby("permno")["mve_permco"].shift(6)

# 4. Signal：计算因子信号
df["BM"] = np.log(df["ceqt"] / df["me_lag6"])

# 5. 输出：[permno, yyyymm, SignalName] → CSV
output_df.to_csv("../pyData/Predictors/BM.csv")
```

### 关键设计：`time_avail_m`

C&Z 在 `PrepScripts/` 和 `SignalMasterTable.py` 中预先计算了每条记录的 point-in-time available date，已内含 accounting lag 处理。所有 predictor 文件按 `time_avail_m` merge，无需各自处理 lag。

这个设计直接影响了本项目 [[architecture#3.2 Data Layer / 数据层]] 的决策：**lag 在 Data Layer 统一处理，signal plugin 只负责 formula computation。**

**项目用途：**
- **Evaluation（可选后期）**：C&Z predictor 文件可作为 signal construction 的 reference implementation。对同一因子，用相同数据分别跑 LLM plugin 和 C&Z 原版，比较 signal 相关系数，量化 formula 层面的偏差。不在 Phase 1 强制执行，作为后期 evaluation 的一个维度。
- **Controlled Meta-Coder**：C&Z predictor 文件作为 few-shot 示例，指导 LLM 生成符合统一代码模式的 plugin（从中间 parquet 读取、用 `[permno, time_avail_m]` merge、只做 formula computation、输出 `[permno, yyyymm, SignalName]`），避免 LLM 自己拉数据或碰 portfolio construction 逻辑。
- **Data Layer**：借鉴 `time_avail_m` 机制——lag 在 Data Layer 统一处理，signal plugin 只负责 formula computation。ablation 实验改 lag 只需改 config，不需要重新生成 plugin，也消除了 LLM 各自实现 lag 导致的不一致和 look-ahead bias 风险。

---

## 3. Portfolio 构造代码 — `Portfolios/Code/`（R）

```
Portfolios/Code/
├── master.R                     ← 主控
├── 00_SettingsAndTools.R        ← 配置 + 工具函数
├── 01_PortfolioFunction.R       ← 核心 portfolio construction 逻辑
├── 10_DownloadCRSP.R            ← 下载 CRSP
├── 11_ProcessCRSP.R             ← 清洗 CRSP
├── 12_CreateCRSPPredictors.R    ← 从 CRSP 构造 Price/Size/STreversal
├── 20_PredictorPorts.R          ← 按 signal 排序构造组合
├── 30_PredictorAltPorts.R       ← 替代组合构造方法
├── 32_Predictor2x3Ports.R       ← 2×3 FF-style 组合
├── 40_PlaceboPorts.R            ← placebo 组合
├── 50_DailyPredictorPorts.R     ← 日频组合
└── *Exhibits.R                  ← 可视化 / 诊断
```

**项目用途：**
- **参考阅读**：`01_PortfolioFunction.R` 和 `30_PredictorAltPorts.R` 可用于理解 C&Z 的 portfolio construction 和 variant 选择。本项目的 controlled engine 独立实现，不直接移植 C&Z 代码；所有比较都通过显式 MethodSpec/config 与 bridge 设计控制。

---

## 4. 可下载数据集（网站）

| 数据集 | 粒度 | 频率 | 格式 | 项目用途 |
|---|---|---|---|---|
| Long-Short Returns (wide) | 212 predictors × month | 月度 | CSV | Portfolio comparison reference：与我们的 LS return 做 observational 对比 |
| Individual Predictor Portfolios | 每个 predictor 分组收益 | 月度 | CSV (文件夹) | 逐组检查 portfolio assignment 是否正确 |
| Firm-Level Characteristics | 209 个 signed firm-level signals | 月度 | CSV (1.6 GB) | **独立信号实现参考**：plugin 输出 vs C&Z 输出逐行比对 |
| Daily Portfolio Returns | portfolio-level | 日度 | CSV | 可选：日频 robustness check |

---

## 5. 编程接口

| 方式 | 说明 |
|---|---|
| Python: `openassetpricing` | pip install，直接拉 portfolio returns 和 signals |
| R: `OpenSourceAP.DownloadR` | R 包 |
| GitHub: `OpenSourceAP/CrossSection` | 全部代码 + SignalDoc.csv |

### 5.1 Python API 实测契约（2026-08-01）

以下结果使用 Python 3.11、`openassetpricing==0.0.2` 和 October 2025
release（`OpenAP(202510)`，data version 2.0.0）实测。该客户端的 portfolio
API 在 Python 3.14 曾触发 native segmentation fault，因此项目开发环境固定为
Python 3.11。

可选 release：`2022`、`2023`、`202408`、`202410`、`202510`。

`list_port()` 暴露八种 portfolio 产品：

| API 名称 | 含义 |
|---|---|
| `op` | C&Z 按 SignalDoc/original-paper profile 构造的 baseline |
| `deciles_ew` | EW deciles |
| `deciles_vw` | VW deciles |
| `quintiles_ew` | EW quintiles |
| `quintiles_vw` | VW quintiles |
| `nyse` | NYSE-only universe |
| `ex_price5` | 排除 price <= 5 的股票 |
| `ex_nyse_p20_me` | 排除 NYSE 市值后 20% 阈值以下股票 |

#### SignalDoc

```python
doc = openap.dl_signal_doc("pandas")
```

202510 返回 331 行、29 列：212 predictors、114 placebos、5 drops。
`Return`/`T-Stat` 是从 original papers 手工收集的 benchmark，不是当前 C&Z
data release 的回测汇总。AssetGrowth 的 SignalDoc 值为 1.73%/月、t=8.45，
而从当前 `op` 月序列按 1968-2003 重算得到约 1.495%/月、t=7.656。
因此研究报告必须分别保存 `paper_reported` 和 `cz_replicated`，不能把二者
当成同一个结果。

#### Firm-level signal

```python
raw = openap.dl_signal("pandas", ["AssetGrowth"], signed=False)
signed = openap.dl_signal("pandas", ["AssetGrowth"], signed=True)
```

输出契约：`[permno:int32, yyyymm:int32, <Acronym>:float64]`。AssetGrowth
实测 3,312,735 个唯一 firm-month、24,301 个 permno，无空值或重复键。
`signed=False` 返回 predictor code 的原始公式值；`signed=True` 再乘
SignalDoc 的 `Sign`。AssetGrowth 的 `Sign=-1`，实测 `signed == -raw`
逐行严格成立。

Signal 数据可延伸到 returns release 之后（AssetGrowth 到 202610，而 return
series 到 202412），因为 C&Z 会把已知 accounting observation 延展到未来可用
月份。这不是未来信息泄漏；与收益比较时仍必须 inner-join 到共同月份。

#### Portfolio returns

```python
port = openap.dl_port("op", "pandas", ["AssetGrowth"])
```

输出契约：
`[signalname, port, date, ret, signallag, Nlong, Nshort]`。AssetGrowth `op`
实测 9,570 行、1952-07 至 2024-12，包含 `01`-`10` 和 `LS`；每个
`(signalname, port, date)` 唯一。`ret` 单位是百分数（例如 `1.0` = 1%），
接入本项目 decimal-return contract 前必须除以 100。

`signallag` 是该 portfolio 的加权平均 signed signal，并已向后移一个月；
LS 行的 `signallag` 为 NA。普通 portfolio 行用 `Nlong` 记录持仓数、
`Nshort=0`；LS 行分别记录两端股票数。C&Z 先给 signal 乘 `Sign` 再排序，
所以 `LS = highest signed-signal portfolio - lowest signed-signal portfolio`。
AssetGrowth 实测严格等于 `port10 - port01`；因 `Sign=-1`，这对应原始
asset growth 的 low-minus-high。

C&Z R summary 使用普通 `mean / standard_error` t-stat；本项目使用最多 6
lags 的 Newey-West t-stat。对同一 AssetGrowth `op` 序列，1968-2003 的
simple t-stat 为 7.656，而本项目算法得到 NW(6) t-stat 6.677。因此对比时
应在同一月序列上同时重算两种 estimator，不能把 estimator difference
误归因于 signal 或 portfolio construction。

API 不提供 firm-level portfolio assignments、每只股票的实际 portfolio
weight、逐月 breakpoint 或底层 WRDS/CCM vintage。它能支持 signal values、
portfolio return series、组合股票数和 profile-level robustness 对比，但不能
仅凭下载结果定位某只股票为何被分到不同组合；这类诊断仍需我们的 engine
artifact 或执行 C&Z code 后增加中间输出。

### 5.2 与本项目对比时的标准化规则

1. **Paper benchmark：** 从 SignalDoc/MethodSpec 取 original-paper result，
	但先匹配 table、EW/VW、raw/alpha、方向、单位和样本期。
2. **Signal comparison：** 使用 `signed=False`，重命名因子列为 `signal`，
	通过 `[permno, yyyymm]` 与 agent 原始 formula output 对齐；不要提前乘
	`Sign`，避免与本项目 engine 的 long/short direction 重复反转。
3. **Return comparison：** 取 `port == "LS"`，将 `date` 转成 `yyyymm`，
	并做 `ret / 100` 后与本项目 decimal monthly return inner-join。
4. **C&Z baseline：** `op` 是 C&Z 对 original-paper profile 的可执行解释；
	它不是论文本身，也不一定与我们选中的 paper target variant 相同。
5. **Robustness：** 七种 alternative profiles 可直接作为 C&Z-side ablation，
	无需运行 C&Z R code。对相同 switch 比较 ours 与 C&Z 时，必须确保
	universe、quantiles、weighting 和 sample window 的定义一致。
6. **Statistic estimator：** 在共同月份上同时报告 simple t-stat 和统一的
	NW(6) t-stat；SignalDoc headline t-stat、C&Z R summary 和本项目 headline
	指标必须标注 estimator，不能直接混用。

---

## 6. C&Z 资源 → 架构模块映射总览

| C&Z 资源 | 架构模块 | 具体用法 |
|---|---|---|
| `SignalDoc.csv` | Extraction Evaluation | **事后参考**，不作为 Extractor 输入；冻结后比对 extraction accuracy |
| `SignalDoc.csv` 的 `Return`, `T-Stat` | Portfolio Comparison | 论文摘录数字，判断 observational replication gap 大小 |
| `SignalDoc.csv` 的 `Predictability`, `Rep Quality` | 实验设计 | 筛选 pilot factors（`1_clear` + `1_good`） |
| `Predictors/*.py` | Controlled Meta-Coder | few-shot examples；指导 plugin 输出格式和代码模式 |
| `Predictors/*.py` | Evaluation（后期可选） | signal-level reference；跑同一数据比较相关系数，量化 formula 偏差 |
| `SignalMasterTable.py` + `PrepScripts/` | Data Layer | `time_avail_m` point-in-time 机制参考 |
| `01_PortfolioFunction.R` | 参考阅读 | 了解 C&Z 的 portfolio construction 思路；不直接移植 |
| `30_PredictorAltPorts.R` | 参考阅读 | 了解 C&Z 的 variant 设计；不直接移植 |
| Firm-Level Characteristics CSV | Signal Evaluation | independent signal reference，逐行比较 plugin 输出 |
| Long-Short Returns CSV | Portfolio Comparison | portfolio-level observational reference，比较 LS return 和 t-stat |

---

## 7. 标准化 track 配置的出处（`HXZ_STANDARD_CONFIG`）

`standardized_hxz` track（单一权威来源 `data/reference/hxz_standard_config.yaml`，
经 [src/infra/reference/__init__.py](../src/infra/reference/__init__.py) 的
`load_hxz_standard_config`/`HXZ_STANDARD_CONFIG` 加载，
[src/steps/step6_dual_track_controller/__init__.py](../src/steps/step6_dual_track_controller/__init__.py)
下的 `HXZ_STANDARD_CONFIG` 只是 re-export，不再是定义处）把**每个因子强制
统一到一套 house standard**，好让跨因子结果可比、original-vs-standardized 的
gap 可归因到一组已知开关。这组值**不是从任何数据集自动推导的**，而是手工
约定；下表给出逐字段出处，使这个"standard"在论文里可被引用、可辩护。

| 字段 | 值 | 出处 |
|---|---|---|
| `breakpoint_source` | `nyse` | Hou, Xue & Zhang (2020, RFS) "Replicating Anomalies" —— NYSE breakpoints |
| `breakpoint_quantiles` | deciles | 同上，decile 排序 |
| `weighting_rule` | `vw` | 同上，value-weighted（NYSE bp + VW 是其抑制 microcap 影响的核心协议） |
| `rebalance_frequency` | `annual` | 论文对年度测量的会计变量用 6 月底分组、7 月至次年 6 月持有的年度调仓，而非月度重分组 |
| `holding_period_months` | 12 | 年度调仓需要持有整年（引擎按 `min(holding_period_months, rebalance_step)` 展开，`rebalance_step` 对 `annual` 是 12） |
| `accounting_lag_months` | 6 | **不是论文的字面数字**——论文对此场景（年度会计变量）从未给出具体月数，只说"6 月底分组、用上一日历年财年数据"，隐含与 Fama-French 相同的 ~6 个月滞后（12 月财年末 -> 6 月分组），因此恰好等于 `original_method` 自己的 `SENSIBLE_DEFAULTS`。论文里确实写了"我们对财年季末到后续收益之间施加 4 个月滞后"，但那是另一种场景（按季重分组的非盈利季度数据,对应 `rebalance_frequency: monthly`,不是这里的 `annual`）——把 4 用在这里是引错了段落 |
| `universe_filters` | `exchcd in (1,2,3)` + `siccd not_between (6000,6999)` + `ceq gt 0` | 论文明确写"NYSE, Amex, and NASDAQ stocks" + "We exclude financial firms" + "firms with negative book equity"（同一句一般样本准则）。**`6000-6999` 这个具体数字不是这句话给的**——通用样本准则那段只说"排除金融业"没给 SIC 数字；`6000-6999` 引自论文别处一段完全不同的段落（industry concentration 因子自己的构造细节），是本文献里"金融业"最标准的 SIC 定义，几乎可以肯定就是通用政策想要的数字，但严格说是推断，不是原句逐字给出。`ceq`（Compustat Annual 的普通股权益）不是 CRSP 原生列，经 `universe_filter_join_sources: {comp_funda: [ceq]}` 由生成脚本的 `join_universe_filter_sources()` point-in-time join 上去——复用 `compute_signal` 输入本就用的同一套 Compustat 拼接机制，未改动引擎。`ceq` 是单一原始列，不是论文别处用的完整 book equity 瀑布公式（优先 SEQ，否则 CEQ+PSTK，否则 AT-LT），是合理近似而非逐字复现；`ceq` 缺失的公司也会被这条过滤掉（视同无法验证）。论文明确**不**加价格筛选（"microcaps are included"），这里也确实没加 |

`missing_action` 字段 2026-08-16 已从此文件删除：`BacktestExecutor.
apply_missing_policy` 无条件丢弃缺失收益的行，从不读这个 config 值（没有
其他实现分支），写它纯属摆设，删掉比留着更诚实。


**与 reviewer `SENSIBLE_DEFAULTS` 的区别（两个不同概念，勿合并）：**

- `SENSIBLE_DEFAULTS`（[src/steps/step2_reviewer/__init__.py](../src/steps/step2_reviewer/__init__.py)）
  在论文**未写**某字段时，用该字段的**惯例默认值**补空，目的是让
  `original_method` 尽量贴近论文；key 是 dotted MethodSpec 路径，
  `accounting_lag_months` 默认走 Fama-French (1992) 的 6 个月惯例。
- `HXZ_STANDARD_CONFIG` 则**故意覆盖**论文方法，把所有因子压到一套统一标准；
  key 是 engine-config 名。

`accounting_lag_months` 这个字段这里恰好和 `SENSIBLE_DEFAULTS` 同值（6 个月）
不是巧合合并，而是两条独立推导路径碰到同一个数：HXZ 论文对年度会计变量的
处理本身就隐含 FF 式的 ~6 个月滞后（见上表脚注）。`rebalance_frequency`
仍然合理地不一致：`SENSIBLE_DEFAULTS` 默认 `annual`（未指定会计类因子的
通常默认）本身也和 `HXZ_STANDARD_CONFIG` 的 `annual` 现在一致——这不是
drift，是两条推导路径对同一个字段给出了相同答案的正常情况，不代表这两个
概念可以合并。

