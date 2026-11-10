// Fit-Here demo: proves our own code runs on the bracelet.
//
// Advertises as FH-DEMO at C0:00:A1:B1:02:64 (the app's address + 3) and accepts a connection.
// The standard Battery Level characteristic is a live counter, 0-100 once a second.
// Writes to the control characteristic 4c500002-3731-3500-b000-000000000000:
//   04             back to the PPlusOTA updater
//   20 pp lo hi    drive pin Ppp (decimal number as hex, e.g. 03) high for lo + hi*256 ms, max 500
//   21 vv          screen light on P34: 01 on, 00 off (held, unlike the pulses)
//   22 pp lo hi    same as 20 but drives the pin low
//   23             measure: notifies on 4c500003, one byte each: 23, P14 mV lo, hi (ffff = failed), P15
//   25 01 / 25 00  emergency exit on the touch key on / off (on at boot): held 10 s = red screen; release,
//                  then 3 taps under 400 ms within 5 s of each other = updater
//   24 01 / 24 00  start / stop watching for the key: candidates become inputs, with pull-up and pull-down
//                  in turn; each change notifies one byte: pin number, 40 = under pull-down, 80 = high
//   30 rr ss mm    wake the display trying RST=Prr, SCK=Pss, MOSI=Pmm; ff = try all (blocks, see probe)
//   31 rr ss mm dd hh ll  same pins plus DC=Pdd: draws a band of colour hhll, its row tells the DC pin
//   7f a5          hang in the main loop, to test that the watchdog resets the app
//   7f 5a          take a processor exception in the main loop, same test
// Drawing, in panel memory coordinates (the 80x160 glass sits inside a larger memory):
//   40             reset and set up the display, light on
//   41 cc args...  send one raw controller command
//   42 x y w h hh ll  fill a rectangle with colour hhll (RGB565)
//   43 x y w h     open a window for 44
//   44 (n hh ll)*  n pixels of colour hhll, repeated, written into the open window
//   45             notifies byte 45 on 4c500003 once everything sent before it has been drawn
//
// Safety: the OTA mode is armed first, so any later soft reset lands in the updater, and the
// watchdog resets a hung app. P07 (test mode) and P09/P10 (UART) can't be driven.
#include "app.h"
#include "ble/ble.h"
#include "ble/services.h"
#include "OSAL.h"
#include "watchdog.h"
#include "adc.h"

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
static volatile bool want_fault;
static volatile bool want_power;
static volatile uint8 want_watch = 0xff;
static volatile uint8 want_emergency = 0xff;
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

// Drawing commands wait here: the panel is driven from the main loop, not from the BLE task.
// A sender must use 45 to stay within CMD_SLOTS commands ahead of the drawing.
#define CMD_SIZE 20
#define CMD_SLOTS 32

static uint8 cmd_queue[CMD_SLOTS][CMD_SIZE];
static uint8 cmd_len[CMD_SLOTS];
static volatile uint8 cmd_head, cmd_tail;
static uint32_t fill_left;
static uint8 fill_hi, fill_lo;

__attribute__((noinline)) __ATTR_SECTION_SRAM__ static void cmd_push(const uint8 *data, uint8 len) {
    uint8 next = (cmd_head + 1) % CMD_SLOTS;
    if (next == cmd_tail || len > CMD_SIZE)
        return;
    for (uint8 i = 0; i < len; i++)
        cmd_queue[cmd_head][i] = data[i];
    cmd_len[cmd_head] = len;
    cmd_head = next;
}

__attribute__((noinline)) __ATTR_SECTION_SRAM__ static void on_command(const uint8 *data, uint8 len) {
    if (data[0] >= 0x40 && data[0] <= 0x45) {
        cmd_push(data, len);
    } else if (data[0] == 0x04) {
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
    } else if (data[0] == 0x7f && len == 2 && data[1] == 0x5a) {
        want_fault = true;
    } else if (data[0] == 0x23 && len == 1) {
        want_power = true;
    } else if (data[0] == 0x24 && len == 2) {
        want_watch = data[1] != 0;
    } else if (data[0] == 0x25 && len == 2) {
        want_emergency = data[1] != 0;
    } else if (data[0] == 0x21 && len == 2) {
        hal_gpio_write(GPIO_P34, data[1] != 0);
    } else if ((data[0] == 0x20 || data[0] == 0x22) && len == 4 && !want_pulse) {
        pulse_level = data[0] == 0x20;
        pulse_number = data[1];
        pulse_ms = data[2] | data[3] << 8;
        want_pulse = true;
    }
}

// Display search. Everything lives in SRAM, to keep the XIP image small.
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

