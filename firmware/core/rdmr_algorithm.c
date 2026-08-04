#include "rdmr_algorithm.h"
#include "rdmr_memory.h"
#include "rdmr_trig.h"

#include <math.h>
#include <stddef.h>

#define RDMR_ALGORITHM_PI               3.14159265358979323846f
#define RDMR_NOTCH_FREQUENCY_HZ         50.0f
#define RDMR_NOTCH_QUALITY_FACTOR       30.0f

static void notch_init(rdmr_notch_t *notch)
{
    const float omega =
        2.0f
        * RDMR_ALGORITHM_PI
        * RDMR_NOTCH_FREQUENCY_HZ
        / RDMR_FS_HZ;
    const float alpha =
        rdmr_trig_sin(omega) / (2.0f * RDMR_NOTCH_QUALITY_FACTOR);
    const float a0 = 1.0f + alpha;
    const float cosine = rdmr_trig_cos(omega);

    rdmr_zero_bytes(notch, (uint32_t)sizeof(*notch));
    notch->b0 = 1.0f / a0;
    notch->b1 = -2.0f * cosine / a0;
    notch->b2 = 1.0f / a0;
    notch->a1 = -2.0f * cosine / a0;
    notch->a2 = (1.0f - alpha) / a0;
}

static float notch_process(rdmr_notch_t *notch, float input)
{
    const float output =
        notch->b0 * input
        + notch->b1 * notch->x1
        + notch->b2 * notch->x2
        - notch->a1 * notch->y1
        - notch->a2 * notch->y2;

    notch->x2 = notch->x1;
    notch->x1 = input;
    notch->y2 = notch->y1;
    notch->y1 = output;
    return output;
}

static rdmr_mode_t algorithm_mode(rdmr_algorithm_id_t algorithm_id)
{
    if (algorithm_id == RDMR_ALGORITHM_A1_FIXED_NLMS) {
        return RDMR_MODE_FIXED_REFERENCE;
    }
    if (algorithm_id == RDMR_ALGORITHM_A2_FULL_RATE) {
        return RDMR_MODE_FULL_RATE;
    }
    return RDMR_MODE_RESIDUAL_MULTIRATE;
}

int rdmr_algorithm_init(
    rdmr_algorithm_t *instance,
    rdmr_algorithm_id_t algorithm_id
)
{
    if (instance == NULL) {
        return 0;
    }
    if (algorithm_id > RDMR_ALGORITHM_A3_RESIDUAL_MULTIRATE) {
        return 0;
    }

    rdmr_zero_bytes(instance, (uint32_t)sizeof(*instance));
    instance->algorithm_id = algorithm_id;
    if (algorithm_id == RDMR_ALGORITHM_A0_FIXED_NOTCH) {
        notch_init(&instance->notch);
    } else {
        rdmr_init(&instance->nlms, algorithm_mode(algorithm_id));
    }
    return 1;
}

float rdmr_algorithm_process(
    rdmr_algorithm_t *instance,
    float input
)
{
    if (instance == NULL) {
        return input;
    }
    if (instance->algorithm_id == RDMR_ALGORITHM_A0_FIXED_NOTCH) {
        return notch_process(&instance->notch, input);
    }
    return rdmr_process(&instance->nlms, input);
}

void rdmr_algorithm_get_telemetry(
    const rdmr_algorithm_t *instance,
    rdmr_algorithm_telemetry_t *telemetry
)
{
    rdmr_telemetry_t nlms_telemetry;

    if ((instance == NULL) || (telemetry == NULL)) {
        return;
    }
    if (instance->algorithm_id == RDMR_ALGORITHM_A0_FIXED_NOTCH) {
        telemetry->frequency_used_hz = RDMR_NOTCH_FREQUENCY_HZ;
        telemetry->frequency_next_hz = RDMR_NOTCH_FREQUENCY_HZ;
        telemetry->residual_ratio = 0.0f;
        telemetry->tracker_calls = 0U;
        telemetry->state_used = RDMR_STATE_FIXED;
        telemetry->state_next = RDMR_STATE_FIXED;
        return;
    }

    rdmr_get_telemetry(&instance->nlms, &nlms_telemetry);
    telemetry->frequency_used_hz = nlms_telemetry.frequency_used_hz;
    telemetry->frequency_next_hz = nlms_telemetry.frequency_next_hz;
    telemetry->residual_ratio = nlms_telemetry.residual_ratio;
    telemetry->tracker_calls = nlms_telemetry.tracker_calls;
    telemetry->state_used = nlms_telemetry.state_used;
    telemetry->state_next = nlms_telemetry.state_next;
}
