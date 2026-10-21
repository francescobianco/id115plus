# Build a BLE firmware for the MSLM707 (MM32F031, Cortex-M0) with arm-none-eabi-gcc,
# linking against the SDK's binary BLE radio library. This proves our GCC toolchain
# produces a valid, fully-linked BLE image from source. NOT to be flashed yet
# (app base address + CRC32 variant still to be confirmed — see ../docs/firmware-build.md).
#
# The SDK is not vendored here: run `make fetch` once to clone it (pinned commit).
# Baseline app = the SDK's app-argun advertising example, built with our startup/linker.
# Customisation starts by editing those sources (then copy them under app/).

CROSS   ?= arm-none-eabi-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
SIZE    := $(CROSS)size
NM      := $(CROSS)nm

SDK     ?= vendor/MS1793-SDK/software
BUILD   := build
OBJ     := $(BUILD)/obj

CPU     := -mcpu=cortex-m0 -mthumb
INC     := -Icompat -I$(SDK)/Src/inc -I$(SDK)/BSP -I$(SDK)/Src/IWDG -I$(SDK)/Src/ADC \
           -I$(SDK)/MM32x031/Include -I$(SDK)/MM32x031/HAL_lib/inc \
           -I$(SDK)/MM32x031/CMSIS/KEIL_CORE -I$(SDK)/app-argun
CFLAGS  := $(CPU) -Os -g -ffunction-sections -fdata-sections -Wall -std=gnu11 $(INC)
LDFLAGS := $(CPU) -nostartfiles -Wl,--gc-sections -Wl,--no-wchar-size-warning \
           -Wl,-Map=$(BUILD)/app.map -T ld/app.ld
LIB     := $(SDK)/Src/lib/mg_BLE_lib_m0.lib

APP     := $(SDK)/app-argun/main.c $(SDK)/app-argun/app.c $(SDK)/app-argun/BSP.c \
           $(SDK)/app-argun/mm32f031_it.c
SUP     := $(SDK)/Src/IWDG/iwdg.c $(SDK)/MM32x031/Source/system_MM32x031.c
HAL     := $(wildcard $(SDK)/MM32x031/HAL_lib/src/*.c)
STARTUP := src/startup_mm32f031.c
SRCS    := $(STARTUP) $(APP) $(SUP) $(HAL)
OBJS    := $(addprefix $(OBJ)/,$(notdir $(SRCS:.c=.o)))

VPATH   := src $(SDK)/app-argun $(SDK)/Src/IWDG $(SDK)/MM32x031/Source $(SDK)/MM32x031/HAL_lib/src

all: check-sdk $(BUILD)/app.bin

$(OBJ)/%.o: %.c | $(OBJ)
	$(CC) $(CFLAGS) -c $< -o $@

$(OBJ):
	@mkdir -p $(OBJ)

$(BUILD)/app.elf: $(OBJS)
	$(CC) $(LDFLAGS) $(OBJS) $(LIB) -o $@
	$(SIZE) $@
	@echo "-- undefined symbols (expect none):"; $(NM) $@ | grep -i " U " || echo "   none"

$(BUILD)/app.bin: $(BUILD)/app.elf
	$(OBJCOPY) -O binary $< $@

image: $(BUILD)/app.bin
	python3 ../tools/mkimage.py $(BUILD)/app.bin $(BUILD)/app-ota.bin

fetch:
	bash vendor/fetch-sdk.sh

check-sdk:
	@test -f "$(LIB)" || { echo "SDK missing: run 'make fetch' first."; exit 1; }

clean:
	rm -rf $(BUILD)

.PHONY: all image fetch check-sdk clean
