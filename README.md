# Residual-Driven Multirate PLI Cancellation on STM32

This repository contains the source code, frozen configuration, derived host results, Proteus logs, physical STM32F103C8T6 UART logs, statistical outputs, and figure data for the study:

> Zihan Wang, “Residual-Driven Multirate Frequency Tracking for Power-Line Interference Cancellation on STM32: A Performance-Overhead Study.”

Canonical repository: <https://github.com/wzh0531/rdmr-pli-stm32>. Its
visibility remains private pending the author's final approval for the exact
public file list and visibility change. The official-policy refresh and
authenticated clean-clone checks are complete.

## Scope

The project compares four power-line interference (PLI) cancellation methods:

- **A0:** fixed 50 Hz notch filter;
- **A1:** fixed-reference quadrature NLMS;
- **A2:** quadrature NLMS with blockwise frequency tracking after every block;
- **A3:** quadrature NLMS with residual-driven FAST/MID/SLOW tracker scheduling.

The frozen host benchmark uses 1 kHz sampling, 8000 samples per run, six frequency trajectories, three PLI amplitudes, three noise conditions, and 30 frozen seeds. The physical validation uses internally generated signals on an STM32F103C8T6; it does not include a sensor, ADC acquisition chain, or analog front end.

## Main evidence boundary

Across 1620 paired host comparisons, A3 had a mean output-SNR difference of -0.140704 dB relative to A2 and met the prespecified -0.5 dB noninferiority margin. Median tracker-call reduction was 81.25%. In five paired physical scenarios, mean measured-cycle reductions ranged from 75.88% to 86.71%.

These results describe an average performance-overhead tradeoff. Neither A2 nor A3 passed the tested 72,000-cycle worst-case deadline gate, selected Proteus consistency gates failed, and no calibrated electrical power measurement was performed.

## Repository layout

```text
config/                         Frozen experiment and tuning configuration
firmware/core/                  Platform-independent C implementation
firmware/host_test/             Host-side C runners and tests
firmware/stm32_keil/            STM32F103C8T6 source and ARMCC build scripts
simulation/golden_model/        Python model, checks, statistics, and figures
outputs/phase1_alignment/       Signal-generator alignment evidence
outputs/phase2_acceptance/      Regenerated host algorithm-alignment evidence
outputs/phase3_freeze/          Frozen-parameter verification
outputs/phase3_tuning/          Validation-only ablation results
outputs/phase4_host/            Per-run host metrics and grouped summaries
outputs/phase5_physical_core/   Physical UART logs and consistency summaries
outputs/phase5_proteus_core/    Proteus logs and gate summaries
outputs/phase6_statistics/      Final paired statistics
outputs/phase6_figures/         Publication figures, tables, and provenance
paper_workspace/scope/          Frozen experiment protocol
```

The private four-page EI working draft is deliberately not included. Some
historical provenance records retain only its SHA-256 identifier; a checksum
does not contain the manuscript text and is not treated as a clean-clone file
verification.

## Python environment

The recorded analysis environment used Python 3.10.11. Create an isolated environment and install the pinned packages:

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

Run the deterministic Python checks:

```bash
python -m unittest discover -s simulation/golden_model -p "test_*.py"
python simulation/golden_model/verify_algorithm_alignment.py
```

Regenerate final statistics and figures from the included metrics and logs:

```bash
python simulation/golden_model/run_phase6_statistics.py
python simulation/golden_model/generate_phase6_figures.py
```

The figure command regenerates Figs. 1 and 3–5 and all three tables. It preserves the hash-locked Fig. 2 and Fig. 6 outputs because the compact public package excludes the large NPZ trace batches and raw photographs.

## Full host rerun

The complete 7920-run host matrix requires a C99 compiler available as `gcc` and substantially more time and temporary disk space than the summary-only checks:

```bash
python simulation/golden_model/run_phase4_host_matrix.py
python simulation/golden_model/verify_phase4_results.py
```

The large intermediate NPZ batches are intentionally excluded from this release because they can be regenerated. The per-run metrics, completion manifest, grouped summaries, statistical outputs, and generation code are included.

## STM32 build and logs

The STM32 source targets an STM32F103C8T6 at 72 MHz and emits `rdmr-block-csv-v2` telemetry over USART1 at 115200 baud. See [`firmware/stm32_keil/README.md`](firmware/stm32_keil/README.md) for build and wiring details.

ARMCC/Keil build outputs are intentionally excluded. The repository provides source, linker/startup files, build scripts, firmware manifests, and the exact UART logs used in the analysis. A licensed ARMCC/Keil installation is required to reproduce the binaries.

## Data and figure integrity

`SHA256SUMS.txt` records the checksum of every released file except itself. `release-manifest.json` records the package scope and exclusions. The large trace batches and raw setup photographs are not separately released; the hash-locked Fig. 2 and rights-cleared Fig. 6 composites are included under `outputs/phase6_figures/figures/`.

See [`docs/known_validation_notes.md`](docs/known_validation_notes.md) for the legacy checks that intentionally require excluded binaries or regenerated intermediate batches.

## Citation

Citation metadata are provided in [`CITATION.cff`](CITATION.cff). Add the final article DOI and GitHub/archival DOI after they are assigned.

The GitHub repository is the canonical development source. A tagged release may
also be archived in a DOI-granting repository so that the manuscript can cite an
immutable version; the archival DOI is recommended but has not yet been minted.

## License

Software source code, build scripts, and files under `config/` are licensed
under the [MIT License](LICENSE). Original data, measurements, UART logs,
figures, tables, the experiment protocol, and documentation are licensed under
[CC BY 4.0](LICENSE-DATA.md). A file-specific notice takes precedence when
present.
