/* Placeholder application for toolchain validation (Fase 4.1).
 *
 * This does NOT yet drive the hardware: the real app will initialise the clocks and the
 * Macrogiga BLE stack (Src/lib/mg_BLE_lib_m0.lib, API in Src/inc/mg_api.h) and advertise.
 * For now it is a minimal, self-contained loop so we can confirm the GCC build produces a
 * valid Cortex-M0 image for this SoC and wrap it with tools/mkimage.py. Not to be flashed. */
#include <stdint.h>

/* a volatile counter so the loop body is not optimised away; proves .data/.bss paths work */
volatile uint32_t ticks;

int main(void)
{
    for (;;) {
        ticks++;
    }
    return 0;
}
