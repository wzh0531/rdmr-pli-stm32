#include "rdmr_cycle_stats.h"
#include "rdmr_memory.h"

#include <stddef.h>

#define RDMR_RESERVOIR_INITIAL_STATE 0x6D2B79F5UL

static uint32_t reservoir_random(uint32_t *state)
{
    uint32_t value = *state;

    value ^= value << 13U;
    value ^= value >> 17U;
    value ^= value << 5U;
    *state = value;
    return value;
}

static uint32_t divide_u64_u32(uint64_t numerator, uint32_t denominator)
{
    uint64_t quotient = 0U;
    uint64_t remainder = 0U;
    uint32_t bit;

    if (denominator == 0U) {
        return 0U;
    }
    for (bit = 0U; bit < 64U; ++bit) {
        remainder =
            (remainder << 1U)
            | ((numerator >> 63U) & 1U);
        numerator <<= 1U;
        quotient <<= 1U;
        if (remainder >= (uint64_t)denominator) {
            remainder -= (uint64_t)denominator;
            quotient |= 1U;
        }
    }
    return (uint32_t)quotient;
}

static void sort_u32(uint32_t *values, uint32_t count)
{
    uint32_t index;

    for (index = 1U; index < count; ++index) {
        const uint32_t value = values[index];
        uint32_t position = index;

        while ((position > 0U) && (values[position - 1U] > value)) {
            values[position] = values[position - 1U];
            --position;
        }
        values[position] = value;
    }
}

static uint32_t percentile(
    const rdmr_cycle_stats_t *stats,
    uint32_t percentage
)
{
    uint32_t sorted[RDMR_CYCLE_RESERVOIR_CAPACITY];
    uint32_t index;
    uint32_t rank;

    if (stats->reservoir_count == 0U) {
        return 0U;
    }
    for (index = 0U; index < stats->reservoir_count; ++index) {
        sorted[index] = stats->reservoir[index];
    }
    sort_u32(sorted, stats->reservoir_count);
    rank =
        (
            percentage * (stats->reservoir_count - 1U)
            + 50U
        )
        / 100U;
    return sorted[rank];
}

void rdmr_cycle_stats_init(
    rdmr_cycle_stats_t *stats,
    uint32_t deadline_cycles
)
{
    if (stats == NULL) {
        return;
    }
    rdmr_zero_bytes(stats, (uint32_t)sizeof(*stats));
    stats->deadline_cycles = deadline_cycles;
    stats->reservoir_rng = RDMR_RESERVOIR_INITIAL_STATE;
}

void rdmr_cycle_stats_update(
    rdmr_cycle_stats_t *stats,
    uint32_t cycles
)
{
    uint32_t replacement;

    if (stats == NULL) {
        return;
    }
    stats->count += 1U;
    stats->sum += (uint64_t)cycles;
    if (cycles > stats->maximum) {
        stats->maximum = cycles;
    }
    if (
        (stats->deadline_cycles != 0U)
        && (cycles >= stats->deadline_cycles)
    ) {
        stats->deadline_violations += 1U;
    }

    if (stats->reservoir_count < RDMR_CYCLE_RESERVOIR_CAPACITY) {
        stats->reservoir[stats->reservoir_count] = cycles;
        stats->reservoir_count += 1U;
        return;
    }

    replacement =
        reservoir_random(&stats->reservoir_rng) % stats->count;
    if (replacement < RDMR_CYCLE_RESERVOIR_CAPACITY) {
        stats->reservoir[replacement] = cycles;
    }
}

void rdmr_cycle_stats_get(
    const rdmr_cycle_stats_t *stats,
    rdmr_cycle_summary_t *summary
)
{
    if ((stats == NULL) || (summary == NULL)) {
        return;
    }
    summary->count = stats->count;
    summary->mean =
        (stats->count == 0U)
            ? 0U
            : divide_u64_u32(
                stats->sum + (uint64_t)(stats->count / 2U),
                stats->count
            );
    summary->median = percentile(stats, 50U);
    summary->p95 = percentile(stats, 95U);
    summary->maximum = stats->maximum;
    summary->deadline_cycles = stats->deadline_cycles;
    summary->deadline_violations = stats->deadline_violations;
}
