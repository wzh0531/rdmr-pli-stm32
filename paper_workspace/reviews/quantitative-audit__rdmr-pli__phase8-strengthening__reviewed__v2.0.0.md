---
artifact_id: quantitative-audit__rdmr-pli__phase8-strengthening__reviewed__v2.0.0
project_id: ft-vss-nlms-stm32-ei
artifact_kind: quantitative_audit
work_unit: quantitative-audit
status: reviewed
language: bilingual
baseline_artifact: paper_workspace/evidence/claim-ledger__rdmr-pli__phase8-strengthening__reviewed__v2.0.0.md
source_registry: paper_workspace/.sci-review-system/state/project_state.json
run_id: run-20260726-001
gate_status: runtime-managed
next_intents:
  - science-drafting
  - science-audit
  - reviewer-audit
---

# Phase 8 quantitative and comparability audit

## Audit verdict

`PASS_WITH_CONDITIONS`. Phase 8 closes the three priority reviewer gaps at the level supported by the frozen experiments: it supplies a controlled two-state comparator and counterexample, expands ECG morphology coverage to all 48 MIT-BIH records with 47-subject clustered inference, and demonstrates 50 ms block-level timing for the hierarchical search on STM32F103. The evidence does not support universal A3 superiority, clinical validation, per-sample hard real time, or ADC/DMA end-to-end operation.

## Comparison matrix

| Layer | Study object / population | Methods compared | Shared input and protocol | Metric / unit | Statistical or timing unit | Reference standard | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Host search bridge | 54 frozen generated-signal conditions × 30 seeds × A2/A3/B4 = 4,860 mode pairs | 201-point exhaustive versus 32-evaluation hierarchical search; same scheduler and canceller | Same archive, seed, trajectory, PLI/noise condition and algorithm; only search mode differs | Output-SNR difference, dB; frequency-MAE difference, Hz; grid evaluations | Paired mode comparison | Exhaustive implementation plus frozen regression outputs | `PASS`: search complexity and numerical fidelity are directly comparable |
| MIT-BIH controlled injection | 48 records, 47 subject clusters; 3 fixed 8 s segments per record; 24 injections per segment | A2, A3 and B4, all using hierarchical search | Same ECG segment and controlled PLI realization for each paired comparison; algorithm parameters frozen before analysis | Output SNR, dB; frequency MAE, Hz; tracker calls and grid evaluations | Primary inference at subject-cluster level; 3,456 pairs are repeated conditions, not subjects | Known clean ECG segment before synthetic PLI injection | `PASS_WITH_CONDITIONS`: valid signal-processing comparison, not clinical validation |
| STM32 Rev17 timing | 17 deterministic UART captures; 160 blocks per capture | A3 exhaustive/hierarchical, B4 hierarchical, A2 hierarchical | Matched F4/PLI/seed for core comparisons; preselected high-activity and unfavorable boundaries | DWT cycles per 50 ms block; block violations; output SNR | Capture/scenario; repeated blocks are serial deterministic observations | 3.6 M hard budget and 2.88 M target at 72 MHz | `PASS_WITH_CONDITIONS`: block-compute timing only |
| Cross-layer synthesis | Host accuracy, ECG morphology and device timing | Different evidence layers | Implementations are formula-aligned, but signals and measurement mechanisms differ | No pooled metric | None | Claim-specific primary source | `NOT_COMBINED`: sample sizes and uncertainty are not pooled across layers |

## Host bridge audit

- Paired comparisons: 4,860.
- Exhaustive maximum grid evaluations: 201; hierarchical maximum: 32.
- Mean grid-evaluation reduction: 84.0801%.
- Mean hierarchical-minus-exhaustive output SNR: +0.0000118 dB.
- Minimum individual output-SNR difference: -0.01631 dB, above the frozen -0.10 dB floor.
- Maximum frequency-MAE increment: 0.002547 Hz, below the 0.01 Hz gate.
- Frozen exhaustive-regression mismatches: 0.

Verdict: the hierarchical search may be described as an accuracy-preserving implementation approximation within the frozen search range and test matrix. It must not be described as mathematically identical or universally equivalent.

## ECG clustered-inference audit

The official PhysioNet description confirms that the database contains 48 half-hour records from 47 subjects. Records 201 and 202 share one subject cluster; all within-record segments and injection conditions are therefore nested observations.

