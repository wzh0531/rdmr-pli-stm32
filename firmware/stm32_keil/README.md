# STM32F103C8 Proteus/Keil firmware

This project implements the v0.3.0 RDMR-PLI experiment protocol with the
Phase-2 implementation contract `0.3.1`.

## Default internal benchmark

`App/main.c` defaults to:

- algorithm A3, residual-driven multi-rate NLMS;
- trajectory F1, 49 Hz to 51 Hz at sample 4000;
- PLI amplitude 0.50;
- no added background noise;
- development seed 0;
- 8000 samples at 1 kHz.

The input generator is shared with the host C reference through
`firmware/core/rdmr_signal_protocol.c`. A0-A3 use the unified interface in
`firmware/core/rdmr_algorithm.c`.

## UART schema

The firmware emits:

1. `BOOT` with protocol, implementation, and schema versions;
2. `CONFIG` with the exact scenario and scale factors;
3. the `rdmr-block-csv-v2` header;
4. 160 block records;
5. `STATS` with cycle summaries and numerical-fault counts;
6. `DONE` with the exact row count and PASS/FAIL state.

Values and frequencies are transmitted as scaled signed integers. The scale
factors are declared in `CONFIG`. Non-finite values and fixed-point overflow
are never silently wrapped: the row receives a nonzero `numeric_flags` mask
and the final `DONE` state becomes `FAIL`.

## DWT measurements

DWT is enabled by default. The timed region contains only
`rdmr_algorithm_process`; signal generation and UART transmission are outside
the region. The log reports:

- exact mean and maximum cycles;
- streaming P² estimates of median and P95;
- samples that reach or exceed the 1 ms cycle deadline;
- the same distribution for samples on which a tracker call occurs.

The target CPU clock is 72 MHz, so the deadline is 72,000 cycles.

## Building one configuration

Set the toolchain paths first:

```powershell
$env:STM32CUBE_F1_ROOT = 'C:\path\to\STM32Cube_FW_F1_V1.8.0'
$env:ARMCC_BIN = 'C:\path\to\Keil\ARM\ARMCC\bin'
```

```powershell
powershell -ExecutionPolicy Bypass -File .\build_armcc.ps1 `
  -Algorithm A3 -Trajectory F1 -Noise none -Seed 0
```

Supported algorithms are A0-A3, trajectories F0-F5, and noise settings
`none`, `snr20`, and `snr10`.

## Building A0-A3

```powershell
powershell -ExecutionPolicy Bypass -File .\build_all_algorithms.ps1
```

This generates independently hashed `.hex`, `.axf`, and `.map` files for the
four algorithms. These builds contain the same unified multi-algorithm core;
their map sizes prove build completeness but are not yet the
algorithm-specialized resource figures for the final paper comparison.

## Proteus settings

- MCU: STM32F103C8;
- OSC Frequency: 9,000,000;
- Clock Scale: 8 Times;
- PA9 to Virtual Terminal RX;
- 115200 baud, 8 data bits, no parity, 1 stop bit.

Assign the selected `.hex` file from `build\` to the MCU Program File.

## Physical-board clock

The non-Proteus path uses an 8 MHz HSE multiplied by 9 for a 72 MHz core.
The released physical evidence contains 36 UART logs from an STM32F103C8T6:
12 scenarios with three cold starts per scenario. These runs validate the
internally generated benchmark, telemetry, scheduler state, and DWT timing;
they do not validate an ADC, sensor, or analog front end.
