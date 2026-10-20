# Build a custom app for the MSLM707 (MM32F031, Cortex-M0) with arm-none-eabi-gcc.
# Produces build/app.elf and build/app.bin. Wrap the .bin into an OTA image with
# ../tools/mkimage.py. Toolchain-validation build for now — see docs/firmware-build.md.

CROSS   ?= arm-none-eabi-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
SIZE    := $(CROSS)size

CPU     := -mcpu=cortex-m0 -mthumb
CFLAGS  := $(CPU) -Os -g -ffunction-sections -fdata-sections -Wall -Wextra \
           -ffreestanding -std=c11
LDFLAGS := $(CPU) -nostartfiles -Wl,--gc-sections -Wl,-Map=build/app.map \
           -T ld/app.ld -ffreestanding

SRC := src/startup.c src/main.c
OBJ := $(SRC:%.c=build/%.o)

all: build/app.bin

build/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

build/app.elf: $(OBJ)
	$(CC) $(LDFLAGS) $(OBJ) -o $@
	$(SIZE) $@

build/app.bin: build/app.elf
	$(OBJCOPY) -O binary $< $@

image: build/app.bin
	python3 ../tools/mkimage.py build/app.bin build/app-ota.bin

clean:
	rm -rf build

.PHONY: all image clean
