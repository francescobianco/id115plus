# firmware-da14585/ — firmware BLE per il chip reale (Dialog DA14585)

Build **GCC** di un'app BLE di advertising per il braccialetto, linkata contro il **Dialog
DA145xx SDK 6.0.24.1464**. Il SoC è un **Dialog/Renesas DA14585** (ARM Cortex-M0, esegue da
SysRAM, no flash interna) — vedi [../docs/chip.md](../docs/chip.md).

## Stato: build reale che linka (advertising `ID115DIY`)

`make` produce un'immagine RAM-resident completamente linkata (**nessun simbolo irrisolto**),
che pubblicizza sotto il nome **`ID115DIY`**. **Niente viene ancora flashato.**

```shell
make                      # -> build/app.elf, build/app.bin
make SDK_PATH=/percorso/al/DA145xx_SDK/6.0.24.1464
make clean
```

Layout verificato (`arm-none-eabi-objdump -h`, la mappa è quella canonica del SDK):

| Cosa | Valore |
|---|---|
| Base immagine (vettori) | `0x07FC0000` (SysRAM) |
| `patch_table` (patch simboli ROM) | offset `0x0C0` |
| Entry (`Reset_Handler`, Thumb) | `0x07FC0511` |
| SP iniziale (`__StackTop`, calcolato dal linker) | entro SysRAM |
| `app.bin` | ~23 KB |

> Nota: lo SP non è un indirizzo fisso tipo `0x07FD8000`; nella mappa del SDK lo stack sta
> **dopo** codice e RAM ritenuta, e l'indirizzo lo calcola il linker. È corretto così.

## Come è costruito (serve il SDK, non ridistribuibile)

Lo stack BLE del DA14585 **non è ridistribuibile**: scarica il **DA145xx SDK 6.0.24.1464** da
Renesas e punta `SDK_PATH` alla sua radice (la cartella con `sdk/` e `projects/`). Il SDK fornisce
tutti i pezzi GCC che usiamo **per path** (mai copiati nel repo):

- libreria radio prebuilt `sdk/platform/system_library/output/Keil_5/da14585_586.lib`;
- startup GCC `sdk/platform/arch/boot/GCC/startup_DA14585_586.S` + `ivtable_DA14585_586.S`;
- template linker GCC `sdk/common_project_files/ldscripts/ldscript_DA14585_586.lds.S`
  (+ `mem_DA14585_586.lds`) e i simboli ROM `.../misc/da14585_symbols.lds`
  (il `Makefile` lo preprocessa in `build/ldscript.ld`);
- i ~55 sorgenti core del SDK (rwip, ke, gap, app_easy, profili…) compilati da `SDK_PATH`.

### File del repo vs file locali

- **Nostri, versionati:** `Makefile`, questo `README.md` (più gli strumenti OTA in `../tools/`).
- **Locali, NON versionati** (`.gitignore`): `config/` e `app/` — al momento sono l'esempio
  **`ble_app_barebone`** del SDK con il nome device impostato a `ID115DIY`; `build/`; `vendor/`.
  Sono materiale derivato dal SDK (non ridistribuibile), quindi restano fuori da git. Il prossimo
  passo è sostituire `app/` con sorgenti **nostri** minimali.

## Come si collega all'OTA del vendor

Il bootloader secondario del vendor carica l'immagine in SysRAM a `0x07FC0000` ed esegue
(`CFG_CODE_LOCATION_EXT`), che è esattamente ciò che questo build produce. Il payload "code" per
l'OTA è il `build/app.bin` grezzo (vettori a `0x07FC0000` in testa). L'immagine OTA si confeziona
con l'header a 16 byte del vendor via `../tools/mkimage.py` / `../tools/crc_candidates.py`, e si
prova col brute-force del checksum `../tools/ota_bruteforce.sh` (vedi
[../docs/ota-flash-runbook.md](../docs/ota-flash-runbook.md)).

**Rischio residuo noto:** non è ancora provato che il vendor si aspetti *esattamente* il `.bin`
grezzo caricato a `0x07FC0000` (offset/header interni al payload). Senza un'immagine di riferimento
o un dump SWD resta un'ipotesi: è l'unica incognita che può ancora causare un brick quando un
checksum verrà accettato con codice valido ma formato errato.

## Da fare

1. Sostituire `app/` con un'app di advertising **nostra** minimale (sorgenti originali).
2. Confezionare `build/app.bin` con l'header del vendor e lanciare il brute-force del checksum.
3. Se tutti i candidati sono rifiutati → dump SWD della cavia per formato + algoritmo.
