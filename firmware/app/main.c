/* id115plus custom firmware — entry point.
 *
 * First real BLE app for the MSLM707 (MM32F031 + Macrogiga radio). It brings up the
 * clocks/BSP and the BLE radio and advertises under our own name ("ID115DIY", set in
 * app.c). The GATT database and the advertising-rotation callback (UsrProcCallback) live
 * in app.c; the radio stack itself is the SDK's binary library (mg_BLE_lib_m0.lib).
 *
 * Init sequence mirrors the SDK reference so the vendor radio lib sees what it expects.
 * NOT to be flashed yet: app base address and the bootloader CRC32 variant are unconfirmed
 * (see ../../docs/firmware-build.md). This builds and links only, to grow our firmware.
 *
 * Based on the MacroGiga MS1793-SDK app-argun example (MIT).
 */
#include <string.h>
#include "HAL_conf.h"
#include "BSP.h"
#include "iwdg.h"
#include "mg_api.h"

/* filled by radio_initBle(); read by the advertising code in app.c */
unsigned char *ble_mac_addr;

int main(void)
{
    volatile unsigned long warmup = 0x200000;
    while (warmup--) { }             /* let the supply settle before touching the radio */

    BSP_Init();                      /* clocks, GPIO, SPI to the radio (see app/BSP.c) */
    Write_Iwdg_ON(IWDG_Prescaler_32, 0x4E2);   /* ~1 s watchdog */

    radio_initBle(TXPWR_0DBM, &ble_mac_addr);  /* bring up the Macrogiga BLE stack */

    ble_run(160 * 2);                /* advertise, 320 * 0.625 ms = 200 ms interval */
    return 0;
}
