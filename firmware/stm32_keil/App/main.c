#include "stm32f1xx.h"

#include <limits.h>
#include <math.h>
#include <stdint.h>

#include "rdmr_algorithm.h"
#include "rdmr_cycle_stats.h"
#include "rdmr_log_schema.h"
#include "rdmr_signal_protocol.h"
#include "rdmr_trig.h"

#ifndef RDMR_INTERNAL_DEMO
#define RDMR_INTERNAL_DEMO            1
#endif
#ifndef RDMR_ENABLE_DWT
#define RDMR_ENABLE_DWT               1
#endif

#ifndef RDMR_PROTEUS_BUILD
#define RDMR_PROTEUS_BUILD            1
#endif
#ifndef RDMR_EMIT_INIT_DIAGNOSTICS
#define RDMR_EMIT_INIT_DIAGNOSTICS    0
#endif
#ifndef RDMR_DEMO_ALGORITHM
#define RDMR_DEMO_ALGORITHM           RDMR_ALGORITHM_A3_RESIDUAL_MULTIRATE
#endif
#ifndef RDMR_DEMO_TRAJECTORY
#define RDMR_DEMO_TRAJECTORY          RDMR_TRAJECTORY_F1
#endif
#ifndef RDMR_DEMO_NEAR_LINE
#define RDMR_DEMO_NEAR_LINE           RDMR_NEAR_LINE_N0
#endif
#ifndef RDMR_DEMO_NOISE
#define RDMR_DEMO_NOISE               RDMR_NOISE_NONE
#endif
#ifndef RDMR_DEMO_SEED
#define RDMR_DEMO_SEED                0U
#endif
#ifndef RDMR_DEMO_PLI_AMPLITUDE
#define RDMR_DEMO_PLI_AMPLITUDE       0.50f
#endif
#ifndef RDMR_DEMO_RUN_ID
#define RDMR_DEMO_RUN_ID              1U
#endif
#ifndef RDMR_DEMO_SCENARIO_ID
#define RDMR_DEMO_SCENARIO_ID         101U
#endif
#define RDMR_VALUE_SCALE              1000000.0f
#define RDMR_FREQUENCY_SCALE          1000.0f
#define RDMR_ENERGY_SCALE             1000000.0f

#define RDMR_NUMERIC_INPUT            (1UL << 0)
#define RDMR_NUMERIC_CLEAN            (1UL << 1)
#define RDMR_NUMERIC_OUTPUT           (1UL << 2)
#define RDMR_NUMERIC_TRUE_FREQUENCY   (1UL << 3)
#define RDMR_NUMERIC_EST_FREQUENCY    (1UL << 4)
#define RDMR_NUMERIC_ENERGY           (1UL << 5)
#define RDMR_NUMERIC_SATURATION       (1UL << 6)
#define RDMR_NUMERIC_RESIDUAL         (1UL << 7)

typedef struct {
    uint32_t sample_index;
    float input;
    float clean;
    float output;
    float true_frequency_hz;
    float desired_energy;
    float input_error_energy;
    float output_error_energy;
} rdmr_log_record_t;

static rdmr_algorithm_t canceller;

static void uart1_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_USART1EN;

    /* PA9: USART1_TX, 50 MHz alternate-function push-pull. */
    GPIOA->CRH &= ~(0xFU << 4U);
    GPIOA->CRH |=  (0xBU << 4U);

    /* PA10: floating input, retained for a conventional UART pin map. */
    GPIOA->CRH &= ~(0xFU << 8U);
    GPIOA->CRH |=  (0x4U << 8U);

    /* Keep the log baud rate at 115200 on both target clock models. */
#if RDMR_PROTEUS_BUILD
    /* Proteus PCLK2=9 MHz: 9,000,000 / 115,200 -> BRR=0x4E. */
    USART1->BRR = 0x4EU;
#else
    /* Physical F103 PCLK2=72 MHz: 72,000,000 / 115,200 -> BRR=0x271. */
    USART1->BRR = 0x271U;
