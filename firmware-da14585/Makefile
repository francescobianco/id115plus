# Build a RAM-resident image for the DA14585 (ARM Cortex-M0) with arm-none-eabi-gcc.
# This standalone target only validates the toolchain + memory map (vector table at the
# SysRAM base 0x07FC0000); it has NO BLE. A real BLE app links against the Dialog DA145xx
# SDK 6.x — see README.md (set SDK_PATH and follow the schrab template). Not to be flashed.

CROSS   ?= arm-none-eabi-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
SIZE    := $(CROSS)size

BUILD   := build
CPU     := -mcpu=cortex-m0 -mthumb
CFLAGS  := $(CPU) -Os -g -ffunction-sections -fdata-sections -Wall -Wextra -ffreestanding -std=c11
LDFLAGS := $(CPU) -nostartfiles -Wl,--gc-sections -Wl,-Map=$(BUILD)/app.map -T ld/da14585.ld -ffreestanding

SRC := src/startup_da14585.c src/main.c
OBJ := $(SRC:%.c=$(BUILD)/%.o)

all: $(BUILD)/app.bin

$(BUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/app.elf: $(OBJ)
	$(CC) $(LDFLAGS) $(OBJ) -o $@
	$(SIZE) $@

$(BUILD)/app.bin: $(BUILD)/app.elf
	$(OBJCOPY) -O binary $< $@

clean:
	rm -rf $(BUILD)

.PHONY: all clean
