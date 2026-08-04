# Known validation notes

This compact release distinguishes checks that pass from archival checks that require deliberately excluded files.

The frozen four-page EI working draft is private and is not included. Its
historical SHA-256 identifier may remain in immutable or derived provenance
records, but public regeneration scripts do not read that file. Accordingly,
its public-package verification state is `NOT_CHECKED_FILE_NOT_PUBLIC`, not
`PASS`.

## Checks executed successfully in the staging package

- Python unit tests: 12/12 passed.
- `verify_algorithm_alignment.py`: passed for 364 rows; all reported maximum absolute differences were below their frozen tolerances.
- `run_phase6_statistics.py`: passed with the reported negative real-time result retained; the primary A3-versus-A2 noninferiority gate passed and the 1 kHz physical hard-real-time gate failed.
- `generate_phase6_figures.py`: produced six figure records and three tables; Figs. 2 and 6 were preserved rather than regenerated.

## Archival checks requiring excluded files

### `verify_signal_alignment.py`

This historical check requires the old `firmware/stm32_keil/build/rdmr_stm32.hex` binary. ARMCC-generated binaries are excluded from the public package, so this check is not a clean-package gate. Its previously generated Phase-1 CSV/JSON evidence is included.

### `verify_phase4_results.py`

This check hashes every Phase-4 NPZ batch. The batches are approximately 287 MB and are deliberately excluded because they can be regenerated. Run `run_phase4_host_matrix.py` first, then run this verifier.

### `verify_phase3_freeze.py`

The legacy verifier binds the exact Rev14 firmware binary and the source state that existed at the Phase-3 freeze. The current Rev15 source contains later platform and telemetry changes, so the legacy full-file hash check fails in both the working project and the compact release. Importantly, its reported frozen parameter fingerprint still matches exactly:

```text
expected: 2BBFC2FF25556E06E7A61B44037C10D41AACBB308D2836F49ACEC5323CFB1802
actual:   2BBFC2FF25556E06E7A61B44037C10D41AACBB308D2836F49ACEC5323CFB1802
```

The validator also confirms 360 candidate rows, validation seeds 100–109, and no overlap with frozen test seeds. The later scientific and implementation audits use the frozen protocol, parameter fingerprint, current formula-alignment checks, host results, and Rev15 physical evidence rather than claiming that the historical whole-file hash gate still passes.

This condition must remain visible; it must not be rewritten as a PASS.
