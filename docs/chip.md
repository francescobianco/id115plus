# Il chip: Maxscend / Macrogiga BLE SoC

Ricostruzione del SoC del braccialetto `MSLM707`, per capire cosa serve a costruire un
firmware proprio. Niente di questo richiede di aprire il dispositivo: è tutto dedotto dai
servizi BLE esposti, dall'APK ufficiale e dalla documentazione pubblica del produttore.

## Identificazione

| Indizio | Valore |
|---|---|
| Servizio OTA sul dispositivo | `fd00` / `fd01` / `fd02` |
| Nome nell'APK | `MAXSCEND_OTA_SERVICE` (`BluetoothLeService.java:225-227`) |
| Produttore (etichetta APK) | `MAXSCEND_OTA` — ma è solo il nome che l'app dà a questo path OTA |
| Core | **NON confermato; molto probabilmente NON ARM** (vedi correzione sotto) |

> ## ⚠️ Correzione 2026-10-21 — l'assunzione "Macrogiga/MM32/ARM" è probabilmente sbagliata
>
> Tutto il lavoro su `firmware/` era basato sull'ipotesi che `fd00` = ecosistema **Macrogiga
> (MM32, ARM Cortex-M0)**. La ricerca mostra che **non regge**:
> - Le schede prodotto dell'**ID115 Plus** indicano come MCU **"mCube MX1003"** (accel MC3613, HR
>   **HRS3300**, 16KB+512KB), un altro venditore dice **"ST17H25"**. Entrambi sono **BLE SoC
>   low-cost NON ARM**: la famiglia **Lenze ST17H2x** (datasheet "low cost BLE+2.4G dual mode
>   SoC"); un teardown di un ST17H26 ha trovato perfino un **ID Telink** → core proprietario
>   (Telink/8051-class), **non** Cortex-M.
> - Conseguenza: l'immagine ARM che costruiamo in `firmware/` **non girerà mai** su questo
>   silicio, e il CRC che il suo bootloader calcola non è quello della famiglia MacroGiga.
>   Questo spiega perché **5 upload OTA sono stati rifiutati** (vedi docs/ota-flash-runbook.md):
>   immagine di architettura sbagliata + CRC di una famiglia diversa.
> - "Maxscend"/"Macrogiga" nell'app è solo l'etichetta di quel path OTA, non la prova del
>   silicio. Gli SDK MacroGiga clonati **non sono il nostro chip**.
>
> **Serve l'identificazione fisica del chip** (serigrafia): aprendo la **cavia**, o dalle foto
> interne del deposito **FCC** (ID115 è depositato da Shenzhen DO Intelligent Technology). I
> venditori non concordano (MX1003 / ST17H25 / mCube / Lenze / Telink) e gli esemplari variano,
> quindi solo il marking risolve. Poi servono SDK+toolchain di QUEL chip e il suo formato immagine.
>
> Risorse di partenza se risultasse famiglia Lenze/Telink: datasheet Lenze ST17H2x; tooling
> community per il fratello **ST17H66** (`biemster/FindMy` issue #5, doc.lenze.club) — ma
> architettura diversa dall'ST17H26, quindi da verificare dopo il marking.

Il servizio OTA `fd00`/`fd01`/`fd02` sul dispositivo resta valido come **transport** (lo abbiamo
pilotato con successo: staging + verifica CRC confermati). È il *contenuto* (architettura +
formato/CRC) che dev'essere quello del chip reale.

## Risorse pubbliche del produttore (GitHub `macrogiga`)

SDK completi con sorgenti C, esempio di OTA e tool per preparare il `.bin`:

| Repo | Chip | Core | Package |
|---|---|---|---|
| `macrogiga/MS1793-SDK` | MS179x | Cortex-M0 | QFN32 |
| `macrogiga/MS1793S-SDK` | MS1793S | – | TSSOP24 |
| `macrogiga/MS1892-SDK` | MS1892 | Cortex-M3 | – |
| `macrogiga/MS1656-SDK` | MS1656 | Cortex-M0+ | QFN20 |

Cloni locali (scratchpad, non versionati): `MS1793-SDK`, `MS1892-SDK`, `MS1656-SDK`.

### Cosa contiene l'SDK (MS1793, rilevante)

- `software/app-OTA/` — bootloader OTA (`main-boot.c`) e applicazione OTA (`app.c`, `main.c`).
  Mostra il database GATT, la dichiarazione del servizio OTA a 128 bit, e la callback
  `OTA_Proc(data, len)` che riceve i pacchetti. **Questo è il modello di riferimento per
  capire la mappa di memoria e il formato dei pacchetti accettati dal bootloader.**
- `software/app-OTA/OtaBinTool/mg_ota_head_hex.exe` — il tool ufficiale che aggiunge
  l'header OTA (con CRC) a un `.hex`/`.bin`. Da replicare in Python per generare i nostri header.
- `software/Src/inc/mg_api.h` — API della libreria BLE (stack radio come blob, il resto sorgente).
- `software/app-*` — tanti esempi (UART, HID, ADC/HRS, motore, OLED…): base per la nostra app.
- `software/MM32x031/` — CMSIS e periferiche. Il core applicativo è un MM32 (clone STM32 di
  MindMotion) con Cortex-M0: toolchain ARM standard (Keil/IAR nei progetti, ma `arm-none-eabi-gcc`
  è utilizzabile).

### Nota sul bootloader OTA dell'SDK vs quello del braccialetto

L'SDK di esempio usa un servizio OTA a **UUID 128 bit** (`...19` little-endian), mentre il
braccialetto usa `fd00/fd01/fd02` a 16 bit. Il produttore del braccialetto ha quindi
personalizzato gli UUID e probabilmente il protocollo applicativo OTA (vedi
[ota-protocol.md](ota-protocol.md), sezione 2). L'SDK resta prezioso per:
- la mappa di memoria del SoC (dove stanno boot / stack / app),
- la toolchain e i linker script,
- l'algoritmo CRC e il formato header (da confrontare con l'header reale dell'immagine ufficiale).

## Toolchain

- Host: `arm-none-eabi-gcc` (ARM Cortex-M0). OpenJDK 21 presente (serve a jadx, non al firmware).
- Lo stack radio BLE è fornito come libreria binaria precompilata nell'SDK: non va ricompilato,
  va linkato. Questo è il pezzo che non possiamo sostituire — ci costruiamo sopra l'applicazione.

## Implicazioni per la sicurezza / recuperabilità

- Dall'APK: verifica solo **CRC32 + compatibilità versione/progetto**, nessuna firma né
  crittografia (vedi [ota-protocol.md](ota-protocol.md) §3). Da confermare sul dispositivo.
- **Recupero senza SWD:** l'OTA non ha rollback. Se sovrascriviamo il bootloader con
  un'immagine che non parte, il braccialetto è irrecuperabile senza collegare i pin SWD
  (cioè senza aprirlo). Finché scriviamo solo nella partizione *app* e il *bootloader* resta
  intatto, un'immagine difettosa dovrebbe comunque lasciare il bootloader OTA in grado di
  riaccettare un'immagine valida. **Questa è l'assunzione chiave da verificare prima di
  rischiare.**

## Fonti

- SDK: https://github.com/macrogiga (MS1793-SDK, MS1892-SDK, MS1656-SDK)
- Produttore: https://www.maxscend.com/details/137.html (低功耗蓝牙微控制器)
- Contesto custom firmware su fitness band economici:
  https://hackaday.com/2019/02/20/custom-firmware-for-cheap-fitness-trackers/
- Dump firmware ID115 (modello Nordic, diverso dal nostro): https://github.com/ctz/id115-firmware-dump
