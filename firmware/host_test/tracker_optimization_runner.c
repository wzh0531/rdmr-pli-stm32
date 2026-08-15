#include "../core/rdmr_algorithm.h"

#include <math.h>
#include <stdint.h>

#if defined(_WIN32)
#define OPTIMIZATION_EXPORT __declspec(dllexport)
#else
#define OPTIMIZATION_EXPORT
#endif

OPTIMIZATION_EXPORT int optimization_run_external(
    int algorithm_id,
    uint32_t sample_count,
    const float *input,
    float *output,
    float *estimated_frequency,
    float *residual_ratio,
    uint32_t *tracker_calls,
    uint32_t *tracker_searches,
    uint32_t *tracker_grid_evaluations,
    uint8_t *state
)
{
    rdmr_algorithm_t algorithm;
    rdmr_algorithm_telemetry_t telemetry;
    uint32_t index;

    if (
        (algorithm_id < (int)RDMR_ALGORITHM_A0_FIXED_NOTCH)
        || (algorithm_id > (int)RDMR_ALGORITHM_B4_TWO_STATE_RESIDUAL)
        || (sample_count == 0U)
        || (input == 0)
        || (output == 0)
        || (estimated_frequency == 0)
        || (residual_ratio == 0)
        || (tracker_calls == 0)
        || (tracker_searches == 0)
        || (tracker_grid_evaluations == 0)
        || (state == 0)
    ) {
        return 0;
    }
    if (
        rdmr_algorithm_init(
            &algorithm,
            (rdmr_algorithm_id_t)algorithm_id
        ) == 0
    ) {
        return 0;
    }
    for (index = 0U; index < sample_count; ++index) {
        output[index] = rdmr_algorithm_process(&algorithm, input[index]);
        rdmr_algorithm_get_telemetry(&algorithm, &telemetry);
        estimated_frequency[index] = telemetry.frequency_used_hz;
        residual_ratio[index] = telemetry.residual_ratio;
        tracker_calls[index] = telemetry.tracker_calls;
        tracker_searches[index] = telemetry.tracker_searches;
        tracker_grid_evaluations[index] =
            telemetry.tracker_grid_evaluations;
        state[index] = (uint8_t)telemetry.state_next;
        if (
            !isfinite((double)output[index])
            || !isfinite((double)estimated_frequency[index])
            || !isfinite((double)residual_ratio[index])
        ) {
            return -1;
        }
    }
    return 1;
}

OPTIMIZATION_EXPORT uint32_t optimization_tracker_search_mode(void)
{
    return (uint32_t)RDMR_TRACKER_SEARCH_MODE;
}

OPTIMIZATION_EXPORT uint32_t optimization_tracker_max_grid_evaluations(void)
{
#if RDMR_TRACKER_SEARCH_MODE == RDMR_TRACKER_SEARCH_HIERARCHICAL
    return RDMR_TRACKER_HIERARCHICAL_MAX_EVAL;
#else
    return RDMR_GRID_SIZE;
#endif
}

OPTIMIZATION_EXPORT uint32_t optimization_firmware_revision(void)
{
    return RDMR_FIRMWARE_REVISION;
}
