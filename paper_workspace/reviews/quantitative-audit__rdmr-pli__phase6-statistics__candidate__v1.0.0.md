---
artifact_id: quantitative-audit__rdmr-pli__phase6-statistics__candidate__v1.0.0
project_id: ft-vss-nlms-stm32-ei
artifact_kind: quantitative-audit
work_unit: quantitative-audit
status: candidate
language: zh
baseline_artifact: paper_workspace/scope/experiment-protocol__rdmr-pli__cssp-journal__candidate__v0.3.0.md
source_registry: paper_workspace/.sci-review-system/state/project_state.json
run_id: run-20260726-001
gate_status: runtime-blocked-upstream-claim-ledger
next_intents:
  - visual-reference-qa
  - argument-architecture
---

# Phase 6 冻结矩阵统计审计

## 目的与范围

本审计只以7920次冻结主机矩阵作为随机总体统计来源，其中主矩阵6480次、近邻保护矩阵1440次。Proteus的12个确定性场景和实物板36次冷启动只用于实现一致性与资源验证，不作为随机统计样本。

## 方法

- 主比较：相同输入、条件和种子下的A3与A2，共1620对。
- 差值方向统一为`A3 − A2`；输出SNR越高越好，RMSE、频率误差和tracker calls越低越好。
- 置信区间：固定种子`20260803`、20000次百分位配对bootstrap。
- 效应量：配对Cohen's dz。
- 六条频率轨迹的SNR次要比较采用Holm校正；非劣界为−0.5 dB。

## 主结果

- A3−A2输出SNR均值：-0.140704 dB。
- 95%配对bootstrap CI：[-0.154105, -0.127889] dB。
- 配对Cohen's dz：-0.5275。
- 非劣门槛：CI下界大于−0.5 dB，结果为`PASS`。
- tracker calls中位减少率：81.250%；均值95% CI为[75.500%, 77.216%]。
- 实物五组配对的平均周期减少范围：75.880%–86.710%。
- 但实物1 kHz最坏时限门禁为`FAIL`。

## 四算法总体描述

| 算法 | n | 输出SNR mean±SD (dB) | RMSE mean | 频率MAE mean (Hz) | tracker calls mean |
|---|---:|---:|---:|---:|---:|
| A0_fixed_notch | 1620 | -0.712 ± 7.881 | 0.22649 | 0.9164 | 0.00 |
| A1_fixed_reference_nlms | 1620 | 8.856 ± 6.621 | 0.07146 | 0.9164 | 0.00 |
| A2_every_block_tracking | 1620 | 12.810 ± 4.894 | 0.03868 | 0.1148 | 160.00 |
| A3_residual_driven_multirate | 1620 | 12.669 ± 4.782 | 0.03907 | 0.1458 | 37.82 |

## 分轨迹A3−A2输出SNR

| 轨迹 | n | 均值(dB) | 95% CI(dB) | dz | Holm p | 非劣 |
|---|---:|---:|---:|---:|---:|---:|
| F0 | 270 | -0.0094 | [-0.0137, -0.0057] | -0.279 | 3.177e-06 | PASS |
| F1 | 270 | -0.0005 | [-0.0008, -0.0003] | -0.273 | 0.159 | PASS |
| F2 | 270 | -0.0010 | [-0.0013, -0.0007] | -0.404 | 1.932e-07 | PASS |
| F3 | 270 | -0.3444 | [-0.3760, -0.3137] | -1.323 | 2.956e-45 | PASS |
| F4 | 270 | -0.3804 | [-0.4339, -0.3288] | -0.863 | 2.956e-45 | PASS |
| F5 | 270 | -0.1084 | [-0.1194, -0.0980] | -1.204 | 2.956e-45 | PASS |

Holm检验回答“差值是否偏离0”，非劣门槛回答“损失是否超过预先允许的−0.5 dB”；二者不能互相替代。统计显著也不等于工程上优越。

## 可比性与泄漏检查

- A0–A3使用相同冻结C执行路径、输入、场景和种子；逐配对输入SHA-256一致。
- 冻结测试种子为1000–1029，首次授权使用已登记；读取测试结果后参数改动为`false`。
- 主机配对矩阵可用于统计推断；Proteus和实物重复只用于确定性实现验证。

## 未冻结的次要指标

- settling time：`NOT_CHECKED`。协议未冻结容差带、连续驻留时长和重复越界处理。
- 50 Hz邻域残余谱能量：`NOT_CHECKED`。协议未冻结频带、窗函数、归一化和聚合规则。

在补充并冻结定义前，不得从现有波形临时挑选算法计算这两个指标。

## Gate

| Gate | 结果 |
|---|---|
| `phase4_completion_and_validation` | PASS |
| `main_6480_and_near_1440_rows` | PASS |
| `four_algorithms_per_paired_input` | PASS |
| `paired_input_sha256_identity` | PASS |
| `a3_vs_a2_1620_pairs` | PASS |
| `all_main_numeric_metrics_finite` | PASS |
| `ablation_360_rows_finite` | PASS |
| `overall_snr_noninferiority_ci_lower_gt_minus_0p5_db` | PASS |
| `all_six_trajectory_snr_noninferiority` | PASS |
| `holm_adjustment_six_trajectory_family` | PASS |
| `effect_sizes_reported` | PASS |
| `settling_time_metric` | NOT_CHECKED |
| `residual_50hz_band_energy_metric` | NOT_CHECKED |
| `phase5_hard_realtime_1khz` | FAIL |

## 允许与禁止表述

- 允许：A3在冻结配对矩阵内满足−0.5 dB SNR非劣门槛，同时大幅减少tracker calls；实物五组配对平均周期均下降。
- 必须披露：A3相对A2的平均SNR差为负，且A2/A3未通过全部自适应场景的1 kHz最坏时限。
- 禁止：A3普遍优于A2、达到1 kHz硬实时、降低功耗、完成真实传感器采集。

## 人工/运行时状态

通用`sci-review-system`运行时要求先存在论文级claim ledger才能启动`quantitative-audit`单元；本项目交接顺序规定先统计后ledger，因此当前报告为文件级候选审计，不宣称运行时单元已完成。下一步应据此建立CSSP论点架构和claim-evidence ledger，再回填运行时审计。