// The panel: pins found with tools/fh_display_search.py. Written straight to the port register, about
// ten times faster than hal_gpio_write, which also reconfigures the pin on every call.
#define TFT_RST   GPIO_P01
#define TFT_SCK   GPIO_P31
#define TFT_MOSI  GPIO_P25
#define TFT_DC    GPIO_P00
#define TFT_CS    GPIO_P02         // always selected: low
#define TFT_LIGHT GPIO_P34
#define FILL_SLICE 132   // pixels per pass of the main loop, so the BLE task keeps running

__ATTR_SECTION_SRAM__ static void lcd_byte(uint8 value) {
    volatile uint32_t *port = &AP_GPIO->swporta_dr;
    uint32_t idle = *port & ~(BIT(TFT_SCK) | BIT(TFT_MOSI));
    for (int bit = 7; bit >= 0; bit--) {
        uint32_t out = (value >> bit) & 1 ? idle | BIT(TFT_MOSI) : idle;
        *port = out;
        *port = out | BIT(TFT_SCK);
        *port = out;
    }
}

__ATTR_SECTION_SRAM__ static void lcd_dc(int data) {
    if (data)
        AP_GPIO->swporta_dr |= BIT(TFT_DC);
    else
        AP_GPIO->swporta_dr &= ~BIT(TFT_DC);
}

__ATTR_SECTION_SRAM__ static void lcd_command(uint8 cmd, const uint8 *args, int count) {
    lcd_dc(0);
    lcd_byte(cmd);
    lcd_dc(1);
    for (int i = 0; i < count; i++)
        lcd_byte(args[i]);
    lcd_dc(0);
}

__ATTR_SECTION_SRAM__ static void lcd_repeat(uint8 hi, uint8 lo, uint32_t count) {
    while (count--) {
        lcd_byte(hi);
        lcd_byte(lo);
    }
}

// Leaves the controller in memory write, ready for pixels.
__attribute__((noinline)) __ATTR_SECTION_SRAM__ static void lcd_window(uint8 x, uint8 y, uint8 w, uint8 h) {
    uint8 columns[4] = {0, x, 0, (uint8)(x + w - 1)};
    uint8 rows[4] = {0, y, 0, (uint8)(y + h - 1)};
    lcd_command(0x2a, columns, 4);
    lcd_command(0x2b, rows, 4);
    lcd_command(0x2c, 0, 0);
    lcd_dc(1);
}

// Colours came out inverted and with red and blue swapped without 21 and bit 3 of 36.
__attribute__((noinline)) __ATTR_SECTION_SRAM__ static void lcd_init(void) {
    uint8 colmod = 0x05, madctl = 0x08;
    static uint8 gamma_pos[16] = {0x02, 0x1c, 0x07, 0x12, 0x37, 0x32, 0x29, 0x2d,
                                  0x29, 0x25, 0x2b, 0x39, 0x00, 0x01, 0x03, 0x10};
    static uint8 gamma_neg[16] = {0x03, 0x1d, 0x07, 0x06, 0x2e, 0x2c, 0x29, 0x2d,
                                  0x2e, 0x2e, 0x37, 0x3f, 0x00, 0x00, 0x02, 0x10};
    hal_gpio_write(TFT_CS, 0);
    hal_gpio_write(TFT_RST, 0);
    hal_gpio_write(TFT_SCK, 0);
    hal_gpio_write(TFT_MOSI, 0);
    hal_gpio_write(TFT_DC, 0);
    wait_ms(20);
    hal_gpio_write(TFT_RST, 1);
    wait_ms(120);
    lcd_command(0x11, 0, 0);          // sleep out
    wait_ms(120);
    lcd_command(0x21, 0, 0);          // inversion on
    lcd_command(0x3a, &colmod, 1);    // 16 bit per pixel
    lcd_command(0x36, &madctl, 1);    // BGR panel
    lcd_command(0xe0, gamma_pos, 16); // without these, mid tones come out too dark
    lcd_command(0xe1, gamma_neg, 16);
    lcd_command(0x29, 0, 0);          // display on
    hal_gpio_write(TFT_LIGHT, 1);
}

__attribute__((noinline)) __ATTR_SECTION_SRAM__ static void draw_command(const uint8 *d, uint8 len) {
    if (d[0] == 0x40 && len == 1) {
        lcd_init();
    } else if (d[0] == 0x41 && len >= 2) {
        lcd_command(d[1], d + 2, len - 2);
    } else if (d[0] == 0x42 && len == 7) {
        lcd_window(d[1], d[2], d[3], d[4]);
        fill_hi = d[5];
        fill_lo = d[6];
        fill_left = (uint32_t)d[3] * d[4];
    } else if (d[0] == 0x43 && len == 5) {
        lcd_window(d[1], d[2], d[3], d[4]);
    } else if (d[0] == 0x44) {
        for (int i = 1; i + 2 < len; i += 3)
            lcd_repeat(d[i + 1], d[i + 2], d[i]);
    } else if (d[0] == 0x45) {
        svc_event((svc_event_t)0x45);
    }
}

