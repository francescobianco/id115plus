/* Minimal Cortex-M0 startup for the MM32F031. Vector table, reset handler (copy .data,
 * zero .bss, call main), default handlers. No CMSIS dependency. Toolchain-validation build. */
#include <stdint.h>

extern uint32_t _sdata, _edata, _sbss, _ebss, _etext, _estack;
int main(void);

void Reset_Handler(void)
{
    uint32_t *src = &_etext, *dst = &_sdata;
    while (dst < &_edata) *dst++ = *src++;   /* init .data from flash */
    for (dst = &_sbss; dst < &_ebss;) *dst++ = 0;  /* zero .bss */
    main();
    for (;;) {}
}

void Default_Handler(void) { for (;;) {} }

/* weak aliases so real handlers can override later */
#define WEAK __attribute__((weak, alias("Default_Handler")))
void NMI_Handler(void) WEAK;
void HardFault_Handler(void) WEAK;
void SVC_Handler(void) WEAK;
void PendSV_Handler(void) WEAK;
void SysTick_Handler(void) WEAK;

/* Cortex-M0 core vector table; peripheral IRQs (32) default-handled for now. */
__attribute__((section(".isr_vector"), used))
void (*const g_vectors[])(void) = {
    (void (*)(void))(&_estack),
    Reset_Handler,
    NMI_Handler,
    HardFault_Handler,
    0, 0, 0, 0, 0, 0, 0,   /* reserved */
    SVC_Handler,
    0, 0,                   /* reserved */
    PendSV_Handler,
    SysTick_Handler,
    /* 32 external interrupt slots -> Default_Handler */
    [16 ... 47] = Default_Handler,
};
