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

### Fase 1 — Procurarsi l'immagine ufficiale  ⏳ (in corso)
- [ ] Elencare il bucket `mcube-ota` (GET firmato, `?max-keys=500`).
- [ ] Scaricare l'immagine del nostro modello (`_60_*_00_86.bin`), inclusa quella in uso.
- [ ] Salvarla in `firmware/` come riferimento e **copia di ripristino**.
- [ ] Verificarne l'header (projId/boot/stack/app/codeSize/crc32) contro lo spec.
- [ ] Capire quale variante CRC32 dà i 4 byte dell'header (riprodurre il CRC dell'immagine
      reale): ci serve per firmare le nostre immagini.

Strumento: `tools/oss.py` (firma OSS, list/get). Le credenziali vengono dall'APK; non vanno
committate in chiaro se il repo diventa pubblico — per ora stanno nel tool con una nota.

### Fase 2 — Osservare l'OTA dal dispositivo (sola lettura)
- [ ] Abilitare le notifiche su `fd02` e leggere la versione che la band annuncia, **senza
      inviare comandi di scrittura**. Conferma che il protocollo combacia e ci dà i campi
      boot/stack/app reali del dispositivo.
- [ ] (Opzionale, più avanti) riprodurre l'intero handshake ri-caricando l'immagine
      **ufficiale identica** a quella già presente: è l'OTA più sicuro possibile (stessa
      immagine), e prova che possiamo pilotare il flusso end-to-end.

### Fase 3 — Capire la mappa di memoria
- [ ] Studiare `app-OTA` dell'SDK MS1793: dove stanno bootloader, stack, app; indirizzi,
      dimensioni, linker script.
- [ ] Disassemblare l'immagine ufficiale (arm-none-eabi-objdump / Ghidra) per confermare
      vettori di reset, base dell'app, e se boot+stack sono separati dall'app.
- [ ] Decidere la partizione *app* come unico bersaglio di scrittura (bootloader intatto).

### Fase 4 — Primo firmware custom minimo
- [ ] Costruire con l'SDK un'app minima che faccia una cosa osservabile e sicura (es. far
      vibrare il motore, o accendere il display), con lo stesso projId/boot/stack dell'originale.
- [ ] Generare l'header 16 byte + CRC32 corretto (tool nostro).
- [ ] Caricarla via il flusso di Fase 2 **solo dopo** aver verificato il ripristino.
- [ ] Verificare l'avvio; se fallisce, ripristinare l'immagine ufficiale.

### Fase 5 — Costruzione incrementale del nostro firmware
- [ ] Portare via via le funzioni (display, sensori, passi, notifiche) sul nostro codice.
- [ ] Eventualmente usare il servizio `ffe0` libero per un nostro protocollo di controllo.

---

## Decisioni aperte
- Un solo braccialetto o due? (secondo = cavia, riduce molto il rischio di Fase 4).
- Fin dove spingersi sul rischio brick con un unico dispositivo.

## Log
- 2026-10-20: setup strumenti, reverse OTA, identificato chip, scritti PLAN e docs. Avvio Fase 1.
