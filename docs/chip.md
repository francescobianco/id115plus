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

> ## ✅ Chip identificato 2026-10-21: **Dialog/Renesas DA14585** (ARM Cortex-M0)
>
> **Marking letto fisicamente** su un'unità aperta della stessa famiglia (modello diverso ma
> imparentato): **`Dialog DA14585 1824NCAE`**. Le foto interne FCC dell'ID115 Plus (filing
> `2AHFTID115PLUSHR` e `2AHFTID115PLUSCOLOR`, Shenzhen DO Intelligent) mostrano un **QFN40 ~6mm**
> al centro della PCB, coerente col package del DA14585 (marking non leggibile a quella
> risoluzione, ma il dato fisico lo conferma).
>
> Questo **corregge due assunzioni**:
> - NON è Macrogiga/MM32 (su cui era basato `firmware/`).
> - NON è nemmeno il non-ARM ST17H2x/MX1003 che certe schede venditore indicavano (l'hardware
>   degli ID115 Plus varia tra lotti; quelle schede erano di altre varianti o errate).
>
> Il **DA14585 è ARM Cortex-M0** → la toolchain `arm-none-eabi-gcc` era giusta nello spirito.
> Sbagliati erano **SDK e memory-map**: il DA14585 **non ha flash interna**, esegue da **SysRAM**
> (96KB) con il codice caricato dalla **SPI flash esterna** (o OTP) dal boot ROM. Niente modello
> `0x08000000`. Formato immagine e checksum sono quelli Dialog/vendor, non MacroGiga → spiega i
> **5 upload OTA rifiutati** (architettura + formato/CRC sbagliati).
>
> **Prossimo:** Dialog **SDK6 (DA145xx)**, linker verso SysRAM, immagine Dialog/secondary-bootloader
> del vendor, e il CRC che il bootloader del vendor verifica (un'immagine ufficiale lo inchioderebbe).
> `firmware/` (MM32/ARM) è **superato**: va rifatto sul SDK DA14585. Il **transport** OTA `fd00`
> (`./id115plus ota-flash`) resta valido. Foto FCC: fccid.io/2AHFTID115PLUSHR e …PLUSCOLOR.

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
