# PLAN — firmware custom per il braccialetto MSLM707, via BLE, senza aprirlo

Obiettivo: caricare sul braccialetto `MSLM707` (`BA:03:5C:05:4A:12`) un firmware costruito da
noi, senza smontare il dispositivo, usando solo il canale OTA Bluetooth LE già presente.
Costruzione incrementale: prima capire e replicare l'OTA ufficiale, poi un firmware minimo,
poi funzioni nostre.

**Documenti di riferimento** (in `docs/`):
- [docs/ota-protocol.md](docs/ota-protocol.md) — protocollo OTA completo ricavato dall'APK.
- [docs/chip.md](docs/chip.md) — il SoC Maxscend/Macrogiga, SDK, toolchain, recuperabilità.

---

## Il dispositivo

| Campo | Valore |
|---|---|
| Nome BLE | `MSLM707` |
| MAC | `BA:03:5C:05:4A:12` (public, già abbinato) |
| Firmware | `60.69.00.86` (da `cc02`, byte 12.13.14.11) |
| Chip | Maxscend / Macrogiga, ARM Cortex-M (servizio OTA `fd00`) |
| Protocollo app | Yoho Sports (`com.uthink.ring`) |
| Funzioni (flag cc02) | `03 00 00 00`: kmd, multi-sport |
| Sensori hardware | **sensore di battito ottico (PPG) presente** (confermato fisicamente), accelerometro, vibrazione, display |

> **Hardware ≠ firmware stock.** Il flag battito è a zero, ma il **sensore PPG c'è davvero** sul
> dispositivo: lo stock non lo espone. Per il firmware custom è una funzione hardware da abilitare
> (AFE ottico da pilotare, probabile I2C). Vedi [docs/firmware-build.md](docs/firmware-build.md).

Servizi GATT: `cc00` (controllo normale), `fd00` (OTA Maxscend), `ffe0` (**non usato
dall'app**, libero per noi), `fee7` (WeChat, solo rilevato).

## Riepilogo tecnico dell'OTA (dettagli in docs/ota-protocol.md)

- **Dove sta il firmware ufficiale:** bucket Aliyun OSS `mcube-ota`, endpoint
  `oss-cn-beijing.aliyuncs.com`. Credenziali hard-coded nell'APK (`update/Aliyun.java:33-40`):
  credenziali AK/SK (redatte qui, in `tools/oss.env` non versionato). Nessuna API HTTP di versione:
  l'app elenca il bucket e sceglie per nome file.
- **Nome file immagine:** `..._<f0>_<f1>_<f2>_<f3>.bin` (11 char prima di `.bin`,
  separati da `_`). È "più nuovo" se `f0` e `f3` combaciano e `f1` (hex) è maggiore. Per noi:
  `_60_XX_00_86.bin`. L'immagine in esecuzione è quasi certamente `_60_69_00_86.bin`.
- **Formato .bin:** header 16 byte (projId u16LE, boot, stack, app u16LE, appStack, appBoot,
  codeSize u32LE @8-11, **crc32 @12-15**) + codice. L'app toglie l'header prima di scriverlo.
- **Flusso (servizio fd00):** notify su `fd02` → la band annuncia versione → `01+versione` →
  `02+codeSize[4]` → codice a blocchi di 20 byte su `fd01` (la band risponde `xx 02 55`) →
  `03+crc32[4]` → la band verifica e si riavvia. Nessun offset/seq sul filo, nessun commit,
  nessun rollback.
- **Verifica lato dispositivo (dedotta):** solo CRC32 + compatibilità projId/boot/stack.
  **Nessuna firma né crittografia** trovata nell'app. Da confermare sul bootloader.
- **Secondo canale di scrittura in flash:** il percorso watchface/`UpdateImage` riusa
  `fd00/fd01/fd02` con opcode `0xF0-0xF7` e scrive a un indirizzo scelto, con sola somma
  additiva a 8 bit come checksum. Utile come vettore alternativo.

## Rischio principale

L'OTA non ha rollback e non possiamo usare SWD senza aprire il dispositivo. Un'immagine che
sovrascrive il **bootloader** e non si avvia = **brick permanente**. Mitigazione: capire la
mappa di memoria, scrivere solo nella partizione *app*, e tenere sempre pronta un'immagine
ufficiale valida da ri-flashare. Avere un secondo braccialetto identico come "cavia" ridurrebbe
molto il rischio.

---

## Fasi

### Fase 0 — Strumenti e ricognizione  ✅ (fatto)
- [x] Script di controllo stabile con riconnessione automatica (`id115plus`).
- [x] Decompilazione APK (jadx) e reverse dell'OTA → `docs/ota-protocol.md`.
- [x] Identificazione chip e SDK pubblici → `docs/chip.md`.

### Fase 1 — Procurarsi l'immagine ufficiale  ❌ (bloccata: credenziali revocate)
- [x] Scritto `tools/oss.py` (firma OSS V1 **e** V4, list/get; credenziali in `tools/oss.env`).
- [x] Tentato `list` e `get` sul bucket `mcube-ota`.
- **Esito:** `HTTP 403 AccessDenied` (EC `0003-00000905`) sia con firma **V1** sia con **V4**,
  sia su `list` sia su `get` di una chiave nota (`force-upgrade/force upgrade.txt`). Due schemi
  di firma diversi danno lo stesso errore identico → non è un problema di firma: le credenziali
  estratte dall'APK **non hanno più accesso in lettura** al bucket (policy ristretta/ruotata dal
  produttore). Possibile anche una restrizione per IP/VPC/Referer lato bucket.
