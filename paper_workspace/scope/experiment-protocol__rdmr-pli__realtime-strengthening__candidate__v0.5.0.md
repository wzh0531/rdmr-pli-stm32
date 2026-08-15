---
artifact_id: experiment-protocol__rdmr-pli__realtime-strengthening__candidate__v0.5.0
project_id: ft-vss-nlms-stm32-ei
artifact_kind: scope_snapshot
work_unit: scope-question
status: candidate
language: zh
baseline_artifact: paper_workspace/scope/experiment-protocol__rdmr-pli__reviewer-revision__candidate__v0.4.0.md
source_registry: paper_workspace/.sci-review-system/state/project_state.json
run_id: run-20260726-001
gate_status: runtime-managed
next_intents:
  - quantitative-audit
  - science-audit
  - reviewer-audit
---

# RDMR-PLI 实时化与证据补强实验协议 v0.5.0

## 1. 目的与授权边界

本协议回答三个已识别的模拟审稿风险：三状态 A3 相对双状态 B4 的增益是否足以支撑额外复杂度；单一 MIT-BIH record 100 是否造成外部验证与统计单位不足；201 点同步搜索是否能够改造成满足 STM32F103C8T6 50 ms 块预算的实现。

作者于 2026-08-13 授权开始本地优化、主机实验和实物测试准备，并约定由作者执行烧录和串口采集、由项目工作区完成固件生成、日志校验、统计和论文证据更新。

本协议不授权撤稿、替换 Editorial Manager 文件、上传 v1.4.1 或后续候选稿，也不改变正式投稿版本 v1.3.5。未收到实物串口原始日志前，STM32 实时性保持 `NOT_CHECKED`。

## 2. 版本与不可覆盖基线

- 原 201 点搜索定义为 `search_mode=0`，作为冻结基线保留。
- 新层级搜索定义为 `search_mode=1`，固件修订号从 Rev16 开始。
- 已有 Phase 4、Phase 5 和 Phase 7 输出只读；新输出进入 `outputs/phase8_realtime_strengthening/`。
- 新论文只能另建 v1.5.x 或更高本地候选版本，不覆盖 v1.3.5/v1.4.1。
- B4 或层级搜索参数一旦进入确认集运行，不得根据确认集结果回调；若修改，必须新建协议版本和未观察种子。

## 3. O1：层级频率搜索实现

搜索范围仍为 45.00--55.00 Hz，最终分辨率仍为 0.05 Hz，窗口仍为 400 点；仅改变候选频点的评估顺序和数量。

1. 粗搜索：索引 0, 10, ..., 200，即 0.50 Hz 步长，共 21 点。
2. 细搜索：以粗搜索峰值为中心评估连续 11 个 0.05 Hz 网格点；靠近上下边界时向区间内部平移，始终不越过索引 0--200。
3. 最坏评估数：21 + 11 = 32；允许粗峰值被重复评估，以保持实现简单和确定的上界。
4. 相同功率时继续使用严格 `>` 更新，从而保持确定的低索引优先规则。
5. 代码必须通过编译期开关同时生成 201 点基线和 32 点候选，不允许删除基线。

## 4. O2：主机桥接验证

### 4.1 冒烟与回归阶段

- 输入：从冻结 Phase 4 矩阵选择 F0、F2、F3、F4、F5，覆盖幅值 0.20/0.50/1.00、无噪声/20 dB/10 dB和至少 3 个种子。
- 算法：A2、A3、B4；每个输入逐点相同。
- 同时运行 `search_mode=0` 与 `search_mode=1`。
- 检查：有限值、确定性、搜索调用数、网格评估数、输出 SNR、频率 MAE、RMSE和最终调用次数。
- 基线回归：`search_mode=0` 必须与冻结输出逐数组一致，否则停止后续实验。

### 4.2 层级搜索暂定科学门槛

- 每次完整搜索的网格评估数不得超过 32；总体评估量相对 201 点搜索至少降低 80%。
- 相对同调度器的 201 点版本，固定矩阵平均 output-SNR 差不得低于 -0.05 dB。
- 54 个条件均值中的最差差值不得低于 -0.25 dB。
- 平均频率 MAE 增量不得超过 0.05 Hz。
- 任何非有限值、数组长度不一致或输入不配对均为 FAIL。

这些门槛是工程保持性门槛，不是临床阈值，也不能代替 STM32 周期证据。

