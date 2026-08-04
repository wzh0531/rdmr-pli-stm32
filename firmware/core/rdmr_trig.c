#include "rdmr_trig.h"
#include "rdmr_trig_values.h"

#include <stdint.h>

#define RDMR_TRIG_HALF_PI          1.57079632679489661923f
#define RDMR_TRIG_TWO_PI           6.28318530717958647692f
#define RDMR_TRIG_TABLE_STEPS      2048U
#define RDMR_TRIG_RADIANS_TO_INDEX \
    ((float)RDMR_TRIG_TABLE_STEPS / RDMR_TRIG_TWO_PI)

float rdmr_trig_sin(float radians)
{
    float scaled;
    float fraction;
    float lower;
    uint32_t index;

    while (radians < 0.0f) {
        radians += RDMR_TRIG_TWO_PI;
    }
    while (radians >= RDMR_TRIG_TWO_PI) {
        radians -= RDMR_TRIG_TWO_PI;
    }

    scaled = radians * RDMR_TRIG_RADIANS_TO_INDEX;
    index = (uint32_t)scaled;
    if (index >= RDMR_TRIG_TABLE_STEPS) {
        index = 0U;
        fraction = 0.0f;
    } else {
        fraction = scaled - (float)index;
    }
    lower = rdmr_sine_table[index];
    return lower + fraction * (rdmr_sine_table[index + 1U] - lower);
}

float rdmr_trig_cos(float radians)
{
    return rdmr_trig_sin(radians + RDMR_TRIG_HALF_PI);
}