// One step per pass: part of a fill, or the next queued command.
__attribute__((noinline)) __ATTR_SECTION_SRAM__ static void draw_step(void) {
    if (fill_left) {
        uint32_t n = fill_left > FILL_SLICE ? FILL_SLICE : fill_left;
        lcd_repeat(fill_hi, fill_lo, n);
        fill_left -= n;
    } else if (cmd_tail != cmd_head) {
        draw_command(cmd_queue[cmd_tail], cmd_len[cmd_tail]);
        cmd_tail = (cmd_tail + 1) % CMD_SLOTS;
    }
}

// Battery and charger, from the stock code: P14 through a divider into the ADC, P15 input with
// pull-down. Set up on the first request, nothing is driven. lib/power can't be used: it drives P23,
// which here is the vibrator.
#define ADC_SAMPLES 32
#define ADC_TIMEOUT_MS 100

static adc_Cfg_t adc_cfg = {
    .channel = ADC_BIT(ADC_CH2P_P14),
    .is_continue_mode = FALSE,
    .is_differential_mode = 0x00,
    .is_high_resolution = ADC_BIT(ADC_CH2P_P14),
};
static uint16_t adc_samples[ADC_SAMPLES];
static uint8 adc_count;
static volatile bool adc_done;
static bool power_ready;
static uint8 report[4];
static uint8 report_next = sizeof(report);

static void adc_event(adc_Evt_t *ev) {
    if (ev->type != HAL_ADC_EVT_DATA || ev->ch != ADC_CH2P_P14)
        return;
    adc_count = ev->size > ADC_SAMPLES ? ADC_SAMPLES : ev->size;
    for (int i = 0; i < adc_count; i++)
        adc_samples[i] = ev->data[i];
    adc_done = true;
}

static int read_pin_mv(void) {
    adc_done = false;
    if (hal_adc_config_channel(adc_cfg, adc_event) != 0 || hal_adc_start() != 0)
        return -1;
    uint32_t start = hal_systick();
    while (!adc_done && hal_systick() - start < MS_TO_TICKS(ADC_TIMEOUT_MS))
        ;
    hal_adc_stop();
    if (!adc_done)
        return -1;
    return (int)hal_adc_value_cal(ADC_CH2P_P14, adc_samples, adc_count, 1, 0);
}

static void measure_power(void) {
    if (!power_ready) {
        hal_gpio_pin_init(GPIO_P15, GPIO_INPUT);
        hal_gpio_pull_set(GPIO_P15, GPIO_PULL_DOWN);
        hal_adc_init();
        power_ready = true;
    }
    int mv = read_pin_mv();
    report[0] = 0x23;
    report[1] = mv;
    report[2] = mv >> 8;
    report[3] = hal_gpio_read(GPIO_P15);
    report_next = 0;
}

// Key search: nothing is driven. A floating pin follows the pull and stays quiet phase after phase; a
// button only shows under the pull that opposes it, a touch chip's output under both.
#define WATCH_PHASE_TICKS 50     // passes of app_update, 10 ms each
#define WATCH_SETTLE_TICKS 3
#define WATCH_PINS 11
#define WATCH_QUEUE 16

static const uint8 watch_list[WATCH_PINS] = {3, 11, 16, 17, 18, 20, 24, 26, 27, 32, 33};
static bool watching;
static uint8 watch_phase, watch_ticks;
static bool watch_known[2];
static uint8 watch_level[2][WATCH_PINS];
static uint8 watch_queue[WATCH_QUEUE];
static uint8 watch_head, watch_tail;

static void watch_pull(gpio_pupd_e pull) {
    for (int i = 0; i < WATCH_PINS; i++)
        hal_gpio_pull_set((gpio_pin_e)pin_of(watch_list[i]), pull);
}

static void watch_start(void) {
    for (int i = 0; i < WATCH_PINS; i++)
        hal_gpio_pin_init((gpio_pin_e)pin_of(watch_list[i]), GPIO_INPUT);
    watch_pull(GPIO_PULL_UP);
    watch_phase = 0;
    watch_ticks = 0;
    watch_known[0] = watch_known[1] = false;
    watching = true;
}

static void watch_stop(void) {
    watch_pull(GPIO_FLOATING);
    watching = false;
}

static void watch_poll(void) {
    if (++watch_ticks >= WATCH_PHASE_TICKS) {
        watch_ticks = 0;
        watch_phase ^= 1;
        watch_pull(watch_phase ? GPIO_PULL_DOWN : GPIO_PULL_UP);
    }
    if (watch_ticks < WATCH_SETTLE_TICKS)
        return;
    for (int i = 0; i < WATCH_PINS; i++) {
        uint8 level = hal_gpio_read((gpio_pin_e)pin_of(watch_list[i]));
        uint8 next = (watch_head + 1) % WATCH_QUEUE;
        if (watch_known[watch_phase] && level != watch_level[watch_phase][i] && next != watch_tail) {
            watch_queue[watch_head] = watch_list[i] | watch_phase << 6 | level << 7;
            watch_head = next;
        }
        watch_level[watch_phase][i] = level;
    }
    watch_known[watch_phase] = true;
}

