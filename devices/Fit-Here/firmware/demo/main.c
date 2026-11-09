// Fit-Here demo: proves our own code runs on the bracelet.
//
// Advertises as FH-DEMO at C0:00:A1:B1:02:64 (the app's address + 3) and accepts a connection.
// The standard Battery Level characteristic is a live counter, 0-100 once a second.
// Writes to the control characteristic 4c500002-3731-3500-b000-000000000000:
//   04             back to the PPlusOTA updater
//   20 pp lo hi    drive pin Ppp (decimal number as hex, e.g. 03) high for lo + hi*256 ms, max 500
//   7f a5          hang in the main loop, to test that the watchdog resets the app
//
// Safety: the OTA mode is armed first, so any later soft reset lands in the updater, and the
// watchdog resets a hung app. P07 (test mode) and P09/P10 (UART) can't be driven.
#include "app.h"
#include "ble/ble.h"
#include "ble/services.h"
#include "OSAL.h"
#include "watchdog.h"

#define OTA_MODE_REG (*(volatile uint32_t *)0x4000f034)
#define MS_TO_TICKS(ms) ((ms) * 8 / 5)   // hal_systick() counts 625 us slots
#define MAX_PULSE_MS 500

extern uint8 ownPublicAddr[6];

static const struct {
    uint8 number;
    gpio_pin_e pin;
} pins[] = {
    {0, GPIO_P00},   {1, GPIO_P01},   {2, GPIO_P02},   {3, GPIO_P03},   {11, GPIO_P11},
    {14, GPIO_P14},  {15, GPIO_P15},  {16, GPIO_P16},  {17, GPIO_P17},  {18, GPIO_P18},
    {20, GPIO_P20},  {23, GPIO_P23},  {24, GPIO_P24},  {25, GPIO_P25},  {26, GPIO_P26},
    {27, GPIO_P27},  {31, GPIO_P31},  {32, GPIO_P32},  {33, GPIO_P33},  {34, GPIO_P34},
};

static volatile bool want_updater;
static volatile bool want_hang;
static volatile bool want_pulse;
static volatile uint8 pulse_number;
static volatile uint16 pulse_ms;

static bool pulsing;
static gpio_pin_e pulse_pin;
static uint32_t pulse_start, pulse_ticks;
static uint32_t last_second;
static uint8 counter;

static void on_command(const uint8 *data, uint8 len) {
    if (data[0] == 0x04) {
        want_updater = true;
    } else if (data[0] == 0x7f && len == 2 && data[1] == 0xa5) {
        want_hang = true;
    } else if (data[0] == 0x20 && len == 4 && !want_pulse) {
        pulse_number = data[1];
        pulse_ms = data[2] | data[3] << 8;
        want_pulse = true;
    }
}

static void start_pulse(void) {
    for (uint32_t i = 0; i < sizeof(pins) / sizeof(pins[0]); i++) {
        if (pins[i].number != pulse_number)
            continue;
        pulse_pin = pins[i].pin;
        pulse_ticks = MS_TO_TICKS(pulse_ms > MAX_PULSE_MS ? MAX_PULSE_MS : pulse_ms);
        pulse_start = hal_systick();
        hal_gpio_write(pulse_pin, 1);
        pulsing = true;
        return;
    }
}

void app_init(void) {
    static const uint8 addr[6] = {0x64, 0x02, 0xb1, 0xa1, 0x00, 0xc0};

    OTA_MODE_REG = (OTA_MODE_REG & ~0xfu) | 2u;
    watchdog_config(WDG_8S);
    osal_memcpy(ownPublicAddr, addr, sizeof(addr));
    ble_set_name("FH-DEMO");
    svc_init(on_command);
}

void app_update(void) {
    hal_watchdog_feed();
    if (want_updater)
        hal_system_soft_reset();
    while (want_hang)
        ;
    if (pulsing &&hal_systick() - pulse_start >= pulse_ticks) {
        hal_gpio_write(pulse_pin, 0);
        hal_gpio_pin_init(pulse_pin, GPIO_INPUT);
        hal_gpio_pull_set(pulse_pin, GPIO_FLOATING);
        pulsing = false;
    }
    if (want_pulse) {
        if (!pulsing)
            start_pulse();
        want_pulse = false;
    }
    if (hal_systick() - last_second >= 1600) {
        last_second = hal_systick();
        counter = (counter + 1) % 101;
        svc_battery_set(counter);
    }
}