#endif
    USART1->CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;
}

static void uart1_putc(char character)
{
    while ((USART1->SR & USART_SR_TXE) == 0U) {
    }
    USART1->DR = (uint16_t)(uint8_t)character;
}

static void uart1_puts(const char *text)
{
    while (*text != '\0') {
        uart1_putc(*text);
        ++text;
    }
}

static void uart1_u32(uint32_t value)
{
    char buffer[10];
    uint32_t count = 0U;

    if (value == 0U) {
        uart1_putc('0');
        return;
    }
    while ((value != 0U) && (count < sizeof(buffer))) {
        buffer[count] = (char)('0' + (value % 10U));
        value /= 10U;
        ++count;
    }
    while (count != 0U) {
        --count;
        uart1_putc(buffer[count]);
    }
}

static void uart1_i32(int32_t value)
{
    uint32_t magnitude;

    if (value < 0) {
        uart1_putc('-');
        magnitude = (uint32_t)(-(value + 1)) + 1U;
    } else {
        magnitude = (uint32_t)value;
    }
    uart1_u32(magnitude);
}

#if RDMR_EMIT_INIT_DIAGNOSTICS
static void emit_trace(
    uint32_t sample_number,
    const char *stage,
    uint32_t cycles
)
{
    uart1_puts(
        "TRACE,revision=" RDMR_FIRMWARE_REVISION_TEXT ",n="
    );
    uart1_u32(sample_number);
    uart1_puts(",stage=");
    uart1_puts(stage);
    uart1_puts(",cycles=");
    uart1_u32(cycles);
    uart1_puts("\r\n");
}
#endif

static int32_t scaled_i32(
    float value,
    float scale,
    uint32_t field_flag,
    uint32_t *numeric_flags
)
{
    float scaled;

    if (!isfinite(value)) {
        *numeric_flags |= field_flag;
        return 0;
    }
    scaled = value * scale;
    if (scaled >= 2147483520.0f) {
        *numeric_flags |= field_flag | RDMR_NUMERIC_SATURATION;
        return INT32_MAX;
    }
    if (scaled <= -2147483648.0f) {
        *numeric_flags |= field_flag | RDMR_NUMERIC_SATURATION;
        return INT32_MIN;
    }
    return (int32_t)scaled;
}

static uint32_t scaled_u32(
    float value,
    float scale,
    uint32_t field_flag,
    uint32_t *numeric_flags
)
{
    float scaled;

    if (!isfinite(value) || (value < 0.0f)) {
        *numeric_flags |= field_flag;
        return 0U;
    }
    scaled = value * scale;
    if (scaled > 4294967040.0f) {
        *numeric_flags |= field_flag | RDMR_NUMERIC_SATURATION;
        return 0xFFFFFFFFUL;
    }
    return (uint32_t)scaled;
}

static void emit_config(const rdmr_experiment_config_t *config)
{
    uart1_puts(
        "CONFIG,protocol=" RDMR_PROTOCOL_ID
        ",implementation=" RDMR_IMPLEMENTATION_VERSION
        ",schema=" RDMR_LOG_SCHEMA_VERSION
        ",firmware_revision="
    );
    uart1_u32(RDMR_FIRMWARE_REVISION);
    uart1_puts(",run_id=");
    uart1_u32(RDMR_DEMO_RUN_ID);
    uart1_puts(",scenario_id=");
    uart1_u32(RDMR_DEMO_SCENARIO_ID);
    uart1_puts(",algorithm=");
    uart1_u32((uint32_t)config->algorithm_id);
    uart1_puts(",trajectory=");
    uart1_u32((uint32_t)config->trajectory_id);
    uart1_puts(",noise=");
    uart1_u32((uint32_t)config->noise_id);
    uart1_puts(",near_line=");
    uart1_u32((uint32_t)config->near_line_id);
    uart1_puts(",seed=");
    uart1_u32(config->seed);
    uart1_puts(",fs_hz=");
    uart1_u32((uint32_t)config->sample_rate_hz);
    uart1_puts(",sample_count=");
    uart1_u32(config->sample_count);
    uart1_puts(",block_size=");
    uart1_u32(RDMR_BLOCK_SIZE);
    uart1_puts(",tracker_search_mode=");
    uart1_u32(RDMR_TRACKER_SEARCH_MODE);
    uart1_puts(",tracker_grid_points_max=");
#if RDMR_TRACKER_SEARCH_MODE == RDMR_TRACKER_SEARCH_HIERARCHICAL
    uart1_u32(RDMR_TRACKER_HIERARCHICAL_MAX_EVAL);
#else
    uart1_u32(RDMR_GRID_SIZE);
#endif
    uart1_puts(",pli_amplitude_u6=");
    uart1_u32(
        (uint32_t)(config->pli_amplitude * RDMR_VALUE_SCALE)
    );
    uart1_puts(",value_scale=1000000,frequency_scale=1000,cycles=block_max\r\n");
}

