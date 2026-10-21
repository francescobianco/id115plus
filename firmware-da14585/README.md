# firmware-da14585/ — firmware per il chip reale (Dialog DA14585, ARM Cortex-M0)

Ricostruzione del firmware sull'**architettura giusta**. Il SoC del braccialetto è un
**Dialog/Renesas DA14585** (vedi [../docs/chip.md](../docs/chip.md)), non l'MM32/Macrogiga su
cui era basato `../firmware/` (ora superato).

## Stato: scheletro + validazione toolchain

`make` produce un'immagine RAM-resident Cortex-M0 valida con la **memory-map del DA14585**
(vector table alla base SysRAM `0x07FC0000`, SP `0x07FD8000`). È un **segnaposto senza BLE**,
serve a confermare toolchain + mappa. **Nulla da flashare.**

```shell
make          # -> build/app.elf, build/app.bin (segnaposto, no BLE)
make clean
```

## Memory map (DA14585)

| Regione | Indirizzo | Note |
|---|---|---|
| SysRAM1 | `0x07FC0000`–`0x07FC7FFF` (32K) | il codice gira da qui; vector table all'inizio |
| SysRAM2 | `0x07FC8000`–`0x07FCBFFF` (16K) | |
| SysRAM3 | `0x07FCC000`–`0x07FCFFFF` (16K) | (SysRAM totale 96K) |
| SPI flash esterna | — | OTP/SPI NOR: il boot ROM copia l'immagine in SysRAM e salta |

**Niente flash interna**: il DA14585 esegue da RAM. Il modello `0x08000000` di `../firmware/`
(MM32) non si applica.

## Per un firmware BLE reale: serve il Dialog SDK6

Il DA14585 è tra i SoC BLE più documentati, ma lo stack BLE **non è ridistribuibile**: va preso
il **DA145xx SDK 6.0.24.1464** (o 6.0.22.1401) dal sito Renesas (registrazione gratuita). Un'app
di advertising si compila con `arm-none-eabi-gcc` linkando lo stack del SDK (`rwip`, `ke`,
`gapc`, `gapm`, profili) + il proprio GATT.

**Template di riferimento (GCC, bare-metal):** `schrab/DA14585-e-ink-display`
(https://github.com/schrab/DA14585-e-ink-display) — Makefile `make SDK_PATH=.../6.0.24.1464 all`,
linker SysRAM, e un `mkimage.py` che genera l'**header immagine standard Dialog** (64 byte, sig
`0x7051`, validflag `0xAA`, **CRC = zlib.crc32** sul codice). Da adattare al nostro caso.

## Nodo OTA: il checksum del vendor NON è l'header standard Dialog

Il nostro device **non** usa l'header SUOTA standard (64B, CRC32): usa un **OTA custom** su
`fd00/fd01/fd02` con header a **16 byte** (projId/boot/stack/app/codeSize/crc) — un **secondary
bootloader del vendor** (uThink/Yoho). Abbiamo provato zlib-CRC32 e varianti: **rifiutate** (vedi
[../docs/ota-flash-runbook.md](../docs/ota-flash-runbook.md)). Per inchiodare il checksum servirà:
- un'**immagine ufficiale** `_60_XX_00_86.bin` (si calcolano i candidati sul suo codice), oppure
- un **dump via SWD** del secondary bootloader del vendor dalla **cavia** (si legge l'algoritmo),
  usando strumenti tipo quelli del progetto schrab (`dump_spi_flash.py`, `extract_partitions.py`).

Il **transport** OTA `../id115plus ota-flash` (staging + verifica, non bricka) resta valido: una
volta nota l'immagine giusta (codice per SysRAM DA14585 + checksum del vendor), si carica da lì.

## Da fare

1. Procurare il DA145xx SDK 6.x (Renesas) → `make SDK_PATH=...`.
2. App minima di advertising col nostro nome, linkata allo stack BLE del SDK.
3. Determinare il formato immagine + checksum del secondary bootloader del vendor (immagine
   ufficiale o dump SWD della cavia).
4. Caricare via il nostro transport OTA.
