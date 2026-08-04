#include "../core/rdmr_algorithm.h"
#include "../core/rdmr_signal_protocol.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#if defined(_WIN32)
#include <windows.h>
#endif

#if defined(__i386__) || defined(__x86_64__)
#include <x86intrin.h>
#define RDMR_HAS_TSC 1
#else
#define RDMR_HAS_TSC 0
#endif

#define PHASE3_SAMPLE_COUNT 8000U
#define PHASE3_TIMING_REPEATS 5U

typedef struct {
    double output_snr_db;
    double frequency_mae_hz;
    uint32_t tracker_calls;
    uint32_t state_fast_samples;
    uint32_t state_mid_samples;
    uint32_t state_slow_samples;
    uint32_t state_transitions;
    int finite;
} case_metrics_t;

static volatile double timing_sink = 0.0;

static int compare_double(const void *left, const void *right)
{
    const double a = *(const double *)left;
    const double b = *(const double *)right;
    return (a > b) - (a < b);
}

static uint64_t read_tsc(void)
{
#if RDMR_HAS_TSC
    unsigned int auxiliary;
    _mm_lfence();
    return __rdtscp(&auxiliary);
#else
    return 0U;
#endif
}

static double elapsed_nanoseconds(
#if defined(_WIN32)
    LARGE_INTEGER start,
    LARGE_INTEGER end,
    LARGE_INTEGER frequency
#else
    uint64_t start,
    uint64_t end,
    uint64_t frequency
#endif
)
{
#if defined(_WIN32)
    return
        1.0e9
        * (double)(end.QuadPart - start.QuadPart)
        / (double)frequency.QuadPart;
#else
    (void)start;
    (void)end;
    (void)frequency;
    return 0.0;
#endif
}

static int generate_case(
    rdmr_trajectory_id_t trajectory,
    uint32_t seed,
    float *input,
    float *clean,
    float *true_frequency
)
{
    rdmr_experiment_config_t config;
    rdmr_signal_generator_t generator;
    rdmr_signal_sample_t sample;
    uint32_t index;

    config.algorithm_id = RDMR_ALGORITHM_A3_RESIDUAL_MULTIRATE;
    config.trajectory_id = trajectory;
    config.near_line_id = RDMR_NEAR_LINE_N0;
    config.noise_id = RDMR_NOISE_SNR_20_DB;
    config.seed = seed;
    config.sample_count = PHASE3_SAMPLE_COUNT;
    config.log_schema_version = RDMR_LOG_SCHEMA_VERSION_ID;
    config.sample_rate_hz = RDMR_PROTOCOL_FS_HZ;
    config.pli_amplitude = 0.50f;
    rdmr_signal_init(&generator, &config);

    for (index = 0U; index < PHASE3_SAMPLE_COUNT; ++index) {
        if (rdmr_signal_next(&generator, &sample) == 0) {
            return 0;
        }
        input[index] = sample.input;
        clean[index] = sample.clean;
        true_frequency[index] = sample.true_frequency_hz;
    }
    return 1;
}

static case_metrics_t evaluate_case(
    rdmr_algorithm_id_t algorithm_id,
    const float *input,
    const float *clean,
    const float *true_frequency
)
{
    rdmr_algorithm_t algorithm;
    rdmr_algorithm_telemetry_t telemetry;
    case_metrics_t metrics;
    double clean_energy = 0.0;
    double error_energy = 0.0;
    double frequency_absolute_error = 0.0;
    rdmr_state_t previous_state = RDMR_STATE_FIXED;
    uint32_t index;

    metrics.output_snr_db = 0.0;
    metrics.frequency_mae_hz = 0.0;
    metrics.tracker_calls = 0U;
    metrics.state_fast_samples = 0U;
    metrics.state_mid_samples = 0U;
    metrics.state_slow_samples = 0U;
    metrics.state_transitions = 0U;
    metrics.finite = 1;

    if (rdmr_algorithm_init(&algorithm, algorithm_id) == 0) {
        metrics.finite = 0;
        return metrics;
    }

    for (index = 0U; index < PHASE3_SAMPLE_COUNT; ++index) {
        const float output = rdmr_algorithm_process(&algorithm, input[index]);
        const double error = (double)output - (double)clean[index];

        rdmr_algorithm_get_telemetry(&algorithm, &telemetry);
        clean_energy += (double)clean[index] * (double)clean[index];
        error_energy += error * error;
        frequency_absolute_error +=
            fabs(
                (double)telemetry.frequency_used_hz
                - (double)true_frequency[index]
            );
        if (telemetry.state_next == RDMR_STATE_FAST) {
            metrics.state_fast_samples += 1U;
        } else if (telemetry.state_next == RDMR_STATE_MID) {
            metrics.state_mid_samples += 1U;
        } else if (telemetry.state_next == RDMR_STATE_SLOW) {
            metrics.state_slow_samples += 1U;
        }
        if (
            (index > 0U)
            && (telemetry.state_next != previous_state)
        ) {
            metrics.state_transitions += 1U;
        }
        previous_state = telemetry.state_next;
        if (
            !isfinite((double)output)
            || !isfinite((double)telemetry.frequency_used_hz)
        ) {
            metrics.finite = 0;
        }
    }
    metrics.output_snr_db =
        10.0 * log10(clean_energy / (error_energy + 1.0e-30));
    metrics.frequency_mae_hz =
        frequency_absolute_error / (double)PHASE3_SAMPLE_COUNT;
    metrics.tracker_calls = telemetry.tracker_calls;
    if (
        !isfinite(metrics.output_snr_db)
        || !isfinite(metrics.frequency_mae_hz)
    ) {
        metrics.finite = 0;
    }
    return metrics;
}

