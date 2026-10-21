# GCC build of a minimal BLE advertising app for the Dialog DA14585 (ARM Cortex-M0).
#
# Links against the Dialog DA145xx SDK 6.0.24.1464 (NOT redistributable: download from Renesas).
# Point SDK_PATH at the SDK root (the dir containing sdk/ and projects/). The SDK ships all the
# GCC pieces we need (prebuilt system library, GCC startup, GCC linker template + ROM symbols),
# so we only add our own app sources + config. Produces a RAM-resident image at the SysRAM base
# 0x07FC0000 (CFG_CODE_LOCATION_EXT), i.e. what the vendor secondary bootloader loads over OTA.
#
#   make                -> build/app.elf, build/app.bin   (no unresolved symbols)
#   make clean
#
# App sources (app/) and config headers (config/) are currently the SDK's ble_app_barebone
# example (device name set to ID115DIY); they are SDK-derived and kept out of git (.gitignore).
# Only this Makefile / README / linker glue are our own, committed files.

SDK_PATH ?= $(HOME)/Desktop/SDK_6.0.24.1464/DA145xx_SDK/6.0.24.1464
CROSS    ?= arm-none-eabi-
CC       := $(CROSS)gcc
OBJCOPY  := $(CROSS)objcopy
SIZE     := $(CROSS)size

BUILD    := build
CPU      := -mcpu=cortex-m0 -mthumb
TARGET   := app

DEFINES  := -D__DA14585__ -D__ARM_FEATURE_DSP=0
PREINC   := -include da1458x_config_basic.h -include da1458x_config_advanced.h -include user_config.h

APP_INC  := -I./config -I./app
SDK_INC  := \
  -I$(SDK_PATH)/sdk/platform/include \
  -I$(SDK_PATH)/sdk/platform/include/CMSIS/5.9.0/CMSIS/Core/Include \
  -I$(SDK_PATH)/sdk/platform/arch \
  -I$(SDK_PATH)/sdk/platform/arch/boot \
  -I$(SDK_PATH)/sdk/platform/arch/boot/GCC \
  -I$(SDK_PATH)/sdk/platform/arch/compiler \
  -I$(SDK_PATH)/sdk/platform/arch/compiler/GCC \
  -I$(SDK_PATH)/sdk/platform/arch/ll \
  -I$(SDK_PATH)/sdk/platform/arch/main \
  -I$(SDK_PATH)/sdk/platform/system_library/include \
  -I$(SDK_PATH)/sdk/platform/driver/gpio \
  -I$(SDK_PATH)/sdk/platform/driver/syscntl \
  -I$(SDK_PATH)/sdk/platform/driver/hw_otpc \
  -I$(SDK_PATH)/sdk/platform/driver/spi \
  -I$(SDK_PATH)/sdk/platform/driver/spi_flash \
  -I$(SDK_PATH)/sdk/platform/driver/uart \
  -I$(SDK_PATH)/sdk/platform/driver/battery \
  -I$(SDK_PATH)/sdk/platform/driver/wkupct_quadec \
  -I$(SDK_PATH)/sdk/platform/driver/adc \
  -I$(SDK_PATH)/sdk/platform/driver/dma \
  -I$(SDK_PATH)/sdk/platform/driver/i2c \
  -I$(SDK_PATH)/sdk/platform/driver/i2c_eeprom \
  -I$(SDK_PATH)/sdk/platform/driver/trng \
  -I$(SDK_PATH)/sdk/platform/driver/ble \
  -I$(SDK_PATH)/sdk/platform/driver/reg \
  -I$(SDK_PATH)/sdk/platform/utilities/otp_cs \
  -I$(SDK_PATH)/sdk/platform/utilities/otp_hdr \
  -I$(SDK_PATH)/sdk/platform/core_modules/common/api \
  -I$(SDK_PATH)/sdk/platform/core_modules/nvds/api \
  -I$(SDK_PATH)/sdk/platform/core_modules/rwip/api \
  -I$(SDK_PATH)/sdk/platform/core_modules/rf/api \
  -I$(SDK_PATH)/sdk/platform/core_modules/ke/api \
  -I$(SDK_PATH)/sdk/platform/core_modules/ke/src \
  -I$(SDK_PATH)/sdk/platform/core_modules/dbg/api \
  -I$(SDK_PATH)/sdk/platform/core_modules/gtl/api \
  -I$(SDK_PATH)/sdk/platform/core_modules/gtl/src \
  -I$(SDK_PATH)/sdk/platform/core_modules/h4tl/api \
  -I$(SDK_PATH)/sdk/platform/core_modules/arch_console \
  -I$(SDK_PATH)/sdk/platform/core_modules/crypto \
  -I$(SDK_PATH)/sdk/common_project_files \
  -I$(SDK_PATH)/sdk/app_modules/api \
  -I$(SDK_PATH)/sdk/ble_stack/rwble \
  -I$(SDK_PATH)/sdk/ble_stack/rwble_hl \
  -I$(SDK_PATH)/sdk/ble_stack/controller/em \
  -I$(SDK_PATH)/sdk/ble_stack/controller/llc \
  -I$(SDK_PATH)/sdk/ble_stack/controller/lld \
  -I$(SDK_PATH)/sdk/ble_stack/controller/llm \
  -I$(SDK_PATH)/sdk/ble_stack/ea/api \
  -I$(SDK_PATH)/sdk/ble_stack/em/api \
  -I$(SDK_PATH)/sdk/ble_stack/hci/api \
  -I$(SDK_PATH)/sdk/ble_stack/hci/src \
  -I$(SDK_PATH)/sdk/ble_stack/host/att \
  -I$(SDK_PATH)/sdk/ble_stack/host/att/attc \
  -I$(SDK_PATH)/sdk/ble_stack/host/att/attm \
  -I$(SDK_PATH)/sdk/ble_stack/host/att/atts \
  -I$(SDK_PATH)/sdk/ble_stack/host/gap \
  -I$(SDK_PATH)/sdk/ble_stack/host/gap/gapc \
  -I$(SDK_PATH)/sdk/ble_stack/host/gap/gapm \
  -I$(SDK_PATH)/sdk/ble_stack/host/gatt \
  -I$(SDK_PATH)/sdk/ble_stack/host/gatt/gattc \
  -I$(SDK_PATH)/sdk/ble_stack/host/gatt/gattm \
  -I$(SDK_PATH)/sdk/ble_stack/host/l2c/l2cc \
  -I$(SDK_PATH)/sdk/ble_stack/host/l2c/l2cm \
  -I$(SDK_PATH)/sdk/ble_stack/host/smp \
  -I$(SDK_PATH)/sdk/ble_stack/host/smp/smpc \
  -I$(SDK_PATH)/sdk/ble_stack/host/smp/smpm \
  -I$(SDK_PATH)/sdk/ble_stack/profiles \
  -I$(SDK_PATH)/sdk/ble_stack/profiles/dis/diss/api \
  -I$(SDK_PATH)/sdk/ble_stack/profiles/dis/disc/api \
  -I$(SDK_PATH)/sdk/ble_stack/profiles/custom \
  -I$(SDK_PATH)/sdk/ble_stack/profiles/custom/custs/api \
  -I$(SDK_PATH)/third_party/hash \
  -I$(SDK_PATH)/third_party/rand \
  -I$(SDK_PATH)/third_party/irng