| Contrast | Mean output-SNR difference | 95% subject-cluster bootstrap CI | Frequency-MAE difference | Tracker-call difference | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| A3 − B4 | +0.01701 dB | [0.01153, 0.02275] dB | -0.003404 Hz | -0.712 | Directionally favorable but very small; no practical or clinical importance established |
| A3 − A2 | -0.02067 dB | [-0.02462, -0.01685] dB | +0.005015 Hz | -66.573 | A3 saves tracker work while giving up a small amount of output SNR and frequency accuracy |

The mean A3–B4 result must not hide heterogeneity: the minimum subject-mean A3–B4 output-SNR difference is -0.05192 dB. This reinforces a conditional tradeoff interpretation.

## STM32 timing audit

The timing reference is a 72 MHz STM32F103 executing 50-sample blocks at a nominal 1 kHz stream. The hard block budget is 3,600,000 cycles and the target with 20% margin is 2,880,000 cycles.

- All 14 hierarchical captures passed the 2.88 M-cycle target; observed maxima were 2,764,456–2,786,472 cycles.
- The three exhaustive A3 captures each reached 17,034,581 cycles and recorded 34 hard-budget violations.
- In the matched F4, PLI=0.20 comparison, hierarchical A3 reached 2,775,151 cycles, an 83.709% reduction and 6.138-fold maximum-cycle speedup relative to exhaustive A3, with unchanged output SNR.
- In the high-activity boundary, A3 performed 143 searches in 160 blocks and still reached only 2,786,472 cycles. Relative to B4, it gained 0.02520 dB but added 14 searches and 235,364 mean cycles.
- Relative to A2 in the same high-activity boundary, A3 saved 10.01% mean cycles and lost 0.01260 dB.
- In the preselected unfavorable boundary, A3 was 0.29646 dB below B4 and made one additional search.

Per-search samples exceed the nominal 72,000-cycle sample interval, so a strict per-sample real-time statement would be false. The valid implementation claim is block-level completion under the frozen memory-to-memory benchmark.

## Leakage, bias and confounding audit

| Risk | Finding | Disposition |
| --- | --- | --- |
| ECG waveform selection after outcome inspection | The 48-record selection manifest, three segment starts (300, 900 and 1500 s), lead rule and 24 injection conditions were frozen before analysis. | No detected outcome-driven segment selection |
| Hyperparameter reuse | Algorithms and hierarchical search were frozen before the multirecord run. | No detected test-set tuning in Phase 8 |
| Pseudoreplication | Multiple segments and injections occur within records; records 201/202 share a subject. | Addressed by 47-subject cluster bootstrap and bounded wording |
| Boundary selection bias | Five device boundaries were selected from the frozen host matrix because they were information-bearing. | Acceptable for targeted falsification and worst-activity checks; prohibited for prevalence estimates |
| Deterministic repetition inflation | Three cold starts per image were byte-identical. | Report as reproducibility, not independent n |
| Platform confounding | Exhaustive and hierarchical timing use matched firmware conditions, but speedup is compiler/platform-specific. | Limit the speedup claim to the frozen STM32F103 build |
| Clinical confounding | Clean ECG morphology is reused with synthetic PLI; no diagnostic endpoint is evaluated. | Prohibit clinical and diagnostic-preservation claims |

## Missing conditions and NOT_CHECKED items

- ADC/DMA acquisition, interrupt contention and continuous peripheral streaming.
- Power or energy per block.
- Diagnostic feature or arrhythmia-detection preservation.
- Prospective, clinical or new-subject validation.
- Random-sample prevalence of favorable or unfavorable A3–B4 conditions.
- Other MCUs, compilers, clock rates, search ranges or tracker implementations.

These omissions do not invalidate the bounded Phase 8 conclusions, but they prevent stronger embedded-product and clinical claims.

## Bounded manuscript wording

Use: “Across 4,860 paired host comparisons, the 32-evaluation hierarchical search reduced mean grid evaluations by 84.08% while remaining within the prespecified SNR and frequency-error gates.”

Use: “Controlled PLI injection was evaluated on 48 MIT-BIH records representing 47 subject clusters; the A3–B4 mean output-SNR difference was 0.017 dB (subject-cluster bootstrap 95% CI, 0.012–0.023 dB).”

Use: “All 14 hierarchical-search STM32 captures met the 2.88 M-cycle target for a 50 ms block, including a 143-search high-activity boundary.”

Use: “The A3 scheduler should be interpreted as a condition-dependent quality–computation tradeoff: an unfavorable boundary produced an A3–B4 difference of -0.296 dB.”

Do not use: “significantly better” without defining statistical and practical significance; “real patient samples” for injection-condition pairs; “per-sample real time”; “end-to-end embedded validation”; or any universal-superiority wording.
