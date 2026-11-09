# Fit-Here

Braccialetto che si annuncia come **`Fit-Here`**. Chip **PhyPlus PHY62xx**, con un bootloader OTA
PhyPlus raggiungibile via BLE senza aprirlo.

## Dispositivo

| Campo | Valore |
|---|---|
| Nome BLE | `Fit-Here` |
| MAC | `C0:00:A1:B1:02:61` (public) |
| Manufacturer data | company `0x00C0`, `a1 b1 02 61 54 4a 44 52` = ultimi 4 byte del MAC + `TJDR` |
| PnP ID (`2A50`) | `01 0504 0000 1001` → vendor **`0x0504` = PHYPLUS Inc**, versione `0x0110` |
| Device Information | stringhe di default dell'SDK (`Model Number`, `Serial Number`, …, `2A2A` = `FE 00 experimental`) |
| Bootloader OTA | PhyPlus `OTA_internal_flash` **V3.0.7** (da `ota_app` cmd `02`) |
| Chip | PHY6222 o PHY6252 (non distinguibili senza aprirlo) |
| App ufficiale | "Fit-here" (iOS, Shenzhen Jiebiya Technology); APK non ancora recuperato |

## GATT (app stock)

| Servizio | Caratteristiche | Note |
|---|---|---|
| `1800`, `1801` | | GAP, GATT |
| `180A` | `2A23`–`2A2A`, `2A50` | Device Information, valori di default SDK |
| `180F` | `2A19` read/notify | batteria (letto `0x5F` = 95 %) |
| `1812`, `1813` | | HID e Scan Parameters (BlueZ li nasconde, handle `0x32`–`0x43`) |
| `18D0` | `2D01` write-no-rsp ("Write"), `2D00` read/notify ("Notify") | protocollo dell'app, frame che iniziano con `0x5A` (letto `5a 05 01 01 6c …`). Da decodificare. |
| `5833ff01-9b8b-5191-6142-22a4536ef123` | `ff02` write, `ff03` notify | `ota_app_service` dell'SDK PhyPlus |

## OTA e updater

Riferimenti: sorgenti SDK in
[e-labInnovations/FitPro-LP715-PHY6222](https://github.com/e-labInnovations/FitPro-LP715-PHY6222)
(`sdk/phy6222/components/profiles/ota_app/` e `.../ota/ota_protocol.c`, `error.h`) e il suo
`tools/ble_ota.py`. È un altro orologio con lo stesso SoC: pin e display non sono i nostri.

### Dall'app (`MAC=C0:00:A1:B1:02:61`)

| Comando su `ff02` | Effetto |
|---|---|
| `02` | INFO: `00` + BD addr LE + `V3.0.7`, sola lettura |
| `01 02` | scrive `2` in AON `0x4000f034` e si riavvia nell'updater (la scrittura riceve ATT `0x0e` perché il device si resetta prima dell'ACK: è normale) |

### L'updater (verificato il 2026-11-07, andata e ritorno senza danni)

- Si annuncia come **`PPlusOTA`** a **`C0:00:A1:B1:02:62`** (MAC + 1, modalità "address plus"),
  manufacturer data `0x0504` = `62 02 b1 a1 00 c0 00 00` (proprio MAC LE + `0000`).
- Schermo nero. Nessun timeout da fermo: resta in attesa finché non lo si riavvia.
- GATT: solo `5833ff01` con `ff02` write (comandi), `ff03` notify (risposte), `ff04`
  write-no-rsp (dati).
- Risposte su `ff03`: `[errore, codice]`, errori di `error.h` (`0x64` = 100 `OTA_INVALID_STATE`).

| Inviato | Risposta | Note |
|---|---|---|
| `02` fuori stato | `64` | rifiutato, niente scritto |
| `03` | `05 ff` | `NOT_SUPPORTED` |
| dati su `ff04` | `64` | rifiutato |
| `05` (ERASE) | `64` | fuori stato, come nell'SDK |
| `06` + 16 byte | nessuna | ignorato: più lungo della struct dei comandi di questa build |
| `04 01` | `00 8a` | riavvio alla disconnessione → torna l'app stock (vibra, mostra batteria/carica) |
| `04` | — | riavvio immediato |
| **`01`** | — | **NON mandare senza un'immagine completa**: START cancella la tabella app a `0x3000`, lo stock non riparte più. `phy_ota.py` lo rifiuta senza `--unsafe` |

