---
type: reference
tags: [factor-replication, chen-zimmermann, open-source-asset-pricing, data]
updated: 2026-05-24
---

# Chen-Zimmermann Open Source Asset Pricing — 资源参考

**GitHub repo:** `OpenSourceAP/CrossSection`（GPL-2.0）
**网站:** https://www.openassetpricing.com
**论文:** Chen & Zimmermann (2021), "Open Source Cross-Sectional Asset Pricing"

本文件记录 C&Z 提供的代码、数据和 metadata 的完整结构，以及它们与 [[architecture]] 各模块的对应关系。

---

## 1. SignalDoc.csv — 结构化因子 metadata

每行一个 predictor（212 个），是 Semantic Extractor 的核心 structured input。关键字段：

| 字段 | 含义 | 对应 MethodSpec 字段 |
|---|---|---|
| `Acronym` | signal 简称 (如 `BM`, `Accruals`) | `factor_id` |
| `Authors`, `Year`, `Journal` | 原始论文信息 | `paper_ref` |
| `LongDescription` | 因子名称 | `factor_name` |
| `Detailed Definition` | **完整信号构造逻辑**（含公式、Compustat 字段名、edge case 处理） | `signal.formula`, `signal.required_fields` |
| `Predictability in OP` | 原文预测能力：`1_clear`, `2_likely`, `3_not-pred` | pilot factor 筛选 |
| `Signal Rep Quality` | C&Z 复现质量：`1_good`, `2_fair`, `3_poor` | extraction 难度评估 |
| `Cat.Form` | signal 形式：continuous / discrete / binary | signal 处理方式 |
| `Cat.Data` | 数据来源类型：Accounting, Market, Analyst | 数据集 mapping |
| `Cat.Economic` | 经济分类：accruals, investment, profitability | topic 归类 |
| `SampleStartYear`, `SampleEndYear` | 原文样本期 | 回测区间参考 |
| `Sign` | long-short 方向 (+1 / -1) | `portfolio.long_leg` |
| `Return`, `T-Stat` | 原文报告的月均收益和 t-stat | benchmark 比对 |
| `Stock Weight` | EW / VW | `portfolio.weighting` |
| `LS Quantile` | 分位数 (如 0.1 = decile) | `portfolio.breakpoints.quantiles` |
| `Quantile Filter` | breakpoint filter (如 NYSE) | `portfolio.breakpoints.source` |
| `Portfolio Period` | holding period（月） | `signal.timing.holding_period` |
| `Start Month` | formation month (如 6 = June) | `signal.timing.formation_month` |
| `Filter` | 额外筛选条件 (如 `abs(prc)>5`) | universe filter |
| `Notes` | 复现说明、与原文差异 | `ambiguous_fields` 参考 |
| `Key Table in OP`, `Test in OP` | 原文对标表格和检验方法 | citation, 回测方法 |
| `GScholarCites202509` | Google Scholar 引用数 | 因子重要性排序 |

**项目用途：** SignalDoc.csv 不作为 Semantic Extractor 的输入（避免信息泄漏），而是作为 **extraction evaluation ground truth**。LLM 仅从论文原文提取 MethodSpec，提取完成后与 SignalDoc.csv 逐字段比对，量化 extraction accuracy。差异分类（论文模糊 / LLM 误读 / C&Z 自行补充 / 合理分歧）本身是论文的分析素材。

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
- **参考阅读**：`01_PortfolioFunction.R` 和 `30_PredictorAltPorts.R` 可作为理解 C&Z 实现思路的参考，了解他们的 portfolio construction 和 variant 设计选择。本项目的 Lifecycle Engine 和 Dual-Track Controller 独立实现，不直接移植 C&Z 代码——其 R 代码未必符合本项目的工程规范，且实现细节需要根据 MethodSpec 和 ablation 设计重新控制。

---

## 4. 可下载数据集（网站）

| 数据集 | 粒度 | 频率 | 格式 | 项目用途 |
|---|---|---|---|---|
| Long-Short Returns (wide) | 212 predictors × month | 月度 | CSV | Attribution Layer benchmark：比对 original_method 的 LS return |
| Individual Predictor Portfolios | 每个 predictor 分组收益 | 月度 | CSV (文件夹) | 逐组检查 portfolio assignment 是否正确 |
| Firm-Level Characteristics | 209 个 signed firm-level signals | 月度 | CSV (1.6 GB) | **Signal validation ground truth**：plugin 输出 vs C&Z 输出逐行比对 |
| Daily Portfolio Returns | portfolio-level | 日度 | CSV | 可选：日频 robustness check |

---

## 5. 编程接口

| 方式 | 说明 |
|---|---|
| Python: `openassetpricing` | pip install，直接拉 portfolio returns 和 signals |
| R: `OpenSourceAP.DownloadR` | R 包 |
| GitHub: `OpenSourceAP/CrossSection` | 全部代码 + SignalDoc.csv |

---

## 6. C&Z 资源 → 架构模块映射总览

| C&Z 资源 | 架构模块 | 具体用法 |
|---|---|---|
| `SignalDoc.csv` | Extraction Evaluation | **ground truth**，不作为 Extractor 输入；事后比对量化 extraction accuracy |
| `SignalDoc.csv` 的 `Return`, `T-Stat` | Attribution Layer | benchmark 数字，判断 replication gap 大小 |
| `SignalDoc.csv` 的 `Predictability`, `Rep Quality` | 实验设计 | 筛选 pilot factors（`1_clear` + `1_good`） |
| `Predictors/*.py` | Controlled Meta-Coder | few-shot examples；指导 plugin 输出格式和代码模式 |
| `Predictors/*.py` | Evaluation（后期可选） | signal-level reference；跑同一数据比较相关系数，量化 formula 偏差 |
| `SignalMasterTable.py` + `PrepScripts/` | Data Layer | `time_avail_m` point-in-time 机制参考 |
| `01_PortfolioFunction.R` | 参考阅读 | 了解 C&Z 的 portfolio construction 思路；不直接移植 |
| `30_PredictorAltPorts.R` | 参考阅读 | 了解 C&Z 的 variant 设计；不直接移植 |
| Firm-Level Characteristics CSV | Adversarial Sandbox | signal-level ground truth，逐行验证 plugin 输出 |
| Long-Short Returns CSV | Attribution Layer | portfolio-level benchmark，验证 LS return 和 t-stat |
