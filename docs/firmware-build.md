# Costruire un firmware: mappa di memoria, rischio, strategia

Base: SDK `macrogiga/MS1793-SDK` (`software/app-OTA/main-boot.c`) + spec OTA del nostro
dispositivo ([ota-protocol.md](ota-protocol.md), [device-ota-params.md](device-ota-params.md)).

## SoC

- MM32 (MindMotion, clone STM32) con core **ARM Cortex-M0**. Flash mappata a `0x08000000`.
- Lo stack radio BLE è una **libreria binaria** precompilata del SDK (`mg_api.h`): non si
  ricompila, si linka. Noi scriviamo solo l'applicazione sopra.
- **Linkaggio GCC verificato (2026-10-21).** `mg_BLE_lib_m0.lib` è un archivio `ar` di oggetti
  ELF Cortex-M0 con ABI EABI: `arm-none-eabi-gcc` la linka senza Keil. Un'app di solo advertising
  (`radio_initBle` + `ble_set_adv_data` + `ble_run`) linka **senza simboli irrisolti**; l'archivio
  tira dentro solo gli oggetti usati, quindi la tabella GATT (`AttCharList`, callback server…) non
  va fornita. Build riproducibile in `firmware/` (`make fetch && make && make image`). Nessun flash.

## ⚠️ Rischio architetturale aperto: modulo a 2 chip vs SoC integrato

Leggendo `firmware/app/BSP.c` (porting layer del SDK MS1793) emerge che **quel SDK è pensato per
un modulo a DUE chip: un MCU host MM32F031 + una radio BLE Macrogiga ESTERNA collegata via SPI**
(SPI1 su PB3/4/5, CS su PB8, IRQ su PA12). La libreria radio parla col chip radio attraverso
`SPI_WriteRead()` — cioè assume hardware con radio separata.

Il nostro **MSLM707 è un braccialetto minuscolo: quasi certamente un SoC BLE integrato (un solo
chip, radio on-die)**, non MM32F031 + radio esterna. Se è così:
- la pinout e il transport SPI di questo SDK **non corrispondono** al nostro hardware;
- il SDK giusto sarebbe un'altra parte Macrogiga/Maxscend (SoC), non MS1793;
- **la nostra `app.bin` attuale linka e advertis-a in teoria, ma non è detto che giri sul nostro
  chip.** Da chiarire *prima* di qualunque flash.

Come dirimere (senza flashare): confrontare i parametri OTA letti dal device (`projId=0x2a4b`,
boot/stack/app) con i vari SDK Macrogiga (MS1656/MS1892/MS179x), e identificare il chip reale dal
marking fisico o da un secondo dispositivo. Questo va risolto prima dell'indirizzo base/CRC.

### Aggiornamento 2026-10-21 — l'OTA del device è "Maxscend", NON Telink, e NON confermato MM32

Dal reverse dell'APK (`com/uthink/ring/service/BluetoothLeService.java`) l'app Yoho Sports ha
**due** famiglie OTA, scelte dai servizi GATT annunciati dal device:
- **Telink** (SPP OTA, UUID base `00010203-...-1912`, classe `TelinkOta`, blocchi 16B, core tc32):
  **NON è il nostro** — è per altri braccialetti della stessa app.
- **Maxscend** (`fd00`/`fd01`/`fd02`, costanti `MAXSCEND_OTA_*`): **è il nostro** (il device
  espone `fd00/fd01/fd02`). Conferma che `docs/ota-protocol.md` descrive il path giusto.

Conseguenza importante: **"Maxscend" ≠ "Macrogiga".** Il SDK MS1793 (Macrogiga, MM32 Cortex-M0)
su cui è basato `firmware/` è un'**assunzione non verificata** e potrebbe essere il chip
sbagliato. Non abbiamo un SDK/toolchain/datasheet del SoC Maxscend (né negli SDK clonati —
MM32/`cx32l003` — né su GitHub). Finché il SoC non è identificato, un'immagine compilata da noi
**potrebbe non girare** anche se l'upload OTA va a buon fine.

Corroborazione HR: il cloud OTA Yoho è organizzato per componenti tipo `MC3631`/`MC3413W`
(accelerometri mCube) e **`HRS3300`** (sensore battito ottico PPG) — coerente col sensore HR
presente sul nostro device.

## Cosa fa `BSP_Init()` e il porting layer (da `firmware/app/BSP.c`)

- `SystemClk_HSEInit()` → clock a 48 MHz da HSI×4; `SysTick_Configuration()` → tick 1 ms.
- `SPIM_Init(SPI_BLE, ...)` → SPI1 master verso la radio esterna (vedi sopra).
- GPIO IRQ della radio (EXTI falling), LED modulo su PA8, tasto su PA0.
- Funzioni di porting che la lib radio richiede: `SPI_WriteRead`, `SPI_CS_Enable_/Disable_`,
  `IsIrqEnabled`, `McuGotoSleepAndWakeup` (sleep/standby), `SysClk48to8`/`SysClk8to48`,
  `DisableEnvINT`/`EnableEnvINT` (no-op qui), `UpdateLEDValueAll` (no-op). Non si possono
  rimuovere: sono il "contratto" lato app che la libreria binaria chiama.

## Periferiche hardware

