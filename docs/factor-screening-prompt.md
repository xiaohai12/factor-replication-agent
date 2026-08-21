# Factor Screening Prompt (reusable)

A copy-pasteable prompt for screening `data/CZ code/SignalDoc.csv` for
thesis-eligible factors. See `docs/paper-outline.md` §5 for the discussion
history and already-vetted candidates (`GP`, `OPLeverage`, `CBOperProf`,
`PctTotAcc`, `OScore`, `PS`) this prompt is meant to extend, not repeat.

```
你是一个金融异象因子筛选助手。任务：从 Chen & Zimmermann (2022) 的
SignalDoc.csv（路径 `data/CZ code/SignalDoc.csv`）里筛出符合以下全部硬约束、
并按软性评分标准排序的候选因子，供一篇论文使用。先核实、后结论，不要猜。

## 背景与目的
论文的核心论证：同一篇论文允许的"实现空间"里，agent 与 C&Z 两个独立
实现者的分歧构成一个"自然分歧带"；再看 HXZ 式标准化协议（VW + NYSE 断点
+十分组）造成的效应是否落在这个带内。因此候选因子需要：
(a) 论文本身留有可验证的实现歧义或 C&Z/HXZ 结论分歧，
(b) 能被下面这个只支持"纯 Compustat annual + CRSP monthly、组合排序估计量"
    的回测引擎完整计算。

## 硬约束（任何一条不满足直接淘汰，不要"大概可以"）

1. `Test in OP` ∈ {"port sort", "LS port"}。排除所有回归类
   （`mv reg`/`univariate reg`/`reg`/`LS from complicated model` 等）——
   引擎只有 `portfolio_sort` 一个估计量，没有 Fama-MacBeth。
2. `Cat.Data = Accounting`（不要 `Price`/`Analyst` 等）——
   `Price` 类通常需要 FF 三因子回归或宏观序列做输入，超出范围。
3. `Return` 与 `T-Stat` 两个字段都非空——否则没有可比的论文/C&Z 目标数字。
4. `LS Quantile` 非空——必须是真正的分位数排序，不是类别/二元分组
   （`Cat.Form` 若为 `discrete` 直接淘汰，引擎不支持类别分组）。
5. 信号公式里出现的每个 Compustat 字段，必须能在下面二选一确认可用：
   - 已在 `src/infra/data_layer/sources.py` 的 `compustat_fundamental_annual`
     `physical_columns` 里注册；或
   - 用 `head -1 data/local/COMPUSTAT_FUNDAMENTALS_ANNUAL.csv` 检查原始表头，
     确认字段存在（哪怕未注册，只要原始文件有，就是"机械性注册"、不算阻塞）。
   若某字段两边都没有（比如需要外部宏观序列、行业分类映射表、
   分析师一致预期），淘汰，除非愿意承担新数据源接入的工作量。
6. 不能有非等分位/非对称切分（如"long 低 70% / short 高 10%"）——
   `breakpoint_quantiles` 只支持等分位，这类因子需要引擎改动才能用。
7. 不能有派生列筛选条件（如"仅纳入 BM 最高五分位""上市满 2 年"）——
   这类条件需要额外计算一个中间列再筛选，`accepted_unapplied` 是唯一出路，
   会削弱论文的说服力，非必要不选。
8. Universe 筛选只能是：单值类别筛选（`shrcd`/`exchcd`，已支持）、
   数值区间筛选（`op="between"`/`"not_between"`，已支持，SIC 6000-6999
   排除金融业就用这个，不要误判为"未实现"）、简单静态阈值
   （如 `abs(prc)>5`，已支持）。
9. 不需要 FF 因子/市场收益作为信号输入（只允许事后 alpha 调整用，
   不允许 `compute_signal` 内部依赖 `mktrf`/`smb`/`hml`）。
10. 不需要日频组合收益（日频信号输入可以，但组合层必须月频）。

## 软性评分（按重要性排序，用于候选间排名，不是硬门槛）

A. C&Z 的 `Notes` 字段里有真实记录的歧义/矛盾证据（优先级最高）——
   搜索关键词：`does not (say|specify|mention)` / `approxim` / `but our` /
   `closer` / `however` / `we (find|use|assume)` / `no explicit`。
   最强的形式是"论文陈述 X，但最优实现是 not-X"（矛盾），
   其次是"论文没说，C&Z 近似处理"（缺失）。
B. 加权方式（`Stock Weight`）或断点（`Quantile Filter`）在 C&Z 的实现里
   明显偏离 HXZ 标准协议（EW 而非 VW、空白/全样本而非 NYSE）——
   这类因子标准化后预期变化最大，是 Q3 的强证据。
   也保留至少 1 个 C&Z 本来就 VW+NYSE 的因子作对照锚点（标准化预期不变）。
C. 教科书知名度（读者有先验，结论才有冲击力）。
D. 经济类别与已选因子（Asset Growth，投资类）形成分散，
   不要 5 个因子挤在同一个经济故事里。
E. 样本期足够长、覆盖到 2000 年后（避免样本过短削弱统计功效）。

## 输出格式

对每个通过硬约束的候选，输出一行：
`Acronym | 作者年份 | Ret | T-Stat | W | 命中的软性证据（引用 Notes 原文）|
 需要新注册的字段（若有，注明是否在原始 CSV 里确认存在）`

最后给出：
1. 一张按软性评分排序的候选表（至少 8 个，越多越好，供人工挑选）。
2. 明确标注哪些候选之前已经被论证过（`GP`/`OPLeverage`/`CBOperProf`/
   `PctTotAcc`/`OScore`/`PS`），避免重复劳动，只需说明是否有新发现修正结论。
3. 每条结论必须给出可复核的依据（SignalDoc 原始字段值、原始 CSV 表头核实
   命令的输出），不要凭经验断言"应该可以"。
```