### OTA reale (verificato il 2026-11-09)

- **`01 <n> ff` risponde `00 81` e cancella più della tabella.** Dopo il primo `01` il banco app
  `0x11000`–`0x1ffff` risultava vuoto e la parte SRAM dello stock non si trova più in tutta la
  flash: questa build (V3.0.7) cancella quasi certamente anche il banco, a differenza degli SDK
  più recenti. Lo stock non si può quindi ripristinare dal dump.
- La partition-info deve essere di **16 byte** (`02`, indice, flash, run, size, CRC **u16**): la
  forma da 18 byte degli SDK più recenti viene ignorata in silenzio.
- La partition-info viene solo validata: la flash si tocca solo dopo l'ultimo pacchetto dati.
- Una partizione XIP a `0x1101f000` è accettata in partition-info ma, dopo i dati, l'updater
  risponde `10` (`INVALID_ADDR`). Partizioni SRAM nel banco a offset `0xB000`: scritte senza errori.
- Il dumper in `firmware/dumper` è tutto in SRAM e occupa solo `0x1c000`–`0x1efff`.

### Mappa della flash (dal dump del 2026-11-09, `dump/`, fuori da git)

| Indirizzo | Contenuto |
|---|---|
| `0x02000` | boot table dell'updater |
| `0x03000` | tabella app (ora quella del dumper) |
| `0x04000` | MAC |
| `0x05000`–`0x101ff` | updater `PPlusOTA` (SRAM da `0x5000`, XIP da `0xa000` e `0x10000`) |
| `0x11000`–`0x1ffff` | banco app: svuotato da `01`, ora il dumper a `0x1c000` |
| `0x20000`–`0x39aff` | codice XIP dello stock (veneer in testa) |
| `0x3c000`–`0x3e0ff` | settori con intestazione `1103c000`, probabilmente il file system |
| `0x40000`–`0x5d8ff` | risorse (a `0x47800` il font `PHY_FONT`) |

### Come scrive la flash (dal sorgente SDK, non vale per questa build)

- `01` (START) cancella solo il settore `0x3000` (tabella app) negli SDK recenti, non qui.
- Ogni partizione cancella e scrive solo i propri settori da 4 KB: le partizioni XIP
  (run = flash) vanno all'indirizzo scelto da noi in `0x11003000`–`0x1107ffff`, quelle SRAM nel
  banco app a un offset scelto da noi. A fine OTA riscrive la tabella a `0x3000`.
- Quindi un dumper piccolo in una zona libera potrebbe leggere la flash senza cancellare lo stock
  (andrebbe ricostruita solo la tabella). Non sappiamo ancora quali zone usa lo stock.
- Rete di sicurezza: il loader UART della ROM PHY62xx (P09 TX, P10 RX, TM) non si può cancellare.

## Firmware nostro

`firmware/demo` (verificato il 2026-11-09): si annuncia come `FH-DEMO` a `C0:00:A1:B1:02:64`, il
Battery Level è un contatore (+1 al secondo), sul controllo `4c500002` risponde a `20 pp lo hi`
(impulso sul pin), `04` (ritorno all'updater) e `7f a5` (blocca il ciclo principale, per provare il
watchdog: dopo circa 9 s riparte in `PPlusOTA`).

Pin noti: **vibro `P23`, attivo alto** (trovato con gli impulsi). Sull'LP715 `P23` controlla la
carica e il vibro è `P03`: i pin dell'LP715 non valgono qui. Provati senza effetti visibili: `P00`,
`P01`, `P02`, `P03`, `P14`, `P15`, `P16`, `P18`, `P20`, `P26`.

```shell
firmware/build.sh demo
tools/phy_flash.py firmware/demo/_build/fh_demo.hex --confine 0x11000:0x27000 --yes   # dall'updater
MAC=C0:00:A1:B1:02:64 tools/phy_ota.py 4c500002=2017f401                              # vibra 500 ms
```

### Pin dal codice stock (analisi statica del dump, 2026-11-09)

Ricavati dal codice XIP `0x20000`–`0x39aff` confrontando le chiamate con le firme dell'SDK. Nessuno è
ancora provato sul dispositivo. Numeri di pin: enum `gpio_pin_e` (`P14`=8, `P15`=9, `P23`=14).