static void benchmark_case(
    rdmr_algorithm_id_t algorithm_id,
    const float *input,
    double *median_ns_per_sample,
    double *median_tsc_ticks_per_sample
)
{
    double elapsed_ns[PHASE3_TIMING_REPEATS];
    double elapsed_tsc[PHASE3_TIMING_REPEATS];
    uint32_t repeat;
#if defined(_WIN32)
    LARGE_INTEGER frequency;
    QueryPerformanceFrequency(&frequency);
#endif

    for (repeat = 0U; repeat < PHASE3_TIMING_REPEATS; ++repeat) {
        rdmr_algorithm_t algorithm;
        double sink = 0.0;
        uint32_t index;
        uint64_t tsc_start;
        uint64_t tsc_end;
#if defined(_WIN32)
        LARGE_INTEGER time_start;
        LARGE_INTEGER time_end;
#else
        uint64_t time_start = 0U;
        uint64_t time_end = 0U;
        uint64_t frequency = 1U;
#endif

        (void)rdmr_algorithm_init(&algorithm, algorithm_id);
#if defined(_WIN32)
        QueryPerformanceCounter(&time_start);
#endif
        tsc_start = read_tsc();
        for (index = 0U; index < PHASE3_SAMPLE_COUNT; ++index) {
            sink += (double)rdmr_algorithm_process(&algorithm, input[index]);
        }
        tsc_end = read_tsc();
#if defined(_WIN32)
        QueryPerformanceCounter(&time_end);
#endif
        timing_sink += sink;
        elapsed_ns[repeat] =
            elapsed_nanoseconds(time_start, time_end, frequency)
            / (double)PHASE3_SAMPLE_COUNT;
        elapsed_tsc[repeat] =
            (double)(tsc_end - tsc_start)
            / (double)PHASE3_SAMPLE_COUNT;
    }
    qsort(
        elapsed_ns,
        PHASE3_TIMING_REPEATS,
        sizeof(elapsed_ns[0]),
        compare_double
    );
    qsort(
        elapsed_tsc,
        PHASE3_TIMING_REPEATS,
        sizeof(elapsed_tsc[0]),
        compare_double
    );
    *median_ns_per_sample = elapsed_ns[PHASE3_TIMING_REPEATS / 2U];
    *median_tsc_ticks_per_sample =
        elapsed_tsc[PHASE3_TIMING_REPEATS / 2U];
}

int main(int argc, char **argv)
{
    static const rdmr_trajectory_id_t trajectories[] = {
        RDMR_TRAJECTORY_F1,
        RDMR_TRAJECTORY_F3,
        RDMR_TRAJECTORY_F4
    };
    float *input;
    float *clean;
    float *true_frequency;
    rdmr_algorithm_id_t algorithm_id;
    uint32_t trajectory_index;
    uint32_t seed;

    if (argc != 2) {
        fprintf(stderr, "usage: phase3_tuning_case.exe <algorithm_id>\n");
        return 2;
    }
    algorithm_id = (rdmr_algorithm_id_t)atoi(argv[1]);
    if (
        (algorithm_id != RDMR_ALGORITHM_A2_FULL_RATE)
        && (algorithm_id != RDMR_ALGORITHM_A3_RESIDUAL_MULTIRATE)
    ) {
        fprintf(stderr, "algorithm_id must be 2 or 3\n");
        return 3;
    }

    input = (float *)malloc(PHASE3_SAMPLE_COUNT * sizeof(float));
    clean = (float *)malloc(PHASE3_SAMPLE_COUNT * sizeof(float));
    true_frequency =
        (float *)malloc(PHASE3_SAMPLE_COUNT * sizeof(float));
    if ((input == NULL) || (clean == NULL) || (true_frequency == NULL)) {
        free(input);
        free(clean);
        free(true_frequency);
        return 4;
    }

    puts(
        "algorithm,trajectory,seed,output_snr_db,frequency_mae_hz,"
        "tracker_calls,state_fast_samples,state_mid_samples,"
        "state_slow_samples,state_transitions,host_ns_per_sample,"
        "host_tsc_ticks_per_sample,finite"
    );
    for (
        trajectory_index = 0U;
        trajectory_index < (
            sizeof(trajectories) / sizeof(trajectories[0])
        );
        ++trajectory_index
    ) {
        for (seed = 100U; seed <= 109U; ++seed) {
            case_metrics_t metrics;
            double host_ns_per_sample;
            double host_tsc_ticks_per_sample;

            if (
                generate_case(
                    trajectories[trajectory_index],
                    seed,
                    input,
                    clean,
                    true_frequency
                ) == 0
            ) {
                free(input);
                free(clean);
                free(true_frequency);
                return 5;
            }
            metrics = evaluate_case(
                algorithm_id,
                input,
                clean,
                true_frequency
            );
            benchmark_case(
                algorithm_id,
                input,
                &host_ns_per_sample,
                &host_tsc_ticks_per_sample
            );
            printf(
                "%u,F%u,%lu,%.9f,%.9f,%lu,%lu,%lu,%lu,%lu,"
                "%.6f,%.6f,%d\n",
                (unsigned int)algorithm_id,
                (unsigned int)trajectories[trajectory_index],
                (unsigned long)seed,
                metrics.output_snr_db,
                metrics.frequency_mae_hz,
                (unsigned long)metrics.tracker_calls,
                (unsigned long)metrics.state_fast_samples,
                (unsigned long)metrics.state_mid_samples,
                (unsigned long)metrics.state_slow_samples,
                (unsigned long)metrics.state_transitions,
                host_ns_per_sample,
                host_tsc_ticks_per_sample,
                metrics.finite
            );
        }
    }

    free(input);
    free(clean);
    free(true_frequency);
    return 0;
}
