/* GCC startup + vector table for MM32F031 (Cortex-M0), translated from the SDK's
   Keil startup_MM32x031.s. No SystemInit in this SDK — clock is set in BSP_Init. */
#include <stdint.h>

extern uint32_t _sdata, _edata, _sbss, _ebss, _sidata, _estack;
int main(void);

void Reset_Handler(void)
{
    uint32_t *src = &_sidata, *dst = &_sdata;
    while (dst < &_edata) *dst++ = *src++;
    for (dst = &_sbss; dst < &_ebss;) *dst++ = 0;
    main();
    for (;;) {}
}

void Default_Handler(void) { for (;;) {} }

#define WEAK __attribute__((weak, alias("Default_Handler")))
void NMI_Handler(void) WEAK;
void HardFault_Handler(void) WEAK;
void SVC_Handler(void) WEAK;
void PendSV_Handler(void) WEAK;
void SysTick_Handler(void) WEAK;
void WWDG_IRQHandler(void) WEAK;
void PVD_IRQHandler(void) WEAK;
void RTC_IRQHandler(void) WEAK;
void FLASH_IRQHandler(void) WEAK;
void RCC_IRQHandler(void) WEAK;
void EXTI0_1_IRQHandler(void) WEAK;
void EXTI2_3_IRQHandler(void) WEAK;
void EXTI4_15_IRQHandler(void) WEAK;
void DMA1_Channel1_IRQHandler(void) WEAK;
void DMA1_Channel2_3_IRQHandler(void) WEAK;
void DMA1_Channel4_5_IRQHandler(void) WEAK;
void ADC1_IRQHandler(void) WEAK;
void TIM1_BRK_UP_TRG_COM_IRQHandler(void) WEAK;
void TIM1_CC_IRQHandler(void) WEAK;
void TIM2_IRQHandler(void) WEAK;
void TIM3_IRQHandler(void) WEAK;
void TIM14_IRQHandler(void) WEAK;
void TIM16_IRQHandler(void) WEAK;
void TIM17_IRQHandler(void) WEAK;
void I2C1_IRQHandler(void) WEAK;
void SPI1_IRQHandler(void) WEAK;
void UART1_IRQHandler(void) WEAK;

__attribute__((section(".isr_vector"), used))
void (*const g_vectors[])(void) = {
    (void (*)(void))(&_estack),
    Reset_Handler, NMI_Handler, HardFault_Handler,
    0, 0, 0, 0, 0, 0, 0,
    SVC_Handler, 0, 0, PendSV_Handler, SysTick_Handler,
    WWDG_IRQHandler, PVD_IRQHandler, RTC_IRQHandler, FLASH_IRQHandler, RCC_IRQHandler,
    EXTI0_1_IRQHandler, EXTI2_3_IRQHandler, EXTI4_15_IRQHandler, 0,
    DMA1_Channel1_IRQHandler, DMA1_Channel2_3_IRQHandler, DMA1_Channel4_5_IRQHandler,
    ADC1_IRQHandler, TIM1_BRK_UP_TRG_COM_IRQHandler, TIM1_CC_IRQHandler,
    TIM2_IRQHandler, TIM3_IRQHandler, 0, 0, TIM14_IRQHandler, 0,
    TIM16_IRQHandler, TIM17_IRQHandler, I2C1_IRQHandler, 0, SPI1_IRQHandler, 0,
    UART1_IRQHandler,
};