INCLUDES := $(APP_INC) $(SDK_INC)
CFLAGS   := $(CPU) $(DEFINES) $(PREINC) $(INCLUDES) -Os -g \
            -fno-exceptions -fno-unwind-tables -ffreestanding \
            -Wall -Wno-unused-parameter -Wno-missing-braces -Wno-int-conversion \
            -Wno-unused-variable -Wno-switch -ffunction-sections -fdata-sections
ASFLAGS  := $(CPU) $(DEFINES) $(INCLUDES) -D__STACK_SIZE=0x800 -x assembler-with-cpp \
            -fno-exceptions -fno-unwind-tables

# ---- our app sources (SDK barebone example, name=ID115DIY; gitignored) --------------------
APP_SRCS := \
  app/user_barebone.c \
  app/user_periph_setup.c

# ---- SDK BLE core sources (compiled from SDK_PATH; never copied into the repo) ------------
SDK_REL := \
  sdk/platform/arch/main/arch_main.c \
  sdk/platform/arch/main/arch_sleep.c \
  sdk/platform/arch/main/arch_system.c \
  sdk/platform/arch/main/arch_hibernation.c \
  sdk/platform/arch/main/jump_table.c \
  sdk/platform/arch/main/hardfault_handler.c \
  sdk/platform/arch/main/nmi_handler.c \
  sdk/platform/arch/main/arch_rom.c \
  sdk/platform/arch/boot/system_DA14585_586.c \
  sdk/platform/core_modules/rwip/src/rwip.c \
  sdk/platform/core_modules/nvds/src/nvds.c \
  sdk/platform/core_modules/arch_console/arch_console.c \
  sdk/platform/core_modules/rf/src/rf_585.c \
  sdk/platform/system_library/src/DA14585_586/system_library_585_586.c \
  sdk/platform/driver/gpio/gpio.c \
  sdk/platform/driver/syscntl/syscntl.c \
  sdk/platform/driver/battery/battery.c \
  sdk/platform/driver/adc/adc_58x.c \
  sdk/platform/driver/dma/dma.c \
  sdk/platform/driver/uart/uart.c \
  sdk/platform/driver/i2c/i2c.c \
  sdk/platform/driver/spi_flash/spi_flash.c \
  sdk/platform/driver/i2c_eeprom/i2c_eeprom.c \
  sdk/platform/driver/wkupct_quadec/wkupct_quadec.c \
  sdk/platform/driver/hw_otpc/hw_otpc_58x.c \
  sdk/platform/driver/trng/trng.c \
  sdk/platform/utilities/otp_cs/otp_cs.c \
  sdk/platform/utilities/otp_hdr/otp_hdr.c \
  sdk/ble_stack/rwble/rwble.c \
  sdk/ble_stack/profiles/prf.c \
  sdk/ble_stack/profiles/prf_utils.c \
  sdk/ble_stack/profiles/dis/diss/src/diss.c \
  sdk/ble_stack/profiles/dis/diss/src/diss_task.c \
  sdk/ble_stack/profiles/custom/custs/src/custs1.c \
  sdk/ble_stack/profiles/custom/custs/src/custs1_task.c \
  sdk/ble_stack/profiles/custom/custom_common.c \
  sdk/ble_stack/host/att/attm/attm_db_128.c \
  sdk/app_modules/src/app_common/app.c \
  sdk/app_modules/src/app_common/app_task.c \
  sdk/app_modules/src/app_common/app_msg_utils.c \
  sdk/app_modules/src/app_common/app_utils.c \
  sdk/app_modules/src/app_default_hnd/app_default_handlers.c \
  sdk/app_modules/src/app_diss/app_diss.c \
  sdk/app_modules/src/app_diss/app_diss_task.c \
  sdk/app_modules/src/app_custs/app_customs.c \
  sdk/app_modules/src/app_custs/app_customs_common.c \
  sdk/app_modules/src/app_custs/app_customs_task.c \
  sdk/app_modules/src/app_easy/app_easy_msg_utils.c \
  sdk/app_modules/src/app_easy/app_easy_timer.c \
  sdk/app_modules/src/app_easy/app_easy_storage.c \
  sdk/app_modules/src/app_easy/app_easy_crypto.c \
  sdk/app_modules/src/app_easy/app_easy_whitelist.c \
  sdk/app_modules/src/app_entry/app_entry_point.c \
  third_party/rand/chacha20.c \
  third_party/hash/hash.c