static uint32_t emit_record(
    const rdmr_log_record_t *record,
    const rdmr_cycle_summary_t *block_cycles,
    uint32_t block_cycles_total
)
{
    rdmr_algorithm_telemetry_t telemetry;
    uint32_t numeric_flags = 0U;
    int32_t input_scaled;
    int32_t clean_scaled;
    int32_t output_scaled;
    int32_t true_frequency_scaled;
    int32_t estimated_frequency_scaled;
    int32_t estimated_frequency_next_scaled;
    uint32_t desired_energy_scaled;
    uint32_t input_error_energy_scaled;
    uint32_t output_error_energy_scaled;
    uint32_t residual_ratio_scaled;

    rdmr_algorithm_get_telemetry(&canceller, &telemetry);
    input_scaled = scaled_i32(
        record->input,
        RDMR_VALUE_SCALE,
        RDMR_NUMERIC_INPUT,
        &numeric_flags
    );
    clean_scaled = scaled_i32(
        record->clean,
        RDMR_VALUE_SCALE,
        RDMR_NUMERIC_CLEAN,
        &numeric_flags
    );
    output_scaled = scaled_i32(
        record->output,
        RDMR_VALUE_SCALE,
        RDMR_NUMERIC_OUTPUT,
        &numeric_flags
    );
    true_frequency_scaled = scaled_i32(
        record->true_frequency_hz,
        RDMR_FREQUENCY_SCALE,
        RDMR_NUMERIC_TRUE_FREQUENCY,
        &numeric_flags
    );
    estimated_frequency_scaled = scaled_i32(
        telemetry.frequency_used_hz,
        RDMR_FREQUENCY_SCALE,
        RDMR_NUMERIC_EST_FREQUENCY,
        &numeric_flags
    );
    estimated_frequency_next_scaled = scaled_i32(
        telemetry.frequency_next_hz,
        RDMR_FREQUENCY_SCALE,
        RDMR_NUMERIC_EST_FREQUENCY,
        &numeric_flags
    );
    desired_energy_scaled = scaled_u32(
        record->desired_energy,
        RDMR_ENERGY_SCALE,
        RDMR_NUMERIC_ENERGY,
        &numeric_flags
    );
    input_error_energy_scaled = scaled_u32(
        record->input_error_energy,
        RDMR_ENERGY_SCALE,
        RDMR_NUMERIC_ENERGY,
        &numeric_flags
    );
    output_error_energy_scaled = scaled_u32(
        record->output_error_energy,
        RDMR_ENERGY_SCALE,
        RDMR_NUMERIC_ENERGY,
        &numeric_flags
    );
    residual_ratio_scaled = scaled_u32(
        telemetry.residual_ratio,
        RDMR_VALUE_SCALE,
        RDMR_NUMERIC_RESIDUAL,
        &numeric_flags
    );

    uart1_u32(RDMR_DEMO_RUN_ID);
    uart1_putc(',');
    uart1_u32(RDMR_DEMO_SCENARIO_ID);
    uart1_putc(',');
    uart1_u32((uint32_t)RDMR_DEMO_ALGORITHM);
    uart1_putc(',');
    uart1_u32(RDMR_DEMO_SEED);
    uart1_putc(',');
    uart1_u32(record->sample_index);
    uart1_putc(',');
    uart1_i32(input_scaled);
    uart1_putc(',');
    uart1_i32(clean_scaled);
    uart1_putc(',');
    uart1_i32(output_scaled);
    uart1_putc(',');
    uart1_i32(true_frequency_scaled);
    uart1_putc(',');
    uart1_i32(estimated_frequency_scaled);
    uart1_putc(',');
    uart1_i32(estimated_frequency_next_scaled);
    uart1_putc(',');
    uart1_u32(telemetry.tracker_calls);
    uart1_putc(',');
    uart1_u32(telemetry.tracker_searches);
    uart1_putc(',');
    uart1_u32(telemetry.tracker_grid_evaluations);
    uart1_putc(',');
    uart1_u32((uint32_t)telemetry.state_next);
    uart1_putc(',');
    uart1_u32(block_cycles->maximum);
    uart1_putc(',');
    uart1_u32(block_cycles_total);
    uart1_putc(',');
    uart1_u32(block_cycles->mean);
    uart1_putc(',');
    uart1_u32(block_cycles->p95);
    uart1_putc(',');
    uart1_u32(residual_ratio_scaled);
    uart1_putc(',');
    uart1_u32(desired_energy_scaled);
    uart1_putc(',');
    uart1_u32(input_error_energy_scaled);
    uart1_putc(',');
    uart1_u32(output_error_energy_scaled);
    uart1_putc(',');
    uart1_u32(numeric_flags);
    uart1_puts("\r\n");
    return numeric_flags;
}

