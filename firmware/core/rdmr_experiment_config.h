#ifndef RDMR_EXPERIMENT_CONFIG_H
#define RDMR_EXPERIMENT_CONFIG_H

/*
 * Generated contract for config/experiment_protocol__rdmr-pli__v0.3.0.json.
 * Keep the JSON file as the human- and machine-readable source of truth.
 */

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RDMR_PROTOCOL_ID                 "cssp-rdmr-pli-v0.5.0"
#define RDMR_PROTOCOL_SCHEMA_VERSION     "0.5.0"
#define RDMR_IMPLEMENTATION_VERSION      "0.4.1"
#ifndef RDMR_FIRMWARE_REVISION
#define RDMR_FIRMWARE_REVISION           17
#endif
#define RDMR_STRINGIFY_INNER(value)      #value
#define RDMR_STRINGIFY(value)            RDMR_STRINGIFY_INNER(value)
#define RDMR_FIRMWARE_REVISION_TEXT      RDMR_STRINGIFY(RDMR_FIRMWARE_REVISION)
#define RDMR_LOG_SCHEMA_VERSION          "rdmr-block-csv-v3"
#define RDMR_LOG_SCHEMA_VERSION_ID       3U
#define RDMR_PROTOCOL_FS_HZ              1000.0f
#define RDMR_PROTOCOL_SAMPLE_COUNT       8000U
#define RDMR_TARGET_CPU_CLOCK_HZ         72000000U
#define RDMR_SAMPLE_DEADLINE_CYCLES      (RDMR_TARGET_CPU_CLOCK_HZ / 1000U)
#define RDMR_BLOCK_DEADLINE_CYCLES       (RDMR_TARGET_CPU_CLOCK_HZ / 20U)

typedef enum {
    RDMR_ALGORITHM_A0_FIXED_NOTCH = 0,
    RDMR_ALGORITHM_A1_FIXED_NLMS = 1,
    RDMR_ALGORITHM_A2_FULL_RATE = 2,
    RDMR_ALGORITHM_A3_RESIDUAL_MULTIRATE = 3,
    RDMR_ALGORITHM_B1_FIXED_INTERVAL_3 = 4,
    RDMR_ALGORITHM_B2_FIXED_INTERVAL_12 = 5,
    RDMR_ALGORITHM_B3_FIXED_INTERVAL_4 = 6,
    RDMR_ALGORITHM_B4_TWO_STATE_RESIDUAL = 7
} rdmr_algorithm_id_t;

typedef enum {
    RDMR_TRAJECTORY_F0 = 0,
    RDMR_TRAJECTORY_F1 = 1,
    RDMR_TRAJECTORY_F2 = 2,
    RDMR_TRAJECTORY_F3 = 3,
    RDMR_TRAJECTORY_F4 = 4,
    RDMR_TRAJECTORY_F5 = 5
} rdmr_trajectory_id_t;

typedef enum {
    RDMR_NEAR_LINE_N0 = 0,
    RDMR_NEAR_LINE_N1 = 1,
    RDMR_NEAR_LINE_N2 = 2,
    RDMR_NEAR_LINE_N3 = 3
} rdmr_near_line_id_t;

typedef enum {
    RDMR_NOISE_NONE = 0,
    RDMR_NOISE_SNR_20_DB = 1,
    RDMR_NOISE_SNR_10_DB = 2
} rdmr_noise_id_t;

typedef struct {
    rdmr_algorithm_id_t algorithm_id;
    rdmr_trajectory_id_t trajectory_id;
    rdmr_near_line_id_t near_line_id;
    rdmr_noise_id_t noise_id;
    uint32_t seed;
    uint32_t sample_count;
    uint16_t log_schema_version;
    float sample_rate_hz;
    float pli_amplitude;
} rdmr_experiment_config_t;

#ifdef __cplusplus
}
#endif

#endif
