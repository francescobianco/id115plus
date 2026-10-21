/* DA14585 standalone GNU linker script (RAM-resident image).
 *
 * The DA14585 (ARM Cortex-M0) has NO internal flash: the boot ROM copies the image from
 * external SPI flash (or OTP) into SysRAM and jumps to it, so code executes from RAM.
 * SysRAM is 96 KB at 0x07FC0000 (SysRAM1 0x07FC0000-0x07FC7FFF, SysRAM2 ..BFFF, SysRAM3 ..FFFF),
 * per the Renesas DA14585/586 memory-map tutorial. The vector table sits at the image start.
 *
 * This is a toolchain-validation skeleton (no Dialog BLE stack yet). A real app links against
 * the DA145xx SDK 6.x and uses the SDK's own scatter/startup — see README.md.
 */
ENTRY(Reset_Handler)

MEMORY
{
  RAM (rwx) : ORIGIN = 0x07FC0000, LENGTH = 96K
}

_estack = ORIGIN(RAM) + LENGTH(RAM);

SECTIONS
{
  .vectors ORIGIN(RAM) :
  {
    KEEP(*(.isr_vector))
  } > RAM

  .text :
  {
    *(.text*)
    *(.rodata*)
    *(.glue_7) *(.glue_7t)
    . = ALIGN(4);
    _etext = .;
  } > RAM

  /* Image is loaded whole into RAM, so .data is already in place (LMA == VMA). */
  .data :
  {
    . = ALIGN(4);
    _sdata = .;
    *(.data*)
    . = ALIGN(4);
    _edata = .;
  } > RAM

  .bss :
  {
    . = ALIGN(4);
    _sbss = .;
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
  } > RAM

  . = ALIGN(8);
  _end = .;

  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) }
}
