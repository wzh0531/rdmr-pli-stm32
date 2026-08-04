#ifndef RDMR_PLI_H
#define RDMR_PLI_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RDMR_FS_HZ                 1000.0f

/*
 * Phase-3 host tuning overrides these values with compiler definitions.
 * The defaults remain the protocol v0.3.0 baseline until the selected
 * configuration is frozen.
 */
#ifndef RDMR_BLOCK_SIZE
#define RDMR_BLOCK_SIZE            50U
#endif
#ifndef RDMR_INTERVAL_FAST
#define RDMR_INTERVAL_FAST         1U
#endif
#ifndef RDMR_INTERVAL_MID
#define RDMR_INTERVAL_MID          3U
#endif
#ifndef RDMR_INTERVAL_SLOW
#define RDMR_INTERVAL_SLOW         12U
#endif
#ifndef RDMR_RESIDUAL_NEW_WEIGHT
#define RDMR_RESIDUAL_NEW_WEIGHT  0.30f
#endif
#ifndef RDMR_THRESHOLD_SCALE
#define RDMR_THRESHOLD_SCALE       1.0f
#endif

#define RDMR_TRACKER_WINDOW        400U
#define RDMR_TRACKER_MIN_SAMPLES   100U
#define RDMR_GRID_SIZE             201U

typedef enum {
    RDMR_MODE_FIXED_REFERENCE = 0,
    RDMR_MODE_FULL_RATE = 1,
    RDMR_MODE_RESIDUAL_MULTIRATE = 2
} rdmr_mode_t;

typedef enum {
    RDMR_STATE_FAST = 0,
    RDMR_STATE_MID = 1,
    RDMR_STATE_SLOW = 2,
    RDMR_STATE_FIXED = 3
} rdmr_state_t;

typedef struct {
    float weights[2];
    float oscillator_cos;
    float oscillator_sin;
    float step_cos;
    float step_sin;
    float frequency_hz;
    float last_frequency_used_hz;

    float input_ring[RDMR_TRACKER_WINDOW];
    uint16_t ring_write;
    uint16_t ring_count;

    float block_c;
    float block_s;
    float block_energy;
    uint16_t block_count;

    float residual_ratio;
    uint16_t blocks_since_tracker;
    uint16_t low_count;
    uint32_t tracker_calls;
    rdmr_mode_t mode;
    rdmr_state_t state;
    rdmr_state_t last_state_used;
} rdmr_pli_t;

typedef struct {
    float frequency_used_hz;
    float frequency_next_hz;
    float residual_ratio;
    uint32_t tracker_calls;
    rdmr_state_t state_used;
    rdmr_state_t state_next;
} rdmr_telemetry_t;

void rdmr_global_init(void);
void rdmr_init(rdmr_pli_t *instance, rdmr_mode_t mode);
float rdmr_process(rdmr_pli_t *instance, float input);
void rdmr_get_telemetry(
    const rdmr_pli_t *instance,
    rdmr_telemetry_t *telemetry
);

#ifdef __cplusplus
}
#endif

#endif
