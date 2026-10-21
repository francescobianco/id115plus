/* Minimal Cortex-M0 startup for a RAM-resident DA14585 image (toolchain validation).
 * The boot ROM loads the whole image into SysRAM, so .data is already in place; we only
 * zero .bss and call main. No CMSIS, no Dialog SDK. Not a real app — see README.md. */
#include <stdint.h>

extern uint32_t _sbss, _ebss, _estack;
int main(void);

void Reset_Handler(void)
{
    for (uint32_t *p = &_sbss; p < &_ebss;) *p++ = 0;   /* zero .bss */
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

/* Cortex-M0 core vectors; the 32 peripheral IRQ slots default-handled for this skeleton. */
__attribute__((section(".isr_vector"), used))
void (*const g_vectors[])(void) = {
    (void (*)(void))(&_estack),
    Reset_Handler, NMI_Handler, HardFault_Handler,
    0, 0, 0, 0, 0, 0, 0,
    SVC_Handler, 0, 0, PendSV_Handler, SysTick_Handler,
    [16 ... 47] = Default_Handler,
};
