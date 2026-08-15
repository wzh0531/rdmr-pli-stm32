#include "rdmr_pli.h"
#include "rdmr_memory.h"
#include "rdmr_tracker_tables.h"
#include "rdmr_trig.h"

#include <math.h>
#include <stddef.h>

#define RDMR_PI                     3.14159265358979323846f
#define RDMR_TWO_PI                 (2.0f * RDMR_PI)
#define RDMR_INITIAL_HZ             50.0f
#define RDMR_SEARCH_LOW_HZ          45.0f
#define RDMR_SEARCH_STEP_HZ         0.05f
#define RDMR_NLMS_MU                0.08f
#define RDMR_FREQ_OLD_WEIGHT        0.25f
#define RDMR_EPSILON                1.0e-9f

static void update_oscillator_step(rdmr_pli_t *instance)
{
    const float omega = RDMR_TWO_PI * instance->frequency_hz / RDMR_FS_HZ;
    instance->step_cos = rdmr_trig_cos(omega);
    instance->step_sin = rdmr_trig_sin(omega);
}

void rdmr_global_init(void)
{
    /* Tables are generated offline and stored as read-only flash data. */
}

void rdmr_init(rdmr_pli_t *instance, rdmr_mode_t mode)
{
    if (instance == NULL) {
        return;
    }

    rdmr_global_init();
    rdmr_zero_bytes(instance, (uint32_t)sizeof(*instance));
    instance->oscillator_cos = 1.0f;
    instance->frequency_hz = RDMR_INITIAL_HZ;
    instance->last_frequency_used_hz = RDMR_INITIAL_HZ;
    instance->mode = mode;
    instance->state =
        (mode == RDMR_MODE_FIXED_REFERENCE)
            ? RDMR_STATE_FIXED
            : RDMR_STATE_FAST;
    instance->last_state_used = instance->state;
    instance->blocks_since_tracker = 0xFFFFU;
    update_oscillator_step(instance);
}

static float ring_mean(const rdmr_pli_t *instance)
{
    float sum = 0.0f;
    uint16_t index;

    for (index = 0U; index < instance->ring_count; ++index) {
        sum += instance->input_ring[index];
    }
    return sum / (float)instance->ring_count;
}

static float grid_power(
    const rdmr_pli_t *instance,
    float mean,
    uint16_t grid_index
)
{
    float q1 = 0.0f;
    float q2 = 0.0f;
    const float coefficient = rdmr_tracker_coefficients[grid_index];
    uint16_t sample_index;

    for (sample_index = 0U; sample_index < instance->ring_count; ++sample_index) {
        uint16_t ring_index;
        float sample;
        float q0;

        if (instance->ring_count < RDMR_TRACKER_WINDOW) {
            ring_index = sample_index;
        } else {
            ring_index =
                (uint16_t)(
                    (instance->ring_write + sample_index)
                    % RDMR_TRACKER_WINDOW
                );
        }
        sample =
            (instance->input_ring[ring_index] - mean)
            * rdmr_tracker_window[
                (uint16_t)(
                    sample_index
                    + RDMR_TRACKER_WINDOW
                    - instance->ring_count
                )
            ];
        q0 = coefficient * q1 - q2 + sample;
        q2 = q1;
        q1 = q0;
    }
    return q1 * q1 + q2 * q2 - coefficient * q1 * q2;
}

static void consider_grid_point(
    const rdmr_pli_t *instance,
    float mean,
    uint16_t grid_index,
    float *best_power,
    uint16_t *best_index
)
{
    const float power = grid_power(instance, mean, grid_index);

    if (power > *best_power) {
        *best_power = power;
        *best_index = grid_index;
    }
}

