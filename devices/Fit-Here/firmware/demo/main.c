// Fit-Here demo: proves our own code runs on the bracelet.
//
// Advertises as FH-DEMO at C0:00:A1:B1:02:64 (the app's address + 3) and accepts a connection.
// The standard Battery Level characteristic is a live counter, 0-100 once a second.
// Writes to the control characteristic 4c500002-3731-3500-b000-000000000000:
//   04             back to the PPlusOTA updater
//   20 pp lo hi    drive pin Ppp (decimal number as hex, e.g. 03) high for lo + hi*256 ms, max 500
//   21 vv          screen light on P34: 01 on, 00 off (held, unlike the pulses)
//   22 pp lo hi    same as 20 but drives the pin low
//   30 rr ss mm    wake the display trying RST=Prr, SCK=Pss, MOSI=Pmm; ff = try all (blocks, see probe)
//   31 rr ss mm dd hh ll  same pins plus DC=Pdd: draws a band of colour hhll, its row tells the DC pin
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
static volatile bool want_probe;
static volatile uint8 probe_args[3];
static volatile uint8 fill_dc = 0xff;
static volatile uint8 fill_color[2];
static volatile uint8 pulse_number;
static volatile uint8 pulse_level;
static volatile uint16 pulse_ms;

static bool pulsing;
static gpio_pin_e pulse_pin;
static uint32_t pulse_start, pulse_ticks;
static uint32_t last_second;
static uint8 counter;

__attribute__((noinline)) __ATTR_SECTION_SRAM__ static void on_command(const uint8 *data, uint8 len) {
    if (data[0] == 0x04) {
        want_updater = true;
    } else if (data[0] == 0x30 && len == 4) {
        probe_args[0] = data[1];
        probe_args[1] = data[2];
        probe_args[2] = data[3];
        want_probe = true;
    } else if (data[0] == 0x31 && len == 7) {
        fill_color[0] = data[5];
        fill_color[1] = data[6];
        probe_args[0] = data[1];
        probe_args[1] = data[2];
        probe_args[2] = data[3];
        fill_dc = data[4];
        want_probe = true;
    } else if (data[0] == 0x7f && len == 2 && data[1] == 0xa5) {
        want_hang = true;
    } else if (data[0] == 0x21 && len == 2) {
        hal_gpio_write(GPIO_P34, data[1] != 0);
    } else if ((data[0] == 0x20 || data[0] == 0x22) && len == 4 && !want_pulse) {
        pulse_level = data[0] == 0x20;
        pulse_number = data[1];
        pulse_ms = data[2] | data[3] << 8;
        want_pulse = true;
    }
}

// Display search. Everything lives in SRAM: the XIP image may not grow past 0x26fff.
// Pins not under test stay low, which covers an active-low CS and DC = command.
#define PROBE_ANY 0xff
#define PROBE_PINS 12

static const uint8 probe_list[PROBE_PINS] = {
    GPIO_P24, GPIO_P25, GPIO_P33, GPIO_P32, GPIO_P31, GPIO_P27,
    GPIO_P26, GPIO_P03, GPIO_P02, GPIO_P01, GPIO_P00, GPIO_P11,
};

__attribute__((noinline)) __ATTR_SECTION_SRAM__ static int pin_of(uint8 number) {
    for (uint32_t i = 0; i < sizeof(pins) / sizeof(pins[0]); i++)
        if (pins[i].number == number)
            return pins[i].pin;
    return -1;
}

__ATTR_SECTION_SRAM__ static void wait_ms(uint32_t ms) {
    uint32_t start = hal_systick();
    while (hal_systick() - start < MS_TO_TICKS(ms))
        hal_watchdog_feed();
}

__ATTR_SECTION_SRAM__ static void spi_byte(gpio_pin_e sck, gpio_pin_e mosi, uint8 value) {
    for (int bit = 7; bit >= 0; bit--) {
        hal_gpio_write(mosi, (value >> bit) & 1);
        hal_gpio_write(sck, 1);
        hal_gpio_write(sck, 0);
    }
}

__ATTR_SECTION_SRAM__ static void buzz(int times) {
    for (int i = 0; i < times; i++) {
        hal_gpio_write(GPIO_P23, 1);
        wait_ms(150);
        hal_gpio_write(GPIO_P23, 0);
        wait_ms(350);
    }
    wait_ms(1000);
}

__ATTR_SECTION_SRAM__ static void probe_trial(gpio_pin_e rst, gpio_pin_e sck, gpio_pin_e mosi, int blinks) {
    for (int i = 0; i < PROBE_PINS; i++)
        hal_gpio_write((gpio_pin_e)probe_list[i], 0);
    wait_ms(20);
    hal_gpio_write(rst, 1);
    wait_ms(30);
    spi_byte(sck, mosi, 0x11);   // sleep out
    wait_ms(120);
    spi_byte(sck, mosi, 0x21);   // inversion on: a black frame memory shows white
    spi_byte(sck, mosi, 0x29);   // display on
    wait_ms(200);
    for (int i = 0; i < blinks; i++) {   // needs no DC pin: the image itself says which pin this is
        spi_byte(sck, mosi, 0x28);
        wait_ms(150);
        spi_byte(sck, mosi, 0x29);
        wait_ms(250);
    }
}