static void emit_stats(
    const rdmr_cycle_summary_t *all_cycles,
    const rdmr_cycle_summary_t *block_total_cycles,
    const rdmr_cycle_summary_t *tracker_cycles,
    uint32_t data_rows,
    uint32_t numeric_faults
)
{
    uart1_puts("STATS,rows=");
    uart1_u32(data_rows);
    uart1_puts(",cycles_count=");
    uart1_u32(all_cycles->count);
    uart1_puts(",cycles_mean=");
    uart1_u32(all_cycles->mean);
    uart1_puts(",cycles_median=");
    uart1_u32(all_cycles->median);
    uart1_puts(",cycles_p95=");
    uart1_u32(all_cycles->p95);
    uart1_puts(",cycles_max=");
    uart1_u32(all_cycles->maximum);
    uart1_puts(",deadline_cycles=");
    uart1_u32(all_cycles->deadline_cycles);
    uart1_puts(",deadline_violations=");
    uart1_u32(all_cycles->deadline_violations);
    uart1_puts(",block_total_count=");
    uart1_u32(block_total_cycles->count);
    uart1_puts(",block_total_mean=");
    uart1_u32(block_total_cycles->mean);
    uart1_puts(",block_total_median=");
    uart1_u32(block_total_cycles->median);
    uart1_puts(",block_total_p95=");
    uart1_u32(block_total_cycles->p95);
    uart1_puts(",block_total_max=");
    uart1_u32(block_total_cycles->maximum);
    uart1_puts(",block_deadline_cycles=");
    uart1_u32(block_total_cycles->deadline_cycles);
    uart1_puts(",block_deadline_violations=");
    uart1_u32(block_total_cycles->deadline_violations);
    uart1_puts(",tracker_cycle_count=");
    uart1_u32(tracker_cycles->count);
    uart1_puts(",tracker_cycles_mean=");
    uart1_u32(tracker_cycles->mean);
    uart1_puts(",tracker_cycles_median=");
    uart1_u32(tracker_cycles->median);
    uart1_puts(",tracker_cycles_p95=");
    uart1_u32(tracker_cycles->p95);
    uart1_puts(",tracker_cycles_max=");
    uart1_u32(tracker_cycles->maximum);
    {
        rdmr_algorithm_telemetry_t telemetry;
        rdmr_algorithm_get_telemetry(&canceller, &telemetry);
        uart1_puts(",tracker_searches=");
        uart1_u32(telemetry.tracker_searches);
        uart1_puts(",tracker_grid_evaluations=");
        uart1_u32(telemetry.tracker_grid_evaluations);
    }
    uart1_puts(",numeric_faults=");
    uart1_u32(numeric_faults);
    uart1_puts("\r\n");
}

