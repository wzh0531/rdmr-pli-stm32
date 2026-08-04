#include "../core/rdmr_algorithm.h"
#include "../core/rdmr_signal_protocol.h"

#include <math.h>
#include <stdint.h>

#if defined(_WIN32)
#define PHASE4_EXPORT __declspec(dllexport)
#else
#define PHASE4_EXPORT
#endif

PHASE4_EXPORT int phase4_run(
    int algorithm_id,
    int trajectory_id,
    int near_line_id,
    int noise_id,
    uint32_t seed,
    float pli_amplitude,
    uint32_t sample_count,
    float *input,
    float *clean,
    float *output,
    float *true_frequency,
    float *estimated_frequency,
    float *residual_ratio,
    uint32_t *tracker_calls,
    uint8_t *state
)
{
    rdmr_experiment_config_t config;
    rdmr_signal_generator_t generator;
    rdmr_signal_sample_t sample;
    rdmr_algorithm_t algorithm;
    rdmr_algorithm_telemetry_t telemetry;
    uint32_t index;

    if (
        (algorithm_id < (int)RDMR_ALGORITHM_A0_FIXED_NOTCH)
        || (algorithm_id > (int)RDMR_ALGORITHM_A3_RESIDUAL_MULTIRATE)
        || (trajectory_id < (int)RDMR_TRAJECTORY_F0)
        || (trajectory_id > (int)RDMR_TRAJECTORY_F5)
        || (near_line_id < (int)RDMR_NEAR_LINE_N0)
        || (near_line_id > (int)RDMR_NEAR_LINE_N3)
        || (noise_id < (int)RDMR_NOISE_NONE)
        || (noise_id > (int)RDMR_NOISE_SNR_10_DB)
        || (sample_count == 0U)
        || (input == 0)
        || (clean == 0)
        || (output == 0)
        || (true_frequency == 0)
        || (estimated_frequency == 0)
        || (residual_ratio == 0)
        || (tracker_calls == 0)
        || (state == 0)
    ) {
        return 0;
    }

    config.algorithm_id = (rdmr_algorithm_id_t)algorithm_id;
    config.trajectory_id = (rdmr_trajectory_id_t)trajectory_id;
    config.near_line_id = (rdmr_near_line_id_t)near_line_id;
    config.noise_id = (rdmr_noise_id_t)noise_id;
    config.seed = seed;
    config.sample_count = sample_count;
    config.log_schema_version = RDMR_LOG_SCHEMA_VERSION_ID;
    config.sample_rate_hz = RDMR_PROTOCOL_FS_HZ;
    config.pli_amplitude = pli_amplitude;
    rdmr_signal_init(&generator, &config);
    if (
        rdmr_algorithm_init(
            &algorithm,
            (rdmr_algorithm_id_t)algorithm_id
        ) == 0
    ) {
        return 0;
    }

    for (index = 0U; index < sample_count; ++index) {
        if (rdmr_signal_next(&generator, &sample) == 0) {
            return 0;
        }
        input[index] = sample.input;
        clean[index] = sample.clean;
        true_frequency[index] = sample.true_frequency_hz;
        output[index] = rdmr_algorithm_process(&algorithm, sample.input);
        rdmr_algorithm_get_telemetry(&algorithm, &telemetry);
        estimated_frequency[index] = telemetry.frequency_used_hz;
        residual_ratio[index] = telemetry.residual_ratio;
        tracker_calls[index] = telemetry.tracker_calls;
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

PHASE4_EXPORT uint32_t phase4_firmware_revision(void)
{
    return RDMR_FIRMWARE_REVISION;
}