// Emergency exit to the updater, without BLE: covers a main loop that runs while the radio is dead,
// which the watchdog can't see. Same gesture as MorseOS. A key stuck down can't trigger it.
#define TOUCH_PIN GPIO_P03
#define EM_WARN_MS  10000
#define EM_STUCK_MS 30000
#define EM_TAP_MS   400
#define EM_TAPS_MS  5000
#define GLASS_X 26
#define GLASS_Y 1

static enum { EM_OFF, EM_IDLE, EM_HELD, EM_COUNT } em_state;
static bool em_pressed, em_valid;
static uint32_t em_edge, em_armed;
static uint8 em_taps;

static void em_buzz(uint16 ms) {
    pulse_number = 23;
    pulse_level = 1;
    pulse_ms = ms;
    want_pulse = true;
}

static void em_screen(uint8 hi, uint8 lo) {
    lcd_window(GLASS_X, GLASS_Y, 80, 160);
    fill_hi = hi;
    fill_lo = lo;
    fill_left = 80 * 160;
}

static void em_marks(void) {
    for (int i = 0; i < 3; i++) {
        lcd_window(GLASS_X + 16 + i * 18, GLASS_Y + 100, 12, 8);
        lcd_repeat(i < em_taps ? 0xff : 0x42, i < em_taps ? 0xff : 0x08, 12 * 8);
    }
}

static void em_cancel(void) {
    em_valid = false;
    em_state = EM_IDLE;
    em_screen(0, 0);
}

static void em_enable(bool on) {
    if (on && em_state == EM_OFF) {
        hal_gpio_pin_init(TOUCH_PIN, GPIO_INPUT);
        hal_gpio_pull_set(TOUCH_PIN, GPIO_PULL_DOWN);
        em_pressed = em_valid = false;
        em_state = EM_IDLE;
    } else if (!on) {
        em_state = EM_OFF;
    }
}

static void em_poll(void) {
    if (em_state == EM_OFF || fill_left)   // while a screen is being painted
        return;
    uint32_t now = hal_systick();
    bool touched = hal_gpio_read(TOUCH_PIN);
    bool released = false;
    uint32_t press_ticks = now - em_edge;
    if (touched != em_pressed) {
        em_pressed = touched;
        em_edge = now;
        released = !touched;
        if (touched) {
            em_valid = true;
            press_ticks = 0;
        }
    }
    if (em_state == EM_IDLE) {
        if (touched && em_valid && press_ticks >= MS_TO_TICKS(EM_WARN_MS)) {
            lcd_init();
            em_screen(0xf8, 0x00);
            em_buzz(400);
            em_state = EM_HELD;
        }
    } else if (em_state == EM_HELD) {
        if (touched && press_ticks >= MS_TO_TICKS(EM_STUCK_MS)) {
            em_cancel();
        } else if (released) {
            em_taps = 0;
            em_armed = now;
            em_marks();
            em_state = EM_COUNT;
        }
    } else if (released && press_ticks < MS_TO_TICKS(EM_TAP_MS)) {
        em_taps++;
        em_buzz(40);
        em_marks();
        em_armed = now;
        if (em_taps == 3)
            want_updater = true;
    } else if (released || (touched && press_ticks >= MS_TO_TICKS(EM_TAP_MS)) ||
               (!touched && now - em_armed >= MS_TO_TICKS(EM_TAPS_MS))) {
        em_cancel();
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
    em_enable(true);
}

void app_update(void) {
    hal_watchdog_feed();
    if (want_updater)
        hal_system_soft_reset();
    while (want_hang)
        ;
    if (want_fault)
        __asm volatile ("udf #0");
    if (want_probe) {
        want_probe = false;
        probe();
    }
    draw_step();
    if (want_power) {
        want_power = false;
        measure_power();
    } else if (report_next < sizeof(report)) {
        svc_event((svc_event_t)report[report_next++]);   // one per pass, the link has few buffers
    } else if (watch_tail != watch_head) {
        svc_event((svc_event_t)watch_queue[watch_tail]);
        watch_tail = (watch_tail + 1) % WATCH_QUEUE;
    }
    if (want_watch != 0xff) {
        if (want_watch)
            watch_start();
        else if (watching)
            watch_stop();
        want_watch = 0xff;
    }
    if (watching)
        watch_poll();
    if (want_emergency != 0xff) {
        em_enable(want_emergency);
        want_emergency = 0xff;
    }
    em_poll();
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
