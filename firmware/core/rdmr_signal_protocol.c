#include "rdmr_signal_protocol.h"
#include "rdmr_memory.h"
#include "rdmr_trig.h"

#include <math.h>
#include <stddef.h>

#define RDMR_SIGNAL_PI                   3.14159265358979323846f
#define RDMR_SIGNAL_TWO_PI               (2.0f * RDMR_SIGNAL_PI)
#define RDMR_STREAM_FREQUENCY            2654435769UL
#define RDMR_STREAM_NOISE                2246822507UL
#define RDMR_STREAM_PHASE                3266489909UL
#define RDMR_U24_SCALE                   (1.0f / 16777216.0f)

static uint32_t splitmix32(uint32_t value)
{
    value += 0x9E3779B9UL;
    value = (value ^ (value >> 16U)) * 0x85EBCA6BUL;
    value = (value ^ (value >> 13U)) * 0xC2B2AE35UL;
    return value ^ (value >> 16U);
}

static uint32_t derive_stream_seed(uint32_t seed, uint32_t stream_tag)
{
    uint32_t state = splitmix32(seed + stream_tag);
    if (state == 0U) {
        state = 0x6D2B79F5UL;
    }
    return state;
}

static uint32_t xorshift32(uint32_t *state)
{
    uint32_t value = *state;
    value ^= value << 13U;
    value ^= value >> 17U;
    value ^= value << 5U;
    *state = value;
    return value;
}

static float uniform01(uint32_t *state)
{
    return (float)(xorshift32(state) >> 8U) * RDMR_U24_SCALE;
}

static float normal_gaussian(uint32_t *state)
{
    float uniform_1 = uniform01(state);
    const float uniform_2 = uniform01(state);

    if (uniform_1 <= 0.0f) {
        uniform_1 = RDMR_U24_SCALE;
    }
    return
        sqrtf(-2.0f * logf(uniform_1))
        * rdmr_trig_cos(RDMR_SIGNAL_TWO_PI * uniform_2);
}

static void oscillator_step(
    float *cosine,
    float *sine,
    float step_cosine,
    float step_sine
)
{
    const float next_cosine =
        (*cosine) * step_cosine - (*sine) * step_sine;
    const float next_sine =
        (*sine) * step_cosine + (*cosine) * step_sine;
    *cosine = next_cosine;
    *sine = next_sine;
}

static float clean_signal_power(rdmr_near_line_id_t near_line_id)
{
    float power = 0.5f * (0.18f * 0.18f + 0.10f * 0.10f);

    if (
        (near_line_id == RDMR_NEAR_LINE_N1)
        || (near_line_id == RDMR_NEAR_LINE_N2)
    ) {
        power += 0.5f * 0.05f * 0.05f;
    } else if (near_line_id == RDMR_NEAR_LINE_N3) {
        power += 0.05f * 0.05f;
    }
    return power;
}

static float noise_standard_deviation(
    rdmr_noise_id_t noise_id,
    rdmr_near_line_id_t near_line_id
)
{
    const float power = clean_signal_power(near_line_id);

    if (noise_id == RDMR_NOISE_SNR_20_DB) {
        return sqrtf(power / 100.0f);
    }
    if (noise_id == RDMR_NOISE_SNR_10_DB) {
        return sqrtf(power / 10.0f);
    }
    return 0.0f;
}

static float reflected_frequency(float frequency)
{
    if (frequency < 48.5f) {
        return 48.5f + (48.5f - frequency);
    }
    if (frequency > 51.5f) {
        return 51.5f - (frequency - 51.5f);
    }
    return frequency;
}

float rdmr_true_frequency(
    rdmr_signal_generator_t *generator,
    uint32_t sample_index
)
{
    const rdmr_trajectory_id_t trajectory =
        generator->config.trajectory_id;

    if (trajectory == RDMR_TRAJECTORY_F0) {
        return 50.0f;
    }
    if (trajectory == RDMR_TRAJECTORY_F1) {
        return (sample_index < 4000U) ? 49.0f : 51.0f;
    }
    if (trajectory == RDMR_TRAJECTORY_F2) {
        return (sample_index < 4000U) ? 47.0f : 53.0f;
    }
    if (trajectory == RDMR_TRAJECTORY_F3) {
        if (sample_index < 1000U) {
            return 49.0f;
        }
        if (sample_index > 6999U) {
            return 51.0f;
        }
        return
            49.0f
            + 2.0f
            * (float)(sample_index - 1000U)
            / 5999.0f;
    }
    if (trajectory == RDMR_TRAJECTORY_F4) {
        return
            50.0f
            + rdmr_trig_sin(
                RDMR_SIGNAL_TWO_PI
                * (float)sample_index
                / 4000.0f
            );
    }
    if (
        (sample_index != 0U)
        && ((sample_index % 50U) == 0U)
    ) {
        const float draw = uniform01(&generator->frequency_rng);
        float step = 0.0f;

        if (draw < 0.25f) {
            step = -0.05f;
        } else if (draw >= 0.75f) {
            step = 0.05f;
        }
        generator->f5_frequency_hz =
            reflected_frequency(generator->f5_frequency_hz + step);
    }
    return generator->f5_frequency_hz;
}

