# Reproducibility guide

## Recorded environment

- Python 3.10.11
- NumPy 2.2.6
- pandas 2.3.3
- SciPy 1.15.3
- Matplotlib 3.10.8
- Pillow 12.0.0
- Host C path: C99/GCC-compatible compiler
- STM32 path: ARMCC/Keil-compatible toolchain, Cortex-M3, `-O2`, split sections

## Fast verification

From the repository root:

```bash
python -m unittest discover -s simulation/golden_model -p "test_*.py"
python simulation/golden_model/verify_algorithm_alignment.py
```

## Derived statistics and figures

The included `outputs/phase4_host/phase4_run_metrics.csv`, Phase-3 ablation data, physical logs, and physical/Proteus summaries are sufficient to regenerate the final statistics and figures:

```bash
python simulation/golden_model/run_phase6_statistics.py
python simulation/golden_model/generate_phase6_figures.py
```

The statistical script uses a deterministic bootstrap seed of `20260803` and 20,000 paired resamples. The noninferiority margin is -0.5 dB.

The compact package regenerates Figs. 1 and 3–5 and the three tables. Fig. 2 is preserved because its large NPZ trace batches are excluded, and Fig. 6 is preserved because the raw photographs are outside the authorized public package.

## Full matrix regeneration

```bash
python simulation/golden_model/run_phase4_host_matrix.py
python simulation/golden_model/verify_phase4_results.py
```

This rebuilds the C shared library, executes 7920 frozen runs, and regenerates the excluded intermediate NPZ batches. Ensure that `gcc` is available on `PATH` and allow several gigabytes of temporary free space.

## Phase 8 multirecord ECG and search bridge

Download MIT-BIH Arrhythmia Database version 1.0.0 from PhysioNet (DOI `10.13026/C2F305`) and extract it to:

```text
sources/physionet_mitdb_1.0.0/mit-bih-arrhythmia-database-1.0.0
```

The release does not redistribute waveform files. The selection manifest records expected source hashes, selected leads, three fixed segments per record, and the 47-subject cluster mapping.

Run the Phase 8 workflows from the repository root:

```bash
python simulation/golden_model/prepare_phase8_mitdb_multirecord.py
python simulation/golden_model/run_phase8_tracker_bridge.py --full-matrix
python simulation/golden_model/run_phase8_mitdb_multirecord.py
```

The included published outputs contain 4,860 exhaustive/hierarchical comparisons and 3,456 paired MIT-BIH inputs. The 284 MiB Phase 4 batch cache remains excluded because it is regenerable.

Validate an individual Rev17 UART log with the scenario, algorithm, and search-mode options reported by the script:

```bash
python simulation/golden_model/validate_phase8_rev16_log.py <log> --firmware-revision 17
```

Verify every released file and detect unlisted files with:

```bash
python verify_release.py
```

## Physical evidence

The repository contains 36 physical UART logs: 12 scenarios with three cold starts per scenario. The board signals were generated internally. The logs validate numerical execution, telemetry, scheduler state, and DWT cycle measurement; they do not validate an ADC, sensor, or analog front end.

The legacy externally applied worst-case deadline is 72,000 cycles per sample at 72 MHz and 1 kHz. Phase 8 instead tests a declared 2.88-million-cycle target for each 50-ms block. All 14 hierarchical-search captures pass that block target, while the matched exhaustive implementation fails. This is not an ADC/DMA or strict per-sample real-time claim.

## Package exclusions

- Large, regenerable Phase-4 NPZ batches.
- Host and ARMCC build caches and executables.
- Unselected ARMCC-generated binaries and build caches; selected Rev17 AXF/HEX/MAP evidence is included.
- Historical pre-fix Proteus experiments.
- Raw physical-setup photographs; the rights-cleared Fig. 6 composite is included.
- Internal conversation handoffs, author decisions, and submission-control records.
- The private frozen four-page EI working draft. Historical manifests may
  retain only its SHA-256 provenance identifier; public scripts do not require
  the draft file.

See `known_validation_notes.md` before running the historical Phase-1/Phase-3 binary-hash verifiers.