- [x] Verificato che l'APK **non impacchetta** alcuna immagine firmware (i `.bin` in
  `assets/<risoluzione>/online/bin/` sono quadranti/immagini, non firmware).
- **Conseguenza:** non abbiamo un'immagine ufficiale di **ripristino**. Senza SWD, questo alza
  molto il rischio della Fase 4. Vie alternative da valutare: APK più recente con credenziali
  valide; mirror del firmware; richiesta diretta al produttore.

**Ricerca su GitHub di firmware già estratti (2026-10-20): nessuno per il nostro chip.**
Tutto il lavoro pubblico sull'ID115 riguarda la variante **Nordic nRF51**, non la nostra Maxscend:
- `rbaron/fitless` — firmware custom di esempio per ID115, ma su **nRF51** (nRF SDK 12, softdevice
  s130, build `nrf51422_xxac`, flash via **SWD**/J-Link). Non gira sul nostro MSLM707.
- `ctz/id115-firmware-dump` — dump del firmware ID115, sempre **nRF51**, via SWD.
- `donomii/ID115` — solo controllo via BLE, non firmware.
- `macrogiga/MS1793-SDK`, `MS1793S-SDK`, `MS1892-SDK`, `MS1656-SDK` — gli SDK del nostro
  produttore (Maxscend/Macrogiga): **questa resta la base per costruire il nostro firmware**.

Ricerche per codice (`mcube-ota`, `MSLM707`, `com.uthink.ring`, `uthink ring`, `MSF0 cc06`,
`0000fd02 OTA`) non hanno dato dump né immagini per la variante Maxscend. In pratica: **nessuno
ha pubblicato un firmware/dump per questo chip**; gli unici dump ID115 sono per un chip diverso.

Strumento: `tools/oss.py` (firma OSS V1/V4, list/get). Le credenziali vengono dall'APK e stanno
in `tools/oss.env` (non versionato). Non sono più valide per la lettura.

### Fase 2 — Osservare l'OTA dal dispositivo (sola lettura)  ✅ (fatto)
- [x] Abilitate le notifiche su `fd02` (`./id115plus ota-probe`, read-only). La band annuncia la
      versione **spontaneamente**: nessun comando di scrittura inviato.
- [x] Parametri reali rilevati → [docs/device-ota-params.md](docs/device-ota-params.md):
      `projId=0x2a4b boot=4 stack=2 app=0x6900 appStack=0 appBoot=0`. Protocollo Maxscend
      confermato combaciante.
- [ ] (Opzionale, più avanti) riprodurre l'intero handshake ri-caricando un'immagine **identica**
      a quella presente: l'OTA più sicuro possibile. Rinviato: non abbiamo l'immagine ufficiale.

### Fase 3 — Capire la mappa di memoria  ✅ (in buona parte; dettagli in docs/firmware-build.md)
- [x] Studiato `app-OTA` dell'SDK MS1793 → [docs/firmware-build.md](docs/firmware-build.md):
      SoC MM32 Cortex-M0, flash a `0x08000000`, schema **doppio banco** (Bank A app @`0x08001000`,
      app linkata a `0x08001010`; Bank B staging OTA), boot copia B→A solo se CRC valido.
- [x] Scoperta chiave: **CRC errato → immagine rifiutata, firmware attuale intatto** (se vale lo
      staging anche sul nostro bootloader). Un upload con CRC errato sarebbe quindi sicuro.