void rdmr_signal_init(
    rdmr_signal_generator_t *generator,
    const rdmr_experiment_config_t *config
)
{
    if ((generator == NULL) || (config == NULL)) {
        return;
    }

    rdmr_zero_bytes(generator, (uint32_t)sizeof(*generator));
    generator->config.algorithm_id = config->algorithm_id;
    generator->config.trajectory_id = config->trajectory_id;
    generator->config.near_line_id = config->near_line_id;
    generator->config.noise_id = config->noise_id;
    generator->config.seed = config->seed;
    generator->config.sample_count = config->sample_count;
    generator->config.log_schema_version = config->log_schema_version;
    generator->config.sample_rate_hz = config->sample_rate_hz;
    generator->config.pli_amplitude = config->pli_amplitude;
    generator->frequency_rng =
        derive_stream_seed(config->seed, RDMR_STREAM_FREQUENCY);
    generator->noise_rng =
        derive_stream_seed(config->seed, RDMR_STREAM_NOISE);
    generator->phase_rng =
        derive_stream_seed(config->seed, RDMR_STREAM_PHASE);
    generator->line_phase_rad =
        uniform01(&generator->phase_rng) * RDMR_SIGNAL_TWO_PI;
    generator->line_cos = rdmr_trig_cos(generator->line_phase_rad);
    generator->line_sin = rdmr_trig_sin(generator->line_phase_rad);
    generator->line_step_frequency_hz = -1.0f;
    generator->f5_frequency_hz = 50.0f;
    generator->clean_7_cos = 1.0f;
    generator->clean_13_cos = 1.0f;
    generator->near_42_cos = 1.0f;
    generator->near_58_cos = 1.0f;
}

int rdmr_signal_next(
    rdmr_signal_generator_t *generator,
    rdmr_signal_sample_t *sample
)
{
    const float clean_7_step_cos = 0.999032935f;
    const float clean_7_step_sin = 0.043968118f;
    const float clean_13_step_cos = 0.996665928f;
    const float clean_13_step_sin = 0.081590612f;
    const float near_42_step_cos = 0.965381639f;
    const float near_42_step_sin = 0.260841519f;
    const float near_58_step_cos = 0.934328942f;
    const float near_58_step_sin = 0.356411879f;
    float line_step;
    float noise_sigma;

    if ((generator == NULL) || (sample == NULL)) {
        return 0;
    }
    if (generator->sample_index >= generator->config.sample_count) {
        return 0;
    }

    sample->true_frequency_hz =
        rdmr_true_frequency(generator, generator->sample_index);
    if (sample->true_frequency_hz != generator->line_step_frequency_hz) {
        const float step_angle =
            RDMR_SIGNAL_TWO_PI
            * sample->true_frequency_hz
            / generator->config.sample_rate_hz;
        generator->line_step_cos = rdmr_trig_cos(step_angle);
        generator->line_step_sin = rdmr_trig_sin(step_angle);
        generator->line_step_frequency_hz = sample->true_frequency_hz;
    }
    sample->clean =
        0.18f * generator->clean_7_sin
        + 0.10f * generator->clean_13_sin;
    if (
        (generator->config.near_line_id == RDMR_NEAR_LINE_N1)
        || (generator->config.near_line_id == RDMR_NEAR_LINE_N3)
    ) {
        sample->clean += 0.05f * generator->near_42_sin;
    }
    if (
        (generator->config.near_line_id == RDMR_NEAR_LINE_N2)
        || (generator->config.near_line_id == RDMR_NEAR_LINE_N3)
    ) {
        sample->clean += 0.05f * generator->near_58_sin;
    }
    sample->interference =
        generator->config.pli_amplitude
        * generator->line_sin;
    noise_sigma = noise_standard_deviation(
        generator->config.noise_id,
        generator->config.near_line_id
    );
    sample->noise =
        (noise_sigma > 0.0f)
            ? noise_sigma * normal_gaussian(&generator->noise_rng)
            : 0.0f;
    sample->input = sample->clean + sample->interference + sample->noise;

    oscillator_step(
        &generator->clean_7_cos,
        &generator->clean_7_sin,
        clean_7_step_cos,
        clean_7_step_sin
    );
    oscillator_step(
        &generator->clean_13_cos,
        &generator->clean_13_sin,
        clean_13_step_cos,
        clean_13_step_sin
    );
    oscillator_step(
        &generator->near_42_cos,
        &generator->near_42_sin,
        near_42_step_cos,
        near_42_step_sin
    );
    oscillator_step(
        &generator->near_58_cos,
        &generator->near_58_sin,
        near_58_step_cos,
        near_58_step_sin
    );
    oscillator_step(
        &generator->line_cos,
        &generator->line_sin,
        generator->line_step_cos,
        generator->line_step_sin
    );

    line_step =
        RDMR_SIGNAL_TWO_PI
        * sample->true_frequency_hz
        / generator->config.sample_rate_hz;
    generator->line_phase_rad += line_step;
    if (generator->line_phase_rad >= RDMR_SIGNAL_TWO_PI) {
        generator->line_phase_rad -= RDMR_SIGNAL_TWO_PI;
    }
    generator->sample_index += 1U;
    return 1;
}
