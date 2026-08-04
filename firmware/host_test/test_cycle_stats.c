#include "../core/rdmr_cycle_stats.h"

#include <stdint.h>
#include <stdio.h>

int main(void)
{
    rdmr_cycle_stats_t stats;
    rdmr_cycle_summary_t summary;
    uint32_t value;

    rdmr_cycle_stats_init(&stats, 90U);
    for (value = 1U; value <= 100U; ++value) {
        rdmr_cycle_stats_update(&stats, value);
    }
    rdmr_cycle_stats_get(&stats, &summary);
    printf(
        "count=%lu mean=%lu median=%lu p95=%lu max=%lu violations=%lu\n",
        (unsigned long)summary.count,
        (unsigned long)summary.mean,
        (unsigned long)summary.median,
        (unsigned long)summary.p95,
        (unsigned long)summary.maximum,
        (unsigned long)summary.deadline_violations
    );
    if (summary.count != 100U) {
        return 1;
    }
    if (summary.mean != 51U) {
        return 2;
    }
    if ((summary.median < 48U) || (summary.median > 52U)) {
        return 3;
    }
    if ((summary.p95 < 92U) || (summary.p95 > 98U)) {
        return 4;
    }
    if (summary.maximum != 100U) {
        return 5;
    }
    if (summary.deadline_violations != 11U) {
        return 6;
    }
    return 0;
}