| Pin | Funzione | Certezza |
|---|---|---|
| `P14` | batteria, ADC canale 5, singolo, alta risoluzione, pin flottante | configurazione letta dal codice |
| `P15` | ingresso con pull-down, interrupt su entrambi i fronti, 100 ms di antirimbalzo; probabile rilevamento caricatore (salva il livello e cambia schermata) | configurazione letta, ruolo dedotto |
| `P23` | vibro (noto): lo stock lo spegne come input con pull-down | coerente con la prova fisica |
| `P18` SDA, `P20` SCL | I2C, dispositivo a `0x19`, probabile accelerometro | indirizzo letto, tipo dedotto |
| `P32` SDA, `P33` SCL | secondo I2C, senza chiamanti diretti: forse codice inutilizzato | da verificare |
| `P03` | solo un `hal_gpioin_disable` | ruolo ignoto |

Batteria: `V_batt ≈ V_adc × 5,5454` (costante `55454` in unità di 0,1 mV, unità dedotta dalle soglie).
Livello `(v - 34500) × 100 / 7300`: 0 % a 3,45 V, 100 % da 4,18 V, letture sotto 2,5 V scartate.

Display: TFT 80×160, pixel a 16 bit (controllo dei limiti e buffer di `uint16` nel codice XIP).
Inizializzazione `0x1fff68b0`, finestra `0x1fff681c` e invio pixel `0x1fff5ef8` sono nella parte
SRAM persa, quindi i pin non si ricavano dal dump. Il PWM canale 0 nel codice XIP è il vibro (`P23`),
non la retroilluminazione.

**`P34` comanda la luce dello schermo, attivo alto** (prova fisica del 2026-11-09: 2 impulsi casuali
alla cieca, 2 lampeggi contati). Probabilmente è la retroilluminazione. `P33` alla stessa prova: 4
impulsi, nessun lampeggio.

A luce accesa il pannello è nero uniforme. La demo ha un comando di ricerca, `30 rr ss mm` (RST, SCK,
MOSI, `ff` = tutti), che manda `11`, `21`, `29` tenendo bassi gli altri candidati (`P00`–`P03`, `P11`,
`P24`–`P27`, `P31`–`P33`). Durante le sequenze di tentativi è comparsa più volte, per un attimo, una
**freccia verso l'alto** (verde, grigia o forse rossa), anche nella prova con RST `P01`. I comandi non
la disegnano, quindi è probabilmente il contenuto rimasto nella memoria del pannello.

**RST `P01`, SCK `P31`, MOSI `P25`** la fa comparire e restare fissa, e reinviando la stessa combinazione
scompare e riappare subito (prova a mano con `tools/fh_display_search.py`, 2026-11-09). Con MOSI `P33`
o `P02` non compare, e un riavvio (`04`) non la mostra.

**DC `P00`** (2026-11-09): con il comando `31` ogni candidato disegna una banda in una riga diversa, e
ripassando con un altro colore la banda cambia esattamente al passo di `P00`, nella riga prevista per
quel pin (136). Il controller risponde a `2a`, `2b`, `2c`, `3a` con pixel a 16 bit. Il rosso `f800`, a
inversione spenta, si vede giallo: compatibile con ordine BGR e pannello a colori invertiti (IPS), da
verificare. CS non trovato: finora è sempre rimasto basso, forse è fisso a massa. Non è ancora una
inizializzazione completa del controller. Cautela nei test: le vibrazioni possono far tremolare lo schermo, e un conteggio di lampeggi
fatto subito dopo è falsato.

Non trovato nemmeno il pin del tasto.

## Strumenti

```shell
tools/scan.py 30                                      # cerca Fit-Here, PPlusOTA e altri PhyPlus
tools/gattdump.py C0:00:A1:B1:02:61                   # tabella GATT con i valori leggibili
tools/phy_ota.py 5833ff02=02                          # INFO dall'app
tools/phy_ota.py 5833ff02=0102                        # app -> updater
MAC=C0:00:A1:B1:02:62 tools/phy_ota.py 5833ff02=0401  # updater -> app (alla disconnessione)
```

Dipendenze: `python3-dbus`, `python3-gi` (BlueZ via D-Bus, come `../../id115plus`).

## Prossimi passi

Stato e storia in [`DOSSIER.md`](DOSSIER.md), lista di lavoro in [`TODO.md`](TODO.md).