- **Sensore di battito ottico (PPG)** sul retro: presente fisicamente (confermato). Il firmware
  stock **non lo espone** (flag battito a zero in `cc02`), ma il firmware custom dovrà poterlo
  pilotare. Tipicamente un AFE ottico (es. famiglia Vcare/VC31 o simili) su **I2C** + LED driver;
  da identificare il bus/indirizzo esatto quando si arriverà a usarlo. Non assumere un retro
  "cieco": c'è una periferica in più rispetto a quanto dichiara lo stock.
- Accelerometro (passi/sonno), motore di vibrazione, display: già usati dallo stock.

## Mappa di memoria del bootloader d'esempio (SDK MS1793, flash 64 KB)

```
0x08000000  0–3KB    BootCode   (bootloader, NON toccare)
0x08000C00  3–4KB    UserData
0x08001000  4–34KB   Bank A     (RunCode: l'app in esecuzione, 30KB)
0x08008800  34–64KB  Bank B     (staging OTA, 30KB)
```

- `APPLICATION_ADDRESS = 0x08001010` = base Bank A (`0x08001000`) + **16 byte di header**.
  La vector table dell'app sta quindi a `0x08001010`.
- Header del SDK (16 byte): `size u16 LE` + `crc16 u16 LE` + 12 riservati. (Diverso dal nostro,
  vedi sotto.)

### Schema a doppio banco (dal `main()` del boot)

1. Al reset gira il **bootloader**.
2. Se `CheckCodeBank(Bank B)` passa (CRC del Bank B valido) → `CopyB2A()` (cancella Bank A,
   copia B in A, riverifica).
3. `ClearBank(Bank B)`.
4. `Jump2App(0x08001010)`.

L'OTA deposita la nuova immagine nel **Bank B** (staging). L'app in esecuzione (Bank A) viene
sostituita **solo al riavvio successivo e solo se il CRC del Bank B è valido**.

## Il nostro bootloader è una variante personalizzata

Il bootloader del braccialetto NON è identico a quello del SDK:

| | SDK MS1793 | Nostro dispositivo (da APK) |
|---|---|---|
| Servizio/char OTA | UUID 128-bit, `OTA_Proc` | `fd00`/`fd01`/`fd02`, opcode `01/02/03` |
| Header | size+crc16 (16B) | projId/boot/stack/app/appStack/appBoot/codeSize/**crc32** (16B) |
| Checksum | CRC-16/CCITT | **CRC32** (variante da determinare) |

Quindi dal SDK **non** conosciamo con certezza, per il nostro chip:
- l'indirizzo base della partizione app (candidato forte: `0x08001010`, ma dimensioni banchi
  e offset possono differire — alcuni modelli hanno flash più grande: l'app dichiara
  `flashSize` 114688 o 258048 byte per certi firmware);
- la **variante esatta di CRC32** attesa dal bootloader (l'app ufficiale si limita a inoltrare
  i 4 byte presenti nell'header dell'immagine; non lo ricalcola).

Questi due valori si ricaverebbero con certezza da un'**immagine ufficiale** (reset vector →
base app; ricalcolo del CRC sull'immagine → variante). Per questo procurarsi un'immagine di
riferimento resta prioritario.

## Rischio di brick: cosa è sicuro e cosa no

Assumendo che il nostro bootloader mantenga lo schema a doppio banco del SDK (**da confermare**):

- **CRC sbagliato = SICURO.** Il bootloader rifiuta il Bank B e continua ad avviare il Bank A
  (firmware attuale). Nessuna sostituzione. → possiamo provare **tutto il flusso di upload OTA**
  (`01` → `02` → dati su `fd01` → `03` con CRC volutamente errato) e leggere la notifica di
  esito `value[1]==3`, **senza rischiare il firmware**.
- **CRC corretto ma codice che non parte = RISCHIOSO.** Il boot copia B→A e salta su codice
  rotto. Recuperabile solo se, al riavvio, il bootloader rientra comunque in OTA (da verificare).
- **Incognita che pesa:** se il bootloader del produttore **non** usa staging e scrive invece
  direttamente sulla partizione app man mano che riceve i dati, allora anche un upload
  interrotto o con CRC errato potrebbe corrompere il firmware in esecuzione. L'APK non lo
  chiarisce; il SDK usa staging. **Con un solo dispositivo e senza immagine di ripristino,
  finché questa incognita non è risolta non carichiamo nulla, nemmeno con CRC errato.**

## Strategia di costruzione (piano piano, senza flashare finché non è sicuro)

1. **Toolchain + build di prova** (nessun flash): installare `arm-none-eabi-gcc`, compilare
   l'esempio più semplice del SDK (es. `blinky`/motore) per confermare che produciamo un `.bin`
   valido per questo SoC. Capire come è linkata l'app e dov'è la vector table.
2. **Tool immagine OTA** (`tools/mkimage.py`, offline): dato un `.bin` applicativo, costruisce
   l'header a 16 byte con `projId=0x2a4b boot=4 stack=2 app=0x6900` e il `codeSize`, e calcola
   il `crc32` in più varianti candidate. Pronto ma non usato finché non sappiamo la variante.
3. **Procurarsi un'immagine di riferimento** (APK più recente, mirror, produttore): sblocca
   base app e variante CRC32, e dà una copia di ripristino.
4. **Dry-run OTA sicuro** (solo se confermato lo staging): upload con CRC volutamente errato,
   leggere l'esito, provare il flusso end-to-end senza sostituire il firmware.
5. **Primo firmware reale**: app minima linkata all'indirizzo giusto, CRC corretto, caricata
   solo con rete di sicurezza (immagine di ripristino o secondo dispositivo).