- [ ] **Incognite ancora aperte** (servirebbe un'immagine ufficiale): indirizzo base app esatto
      del nostro bootloader (candidato `0x08001010`) e **variante CRC32**. Confermare che il
      nostro bootloader usa davvero lo staging (altrimenti anche un CRC errato è rischioso).

### Fase 4 — Primo firmware custom
- [x] 4.1 Toolchain `arm-none-eabi-gcc` OK; build GCC in `firmware/` compila un .bin Cortex-M0 valido (vector table @0x08001010) e lo incapsula in immagine OTA. Segnaposto, non flashato.
- [x] 4.2 `tools/mkimage.py`: header 16B (`projId=0x2a4b boot=4 stack=2 app=0x6900`) + CRC32
      (varianti candidate). Offline, nessun dispositivo.
- [ ] 4.3 Dry-run OTA **sicuro**: upload con CRC volutamente errato, leggere l'esito
      (`value[1]==3`) — **solo** dopo aver confermato lo staging. Prova il flusso end-to-end
      senza sostituire il firmware.
- [ ] 4.4 Primo firmware reale: app minima all'indirizzo giusto, CRC corretto, caricata solo con
      rete di sicurezza (immagine di ripristino o secondo dispositivo).

### Fase 5 — Costruzione incrementale del nostro firmware
- [ ] Portare via via le funzioni (display, sensori, passi, notifiche) sul nostro codice.
- [ ] **Abilitare il sensore di battito (PPG)**: lo stock non lo espone ma l'hardware c'è —
      identificare l'AFE ottico e il suo bus (probabile I2C), leggere i campioni, calcolare l'HR.
- [ ] Eventualmente usare il servizio `ffe0` libero per un nostro protocollo di controllo.

---

## Decisioni aperte
- Un solo braccialetto o due? (secondo = cavia, riduce molto il rischio di Fase 4).
- Fin dove spingersi sul rischio brick con un unico dispositivo.

## Ripresa — prossima sessione (per domani)

**Dove siamo:** Fasi 0-3 fatte; 4.1 (toolchain+build) e 4.2 (mkimage) fatte. Toolchain
`arm-none-eabi-gcc` installata e funzionante. La build in `firmware/` produce un `.bin`
Cortex-M0 valido e lo incapsula in immagine OTA. `src/main.c` è un segnaposto (niente BLE).

**Prossimo passo (sicuro, senza flash):** linkare lo stack BLE del SDK e scrivere una prima app
reale che fa advertising, verificando che compili e linki pulito. In pratica:
1. Copiare/collegare in `firmware/` quel che serve dal SDK (scratchpad: `…/sdk/MS1793-SDK`):
   `Src/lib/mg_BLE_lib_m0.lib` (ELF Cortex-M0, GCC-linkabile), `Src/inc/mg_api.h`, i file BSP e
   gli header MM32x031. **Nota:** l'SDK è nella scratchpad (non versionato); valutare se
   ricopiarlo in `firmware/vendor/` o riclonare `macrogiga/MS1793-SDK`.
2. Partire dall'esempio più semplice che usa `ble_run_interrupt_start` (es. `app-hid-shutter`)
   come modello di init (clock, `BSP_Init`, `radio_initBle`, `ble_run...`).
3. Linker: il `.sct` Keil mappa flash `0x08000000` size `0x8000`, RAM `0x20000000` size `0x1000`.
   Adattare `ld/app.ld` di conseguenza quando si linka davvero contro la lib.
4. Obiettivo della sessione: un `firmware/build/app.bin` che linka con la radio BLE. **Ancora
   nessun flash.**

**Nodi aperti prima di flashare davvero:** (a) indirizzo base app esatto + variante CRC32 del
nostro bootloader — servirebbe un'immagine ufficiale; (b) confermare lo staging del bootloader;
(c) rete di sicurezza: immagine di ripristino o secondo braccialetto. Vedi "Decisioni aperte".

## Log
- 2026-10-20: setup strumenti, reverse OTA, identificato chip, scritti PLAN e docs. Avvio Fase 1.
- 2026-10-20: Fase 1 bloccata — credenziali OSS dell'APK revocate (403 AccessDenied in V1 e V4).
  Nessun firmware nell'APK; ricerca GitHub: dump ID115 solo per il chip Nordic, nessuno per il
  nostro Maxscend. Gli SDK Macrogiga restano la base.
- 2026-10-20: Fase 2 — `ota-probe` (sola lettura): la band annuncia `projId=0x2a4b boot=4 stack=2
  app=0x6900`. Protocollo Maxscend confermato.
- 2026-10-20: Fase 3 — mappa di memoria dal SDK (doppio banco, app @`0x08001010`); CRC errato =
  immagine rifiutata (se c'è staging). Incognite: base app esatta, variante CRC32, staging.
- 2026-10-20: Fase 4.1/4.2 — `tools/mkimage.py` (immagine OTA) + build GCC in `firmware/` che
  compila un `.bin` Cortex-M0 valido. Toolchain validata end-to-end. Nulla flashato. Push su
  `origin/main`. Pausa: si riprende dal linkaggio dello stack BLE (vedi "Ripresa").
- 2026-10-21: correzione — il braccialetto **ha un sensore di battito ottico (PPG)**; i flag
  stock non lo espongono ma l'hardware c'è (era stato attribuito per errore all'altro device).
  Propagato in README, docs/firmware-build.md, device table. Verifiche live: `info` e `battery`
  OK (batteria ora 100%, il vecchio "0% charging" era inaffidabile); `ota-probe` fallito per
  segnale debole (RSSI ~-93 dBm) — avvicinare il device per le notifiche. Nulla flashato.