SDK_SRCS := $(addprefix $(SDK_PATH)/,$(SDK_REL))

ASM_SRCS := \
  $(SDK_PATH)/sdk/platform/arch/boot/GCC/startup_DA14585_586.S \
  $(SDK_PATH)/sdk/platform/arch/boot/GCC/ivtable_DA14585_586.S

# ---- object files (flatten to unique names in build/) -------------------------------------
APP_OBJS := $(foreach s,$(APP_SRCS),$(BUILD)/app__$(notdir $(s:.c=.o)))
SDK_OBJS := $(foreach s,$(SDK_REL),$(BUILD)/sdk__$(subst /,_,$(s:.c=.o)))
ASM_OBJS := $(BUILD)/startup_DA14585_586.o $(BUILD)/ivtable_DA14585_586.o
OBJS     := $(APP_OBJS) $(SDK_OBJS) $(ASM_OBJS)

# ---- linker: preprocess the SDK's GCC linker template, link against the prebuilt lib -------
LDS_DIR  := $(SDK_PATH)/sdk/common_project_files/ldscripts
LDS_IN   := $(LDS_DIR)/ldscript_DA14585_586.lds.S
LDS_OUT  := $(BUILD)/ldscript.ld
LDFLAGS  := $(CPU) -T$(LDS_OUT) \
            -L$(LDS_DIR) \
            -L$(SDK_PATH)/sdk/common_project_files/misc \
            -L$(SDK_PATH)/sdk/platform/system_library/output/Keil_5 \
            -Wl,--gc-sections -Wl,-Map=$(BUILD)/$(TARGET).map \
            --specs=nano.specs --specs=nosys.specs \
            -l:da14585_586.lib

all: $(BUILD)/$(TARGET).bin

$(BUILD):
	@mkdir -p $(BUILD)

$(LDS_OUT): $(LDS_IN) | $(BUILD)
	$(CC) -E -P -x c $(DEFINES) $(APP_INC) \
	  -I$(LDS_DIR) -I$(SDK_PATH)/sdk/common_project_files -I$(SDK_PATH)/sdk/platform/include \
	  $(LDS_IN) -o $@

$(BUILD)/app__%.o: app/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

define SDK_RULE
$(BUILD)/sdk__$(subst /,_,$(1:.c=.o)): $(SDK_PATH)/$(1) | $(BUILD)
	$$(CC) $$(CFLAGS) -c $$< -o $$@
endef
$(foreach s,$(SDK_REL),$(eval $(call SDK_RULE,$(s))))

$(BUILD)/startup_DA14585_586.o: $(SDK_PATH)/sdk/platform/arch/boot/GCC/startup_DA14585_586.S | $(BUILD)
	$(CC) $(ASFLAGS) -c $< -o $@
$(BUILD)/ivtable_DA14585_586.o: $(SDK_PATH)/sdk/platform/arch/boot/GCC/ivtable_DA14585_586.S | $(BUILD)
	$(CC) $(ASFLAGS) -c $< -o $@

$(BUILD)/$(TARGET).elf: $(LDS_OUT) $(OBJS)
	$(CC) $(OBJS) $(LDFLAGS) -o $@
	$(SIZE) $@

$(BUILD)/$(TARGET).bin: $(BUILD)/$(TARGET).elf
	$(OBJCOPY) -O binary $< $@

clean:
	rm -rf $(BUILD)

.PHONY: all clean
