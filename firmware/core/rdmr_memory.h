#ifndef RDMR_MEMORY_H
#define RDMR_MEMORY_H

#include <stdint.h>

/*
 * Keep initialization independent of the optimized ARM run-time memory
 * routines.  Some Proteus Cortex-M3 models do not execute their Thumb-2
 * tail-copy sequences consistently.
 */
static void rdmr_zero_bytes(void *destination, uint32_t byte_count)
{
    volatile uint8_t *bytes = (volatile uint8_t *)destination;

    while (byte_count > 0U) {
        *bytes = 0U;
        ++bytes;
        --byte_count;
    }
}

#endif
