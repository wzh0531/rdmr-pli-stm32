"""Golden model for a residual-driven multi-rate PLI canceller.

The model is intentionally NumPy-only so that it can be executed without a
large scientific Python stack.  It is the algorithmic reference for the
later STM32 implementation and Proteus verification.  Formal v0.3.0 signal
generation is provided by :mod:`signal_protocol`; the older synthesis helper
below is retained only so the exploratory 216-run benchmark stays reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from formal_algorithms import (
    FormalAlgorithmResult,
    run_formal_algorithm,
)
from signal_protocol import (
    ExperimentConfig,
    SignalArrays,
    generate_signal,
)


Array = np.ndarray


@dataclass(frozen=True)
class CancellerConfig:
    fs: float = 1000.0
    block_size: int = 50
    tracker_window: int = 400
    tracker_min_samples: int = 100
    search_low_hz: float = 45.0
    search_high_hz: float = 55.0
    search_step_hz: float = 0.05
    initial_frequency_hz: float = 50.0
    nlms_mu: float = 0.08
    frequency_smoothing: float = 0.25
    epsilon: float = 1.0e-9


@dataclass
class CancellerResult:
    output: Array
    frequency_hz: Array
    residual_ratio: Array
    states: list[str]
    tracker_calls: int


def make_frequency_profile(
    kind: str,
    sample_count: int,
    fs: float,
) -> Array:
    """Create deterministic mains-frequency trajectories."""

    t = np.arange(sample_count, dtype=float) / fs
    if kind == "constant_49":
        return np.full(sample_count, 49.0)
    if kind == "constant_50":
        return np.full(sample_count, 50.0)
    if kind == "constant_51":
        return np.full(sample_count, 51.0)
    if kind == "ramp_up":
        return 49.0 + 2.0 * t / max(t[-1], 1.0 / fs)
    if kind == "ramp_down":
        return 51.0 - 2.0 * t / max(t[-1], 1.0 / fs)
    if kind == "step":
        return np.where(t < t[-1] / 2.0, 49.5, 50.5)
    raise ValueError(f"Unsupported frequency profile: {kind}")


def synthesize_sensor_signal(
    duration_s: float,
    fs: float,
    frequency_profile: str,
    interference_amplitude: float,
    seed: int,
) -> tuple[Array, Array, Array, Array]:
    """Generate the legacy exploratory signal contaminated by PLI.

    The useful signal includes a weak 48 Hz component.  This makes the test
    stricter than using only low-frequency content because an overly broad
    canceller will visibly distort a legitimate component near the mains.
    Do not use this helper for the frozen v0.3.0 CSSP matrix.
    """

    rng = np.random.default_rng(seed)
    sample_count = int(round(duration_s * fs))
    t = np.arange(sample_count, dtype=float) / fs

    clean = (
        0.42 * np.sin(2.0 * np.pi * 7.0 * t + 0.2)
        + 0.23 * np.sin(2.0 * np.pi * 17.0 * t + 1.1)
        + 0.12 * np.sin(2.0 * np.pi * 31.0 * t + 0.7)
        + 0.06 * np.sin(2.0 * np.pi * 48.0 * t + 0.4)
    )
    pulse_centres = np.arange(0.8, duration_s, 1.4)
    for centre in pulse_centres:
        clean += 0.18 * np.exp(-0.5 * ((t - centre) / 0.025) ** 2)
    clean += 0.015 * rng.standard_normal(sample_count)

    frequency_hz = make_frequency_profile(
        frequency_profile,
        sample_count,
        fs,
    )
    phase = 2.0 * np.pi * np.cumsum(frequency_hz) / fs + 0.35
    interference = interference_amplitude * np.sin(phase)
    observed = clean + interference
    return clean, interference, observed, frequency_hz


def _estimate_frequency_grid(
    samples: Array,
    end: int,
    config: CancellerConfig,
) -> float:
    """Estimate the dominant line frequency using a windowed local DFT."""

    start = max(0, end - config.tracker_window)
    segment = samples[start:end]
    if segment.size < config.tracker_min_samples:
        return config.initial_frequency_hz

    segment = segment - float(np.mean(segment))
    window = np.hanning(segment.size)
    weighted = segment * window
    sample_index = np.arange(start, end, dtype=float)
    frequency_grid = np.arange(
        config.search_low_hz,
        config.search_high_hz + 0.5 * config.search_step_hz,
        config.search_step_hz,
    )
    kernel = np.exp(
        -2.0j
        * np.pi
        * frequency_grid[:, None]
        * sample_index[None, :]
        / config.fs
    )
    magnitude = np.abs(kernel @ weighted)
    return float(frequency_grid[int(np.argmax(magnitude))])


def _next_state(
    state: str,
    residual_ratio: float,
    low_count: int,
) -> tuple[str, int]:
    """Three-state scheduler with hysteresis and persistence."""

    if state == "fast":
        low_count = low_count + 1 if residual_ratio < 0.035 else 0
        if low_count >= 3:
            return "mid", 0
        return state, low_count

    if state == "mid":
        if residual_ratio > 0.055:
            return "fast", 0
        low_count = low_count + 1 if residual_ratio < 0.025 else 0
        if low_count >= 3:
            return "slow", 0
        return state, low_count

    if residual_ratio > 0.060:
        return "fast", 0
    if residual_ratio > 0.040:
        return "mid", 0
    return state, 0


def run_quadrature_nlms(
    observed: Array,
    config: CancellerConfig,
    mode: str,
) -> CancellerResult:
    """Run fixed-reference, full-rate, or residual-driven tracking NLMS."""

    if mode not in {"fixed", "full_rate", "residual_multirate"}:
        raise ValueError(f"Unsupported mode: {mode}")

    sample_count = observed.size
    output = np.empty(sample_count, dtype=float)
    frequency_trace = np.empty(sample_count, dtype=float)
    residual_trace: list[float] = []
    states: list[str] = []

    weights = np.zeros(2, dtype=float)
    phase = 0.0
    frequency_estimate = config.initial_frequency_hz
    tracker_calls = 0
    blocks_since_tracker = 10_000
    state = "fast"
    low_count = 0
    smoothed_residual_ratio = 0.0
    intervals = {"fast": 1, "mid": 3, "slow": 12}

    for block_start in range(0, sample_count, config.block_size):
        block_end = min(sample_count, block_start + config.block_size)
        block_cos = np.empty(block_end - block_start, dtype=float)
        block_sin = np.empty(block_end - block_start, dtype=float)

        for offset, sample_index in enumerate(range(block_start, block_end)):
            reference = np.array([np.cos(phase), np.sin(phase)])
            estimate = float(weights @ reference)
            error = float(observed[sample_index] - estimate)
            weights += (
                config.nlms_mu
                * error
                * reference
                / (float(reference @ reference) + config.epsilon)
            )
            output[sample_index] = error
            frequency_trace[sample_index] = frequency_estimate
            block_cos[offset] = reference[0]
            block_sin[offset] = reference[1]
            phase += 2.0 * np.pi * frequency_estimate / config.fs
            if phase >= 2.0 * np.pi:
                phase -= 2.0 * np.pi

        block_output = output[block_start:block_end]
        energy = float(np.mean(block_output * block_output))
        c = float(np.mean(block_output * block_cos))
        s = float(np.mean(block_output * block_sin))
        residual_ratio = min(1.0, 2.0 * (c * c + s * s) / (energy + config.epsilon))
        smoothed_residual_ratio = (
            0.85 * smoothed_residual_ratio + 0.15 * residual_ratio
        )
        residual_trace.append(smoothed_residual_ratio)

        blocks_since_tracker += 1
        if mode == "fixed":
            state = "fixed"
        elif mode == "full_rate":
            state = "fast"
            candidate = _estimate_frequency_grid(observed, block_end, config)
            frequency_estimate = (
                config.frequency_smoothing * frequency_estimate
                + (1.0 - config.frequency_smoothing) * candidate
            )
            tracker_calls += 1
            blocks_since_tracker = 0
        else:
            state, low_count = _next_state(
                state,
                smoothed_residual_ratio,
                low_count,
            )
            if blocks_since_tracker >= intervals[state]:
                candidate = _estimate_frequency_grid(observed, block_end, config)
                frequency_estimate = (
                    config.frequency_smoothing * frequency_estimate
                    + (1.0 - config.frequency_smoothing) * candidate
                )
                tracker_calls += 1
                blocks_since_tracker = 0
        states.append(state)

    return CancellerResult(
        output=output,
        frequency_hz=frequency_trace,
        residual_ratio=np.asarray(residual_trace),
        states=states,
        tracker_calls=tracker_calls,
    )


def run_fixed_notch(
    observed: Array,
    fs: float,
    notch_hz: float = 50.0,
    quality_factor: float = 30.0,
) -> Array:
    """Apply a normalized second-order IIR notch without SciPy."""

    omega = 2.0 * np.pi * notch_hz / fs
    alpha = np.sin(omega) / (2.0 * quality_factor)
    a0 = 1.0 + alpha
    b0 = 1.0 / a0
    b1 = -2.0 * np.cos(omega) / a0
    b2 = 1.0 / a0
    a1 = -2.0 * np.cos(omega) / a0
    a2 = (1.0 - alpha) / a0

    output = np.zeros_like(observed, dtype=float)
    x1 = x2 = y1 = y2 = 0.0
    for index, value in enumerate(observed):
        current = b0 * value + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        output[index] = current
        x2, x1 = x1, float(value)
        y2, y1 = y1, current
    return output


def calculate_metrics(
    clean: Array,
    interference: Array,
    output: Array,
    true_frequency_hz: Array | None = None,
    estimated_frequency_hz: Array | None = None,
) -> dict[str, float]:
    """Calculate simulation-only metrics with known clean ground truth."""

    error = output - clean
    clean_power = float(np.mean(clean * clean))
    interference_power = float(np.mean(interference * interference))
    error_power = float(np.mean(error * error))
    metrics = {
        "rmse": float(np.sqrt(error_power)),
        "output_snr_db": float(10.0 * np.log10(clean_power / (error_power + 1.0e-15))),
        "suppression_db": float(
            10.0 * np.log10(interference_power / (error_power + 1.0e-15))
        ),
    }
    if true_frequency_hz is not None and estimated_frequency_hz is not None:
        metrics["frequency_mae_hz"] = float(
            np.mean(np.abs(true_frequency_hz - estimated_frequency_hz))
        )
    return metrics


Algorithm = Callable[[Array], Array]


def synthesize_protocol_signal(config: ExperimentConfig) -> SignalArrays:
    """Generate the formal v0.3.0 signal shared with STM32/Proteus."""

    return generate_signal(config)


def run_protocol_algorithm(
    observed: Array,
    algorithm_id: int,
) -> FormalAlgorithmResult:
    """Run the formal float32 A0-A3 implementation used for CSSP evidence."""

    return run_formal_algorithm(observed, algorithm_id)
