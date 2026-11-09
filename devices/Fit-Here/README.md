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

- `01 <n> ff` risponde `00 81`. Da quel momento lo stock non parte più finché non viene riscritta
  la tabella a `0x3000`.
- La partition-info deve essere di **16 byte** (`02`, indice, flash, run, size, CRC **u16**): la
  forma da 18 byte degli SDK più recenti viene ignorata in silenzio.
- La partition-info viene solo validata: la flash si tocca solo dopo l'ultimo pacchetto dati.
- Una partizione XIP a `0x1101f000` è accettata in partition-info ma, dopo i dati, l'updater
  risponde `10` (`INVALID_ADDR`). Partizioni SRAM nel banco a offset `0xB000`: scritte senza errori.
- Il dumper in `firmware/dumper` è tutto in SRAM e occupa solo `0x1c000`–`0x1efff`.

### Come scrive la flash (dal sorgente SDK, non ancora verificato su questa build)

- `01` (START) cancella solo il settore `0x3000` (tabella app).
- Ogni partizione cancella e scrive solo i propri settori da 4 KB: le partizioni XIP
  (run = flash) vanno all'indirizzo scelto da noi in `0x11003000`–`0x1107ffff`, quelle SRAM nel
  banco app a un offset scelto da noi. A fine OTA riscrive la tabella a `0x3000`.
- Quindi un dumper piccolo in una zona libera potrebbe leggere la flash senza cancellare lo stock
  (andrebbe ricostruita solo la tabella). Non sappiamo ancora quali zone usa lo stock.
- Rete di sicurezza: il loader UART della ROM PHY62xx (P09 TX, P10 RX, TM) non si può cancellare.

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

- Backup completo della flash: via UART (sicuro, ~35 min) o con un dumper OTA in una zona libera.
- Decodificare il protocollo `18D0`/`0x5A` (serve l'APK "Fit-here").
