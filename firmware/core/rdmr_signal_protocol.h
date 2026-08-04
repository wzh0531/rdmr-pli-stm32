#ifndef RDMR_SIGNAL_PROTOCOL_H
#define RDMR_SIGNAL_PROTOCOL_H

#include <stdint.h>

#include "rdmr_experiment_config.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float clean;
    float interference;
    float noise;
    float input;
    float true_frequency_hz;
} rdmr_signal_sample_t;

typedef struct {
    rdmr_experiment_config_t config;
    uint32_t sample_index;
    uint32_t frequency_rng;
    uint32_t noise_rng;
    uint32_t phase_rng;
    float line_phase_rad;
    float line_cos;
    float line_sin;
    float line_step_cos;
    float line_step_sin;
    float line_step_frequency_hz;
    float f5_frequency_hz;
    float clean_7_cos;
    float clean_7_sin;
    float clean_13_cos;
    float clean_13_sin;
    float near_42_cos;
    float near_42_sin;
    float near_58_cos;
    float near_58_sin;
} rdmr_signal_generator_t;

void rdmr_signal_init(
    rdmr_signal_generator_t *generator,
    const rdmr_experiment_config_t *config
);

int rdmr_signal_next(
    rdmr_signal_generator_t *generator,
    rdmr_signal_sample_t *sample
);

float rdmr_true_frequency(
    rdmr_signal_generator_t *generator,
    uint32_t sample_index
);

#ifdef __cplusplus
}
#endif

#endif
