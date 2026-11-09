// Fit-Here flash dumper. No BLE host and no connection: the link layer in ROM broadcasts the
// flash in numbered manufacturer-data frames that tools/fh_dump_rx.py collects.
//
// It only reads flash. It ends by itself: after PASSES passes, or on any advertising error, it
// resets into the PPlusOTA updater, because main() armed the OTA mode before doing anything else.
#include "OSAL.h"
#include "clock.h"
#include "ll.h"
#include "watchdog.h"

#define FLASH_BASE 0x11000000u
#define FLASH_SIZE 0x80000u
#define BLOCK      24u
#define BLOCKS     ((FLASH_SIZE + BLOCK - 1) / BLOCK)
#define COMPANY    0x4648u        // "FH": frames are found by this and by the address below

#define EVT_START  0x0001
#define EVT_TICK   0x0002

#define ADV_FAST   32             // 20 ms in 625 us units, what the SDK's patch.c accepts
#define ADV_SLOW   160            // 100 ms, the Bluetooth 4 minimum for this advertising type
#define TICK_FAST  40             // ms per frame: about 2 advertising events each
#define TICK_SLOW  220
#define PASSES_FAST 3
#define PASSES_SLOW 1

#define MAX_ERRORS 100

extern uint8 ownPublicAddr[6];

static uint8 task;
static uint8 adv[31];
static uint32 block;
static uint8 pass;
static uint8 passes;
static uint32 errors;

static void to_updater(void) {
    LL_SetAdvControl(LL_ADV_MODE_OFF);
    hal_system_soft_reset();
}

static void fill_frame(void) {
    uint32 off = block * BLOCK;
    const uint8 *src = (const uint8 *)(FLASH_BASE + off);
    adv[0] = 30;
    adv[1] = 0xff;
    adv[2] = COMPANY & 0xff;
    adv[3] = COMPANY >> 8;
    adv[4] = block & 0xff;
    adv[5] = block >> 8;
    adv[6] = pass;
    for (uint32 i = 0; i < BLOCK; i++)
        adv[7 + i] = off + i < FLASH_SIZE ? src[i] : 0xff;
}

static uint16 start_advertising(void) {
    static uint8 peer[6];
    uint8 channels = LL_ADV_CHAN_37 | LL_ADV_CHAN_38 | LL_ADV_CHAN_39;
    uint16 tick = TICK_FAST;

    passes = PASSES_FAST;
    if (LL_SetAdvParam(ADV_FAST, ADV_FAST, LL_ADV_NONCONNECTABLE_UNDIRECTED_EVT, 0, 0, peer,
                       channels, LL_ADV_WL_POLICY_ANY_REQ) != LL_STATUS_SUCCESS) {
        tick = TICK_SLOW;
        passes = PASSES_SLOW;
        if (LL_SetAdvParam(ADV_SLOW, ADV_SLOW, LL_ADV_NONCONNECTABLE_UNDIRECTED_EVT, 0, 0, peer,
                           channels, LL_ADV_WL_POLICY_ANY_REQ) != LL_STATUS_SUCCESS)
            return 0;
    }
    fill_frame();
    if (LL_SetAdvData(sizeof(adv), adv) != LL_STATUS_SUCCESS)
        return 0;
    if (LL_SetAdvControl(LL_ADV_MODE_ON) != LL_STATUS_SUCCESS)
        return 0;
    return tick;
}

static void next_frame(void) {
    if (++block == BLOCKS) {
        block = 0;
        if (++pass == passes)
            to_updater();
    }
    fill_frame();
    if (LL_SetAdvData(sizeof(adv), adv) == LL_STATUS_SUCCESS)
        errors = 0;
    else if (++errors > MAX_ERRORS)
        to_updater();
}

void dumper_init(uint8 task_id) {
    // C0:00:A1:B1:02:63, the app's address + 2 (the updater uses + 1)
    static const uint8 addr[6] = {0x63, 0x02, 0xb1, 0xa1, 0x00, 0xc0};

    task = task_id;
    osal_memcpy(ownPublicAddr, addr, sizeof(addr));
    watchdog_config(WDG_8S);
    osal_start_timerEx(task, EVT_START, 500);
}

uint16 dumper_process_event(uint8 task_id, uint16 events) {
    (void)task_id;
    if (events & SYS_EVENT_MSG) {
        uint8 *msg;
        while ((msg = osal_msg_receive(task)) != NULL)
            osal_msg_deallocate(msg);
        return events ^ SYS_EVENT_MSG;
    }
    if (events & EVT_START) {
        uint16 tick = start_advertising();
        if (!tick)
            to_updater();
        osal_start_reload_timer(task, EVT_TICK, tick);
        return events ^ EVT_START;
    }
    if (events & EVT_TICK) {
        hal_watchdog_feed();
        next_frame();
        return events ^ EVT_TICK;
    }
    return 0;
}