## 5. O3：A3 与 B4 公平比较

### 5.1 开发调参

- 仅使用既有开发集或明确标记为开发用的新种子。
- A3 参数保持冻结；B4 只在高/低阈值、低状态间隔的预声明有限网格中选择。
- 选择规则：先满足相对 A2 的平均 SNR 保持门槛，再最小化搜索评估总数；不得按单一最好种子选择。

### 5.2 新种子确认集

- `54 conditions × 30 new seeds = 1620` 个配对输入。
- 算法：层级搜索 A2、A3、B4，共 4860 次算法执行。
- 主统计：A3-B4 的 output SNR、频率 MAE和评估总数；以 seed 为聚类单位重采样，保留每个 seed 的全部 54 个条件。
- 尾部统计：最小值、P5、低于 -0.25/-0.5 dB 比例、最差条件均值、F1/F2 跳变恢复时间和状态切换次数。
- 若 A3 未在尾部风险、恢复时间或同预算性能上显示可复核优势，论文不得宣称 MID 状态具有必要性；应将贡献改写为残差驱动调度族并报告 B4 为低复杂度变体。

## 6. O4：多记录 ECG

- 数据源：MIT-BIH Arrhythmia Database v1.0.0。
- 纳入：全部 48 条记录；若两条记录属于同一受试者，统计时按受试者聚类。记录排除只能依据预声明的文件损坏、长度不足或导联规则不满足，不能依据结果。
- 每记录取 3 个等间隔、非重叠 8 s 片段；片段起点在读取波形指标前由脚本确定。
- 导联规则：优先 MLII；无 MLII 时采用头文件中第一条可用 ECG 导联并记录名称，另做 MLII-only 敏感性分析。
- 注入矩阵：F0--F5 × PLI 0.20/0.50 × noise none/20 dB，共 24 条件。
- 算法：层级搜索 A2、A3、B4；共 `48 × 3 × 24 = 3456` 个配对输入和 10368 次算法执行。
- 主要统计单位为记录/受试者。先在记录内汇总片段和注入条件，再做记录级或受试者级 bootstrap；不得把 3456 个条件写成独立受试样本。
- record 100 旧结果保留为先导案例，不与新确认性区间混算。

## 7. O5：STM32 Rev16 验证

### 7.1 烧录矩阵

- 核心矩阵：18 个预声明工况 × A2/A3/B4 × 3 次独立冷启动，共 162 次。
- 持续运行矩阵：6 个最坏或边界工况 × A2/A3/B4 × 3 次冷启动，共 54 次。
- 固件必须输出 firmware revision、search mode、最大候选点数、搜索次数、网格评估总数、每块总周期、样本级最大周期和截止时间违约数。

### 7.2 时间门槛

- CPU：72 MHz；采样率：1 kHz；块长：50 ms。
- 硬上限：每块总周期 `< 3,600,000`。
- 目标门槛：每块总周期 `<= 2,880,000`，提供至少 20% 块预算裕量。
- 1 ms 样本预算继续报告，但同步块搜索的部署判断以 50 ms 块总周期为主；不得把平均周期或 P95 代替最大块周期。
- 若内部信号版本通过，只能声称在芯计算核实测通过；ADC/DMA、定时器和持续零丢块另设独立门槛。

### 7.3 作者与工作区分工

- 工作区：生成 HEX/AXF/MAP、SHA-256 manifest、烧录顺序、串口文件命名规则和日志验证脚本。
- 作者：按清单烧录，每次断电冷启动，完整保存从 BOOT/CONFIG 到 DONE 的原始串口文本，不手工修改日志。
- 工作区收到日志后：验证160行完整性、配置哈希、数值标志、周期、搜索评估数、配对一致性和重复运行离散性。

## 8. 输出与判定

计划输出：

- `outputs/phase8_realtime_strengthening/host_bridge/`
- `outputs/phase8_realtime_strengthening/confirmatory_synthetic/`
- `outputs/phase8_realtime_strengthening/mitdb_multirecord/`
- `outputs/phase8_realtime_strengthening/physical_rev16/`
- `simulation/stm32/Phase8实物F103层级搜索运行指南__Rev16__v1.0.0.md`

任何未执行项必须标为 `NOT_CHECKED`。只有主机科学门槛、机械复核和实物日志门槛分别通过后，才能在后续本地稿件中写入相应结论。正式投稿状态继续保持，不因本协议自动触发撤稿、替换或上传。