#if RDMR_INTERNAL_DEMO

static void run_internal_demo(void)
{
    rdmr_experiment_config_t config;
    rdmr_signal_generator_t signal_generator;
    rdmr_signal_sample_t signal_sample;
    rdmr_cycle_stats_t all_cycle_stats;
    rdmr_cycle_stats_t block_cycle_stats;
    rdmr_cycle_stats_t block_total_cycle_stats;
    rdmr_cycle_stats_t tracker_cycle_stats;
    rdmr_cycle_summary_t all_cycle_summary;
    rdmr_cycle_summary_t block_cycle_summary;
    rdmr_cycle_summary_t block_total_cycle_summary;
    rdmr_cycle_summary_t tracker_cycle_summary;
    rdmr_log_record_t record;
    uint32_t sample_index;
    uint32_t data_rows = 0U;
    uint32_t numeric_faults = 0U;
    uint32_t block_cycles_total = 0U;
    /*
     * Use the protocol-bound 72 MHz target clock for evidence metadata.
     * DWT still measures the actual elapsed core cycles.  Keeping the
     * acceptance budgets independent of mutable CMSIS clock state prevents
     * a valid timing run from reporting a zero deadline.
     */
    const uint32_t deadline_cycles = RDMR_SAMPLE_DEADLINE_CYCLES;
    const uint32_t block_deadline_cycles = RDMR_BLOCK_DEADLINE_CYCLES;

    config.algorithm_id =
        (rdmr_algorithm_id_t)RDMR_DEMO_ALGORITHM;
    config.trajectory_id =
        (rdmr_trajectory_id_t)RDMR_DEMO_TRAJECTORY;
    config.near_line_id =
        (rdmr_near_line_id_t)RDMR_DEMO_NEAR_LINE;
    config.noise_id =
        (rdmr_noise_id_t)RDMR_DEMO_NOISE;
    config.seed = RDMR_DEMO_SEED;
    config.sample_count = RDMR_PROTOCOL_SAMPLE_COUNT;
    config.log_schema_version = RDMR_LOG_SCHEMA_VERSION_ID;
    config.sample_rate_hz = RDMR_PROTOCOL_FS_HZ;
    config.pli_amplitude = RDMR_DEMO_PLI_AMPLITUDE;

    rdmr_signal_init(&signal_generator, &config);
#if RDMR_EMIT_INIT_DIAGNOSTICS
    {
        rdmr_signal_generator_t probe_generator;
        rdmr_signal_sample_t probe_sample;
        uint32_t probe_flags = 0U;
        int probe_ok;

        rdmr_signal_init(&probe_generator, &config);
        probe_ok = rdmr_signal_next(&probe_generator, &probe_sample);

        uart1_puts(
            "DIAG,revision=" RDMR_FIRMWARE_REVISION_TEXT
            ",dwt_enabled="
        );
        uart1_u32((uint32_t)RDMR_ENABLE_DWT);
        uart1_puts(",dwt_ctrl=");
        uart1_u32(DWT->CTRL);
        uart1_puts(",dwt_count=");
        uart1_u32(DWT->CYCCNT);
        uart1_puts(",probe_ok=");
        uart1_u32((uint32_t)probe_ok);
        uart1_puts(",pli_u6=");
        uart1_i32(
            scaled_i32(
                config.pli_amplitude,
                RDMR_VALUE_SCALE,
                RDMR_NUMERIC_INPUT,
                &probe_flags
            )
        );
        uart1_puts(",phase_u6=");
        uart1_i32(
            scaled_i32(
                signal_generator.line_phase_rad,
                RDMR_VALUE_SCALE,
                RDMR_NUMERIC_INPUT,
                &probe_flags
            )
        );
        uart1_puts(",line_sin_u6=");
        uart1_i32(
            scaled_i32(
                signal_generator.line_sin,
                RDMR_VALUE_SCALE,
                RDMR_NUMERIC_INPUT,
                &probe_flags
            )
        );
        uart1_puts(",line_cos_u6=");
        uart1_i32(
            scaled_i32(
                signal_generator.line_cos,
                RDMR_VALUE_SCALE,
                RDMR_NUMERIC_INPUT,
                &probe_flags
            )
        );
        uart1_puts(",sin1_u6=");
        uart1_i32(
            scaled_i32(
                rdmr_trig_sin(1.0f),
                RDMR_VALUE_SCALE,
                RDMR_NUMERIC_INPUT,
                &probe_flags
            )
        );
        uart1_puts(",internal_n=");
        uart1_u32(probe_generator.sample_index);
        uart1_puts(",internal_count=");
        uart1_u32(probe_generator.config.sample_count);
        uart1_puts(",internal_pli_u6=");
        uart1_i32(
            scaled_i32(
                probe_generator.config.pli_amplitude,
                RDMR_VALUE_SCALE,
                RDMR_NUMERIC_INPUT,
                &probe_flags
            )
        );
        uart1_puts(",clean_u6=");
        uart1_i32(
            scaled_i32(
                probe_sample.clean,
                RDMR_VALUE_SCALE,
                RDMR_NUMERIC_CLEAN,
                &probe_flags
            )
        );
        uart1_puts(",interference_u6=");
        uart1_i32(
            scaled_i32(
                probe_sample.interference,
                RDMR_VALUE_SCALE,
                RDMR_NUMERIC_INPUT,
                &probe_flags
            )
        );
        uart1_puts(",input_u6=");
        uart1_i32(
            scaled_i32(
                probe_sample.input,
                RDMR_VALUE_SCALE,
                RDMR_NUMERIC_INPUT,
                &probe_flags
            )
        );
        uart1_puts(",flags=");
        uart1_u32(probe_flags);
        uart1_puts("\r\n");
    }
#endif
    rdmr_cycle_stats_init(&all_cycle_stats, deadline_cycles);
    rdmr_cycle_stats_init(&block_cycle_stats, deadline_cycles);
    rdmr_cycle_stats_init(
        &block_total_cycle_stats,
        block_deadline_cycles
    );
    rdmr_cycle_stats_init(&tracker_cycle_stats, deadline_cycles);
    if (rdmr_algorithm_init(&canceller, config.algorithm_id) == 0) {
        uart1_puts("ERROR,algorithm_initialization_failed\r\n");
        uart1_puts("DONE,rows=0,status=FAIL\r\n");
        return;
    }

#if RDMR_EMIT_INIT_DIAGNOSTICS && RDMR_ENABLE_DWT
    {
        uint32_t timing_start;
        uint32_t timing_cycles;
        volatile float timing_output;

        timing_start = DWT->CYCCNT;
        timing_output = rdmr_algorithm_process(&canceller, 0.5f);
        timing_cycles = DWT->CYCCNT - timing_start;
        uart1_puts(
            "TIMING,revision=" RDMR_FIRMWARE_REVISION_TEXT
            ",algorithm="
        );
        uart1_u32((uint32_t)config.algorithm_id);
        uart1_puts(",single_sample_cycles=");
        uart1_u32(timing_cycles);
        uart1_puts(",output_u6=");
        uart1_i32(
            (int32_t)(timing_output * RDMR_VALUE_SCALE)
        );
        uart1_puts("\r\n");
        (void)rdmr_algorithm_init(&canceller, config.algorithm_id);
    }
#endif

    emit_config(&config);
    uart1_puts(RDMR_LOG_HEADER);

    record.desired_energy = 0.0f;
    record.input_error_energy = 0.0f;
    record.output_error_energy = 0.0f;
    for (sample_index = 0U; sample_index < config.sample_count; ++sample_index) {
        rdmr_algorithm_telemetry_t before;
        rdmr_algorithm_telemetry_t after;
        float input_error;
        float output_error;
#if RDMR_ENABLE_DWT
        uint32_t start_cycles;
#endif
        uint32_t elapsed_cycles;
#if RDMR_EMIT_INIT_DIAGNOSTICS
        const uint32_t sample_number = sample_index + 1U;
        const int trace_milestone =
            (sample_number == 1U)
            || (sample_number == 5U)
            || (sample_number == 10U)
            || (sample_number == 20U)
            || (sample_number == 50U);
        if (trace_milestone != 0) {
            emit_trace(sample_number, "enter", 0U);
        }
#endif

        if (rdmr_signal_next(&signal_generator, &signal_sample) == 0) {
            uart1_puts("ERROR,signal_generator_ended_early\r\n");
            uart1_puts("DONE,rows=");
            uart1_u32(data_rows);
            uart1_puts(",status=FAIL\r\n");
            return;
        }
#if RDMR_EMIT_INIT_DIAGNOSTICS
        if (sample_number == 1U) {
            emit_trace(sample_number, "signal", 0U);
        }
#endif

        rdmr_algorithm_get_telemetry(&canceller, &before);
#if RDMR_EMIT_INIT_DIAGNOSTICS
        if (sample_number == 1U) {
            emit_trace(sample_number, "telemetry_before", 0U);
        }
#endif
#if RDMR_ENABLE_DWT
        start_cycles = DWT->CYCCNT;
#endif
        record.output =
            rdmr_algorithm_process(&canceller, signal_sample.input);
#if RDMR_ENABLE_DWT
        elapsed_cycles = DWT->CYCCNT - start_cycles;
#else
        elapsed_cycles = 0U;
#endif
#if RDMR_EMIT_INIT_DIAGNOSTICS
        if (sample_number == 1U) {
            emit_trace(sample_number, "algorithm", elapsed_cycles);
        }
#endif
        rdmr_algorithm_get_telemetry(&canceller, &after);
#if RDMR_EMIT_INIT_DIAGNOSTICS
        if (sample_number == 1U) {
            emit_trace(sample_number, "telemetry_after", elapsed_cycles);
        }
#endif
        rdmr_cycle_stats_update(&all_cycle_stats, elapsed_cycles);
#if RDMR_EMIT_INIT_DIAGNOSTICS
        if (sample_number == 1U) {
            emit_trace(sample_number, "all_stats", elapsed_cycles);
        }
#endif
        rdmr_cycle_stats_update(&block_cycle_stats, elapsed_cycles);
        block_cycles_total += elapsed_cycles;
#if RDMR_EMIT_INIT_DIAGNOSTICS
        if (sample_number == 1U) {
            emit_trace(sample_number, "block_stats", elapsed_cycles);
        }
#endif
        if (after.tracker_calls > before.tracker_calls) {
            rdmr_cycle_stats_update(&tracker_cycle_stats, elapsed_cycles);
        }

        input_error = signal_sample.input - signal_sample.clean;
        output_error = record.output - signal_sample.clean;
        record.desired_energy += signal_sample.clean * signal_sample.clean;
        record.input_error_energy += input_error * input_error;
        record.output_error_energy += output_error * output_error;
#if RDMR_EMIT_INIT_DIAGNOSTICS
        if (trace_milestone != 0) {
            emit_trace(sample_number, "sample_complete", elapsed_cycles);
        }
#endif

        if (((sample_index + 1U) % RDMR_BLOCK_SIZE) == 0U) {
            record.sample_index = sample_index + 1U;
            record.input = signal_sample.input;
            record.clean = signal_sample.clean;
            record.true_frequency_hz = signal_sample.true_frequency_hz;
            rdmr_cycle_stats_get(&block_cycle_stats, &block_cycle_summary);
            rdmr_cycle_stats_update(
                &block_total_cycle_stats,
                block_cycles_total
            );
#if RDMR_EMIT_INIT_DIAGNOSTICS
            emit_trace(sample_number, "block_summary", elapsed_cycles);
#endif
            if (
                emit_record(
                    &record,
                    &block_cycle_summary,
                    block_cycles_total
                ) != 0U
            ) {
                numeric_faults += 1U;
            }
#if RDMR_EMIT_INIT_DIAGNOSTICS
            emit_trace(sample_number, "record_emitted", elapsed_cycles);
#endif
            data_rows += 1U;
            record.desired_energy = 0.0f;
            record.input_error_energy = 0.0f;
            record.output_error_energy = 0.0f;
            block_cycles_total = 0U;
            rdmr_cycle_stats_init(&block_cycle_stats, deadline_cycles);
        }
    }

    rdmr_cycle_stats_get(&all_cycle_stats, &all_cycle_summary);
    rdmr_cycle_stats_get(
        &block_total_cycle_stats,
        &block_total_cycle_summary
    );
    rdmr_cycle_stats_get(&tracker_cycle_stats, &tracker_cycle_summary);
    emit_stats(
        &all_cycle_summary,
        &block_total_cycle_summary,
        &tracker_cycle_summary,
        data_rows,
        numeric_faults
    );
    uart1_puts("DONE,rows=");
    uart1_u32(data_rows);
    uart1_puts(",status=");
    uart1_puts(
        (
            (numeric_faults == 0U)
            && (data_rows == RDMR_LOG_EXPECTED_ROWS)
        )
            ? "PASS"
            : "FAIL"
    );
    uart1_puts("\r\n");
}

