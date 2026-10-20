/* Linker script for a custom app on the MSLM707 (MM32F031, Cortex-M0).
 *
 * FLASH origin is the app region the vendor bootloader jumps to. The SDK sample uses
 * 0x08001010 (Bank A base 0x08001000 + 16-byte header). For OUR device this exact base is
 * still TO BE CONFIRMED from an official image (see docs/firmware-build.md); 0x08001010 is
 * the working assumption. This build is for toolchain validation only — not to be flashed yet.
 */
MEMORY
{
  FLASH (rx) : ORIGIN = 0x08001010, LENGTH = 28K
  RAM  (rwx) : ORIGIN = 0x20000000, LENGTH = 4K
}

_estack = ORIGIN(RAM) + LENGTH(RAM);

SECTIONS
{
  .isr_vector : { KEEP(*(.isr_vector)) } > FLASH

  .text : {
    *(.text*)
    *(.rodata*)
    . = ALIGN(4);
    _etext = .;
  } > FLASH

  .data : AT (_etext) {
    _sdata = .;
    *(.data*)
    . = ALIGN(4);
    _edata = .;
  } > RAM

  .bss : {
    _sbss = .;
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
  } > RAM
}
