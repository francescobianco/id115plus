/* Placeholder application for DA14585 toolchain validation.
 *
 * This does NOT drive the radio: a real app initialises the Dialog BLE stack from the
 * DA145xx SDK 6.x (rwip/ke/gapc/gapm + profiles) and advertises. For now this is a minimal
 * RAM-resident loop so we can confirm the GCC build produces a valid Cortex-M0 image at the
 * DA14585 SysRAM base (0x07FC0000). Not to be flashed. See README.md. */
#include <stdint.h>

volatile uint32_t ticks;

int main(void)
{
    for (;;) {
        ticks++;
    }
    return 0;
}
