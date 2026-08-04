"""Float32 sine-table interpolation matching firmware/core/rdmr_trig.c."""

from __future__ import annotations

import numpy as np


F32 = np.float32
PI = F32(np.pi)
HALF_PI = F32(np.pi / 2.0)
TWO_PI = F32(2.0 * np.pi)
TABLE_STEPS = 2048
RADIANS_TO_INDEX = F32(F32(TABLE_STEPS) / TWO_PI)
_INDICES = np.arange(TABLE_STEPS + 1, dtype=np.float32)
SINE_TABLE = np.float32(
    np.sin(F32(F32(TWO_PI * _INDICES) / F32(TABLE_STEPS)))
)


def table_sin(radians: F32) -> F32:
    radians = F32(radians)
    while radians < F32(0.0):
        radians = F32(radians + TWO_PI)
    while radians >= TWO_PI:
        radians = F32(radians - TWO_PI)

    scaled = F32(radians * RADIANS_TO_INDEX)
    index = int(scaled)
    if index >= TABLE_STEPS:
        index = 0
        fraction = F32(0.0)
    else:
        fraction = F32(scaled - F32(index))
    lower = SINE_TABLE[index]
    return F32(
        lower
        + F32(fraction * F32(SINE_TABLE[index + 1] - lower))
    )


def table_cos(radians: F32) -> F32:
    return table_sin(F32(radians + HALF_PI))
