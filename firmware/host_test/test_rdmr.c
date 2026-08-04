#include "../core/rdmr_pli.h"

#include <math.h>
#include <stdio.h>

#define TEST_PI 3.14159265358979323846
#define TEST_SAMPLES 8000

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

static double internal_demo_energy_mismatch(void)
{
    float cosine = 1.0f;
    float sine = 0.0f;
    float step_cosine = 0.956712052f;
    float step_sine = 0.291036167f;
    double first_energy = 0.0;
    double second_energy = 0.0;
    int index;

    for (index = 0; index < TEST_SAMPLES; ++index) {
        const double interference = 0.5 * (double)sine;
        if (index < (TEST_SAMPLES / 2)) {
            first_energy += interference * interference;
        } else {
            second_energy += interference * interference;
        }
        oscillator_step(&cosine, &sine, step_cosine, step_sine);
        if (index == (TEST_SAMPLES / 2) - 1) {
            step_cosine = 0.945063075f;
            step_sine = 0.326888030f;
        }
    }

    printf(
        "internal_demo: first_energy=%.6f second_energy=%.6f "
        "mismatch=%.6f%%\n",
        first_energy,
        second_energy,
        100.0 * fabs(first_energy - second_energy)
            / (0.5 * (first_energy + second_energy))
    );
    return fabs(first_energy - second_energy)
        / (0.5 * (first_energy + second_energy));
}

static void run_case(
    rdmr_mode_t mode,
    double *suppression_db,
    double *input_snr_db,
    double *output_snr_db,
    double *rmse,
    uint32_t *tracker_calls
)
{
    rdmr_pli_t canceller;
    double phase = 0.0;
    double interference_power = 0.0;
    double error_power = 0.0;
    double clean_power = 0.0;
    int index;

    rdmr_init(&canceller, mode);
    for (index = 0; index < TEST_SAMPLES; ++index) {
        const double t = (double)index / (double)RDMR_FS_HZ;
        const double frequency = (index < 4000) ? 47.0 : 53.0;
        const double clean =
            0.18 * sin(2.0 * TEST_PI * 7.0 * t)
            + 0.10 * sin(2.0 * TEST_PI * 13.0 * t);
        double interference;
        double output;
        double error;

        phase += 2.0 * TEST_PI * frequency / (double)RDMR_FS_HZ;
        interference = 0.50 * sin(phase);
        output = (double)rdmr_process(
            &canceller,
            (float)(clean + interference)
        );
        error = output - clean;
        interference_power += interference * interference;
        error_power += error * error;
        clean_power += clean * clean;
    }

    *suppression_db = 10.0 * log10(interference_power / error_power);
    *input_snr_db = 10.0 * log10(clean_power / interference_power);
    *output_snr_db = 10.0 * log10(clean_power / error_power);
    *rmse = sqrt(error_power / (double)TEST_SAMPLES);
    *tracker_calls = canceller.tracker_calls;
}

int main(void)
{
    double full_suppression;
    double multirate_suppression;
    double full_input_snr;
    double full_output_snr;
    double full_rmse;
    double multirate_input_snr;
    double multirate_output_snr;
    double multirate_rmse;
    uint32_t full_calls;
    uint32_t multirate_calls;

    run_case(
        RDMR_MODE_FULL_RATE,
        &full_suppression,
        &full_input_snr,
        &full_output_snr,
        &full_rmse,
        &full_calls
    );
    run_case(
        RDMR_MODE_RESIDUAL_MULTIRATE,
        &multirate_suppression,
        &multirate_input_snr,
        &multirate_output_snr,
        &multirate_rmse,
        &multirate_calls
    );

    printf(
        "full_rate: input_snr=%.3f dB output_snr=%.3f dB "
        "suppression=%.3f dB rmse=%.6f calls=%lu\n",
        full_input_snr,
        full_output_snr,
        full_suppression,
        full_rmse,
        (unsigned long)full_calls
    );
    printf(
        "residual_multirate: input_snr=%.3f dB output_snr=%.3f dB "
        "suppression=%.3f dB rmse=%.6f calls=%lu\n",
        multirate_input_snr,
        multirate_output_snr,
        multirate_suppression,
        multirate_rmse,
        (unsigned long)multirate_calls
    );

    if (multirate_calls >= full_calls) {
        return 1;
    }
    if (multirate_suppression < full_suppression - 1.0) {
        return 2;
    }
    if (fabs(
            (multirate_output_snr - multirate_input_snr)
            - multirate_suppression
        ) > 1.0e-9) {
        return 3;
    }
    if (multirate_rmse <= 0.0) {
        return 4;
    }
    if (internal_demo_energy_mismatch() > 0.01) {
        return 5;
    }
    return 0;
}