static float estimate_frequency(rdmr_pli_t *instance)
{
    float best_power = -1.0f;
    float mean;
    uint16_t best_index = 100U;
    uint16_t grid_index;
    uint16_t evaluations = 0U;

    if (instance->ring_count < RDMR_TRACKER_MIN_SAMPLES) {
        return RDMR_INITIAL_HZ;
    }

    mean = ring_mean(instance);
#if RDMR_TRACKER_SEARCH_MODE == RDMR_TRACKER_SEARCH_HIERARCHICAL
    for (
        grid_index = 0U;
        grid_index < RDMR_GRID_SIZE;
        grid_index = (uint16_t)(grid_index + RDMR_TRACKER_COARSE_STRIDE)
    ) {
        consider_grid_point(
            instance,
            mean,
            grid_index,
            &best_power,
            &best_index
        );
        evaluations += 1U;
    }

    {
        uint16_t fine_start;
        uint16_t fine_end;

        if (best_index < RDMR_TRACKER_FINE_RADIUS) {
            fine_start = 0U;
        } else if (
            best_index
            > (uint16_t)(
                RDMR_GRID_SIZE
                - 1U
                - RDMR_TRACKER_FINE_RADIUS
            )
        ) {
            fine_start =
                (uint16_t)(RDMR_GRID_SIZE - RDMR_TRACKER_FINE_POINTS);
        } else {
            fine_start =
                (uint16_t)(best_index - RDMR_TRACKER_FINE_RADIUS);
        }
        fine_end =
            (uint16_t)(fine_start + RDMR_TRACKER_FINE_POINTS);
        for (grid_index = fine_start; grid_index < fine_end; ++grid_index) {
            consider_grid_point(
                instance,
                mean,
                grid_index,
                &best_power,
                &best_index
            );
            evaluations += 1U;
        }
    }
#else
    for (grid_index = 0U; grid_index < RDMR_GRID_SIZE; ++grid_index) {
        consider_grid_point(
            instance,
            mean,
            grid_index,
            &best_power,
            &best_index
        );
        evaluations += 1U;
    }
#endif

    instance->tracker_grid_evaluations += evaluations;
    return
        RDMR_SEARCH_LOW_HZ
        + RDMR_SEARCH_STEP_HZ * (float)best_index;
}

static uint16_t state_interval(rdmr_state_t state)
{
    if (state == RDMR_STATE_FAST) {
        return RDMR_INTERVAL_FAST;
    }
    if (state == RDMR_STATE_MID) {
        return RDMR_INTERVAL_MID;
    }
    return RDMR_INTERVAL_SLOW;
}

static void update_scheduler(rdmr_pli_t *instance)
{
    const float ratio = instance->residual_ratio;

    if (instance->state == RDMR_STATE_FAST) {
        instance->low_count =
            (ratio < (0.035f * RDMR_THRESHOLD_SCALE))
                ? (uint16_t)(instance->low_count + 1U)
                : 0U;
        if (instance->low_count >= 3U) {
            instance->state = RDMR_STATE_MID;
            instance->low_count = 0U;
        }
        return;
    }

    if (instance->state == RDMR_STATE_MID) {
        if (ratio > (0.055f * RDMR_THRESHOLD_SCALE)) {
            instance->state = RDMR_STATE_FAST;
            instance->low_count = 0U;
            return;
        }
        instance->low_count =
            (ratio < (0.025f * RDMR_THRESHOLD_SCALE))
                ? (uint16_t)(instance->low_count + 1U)
                : 0U;
        if (instance->low_count >= 3U) {
            instance->state = RDMR_STATE_SLOW;
            instance->low_count = 0U;
        }
        return;
    }

    if (ratio > (0.060f * RDMR_THRESHOLD_SCALE)) {
        instance->state = RDMR_STATE_FAST;
    } else if (ratio > (0.040f * RDMR_THRESHOLD_SCALE)) {
        instance->state = RDMR_STATE_MID;
    }
}

static void run_tracker(rdmr_pli_t *instance)
{
    if (instance->ring_count >= RDMR_TRACKER_MIN_SAMPLES) {
        instance->tracker_searches += 1U;
    }
    const float candidate = estimate_frequency(instance);
    instance->frequency_hz =
        RDMR_FREQ_OLD_WEIGHT * instance->frequency_hz
        + (1.0f - RDMR_FREQ_OLD_WEIGHT) * candidate;
    instance->tracker_calls += 1U;
    instance->blocks_since_tracker = 0U;
    update_oscillator_step(instance);
}