__ATTR_SECTION_SRAM__ static void lcd_cmd(gpio_pin_e sck, gpio_pin_e mosi, gpio_pin_e dc, uint8 cmd,
                                          const uint8 *args, int count) {
    hal_gpio_write(dc, 0);
    spi_byte(sck, mosi, cmd);
    hal_gpio_write(dc, 1);
    for (int i = 0; i < count; i++)
        spi_byte(sck, mosi, args[i]);
    hal_gpio_write(dc, 0);
}

// The panel keeps its memory across resets, so a pixel on screen doesn't say which trial wrote it:
// each DC candidate gets its own 7-row band, 10 rows below the previous one, starting at row 66.
__attribute__((noinline)) __ATTR_SECTION_SRAM__
static void fill_strip(gpio_pin_e rst, gpio_pin_e sck, gpio_pin_e mosi, gpio_pin_e dc) {
    static const uint8 colmod[] = {0x05};
    static const uint8 columns[] = {0, 0, 0, 131};
    int slot = 0;
    for (int i = 0; i < PROBE_PINS && probe_list[i] != dc; i++)
        if (probe_list[i] != rst && probe_list[i] != sck && probe_list[i] != mosi)
            slot++;
    uint8 first = 66 + 10 * slot;
    uint8 rows[] = {0, first, 0, (uint8)(first + 6)};

    for (int i = 0; i < PROBE_PINS; i++)
        hal_gpio_write((gpio_pin_e)probe_list[i], 0);
    wait_ms(20);
    hal_gpio_write(rst, 1);
    wait_ms(30);
    lcd_cmd(sck, mosi, dc, 0x11, 0, 0);          // sleep out
    wait_ms(120);
    lcd_cmd(sck, mosi, dc, 0x20, 0, 0);          // inversion off
    lcd_cmd(sck, mosi, dc, 0x3a, colmod, 1);     // 16 bit per pixel
    lcd_cmd(sck, mosi, dc, 0x2a, columns, 4);
    lcd_cmd(sck, mosi, dc, 0x2b, rows, 4);
    lcd_cmd(sck, mosi, dc, 0x2c, 0, 0);          // memory write
    hal_gpio_write(dc, 1);
    for (int y = 0; y < 7; y++) {
        for (int x = 0; x <= 131; x++) {
            spi_byte(sck, mosi, fill_color[0]);
            spi_byte(sck, mosi, fill_color[1]);
        }
        hal_watchdog_feed();
    }
    hal_gpio_write(dc, 0);
    lcd_cmd(sck, mosi, dc, 0x29, 0, 0);          // display on
}

// One explicit trial leaves the pins driven. With wildcards: a wildcard RST buzzes index+1 times, the
// image blinks index+1 times for the SCK (or, with SCK fixed, MOSI) pin, and the pins are released.
__attribute__((noinline)) __ATTR_SECTION_SRAM__ static void probe(void) {
    int want[3];
    for (int i = 0; i < 3; i++)
        want[i] = probe_args[i] == PROBE_ANY ? -1 : pin_of(probe_args[i]);
    bool any = want[0] < 0 || want[1] < 0 || want[2] < 0;
    hal_gpio_write(GPIO_P34, 1);
    if (fill_dc != PROBE_ANY) {
        int dc = pin_of(fill_dc);
        fill_dc = PROBE_ANY;
        if (!any && dc >= 0)
            fill_strip((gpio_pin_e)want[0], (gpio_pin_e)want[1], (gpio_pin_e)want[2], (gpio_pin_e)dc);
        return;
    }
    if (!any) {
        probe_trial((gpio_pin_e)want[0], (gpio_pin_e)want[1], (gpio_pin_e)want[2], 0);
        return;
    }
    if (want[0] >= 0)
        buzz(1);
    for (int r = 0; r < PROBE_PINS; r++) {
        if (want[0] >= 0 && probe_list[r] != want[0])
            continue;
        if (want[0] < 0)
            buzz(r + 1);
        for (int s = 0; s < PROBE_PINS; s++) {
            if (s == r || (want[1] >= 0 && probe_list[s] != want[1]))
                continue;
            for (int m = 0; m < PROBE_PINS; m++) {
                if (m == r || m == s || (want[2] >= 0 && probe_list[m] != want[2]))
                    continue;
                probe_trial((gpio_pin_e)probe_list[r], (gpio_pin_e)probe_list[s],
                            (gpio_pin_e)probe_list[m], want[1] < 0 ? s + 1 : m + 1);
            }
        }
    }
    for (int i = 0; i < PROBE_PINS; i++) {
        hal_gpio_pin_init((gpio_pin_e)probe_list[i], GPIO_INPUT);
        hal_gpio_pull_set((gpio_pin_e)probe_list[i], GPIO_FLOATING);
    }
}

static void start_pulse(void) {
    int pin = pin_of(pulse_number);
    if (pin >= 0) {
        pulse_pin = (gpio_pin_e)pin;
        pulse_ticks = MS_TO_TICKS(pulse_ms > MAX_PULSE_MS ? MAX_PULSE_MS : pulse_ms);
        pulse_start = hal_systick();
        hal_gpio_write(pulse_pin, pulse_level);
        pulsing = true;
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
    if (want_probe) {
        want_probe = false;
        probe();
    }
    if (pulsing && hal_systick() - pulse_start >= pulse_ticks) {
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
