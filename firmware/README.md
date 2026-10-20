# firmware/ — firmware custom per MSLM707 (MM32F031, Cortex-M0)

Build GCC di un'applicazione per il braccialetto. Vedi [../docs/firmware-build.md](../docs/firmware-build.md)
per mappa di memoria, rischio brick e strategia.

**Stato: validazione toolchain (Fase 4.1).** `src/main.c` è un segnaposto (loop minimo), senza
BLE e **da non flashare**. Serve a confermare che produciamo un `.bin` Cortex-M0 valido e a
incapsularlo nell'immagine OTA.

## Build

```shell
make          # -> build/app.elf, build/app.bin
make image    # -> build/app-ota.bin (header 16B + codice, via ../tools/mkimage.py)
make clean
```

Richiede `arm-none-eabi-gcc`.

## Struttura

| File | Contenuto |
|---|---|
| `src/startup.c` | vector table + reset handler (copia `.data`, azzera `.bss`, chiama `main`) |
| `src/main.c` | applicazione (ora segnaposto) |
| `ld/app.ld` | linker script: FLASH `0x08001010` (base app, **da confermare**), RAM `0x20000000` 4K |
| `Makefile` | compilazione, link, objcopy, `image` |

## Da fare (prima di avere un firmware reale)

- Confermare l'indirizzo base dell'app del nostro bootloader (ora assunto `0x08001010`) e la
  variante CRC32 — idealmente da un'immagine ufficiale.
- Linkare la libreria radio del SDK (`Src/lib/mg_BLE_lib_m0.lib`, Cortex-M0, GCC-compatibile:
  oggetti ELF con simboli `__aeabi_*`) e inizializzare clock + stack BLE (vedi gli esempi del SDK).
- Non flashare senza rete di sicurezza (immagine di ripristino o secondo dispositivo) e senza
  aver confermato lo staging del bootloader.