static void finish_block(rdmr_pli_t *instance)
{
    float raw_ratio =
        2.0f
        * (
            instance->block_c * instance->block_c
            + instance->block_s * instance->block_s
        )
        / (
            (float)RDMR_BLOCK_SIZE
            * instance->block_energy
            + RDMR_EPSILON
        );

    if (raw_ratio > 1.0f) {
        raw_ratio = 1.0f;
    }
    instance->residual_ratio =
        (1.0f - RDMR_RESIDUAL_NEW_WEIGHT) * instance->residual_ratio
        + RDMR_RESIDUAL_NEW_WEIGHT * raw_ratio;
    instance->block_c = 0.0f;
    instance->block_s = 0.0f;
    instance->block_energy = 0.0f;
    instance->block_count = 0U;

    if (instance->blocks_since_tracker < 0xFFFFU) {
        instance->blocks_since_tracker += 1U;
    }

    if (instance->mode == RDMR_MODE_FIXED_REFERENCE) {
        instance->state = RDMR_STATE_FIXED;
        return;
    }
    if (instance->mode == RDMR_MODE_FULL_RATE) {
        instance->state = RDMR_STATE_FAST;
        run_tracker(instance);
        return;
    }

    if (
        (instance->mode == RDMR_MODE_FIXED_INTERVAL_3)
        || (instance->mode == RDMR_MODE_FIXED_INTERVAL_12)
        || (instance->mode == RDMR_MODE_FIXED_INTERVAL_4)
    ) {
        uint16_t interval = 4U;
        if (instance->mode == RDMR_MODE_FIXED_INTERVAL_3) {
            interval = 3U;
        } else if (instance->mode == RDMR_MODE_FIXED_INTERVAL_12) {
            interval = 12U;
        }
        instance->state = RDMR_STATE_FIXED;
        if (instance->blocks_since_tracker >= interval) {
            run_tracker(instance);
        }
        return;
    }

    if (instance->mode == RDMR_MODE_TWO_STATE_RESIDUAL) {
        if (instance->residual_ratio > (0.055f * RDMR_THRESHOLD_SCALE)) {
            instance->state = RDMR_STATE_FAST;
        } else if (instance->residual_ratio < (0.025f * RDMR_THRESHOLD_SCALE)) {
            instance->state = RDMR_STATE_SLOW;
        }
        if (instance->blocks_since_tracker >= state_interval(instance->state)) {
            run_tracker(instance);
        }
        return;
    }

    update_scheduler(instance);
    if (
        instance->blocks_since_tracker
        >= state_interval(instance->state)
    ) {
        run_tracker(instance);
    }
}

float rdmr_process(rdmr_pli_t *instance, float input)
{
    float estimate;
    float error;
    float denominator;
    float next_cos;
    float next_sin;

    if (instance == NULL) {
        return input;
    }

    instance->last_frequency_used_hz = instance->frequency_hz;
    instance->last_state_used = instance->state;
    instance->input_ring[instance->ring_write] = input;
    instance->ring_write =
        (uint16_t)((instance->ring_write + 1U) % RDMR_TRACKER_WINDOW);
    if (instance->ring_count < RDMR_TRACKER_WINDOW) {
        instance->ring_count += 1U;
    }

    estimate =
        instance->weights[0] * instance->oscillator_cos
        + instance->weights[1] * instance->oscillator_sin;
    error = input - estimate;
    denominator =
        instance->oscillator_cos * instance->oscillator_cos
        + instance->oscillator_sin * instance->oscillator_sin
        + RDMR_EPSILON;
    instance->weights[0] +=
        RDMR_NLMS_MU
        * error
        * instance->oscillator_cos
        / denominator;
    instance->weights[1] +=
        RDMR_NLMS_MU
        * error
        * instance->oscillator_sin
        / denominator;

    instance->block_c += error * instance->oscillator_cos;
    instance->block_s += error * instance->oscillator_sin;
    instance->block_energy += error * error;
    instance->block_count += 1U;

    next_cos =
        instance->oscillator_cos * instance->step_cos
        - instance->oscillator_sin * instance->step_sin;
    next_sin =
        instance->oscillator_sin * instance->step_cos
        + instance->oscillator_cos * instance->step_sin;
    instance->oscillator_cos = next_cos;
    instance->oscillator_sin = next_sin;

    if (instance->block_count >= RDMR_BLOCK_SIZE) {
        finish_block(instance);
    }
    return error;
}

void rdmr_get_telemetry(
    const rdmr_pli_t *instance,
    rdmr_telemetry_t *telemetry
)
{
    if ((instance == NULL) || (telemetry == NULL)) {
        return;
    }
    telemetry->frequency_used_hz = instance->last_frequency_used_hz;
    telemetry->frequency_next_hz = instance->frequency_hz;
    telemetry->residual_ratio = instance->residual_ratio;
    telemetry->tracker_calls = instance->tracker_calls;
    telemetry->tracker_searches = instance->tracker_searches;
    telemetry->tracker_grid_evaluations =
        instance->tracker_grid_evaluations;
    telemetry->state_used = instance->last_state_used;
    telemetry->state_next = instance->state;
}
