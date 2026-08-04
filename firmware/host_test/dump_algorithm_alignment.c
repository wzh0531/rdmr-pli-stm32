#include "../core/rdmr_algorithm.h"
#include "../core/rdmr_signal_protocol.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>

#define ALIGNMENT_SAMPLE_COUNT 4202U

static int should_emit(uint32_t sample_index)
{
    if ((sample_index % 50U) == 49U) {
        return 1;
    }
    if (
        (sample_index == 0U)
        || (sample_index == 1U)
        || (sample_index == 2U)
        || (sample_index == 3998U)
        || (sample_index == 3999U)
        || (sample_index == 4000U)
        || (sample_index == 4001U)
        || (sample_index == 4201U)
    ) {
        return 1;
    }
    return 0;
}

static int run_algorithm(rdmr_algorithm_id_t algorithm_id)
{
    rdmr_experiment_config_t config;
    rdmr_signal_generator_t generator;
    rdmr_signal_sample_t signal_sample;
    rdmr_algorithm_t algorithm;
    rdmr_algorithm_telemetry_t telemetry;
    uint32_t sample_index;

    config.algorithm_id = algorithm_id;
    config.trajectory_id = RDMR_TRAJECTORY_F1;
    config.near_line_id = RDMR_NEAR_LINE_N0;
    config.noise_id = RDMR_NOISE_SNR_20_DB;
    config.seed = 0U;
    config.sample_count = ALIGNMENT_SAMPLE_COUNT;
    config.log_schema_version = RDMR_LOG_SCHEMA_VERSION_ID;
    config.sample_rate_hz = RDMR_PROTOCOL_FS_HZ;
    config.pli_amplitude = 0.50f;

    rdmr_signal_init(&generator, &config);
    if (rdmr_algorithm_init(&algorithm, algorithm_id) == 0) {
        return 0;
    }
    for (sample_index = 0U; sample_index < config.sample_count; ++sample_index) {
        float output;
        if (rdmr_signal_next(&generator, &signal_sample) == 0) {
            return 0;
        }
        output = rdmr_algorithm_process(&algorithm, signal_sample.input);
        rdmr_algorithm_get_telemetry(&algorithm, &telemetry);
        if (
            !isfinite(output)
            || !isfinite(telemetry.frequency_used_hz)
            || !isfinite(telemetry.frequency_next_hz)
        ) {
            return 0;
        }
        if (should_emit(sample_index) != 0) {
            printf(
                "%u,%lu,%.9g,%.9g,%.9g,%.9g,%lu,%u,%u,%.9g\n",
                (unsigned int)algorithm_id,
                (unsigned long)sample_index,
                (double)signal_sample.input,
                (double)output,
                (double)telemetry.frequency_used_hz,
                (double)telemetry.frequency_next_hz,
                (unsigned long)telemetry.tracker_calls,
                (unsigned int)telemetry.state_used,
                (unsigned int)telemetry.state_next,
                (double)telemetry.residual_ratio
            );
        }
    }
    return 1;
}

int main(void)
{
    uint32_t algorithm_id;
    puts(
        "algorithm,n,input,output,frequency_used_hz,frequency_next_hz,"
        "tracker_calls,state_used,state_next,residual_ratio"
    );
    for (algorithm_id = 0U; algorithm_id <= 3U; ++algorithm_id) {
        if (run_algorithm((rdmr_algorithm_id_t)algorithm_id) == 0) {
            return 1;
        }
    }
    return 0;
}
