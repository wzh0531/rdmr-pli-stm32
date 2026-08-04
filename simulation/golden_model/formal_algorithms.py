"""Float32 A0-A3 reference matching the STM32 C implementation.

This module is the formal v0.3.0 algorithm path.  The older vectorized model
in ``rdmr_pli.py`` remains available only for reproducing exploratory results.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trig_table import table_cos, table_sin


Array = np.ndarray
F32 = np.float32
PI = F32(np.pi)
TWO_PI = F32(2.0 * np.pi)
FS_HZ = F32(1000.0)
BLOCK_SIZE = 50
TRACKER_WINDOW = 400
TRACKER_MIN_SAMPLES = 100
GRID_SIZE = 201
SEARCH_LOW_HZ = F32(45.0)
SEARCH_STEP_HZ = F32(0.05)
INITIAL_HZ = F32(50.0)
NLMS_MU = F32(0.08)
FREQUENCY_OLD_WEIGHT = F32(0.25)
RESIDUAL_NEW_WEIGHT = F32(0.30)
EPSILON = F32(1.0e-9)

STATE_FAST = 0
STATE_MID = 1
STATE_SLOW = 2
STATE_FIXED = 3


@dataclass(frozen=True)
class FormalAlgorithmResult:
    output: Array
    frequency_used_hz: Array
    frequency_next_hz: Array
    residual_ratio: Array
    tracker_calls: Array
    state_used: Array
    state_next: Array


def _fadd(left: F32, right: F32) -> F32:
    return F32(left + right)


def _fsub(left: F32, right: F32) -> F32:
    return F32(left - right)


def _fmul(left: F32, right: F32) -> F32:
    return F32(left * right)


def _fdiv(left: F32, right: F32) -> F32:
    return F32(left / right)


class _Notch:
    def __init__(self) -> None:
        omega = _fdiv(
            _fmul(_fmul(F32(2.0), PI), F32(50.0)),
            FS_HZ,
        )
        alpha = _fdiv(
            table_sin(omega),
            _fmul(F32(2.0), F32(30.0)),
        )
        a0 = _fadd(F32(1.0), alpha)
        cosine = table_cos(omega)
        self.b0 = _fdiv(F32(1.0), a0)
        self.b1 = _fdiv(_fmul(F32(-2.0), cosine), a0)
        self.b2 = _fdiv(F32(1.0), a0)
        self.a1 = _fdiv(_fmul(F32(-2.0), cosine), a0)
        self.a2 = _fdiv(_fsub(F32(1.0), alpha), a0)
        self.x1 = F32(0.0)
        self.x2 = F32(0.0)
        self.y1 = F32(0.0)
        self.y2 = F32(0.0)

    def process(self, input_value: F32) -> F32:
        output = _fadd(
            _fadd(
                _fadd(
                    _fmul(self.b0, input_value),
                    _fmul(self.b1, self.x1),
                ),
                _fmul(self.b2, self.x2),
            ),
            _fsub(
                _fmul(F32(-1.0), _fmul(self.a1, self.y1)),
                _fmul(self.a2, self.y2),
            ),
        )
        self.x2 = self.x1
        self.x1 = input_value
        self.y2 = self.y1
        self.y1 = output
        return output


class _Nlms:
    def __init__(self, algorithm_id: int) -> None:
        if algorithm_id not in (1, 2, 3):
            raise ValueError(f"NLMS algorithm must be A1-A3, got A{algorithm_id}")
        self.algorithm_id = algorithm_id
        self.weights = np.zeros(2, dtype=np.float32)
        self.oscillator_cos = F32(1.0)
        self.oscillator_sin = F32(0.0)
        self.frequency_hz = INITIAL_HZ
        self.last_frequency_used_hz = INITIAL_HZ
        self.step_cos = F32(0.0)
        self.step_sin = F32(0.0)
        self._update_oscillator_step()

        self.input_ring = np.zeros(TRACKER_WINDOW, dtype=np.float32)
        self.ring_write = 0
        self.ring_count = 0
        self.block_c = F32(0.0)
        self.block_s = F32(0.0)
        self.block_energy = F32(0.0)
        self.block_count = 0
        self.residual_ratio = F32(0.0)
        self.blocks_since_tracker = 0xFFFF
        self.low_count = 0
        self.tracker_calls = 0
        self.state = STATE_FIXED if algorithm_id == 1 else STATE_FAST
        self.last_state_used = self.state

        grid_indices = np.arange(GRID_SIZE, dtype=np.float32)
        frequencies = F32(SEARCH_LOW_HZ) + F32(
            grid_indices * SEARCH_STEP_HZ
        )
        angles = F32(F32(TWO_PI * frequencies) / FS_HZ)
        self.tracker_coefficients = F32(F32(2.0) * np.cos(angles))
        window_indices = np.arange(TRACKER_WINDOW, dtype=np.float32)
        window_angles = F32(
            F32(TWO_PI * window_indices) / F32(TRACKER_WINDOW - 1)
        )
        self.tracker_window = F32(
            F32(0.5) - F32(F32(0.5) * np.cos(window_angles))
        )

    def _update_oscillator_step(self) -> None:
        omega = _fdiv(_fmul(TWO_PI, self.frequency_hz), FS_HZ)
        self.step_cos = table_cos(omega)
        self.step_sin = table_sin(omega)

    def _ring_mean(self) -> F32:
        total = F32(0.0)
        for index in range(self.ring_count):
            total = _fadd(total, self.input_ring[index])
        return _fdiv(total, F32(self.ring_count))

    def _estimate_frequency(self) -> F32:
        if self.ring_count < TRACKER_MIN_SAMPLES:
            return INITIAL_HZ
        mean = self._ring_mean()
        best_power = F32(-1.0)
        best_frequency = INITIAL_HZ
        for grid_index in range(GRID_SIZE):
            q1 = F32(0.0)
            q2 = F32(0.0)
            coefficient = self.tracker_coefficients[grid_index]
            for sample_index in range(self.ring_count):
                if self.ring_count < TRACKER_WINDOW:
                    ring_index = sample_index
                else:
                    ring_index = (self.ring_write + sample_index) % TRACKER_WINDOW
                window_index = sample_index + TRACKER_WINDOW - self.ring_count
                sample = _fmul(
                    _fsub(self.input_ring[ring_index], mean),
                    self.tracker_window[window_index],
                )
                q0 = _fadd(_fsub(_fmul(coefficient, q1), q2), sample)
                q2 = q1
                q1 = q0
            power = _fsub(
                _fadd(_fmul(q1, q1), _fmul(q2, q2)),
                _fmul(_fmul(coefficient, q1), q2),
            )
            if power > best_power:
                best_power = power
                best_frequency = _fadd(
                    SEARCH_LOW_HZ,
                    _fmul(SEARCH_STEP_HZ, F32(grid_index)),
                )
        return best_frequency

    @staticmethod
    def _state_interval(state: int) -> int:
        if state == STATE_FAST:
            return 1
        if state == STATE_MID:
            return 3
        return 12

    def _update_scheduler(self) -> None:
        ratio = self.residual_ratio
        if self.state == STATE_FAST:
            self.low_count = self.low_count + 1 if ratio < F32(0.035) else 0
            if self.low_count >= 3:
                self.state = STATE_MID
                self.low_count = 0
            return
        if self.state == STATE_MID:
            if ratio > F32(0.055):
                self.state = STATE_FAST
                self.low_count = 0
                return
            self.low_count = self.low_count + 1 if ratio < F32(0.025) else 0
            if self.low_count >= 3:
                self.state = STATE_SLOW
                self.low_count = 0
            return
        if ratio > F32(0.060):
            self.state = STATE_FAST
        elif ratio > F32(0.040):
            self.state = STATE_MID

    def _run_tracker(self) -> None:
        candidate = self._estimate_frequency()
        self.frequency_hz = _fadd(
            _fmul(FREQUENCY_OLD_WEIGHT, self.frequency_hz),
            _fmul(_fsub(F32(1.0), FREQUENCY_OLD_WEIGHT), candidate),
        )
        self.tracker_calls += 1
        self.blocks_since_tracker = 0
        self._update_oscillator_step()

    def _finish_block(self) -> None:
        numerator = _fmul(
            F32(2.0),
            _fadd(
                _fmul(self.block_c, self.block_c),
                _fmul(self.block_s, self.block_s),
            ),
        )
        denominator = _fadd(
            _fmul(F32(BLOCK_SIZE), self.block_energy),
            EPSILON,
        )
        raw_ratio = _fdiv(numerator, denominator)
        if raw_ratio > F32(1.0):
            raw_ratio = F32(1.0)
        self.residual_ratio = _fadd(
            _fmul(
                _fsub(F32(1.0), RESIDUAL_NEW_WEIGHT),
                self.residual_ratio,
            ),
            _fmul(RESIDUAL_NEW_WEIGHT, raw_ratio),
        )
        self.block_c = F32(0.0)
        self.block_s = F32(0.0)
        self.block_energy = F32(0.0)
        self.block_count = 0

        if self.blocks_since_tracker < 0xFFFF:
            self.blocks_since_tracker += 1
        if self.algorithm_id == 1:
            self.state = STATE_FIXED
            return
        if self.algorithm_id == 2:
            self.state = STATE_FAST
            self._run_tracker()
            return
        self._update_scheduler()
        if self.blocks_since_tracker >= self._state_interval(self.state):
            self._run_tracker()

    def process(self, input_value: F32) -> F32:
        self.last_frequency_used_hz = self.frequency_hz
        self.last_state_used = self.state
        self.input_ring[self.ring_write] = input_value
        self.ring_write = (self.ring_write + 1) % TRACKER_WINDOW
        if self.ring_count < TRACKER_WINDOW:
            self.ring_count += 1

        estimate = _fadd(
            _fmul(self.weights[0], self.oscillator_cos),
            _fmul(self.weights[1], self.oscillator_sin),
        )
        error = _fsub(input_value, estimate)
        denominator = _fadd(
            _fadd(
                _fmul(self.oscillator_cos, self.oscillator_cos),
                _fmul(self.oscillator_sin, self.oscillator_sin),
            ),
            EPSILON,
        )
        update_0 = _fdiv(
            _fmul(
                _fmul(NLMS_MU, error),
                self.oscillator_cos,
            ),
            denominator,
        )
        update_1 = _fdiv(
            _fmul(
                _fmul(NLMS_MU, error),
                self.oscillator_sin,
            ),
            denominator,
        )
        self.weights[0] = _fadd(self.weights[0], update_0)
        self.weights[1] = _fadd(self.weights[1], update_1)

        self.block_c = _fadd(
            self.block_c,
            _fmul(error, self.oscillator_cos),
        )
        self.block_s = _fadd(
            self.block_s,
            _fmul(error, self.oscillator_sin),
        )
        self.block_energy = _fadd(
            self.block_energy,
            _fmul(error, error),
        )
        self.block_count += 1

        next_cos = _fsub(
            _fmul(self.oscillator_cos, self.step_cos),
            _fmul(self.oscillator_sin, self.step_sin),
        )
        next_sin = _fadd(
            _fmul(self.oscillator_sin, self.step_cos),
            _fmul(self.oscillator_cos, self.step_sin),
        )
        self.oscillator_cos = next_cos
        self.oscillator_sin = next_sin
        if self.block_count >= BLOCK_SIZE:
            self._finish_block()
        return error


def run_formal_algorithm(observed: Array, algorithm_id: int) -> FormalAlgorithmResult:
    values = np.asarray(observed, dtype=np.float32)
    sample_count = values.size
    output = np.empty(sample_count, dtype=np.float32)
    frequency_used = np.empty(sample_count, dtype=np.float32)
    frequency_next = np.empty(sample_count, dtype=np.float32)
    residual = np.empty(sample_count, dtype=np.float32)
    tracker_calls = np.empty(sample_count, dtype=np.uint32)
    state_used = np.empty(sample_count, dtype=np.uint8)
    state_next = np.empty(sample_count, dtype=np.uint8)

    if algorithm_id == 0:
        algorithm: _Notch | _Nlms = _Notch()
    elif algorithm_id in (1, 2, 3):
        algorithm = _Nlms(algorithm_id)
    else:
        raise ValueError(f"Unsupported algorithm id: {algorithm_id}")

    for index, input_value in enumerate(values):
        output[index] = algorithm.process(F32(input_value))
        if algorithm_id == 0:
            frequency_used[index] = F32(50.0)
            frequency_next[index] = F32(50.0)
            residual[index] = F32(0.0)
            tracker_calls[index] = 0
            state_used[index] = STATE_FIXED
            state_next[index] = STATE_FIXED
        else:
            assert isinstance(algorithm, _Nlms)
            frequency_used[index] = algorithm.last_frequency_used_hz
            frequency_next[index] = algorithm.frequency_hz
            residual[index] = algorithm.residual_ratio
            tracker_calls[index] = algorithm.tracker_calls
            state_used[index] = algorithm.last_state_used
            state_next[index] = algorithm.state
    return FormalAlgorithmResult(
        output=output,
        frequency_used_hz=frequency_used,
        frequency_next_hz=frequency_next,
        residual_ratio=residual,
        tracker_calls=tracker_calls,
        state_used=state_used,
        state_next=state_next,
    )
