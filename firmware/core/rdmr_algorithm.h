#ifndef RDMR_ALGORITHM_H
#define RDMR_ALGORITHM_H

#include "rdmr_experiment_config.h"
#include "rdmr_pli.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float x1;
    float x2;
    float y1;
    float y2;
    float b0;
    float b1;
    float b2;
    float a1;
    float a2;
} rdmr_notch_t;

typedef struct {
    rdmr_algorithm_id_t algorithm_id;
    rdmr_notch_t notch;
    rdmr_pli_t nlms;
} rdmr_algorithm_t;

typedef struct {
    float frequency_used_hz;
    float frequency_next_hz;
    float residual_ratio;
    uint32_t tracker_calls;
    rdmr_state_t state_used;
    rdmr_state_t state_next;
} rdmr_algorithm_telemetry_t;

int rdmr_algorithm_init(
    rdmr_algorithm_t *instance,
    rdmr_algorithm_id_t algorithm_id
);

float rdmr_algorithm_process(
    rdmr_algorithm_t *instance,
    float input
);

void rdmr_algorithm_get_telemetry(
    const rdmr_algorithm_t *instance,
    rdmr_algorithm_telemetry_t *telemetry
);

#ifdef __cplusplus
}
#endif

#endif
