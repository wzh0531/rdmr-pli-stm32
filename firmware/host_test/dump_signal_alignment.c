#include "../core/rdmr_signal_protocol.h"

#include <stdint.h>
#include <stdio.h>

static const uint32_t alignment_indices[] = {
    0U, 1U, 2U, 49U, 50U, 99U, 100U,
    3998U, 3999U, 4000U, 4001U, 7999U
};

static int is_alignment_index(uint32_t sample_index)
{
    uint32_t index;
    for (
        index = 0U;
        index < (uint32_t)(
            sizeof(alignment_indices) / sizeof(alignment_indices[0])
        );
        ++index
    ) {
        if (sample_index == alignment_indices[index]) {
            return 1;
        }
    }
    return 0;
}

static void dump_scenario(
    const char *scenario_id,
    rdmr_trajectory_id_t trajectory_id,
    rdmr_noise_id_t noise_id,
    uint32_t seed
)
{
    rdmr_experiment_config_t config;
    rdmr_signal_generator_t generator;
    rdmr_signal_sample_t sample;
    uint32_t sample_index;

    config.algorithm_id = RDMR_ALGORITHM_A3_RESIDUAL_MULTIRATE;
    config.trajectory_id = trajectory_id;
    config.near_line_id = RDMR_NEAR_LINE_N0;
    config.noise_id = noise_id;
    config.seed = seed;
    config.sample_count = RDMR_PROTOCOL_SAMPLE_COUNT;
    config.log_schema_version = RDMR_LOG_SCHEMA_VERSION_ID;
    config.sample_rate_hz = RDMR_PROTOCOL_FS_HZ;
    config.pli_amplitude = 0.50f;
    rdmr_signal_init(&generator, &config);

    for (sample_index = 0U; sample_index < config.sample_count; ++sample_index) {
        if (rdmr_signal_next(&generator, &sample) == 0) {
            return;
        }
        if (is_alignment_index(sample_index) != 0) {
            printf(
                "%s,%lu,%lu,%.9g,%.9g,%.9g,%.9g,%.9g\n",
                scenario_id,
                (unsigned long)seed,
                (unsigned long)sample_index,
                (double)sample.clean,
                (double)sample.interference,
                (double)sample.noise,
                (double)sample.input,
                (double)sample.true_frequency_hz
            );
        }
    }
}

int main(void)
{
    uint32_t seed;

    puts(
        "scenario_id,seed,n,clean,interference,noise,input,true_frequency_hz"
    );
    for (seed = 0U; seed <= 4U; ++seed) {
        dump_scenario(
            "DEV-F0-NONE",
            RDMR_TRAJECTORY_F0,
            RDMR_NOISE_NONE,
            seed
        );
        dump_scenario(
            "DEV-F1-20DB",
            RDMR_TRAJECTORY_F1,
            RDMR_NOISE_SNR_20_DB,
            seed
        );
    }
    return 0;
}
