"""Formula-aligned v0.3.0 signal generator for host and STM32.

The implementation mirrors ``firmware/core/rdmr_signal_protocol.c`` using
explicit float32 operations and the same integer RNG.  The JSON protocol is
the source of identifiers, scenario definitions, and audit metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterator

import numpy as np

from trig_table import table_cos, table_sin


Array = np.ndarray
F32 = np.float32
U32_MASK = 0xFFFFFFFF
TWO_PI = F32(2.0 * np.pi)
U24_SCALE = F32(1.0 / 16777216.0)
STREAM_FREQUENCY = 2654435769
STREAM_NOISE = 2246822507
STREAM_PHASE = 3266489909


def protocol_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "config"
        / "experiment_protocol__rdmr-pli__v0.3.0.json"
    )


def load_protocol() -> dict[str, object]:
    with protocol_path().open(encoding="utf-8") as handle:
        return json.load(handle)


@dataclass(frozen=True)
class ExperimentConfig:
    algorithm: str
    trajectory: str
    pli_amplitude: float
    noise: str
    near_line: str
    seed: int
    sample_rate_hz: int = 1000
    sample_count: int = 8000
    log_schema_version: str = "rdmr-alignment-csv-v1"

    def validate(self, protocol: dict[str, object] | None = None) -> None:
        contract = load_protocol() if protocol is None else protocol
        if self.algorithm not in contract["algorithm_ids"]:
            raise ValueError(f"Unsupported algorithm: {self.algorithm}")
        if self.trajectory not in contract["trajectory_ids"]:
            raise ValueError(f"Unsupported trajectory: {self.trajectory}")
        if self.noise not in contract["noise_ids"]:
            raise ValueError(f"Unsupported noise level: {self.noise}")
        if self.near_line not in contract["near_line_ids"]:
            raise ValueError(f"Unsupported near-line case: {self.near_line}")
        if self.sample_rate_hz != int(contract["sample_rate_hz"]):
            raise ValueError("Phase-1 firmware contract requires Fs=1000 Hz")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if self.seed < 0 or self.seed > U32_MASK:
            raise ValueError("seed must fit uint32")


@dataclass(frozen=True)
class SignalArrays:
    clean: Array
    interference: Array
    noise: Array
    input: Array
    true_frequency_hz: Array


def _u32(value: int) -> int:
    return value & U32_MASK


def _splitmix32(value: int) -> int:
    value = _u32(value + 0x9E3779B9)
    value = _u32((value ^ (value >> 16)) * 0x85EBCA6B)
    value = _u32((value ^ (value >> 13)) * 0xC2B2AE35)
    return _u32(value ^ (value >> 16))


def _derive_stream_seed(seed: int, stream_tag: int) -> int:
    state = _splitmix32(_u32(seed + stream_tag))
    return state if state != 0 else 0x6D2B79F5


class _XorShift32:
    def __init__(self, state: int):
        self.state = _u32(state)

    def next_u32(self) -> int:
        value = self.state
        value = _u32(value ^ _u32(value << 13))
        value = _u32(value ^ (value >> 17))
        value = _u32(value ^ _u32(value << 5))
        self.state = value
        return value

    def uniform01(self) -> F32:
        return F32(F32(self.next_u32() >> 8) * U24_SCALE)

    def normal_gaussian(self) -> F32:
        uniform_1 = self.uniform01()
        uniform_2 = self.uniform01()
        if uniform_1 <= F32(0.0):
            uniform_1 = U24_SCALE
        radius = F32(np.sqrt(F32(F32(-2.0) * F32(np.log(uniform_1)))))
        angle = F32(TWO_PI * uniform_2)
        return F32(radius * table_cos(angle))


def _oscillator_step(
    cosine: F32,
    sine: F32,
    step_cosine: F32,
    step_sine: F32,
) -> tuple[F32, F32]:
    next_cosine = F32(
        F32(cosine * step_cosine) - F32(sine * step_sine)
    )
    next_sine = F32(
        F32(sine * step_cosine) + F32(cosine * step_sine)
    )
    return next_cosine, next_sine


def _clean_signal_power(near_line: str) -> F32:
    power = F32(
        F32(0.5)
        * F32(F32(F32(0.18) * F32(0.18)) + F32(F32(0.10) * F32(0.10)))
    )
    if near_line in {"N1", "N2"}:
        power = F32(
            power + F32(F32(0.5) * F32(F32(0.05) * F32(0.05)))
        )
    elif near_line == "N3":
        power = F32(power + F32(F32(0.05) * F32(0.05)))
    return power


def _noise_standard_deviation(noise: str, near_line: str) -> F32:
    power = _clean_signal_power(near_line)
    if noise == "snr_20_db":
        return F32(np.sqrt(F32(power / F32(100.0))))
    if noise == "snr_10_db":
        return F32(np.sqrt(F32(power / F32(10.0))))
    return F32(0.0)


class SignalGenerator:
    """Stateful float32 generator matching the embedded C implementation."""

    def __init__(self, config: ExperimentConfig):
        config.validate()
        self.config = config
        self.sample_index = 0
        self.frequency_rng = _XorShift32(
            _derive_stream_seed(config.seed, STREAM_FREQUENCY)
        )
        self.noise_rng = _XorShift32(
            _derive_stream_seed(config.seed, STREAM_NOISE)
        )
        self.phase_rng = _XorShift32(
            _derive_stream_seed(config.seed, STREAM_PHASE)
        )
        self.line_phase_rad = F32(self.phase_rng.uniform01() * TWO_PI)
        self.line_cos = table_cos(self.line_phase_rad)
        self.line_sin = table_sin(self.line_phase_rad)
        self.line_step_cos = F32(1.0)
        self.line_step_sin = F32(0.0)
        self.line_step_frequency_hz = F32(-1.0)
        self.f5_frequency_hz = F32(50.0)
        self.clean_7_cos = F32(1.0)
        self.clean_7_sin = F32(0.0)
        self.clean_13_cos = F32(1.0)
        self.clean_13_sin = F32(0.0)
        self.near_42_cos = F32(1.0)
        self.near_42_sin = F32(0.0)
        self.near_58_cos = F32(1.0)
        self.near_58_sin = F32(0.0)

    def true_frequency(self, sample_index: int) -> F32:
        trajectory = self.config.trajectory
        if trajectory == "F0":
            return F32(50.0)
        if trajectory == "F1":
            return F32(49.0 if sample_index < 4000 else 51.0)
        if trajectory == "F2":
            return F32(47.0 if sample_index < 4000 else 53.0)
        if trajectory == "F3":
            if sample_index < 1000:
                return F32(49.0)
            if sample_index > 6999:
                return F32(51.0)
            numerator = F32(F32(2.0) * F32(sample_index - 1000))
            return F32(F32(49.0) + F32(numerator / F32(5999.0)))
        if trajectory == "F4":
            angle = F32(
                F32(TWO_PI * F32(sample_index)) / F32(4000.0)
            )
            return F32(F32(50.0) + table_sin(angle))
        if sample_index != 0 and sample_index % 50 == 0:
            draw = self.frequency_rng.uniform01()
            step = F32(0.0)
            if draw < F32(0.25):
                step = F32(-0.05)
            elif draw >= F32(0.75):
                step = F32(0.05)
            candidate = F32(self.f5_frequency_hz + step)
            if candidate < F32(48.5):
                candidate = F32(F32(48.5) + F32(F32(48.5) - candidate))
            elif candidate > F32(51.5):
                candidate = F32(F32(51.5) - F32(candidate - F32(51.5)))
            self.f5_frequency_hz = candidate
        return self.f5_frequency_hz

    def next_sample(self) -> tuple[F32, F32, F32, F32, F32]:
        if self.sample_index >= self.config.sample_count:
            raise StopIteration

        true_frequency = self.true_frequency(self.sample_index)
        if true_frequency != self.line_step_frequency_hz:
            step_angle = F32(
                F32(TWO_PI * true_frequency)
                / F32(self.config.sample_rate_hz)
            )
            self.line_step_cos = table_cos(step_angle)
            self.line_step_sin = table_sin(step_angle)
            self.line_step_frequency_hz = true_frequency
        clean = F32(
            F32(F32(0.18) * self.clean_7_sin)
            + F32(F32(0.10) * self.clean_13_sin)
        )
        if self.config.near_line in {"N1", "N3"}:
            clean = F32(clean + F32(F32(0.05) * self.near_42_sin))
        if self.config.near_line in {"N2", "N3"}:
            clean = F32(clean + F32(F32(0.05) * self.near_58_sin))

        interference = F32(
            F32(self.config.pli_amplitude)
            * self.line_sin
        )
        noise_sigma = _noise_standard_deviation(
            self.config.noise,
            self.config.near_line,
        )
        noise = (
            F32(noise_sigma * self.noise_rng.normal_gaussian())
            if noise_sigma > F32(0.0)
            else F32(0.0)
        )
        input_value = F32(F32(clean + interference) + noise)

        self.clean_7_cos, self.clean_7_sin = _oscillator_step(
            self.clean_7_cos,
            self.clean_7_sin,
            F32(0.999032935),
            F32(0.043968118),
        )
        self.clean_13_cos, self.clean_13_sin = _oscillator_step(
            self.clean_13_cos,
            self.clean_13_sin,
            F32(0.996665928),
            F32(0.081590612),
        )
        self.near_42_cos, self.near_42_sin = _oscillator_step(
            self.near_42_cos,
            self.near_42_sin,
            F32(0.965381639),
            F32(0.260841519),
        )
        self.near_58_cos, self.near_58_sin = _oscillator_step(
            self.near_58_cos,
            self.near_58_sin,
            F32(0.934328942),
            F32(0.356411879),
        )
        self.line_cos, self.line_sin = _oscillator_step(
            self.line_cos,
            self.line_sin,
            self.line_step_cos,
            self.line_step_sin,
        )

        line_step = F32(
            F32(TWO_PI * true_frequency)
            / F32(self.config.sample_rate_hz)
        )
        self.line_phase_rad = F32(self.line_phase_rad + line_step)
        if self.line_phase_rad >= TWO_PI:
            self.line_phase_rad = F32(self.line_phase_rad - TWO_PI)
        self.sample_index += 1
        return clean, interference, noise, input_value, true_frequency

    def __iter__(
        self,
    ) -> Iterator[tuple[F32, F32, F32, F32, F32]]:
        while self.sample_index < self.config.sample_count:
            yield self.next_sample()


def generate_signal(config: ExperimentConfig) -> SignalArrays:
    generator = SignalGenerator(config)
    clean = np.empty(config.sample_count, dtype=np.float32)
    interference = np.empty(config.sample_count, dtype=np.float32)
    noise = np.empty(config.sample_count, dtype=np.float32)
    input_values = np.empty(config.sample_count, dtype=np.float32)
    true_frequency = np.empty(config.sample_count, dtype=np.float32)

    for index, values in enumerate(generator):
        (
            clean[index],
            interference[index],
            noise[index],
            input_values[index],
            true_frequency[index],
        ) = values
    return SignalArrays(
        clean=clean,
        interference=interference,
        noise=noise,
        input=input_values,
        true_frequency_hz=true_frequency,
    )


def alignment_configs() -> list[tuple[str, ExperimentConfig]]:
    contract = load_protocol()
    configs: list[tuple[str, ExperimentConfig]] = []
    for scenario in contract["alignment_scenarios"]:
        for seed in contract["seed_partitions"]["development"]:
            configs.append(
                (
                    str(scenario["scenario_id"]),
                    ExperimentConfig(
                        algorithm=str(scenario["algorithm"]),
                        trajectory=str(scenario["trajectory"]),
                        pli_amplitude=float(scenario["pli_amplitude"]),
                        noise=str(scenario["noise"]),
                        near_line=str(scenario["near_line"]),
                        seed=int(seed),
                        sample_rate_hz=int(contract["sample_rate_hz"]),
                        sample_count=int(contract["sample_count"]),
                        log_schema_version=str(contract["log_schema_version"]),
                    ),
                )
            )
    return configs
