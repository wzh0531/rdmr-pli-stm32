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

## Physical evidence

The repository contains 36 physical UART logs: 12 scenarios with three cold starts per scenario. The board signals were generated internally. The logs validate numerical execution, telemetry, scheduler state, and DWT cycle measurement; they do not validate an ADC, sensor, or analog front end.

The externally applied worst-case deadline is 72,000 cycles per sample at 72 MHz and 1 kHz. The adaptive A2/A3 scenarios fail this deadline even though A3 reduces mean cycles.

## Package exclusions

- Large, regenerable Phase-4 NPZ batches.
- Host and ARMCC build caches and executables.
- ARMCC-generated AXF/HEX/MAP binaries.
- Historical pre-fix Proteus experiments.
- Raw physical-setup photographs; the rights-cleared Fig. 6 composite is included.
- Internal conversation handoffs, author decisions, and submission-control records.
- The private frozen four-page EI working draft. Historical manifests may
  retain only its SHA-256 provenance identifier; public scripts do not require
  the draft file.

See `known_validation_notes.md` before running the historical Phase-1/Phase-3 binary-hash verifiers.
