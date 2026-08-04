#ifndef RDMR_CYCLE_STATS_H
#define RDMR_CYCLE_STATS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RDMR_CYCLE_RESERVOIR_CAPACITY 128U

typedef struct {
    uint32_t count;
    uint64_t sum;
    uint32_t maximum;
    uint32_t deadline_cycles;
    uint32_t deadline_violations;
    uint32_t reservoir_count;
    uint32_t reservoir_rng;
    uint32_t reservoir[RDMR_CYCLE_RESERVOIR_CAPACITY];
} rdmr_cycle_stats_t;

typedef struct {
    uint32_t count;
    uint32_t mean;
    uint32_t median;
    uint32_t p95;
    uint32_t maximum;
    uint32_t deadline_cycles;
    uint32_t deadline_violations;
} rdmr_cycle_summary_t;

void rdmr_cycle_stats_init(
    rdmr_cycle_stats_t *stats,
    uint32_t deadline_cycles
);

void rdmr_cycle_stats_update(
    rdmr_cycle_stats_t *stats,
    uint32_t cycles
);

void rdmr_cycle_stats_get(
    const rdmr_cycle_stats_t *stats,
    rdmr_cycle_summary_t *summary
);

#ifdef __cplusplus
}
#endif

#endif
