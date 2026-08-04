#include "stm32f1xx.h"

#ifndef RDMR_PROTEUS_BUILD
#define RDMR_PROTEUS_BUILD 1
#endif

uint32_t SystemCoreClock = 72000000U;

void SystemInit(void)
{
#if RDMR_PROTEUS_BUILD
    /*
     * Proteus drives the simulated processor clock from OSC Frequency
     * (9 MHz) and Clock Scale (8 Times). Avoid waiting for PLL status bits,
     * which are not required by the simulation clock model.
     */
    SystemCoreClock = 72000000U;
#else
    RCC->CR |= RCC_CR_HSEON;
    while ((RCC->CR & RCC_CR_HSERDY) == 0U) {
    }

    RCC->CFGR = 0U;
    FLASH->ACR = FLASH_ACR_PRFTBE | FLASH_ACR_LATENCY_2;

    /*
     * HSE 8 MHz * 9 = 72 MHz.
     * AHB = 72 MHz, APB1 = 36 MHz, APB2 = 72 MHz, ADC = 12 MHz.
     */
    RCC->CFGR =
        RCC_CFGR_PLLSRC
        | RCC_CFGR_PLLMULL9
        | RCC_CFGR_PPRE1_DIV2
        | RCC_CFGR_ADCPRE_DIV6;
    RCC->CR |= RCC_CR_PLLON;
    while ((RCC->CR & RCC_CR_PLLRDY) == 0U) {
    }

    RCC->CFGR |= RCC_CFGR_SW_PLL;
    while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_PLL) {
    }
#endif
}

void SystemCoreClockUpdate(void)
{
    SystemCoreClock = 72000000U;
}