#else

static void adc1_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_ADC1EN;
    GPIOA->CRL &= ~0xFU;
    ADC1->CR2 = ADC_CR2_ADON;
    ADC1->SMPR2 = ADC_SMPR2_SMP0_1 | ADC_SMPR2_SMP0_0;
    ADC1->CR2 |= ADC_CR2_RSTCAL;
    while ((ADC1->CR2 & ADC_CR2_RSTCAL) != 0U) {
    }
    ADC1->CR2 |= ADC_CR2_CAL;
    while ((ADC1->CR2 & ADC_CR2_CAL) != 0U) {
    }
}

static uint16_t adc1_read(void)
{
    ADC1->CR2 |= ADC_CR2_ADON;
    while ((ADC1->SR & ADC_SR_EOC) == 0U) {
    }
    return (uint16_t)ADC1->DR;
}

static void delay_one_millisecond(void)
{
    const uint32_t start = DWT->CYCCNT;
    const uint32_t interval = SystemCoreClock / 1000U;
    while ((DWT->CYCCNT - start) < interval) {
    }
}

static void run_adc(void)
{
    uint32_t sample_index = 0U;

    adc1_init();
    if (rdmr_algorithm_init(&canceller, RDMR_DEMO_ALGORITHM) == 0) {
        uart1_puts("ERROR,algorithm_initialization_failed\r\n");
        return;
    }
    while (1) {
        const float input =
            ((float)adc1_read() - 2048.0f) / 2048.0f;
        const uint32_t start_cycles = DWT->CYCCNT;
        (void)rdmr_algorithm_process(&canceller, input);
        ++sample_index;
        delay_one_millisecond();
    }
}

#endif

int main(void)
{
    uart1_init();
    uart1_puts(
        "BOOT,protocol=" RDMR_PROTOCOL_ID
        ",implementation=" RDMR_IMPLEMENTATION_VERSION
        ",schema=" RDMR_LOG_SCHEMA_VERSION
        ",firmware_revision=" RDMR_FIRMWARE_REVISION_TEXT "\r\n"
    );

#if RDMR_ENABLE_DWT
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0U;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
#endif

#if RDMR_INTERNAL_DEMO
    run_internal_demo();
#else
    run_adc();
#endif

    while (1) {
    }
}
