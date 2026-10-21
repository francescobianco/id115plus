# firmware/ — firmware BLE custom per MSLM707 (MM32F031, Cortex-M0)

Build GCC di un'applicazione BLE per il braccialetto, **linkata contro la libreria radio
binaria del SDK Macrogiga**. Vedi [../docs/firmware-build.md](../docs/firmware-build.md) per
mappa di memoria, rischio brick e strategia.

**Stato: linkaggio stack BLE OK (Fase 5, avvio).** La toolchain GCC produce un'immagine BLE
completamente linkata (nessun simbolo irrisolto) a partire dai sorgenti, usando come baseline
l'esempio di advertising `app-argun` del SDK. **Niente viene ancora flashato**: l'indirizzo base
dell'app e la variante CRC32 del nostro bootloader vanno prima confermati.

## Build

```shell
make fetch    # una volta: clona il SDK Macrogiga (commit fissato) in vendor/ (non versionato)
make          # -> build/app.elf, build/app.bin  (link contro mg_BLE_lib_m0.lib)
make image    # -> build/app-ota.bin  (header 16B + codice, via ../tools/mkimage.py)
make clean
```

Richiede `arm-none-eabi-gcc`. Il link termina stampando i simboli irrisolti (atteso: nessuno).

## Perché il link funziona in GCC

La libreria radio (`mg_BLE_lib_m0.lib`) è un archivio `ar` di oggetti ELF Cortex-M0 con ABI EABI
(`__aeabi_*`): GCC la linka senza Keil. L'archivio referenzia molti simboli interni (tabella
GATT `AttCharList`, callback server, ecc.) **ma il linker tira dentro solo gli oggetti
effettivamente usati**: un'app di solo advertising non li pesca, quindi non vanno forniti. Le
uniche dipendenze esterne risolte sono HAL/BSP del SoC e la runtime (`__aeabi_*`, `memcmp`).

## Struttura

| File | Contenuto |
|---|---|
| `src/startup_mm32f031.c` | vector table MM32F031 + reset handler (init `.data`/`.bss`, chiama `main`) |
| `ld/app.ld` | linker script: FLASH `0x08001010` (base app, **da confermare**), RAM `0x20000000` 4K |
| `compat/` | shim per i `#include` con maiuscole/minuscole diverse (`bsp.h`→`BSP.h`, `spi.h`→`SPI.h`) |
| `vendor/fetch-sdk.sh` | clona il SDK Macrogiga al commit fissato (il SDK non è versionato qui) |
| `Makefile` | compila baseline (`app-argun`) + HAL + startup, linka la radio, `image` |

La baseline è l'esempio del SDK; la personalizzazione inizia modificando `main.c`/`app.c`
(allora conviene copiarli qui sotto `app/` con la loro licenza MIT).

## Da fare (prima di avere un firmware reale da flashare)

- Confermare l'indirizzo base dell'app del nostro bootloader (ora `0x08001010`) e la variante
  CRC32 — idealmente da un'immagine ufficiale.
- Scrivere la nostra `main.c` (advertising con il nostro nome, poi funzioni) al posto della baseline.
- Non flashare senza rete di sicurezza (immagine di ripristino o secondo dispositivo) e senza
  aver confermato lo staging del bootloader.
