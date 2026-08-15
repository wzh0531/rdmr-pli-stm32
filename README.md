# Residual-Driven Multirate PLI Cancellation on STM32

This repository contains the source code, frozen configuration, derived host results, Proteus logs, physical STM32F103C8T6 UART logs, statistical outputs, and figure data for the study:

> Zihan Wang, “Residual-Driven Multirate Frequency Tracking for Power-Line Interference Cancellation on STM32: A Performance-Overhead Study.”

Canonical public repository: <https://github.com/wzh0531/rdmr-pli-stm32>.
The author granted final public-release approval on 2026-08-11, and logged-out
public access was verified on 2026-08-12. The official-policy refresh and
clean-clone checks are complete.

## Scope

The project compares the following power-line interference (PLI) cancellation methods and implementation modes:

- **A0:** fixed 50 Hz notch filter;
- **A1:** fixed-reference quadrature NLMS;
- **A2:** quadrature NLMS with blockwise frequency tracking after every block;
- **A3:** quadrature NLMS with residual-driven FAST/MID/SLOW tracker scheduling.
- **B4:** a simpler two-state residual scheduler used as a deployment comparator.
- **Search modes:** the frozen 201-point exhaustive search and a bounded 21+11 hierarchical search with 32 evaluations.

The frozen host benchmark uses 1 kHz sampling, 8000 samples per run, six frequency trajectories, three PLI amplitudes, three noise conditions, and 30 frozen seeds. Phase 8 adds controlled PLI injection on all 48 MIT-BIH records (47 subject clusters), an exhaustive-to-hierarchical search bridge, and Rev17 block-level timing on an STM32F103C8T6. The physical validation uses internally generated signals; it does not include a sensor, ADC acquisition chain, or analog front end.

## Phase 8 evidence summary

Across the original 1620 paired host comparisons, A3 had a mean output-SNR difference of -0.140704 dB relative to A2, although 146 runs and five frozen-condition means crossed the prespecified -0.5 dB design margin. A3 exceeded B4 by only 0.054 dB while using 3.03 more calls, so neither dominated the synthetic quality-activity plane.

Across controlled PLI injections on 48 MIT-BIH records representing 47 subject clusters, A3 exceeded B4 by 0.017011 dB on average and used 0.712 fewer calls, but subject-level and preselected boundary results were not uniformly favorable. The 4,860-pair search bridge reduced mean grid evaluations by 84.0801% with a mean output-SNR difference of +0.0000118 dB. All 14 Rev17 hierarchical-search captures met the 2.88-million-cycle target for a 50-ms block; the maximum was 2,786,472 cycles, whereas the matched exhaustive implementation reached 17,034,581 cycles.

These results support a search-scheduling-budget co-design and block-level memory-to-memory timing. They do not establish clinical validity, strict 1-ms per-sample execution, ADC/DMA end-to-end timing, or calibrated electrical power savings. Selected Proteus consistency gates also remain failed and visible.

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
outputs/phase8_realtime_strengthening/
                                Multirecord ECG, search bridge, Rev17 firmware, and raw UART evidence
paper_workspace/scope/          Frozen experiment protocol
paper_workspace/reviews/        Quantitative audit records
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

Verify the Phase 8 public release payload:

```bash
python verify_release.py
```

The Phase 8 scripts are:

```bash
python simulation/golden_model/prepare_phase8_mitdb_multirecord.py
python simulation/golden_model/run_phase8_tracker_bridge.py --full-matrix
python simulation/golden_model/run_phase8_mitdb_multirecord.py
```

MIT-BIH waveform files are not redistributed. Download database version 1.0.0 from PhysioNet (DOI `10.13026/C2F305`) and place it at the path described in [`docs/reproducibility.md`](docs/reproducibility.md).

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

Historical ARMCC/Keil build caches remain excluded. The Phase 8 release includes the selected Rev17 AXF/HEX/MAP evidence, source, linker/startup files, build scripts, firmware manifests, and the exact UART logs used in the analysis. A licensed ARMCC/Keil installation is required to regenerate the binaries.

## Data and figure integrity

`SHA256SUMS.txt` records the checksum of every released file except itself. `verify_release.py` checks both hashes and file-list completeness. `release-manifest.json` records the package scope and exclusions. The large trace batches, MIT-BIH waveforms, and raw setup photographs are not redistributed.

See [`docs/known_validation_notes.md`](docs/known_validation_notes.md) for the legacy checks that intentionally require excluded binaries or regenerated intermediate batches.

## Citation

Citation metadata are provided in [`CITATION.cff`](CITATION.cff). The immutable Phase 8 repository version is tagged `phase8-v1.0.0`. Add the final article DOI and archival DOI after they are assigned.

The GitHub repository is the canonical development source. A tagged release may
also be archived in a DOI-granting repository so that the manuscript can cite an
immutable version; the archival DOI is recommended but has not yet been minted.

## License

Software source code, build scripts, and files under `config/` are licensed
under the [MIT License](LICENSE). Original data, measurements, UART logs,
figures, tables, the experiment protocol, and documentation are licensed under
[CC BY 4.0](LICENSE-DATA.md). A file-specific notice takes precedence when
present.
