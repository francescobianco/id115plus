// System bring-up of the dumper: clocks, power manager, RF/BLE controller, then OSAL.
// Adapted from lib/core/main.c of e-labInnovations/FitPro-LP715-PHY6222 (itself from
// amir1387aht/phy6222_smartwatch, MIT). Pins are left floating: this board's are not known.
#include "gpio.h"
#include "clock.h"
#include "global_config.h"
#include "jump_function.h"
#include "pwrmgr.h"
#include "mcu.h"
#include "log.h"
#include "rf_phy_driver.h"
#include "flash.h"
#include "OSAL_Memory.h"
#include "ll.h"
#include "ll_def.h"
#include "ll_buf.h"

extern void init_config(void);
extern void app_osal_init(void);

#define LARGE_HEAP_SIZE (8 * 1024)
ALIGN4_U8 g_largeHeap[LARGE_HEAP_SIZE];
volatile uint8 g_clk32K_config;
volatile sysclk_t g_spif_clk_config;

#define BLE_MAX_CONN        1
#define BLE_PKTS_PER_EVT_TX 3
#define BLE_PKTS_PER_EVT_RX 3
#define BLE_PKT_SLOT        272
#define BLE_CONN_BUF_SIZE \
    (BLE_MAX_CONN * (BLE_PKTS_PER_EVT_TX * 2 + BLE_PKTS_PER_EVT_RX + 1) * BLE_PKT_SLOT)
ALIGN4_U8 g_pConnectionBuffer[BLE_CONN_BUF_SIZE];
llConnState_t pConnContext[BLE_MAX_CONN];

static void hal_low_power_io_init(void) {
    DCDC_CONFIG_SETTING(0x0a);
    DCDC_REF_CLK_SETTING(1);
    DIG_LDO_CURRENT_SETTING(1);
    hal_pwrmgr_RAM_retention(RET_SRAM0 | RET_SRAM1 | RET_SRAM2);
    hal_pwrmgr_RAM_retention_set();
    subWriteReg(0x4000f014, 26, 26, 1); // hal_pwrmgr_LowCurrentLdo_enable()
}

static void hal_rfphy_init(void) {
    g_rfPhyTxPower = RF_PHY_TX_POWER_0DBM;
    g_rfPhyPktFmt = PKT_FMT_BLE1M;
    g_rfPhyFreqOffSet = RF_PHY_FREQ_FOFF_00KHZ;
    XTAL16M_CAP_SETTING(0x09);
    XTAL16M_CURRENT_SETTING(0x01);
    hal_rc32k_clk_tracking_init();
    {
        extern void efuse_init(void);
        typedef void (*rom_fn)(void);
        efuse_init();
        ((rom_fn)0xa2e1)(); // the ROM's ble_main
    }
    osal_mem_set_heap((osalMemHdr_t *)g_largeHeap, LARGE_HEAP_SIZE);
    LL_InitConnectContext(pConnContext, g_pConnectionBuffer, BLE_MAX_CONN, BLE_PKTS_PER_EVT_TX,
                          BLE_PKTS_PER_EVT_RX, BLE_PKT_VERSION_5_1);
    hal_rfPhyFreqOff_Set();
    NVIC_SetPriority((IRQn_Type)BB_IRQn, IRQ_PRIO_REALTIME);
    NVIC_SetPriority((IRQn_Type)TIM1_IRQn, IRQ_PRIO_HIGH);
    NVIC_SetPriority((IRQn_Type)TIM2_IRQn, IRQ_PRIO_HIGH);
    NVIC_SetPriority((IRQn_Type)TIM4_IRQn, IRQ_PRIO_HIGH);
}

static void hal_init(void) {
    hal_low_power_io_init();
    clk_init(g_system_clk);
    hal_rtc_clock_config((CLK32K_e)g_clk32K_config);
    hal_pwrmgr_init();
    hal_spif_cache_init(SYS_CLK_DLL_64M, XFRD_FCMD_READ_DUAL);
    hal_gpio_init();
}

int main(void) {
    // First thing: any later soft reset lands in PPlusOTA. The bootloader reads the low nibble.
    *(volatile uint32_t *)0x4000f034 = (*(volatile uint32_t *)0x4000f034 & ~0xfu) | 2u;

    g_system_clk = CFG_SYS_CLK;
    g_clk32K_config = CLK_32K_RCOSC;
    drv_irq_init();
    init_config();
    {
        extern void ll_patch_slave(void);
        ll_patch_slave();
    }
    hal_rfphy_init();
    hal_init();
    app_osal_init();
    return 0;
}
