# OTA flash runbook — MSLM707 (Maxscend, fd00/fd01/fd02)

Tutto pronto per tentare l'upload del primo firmware custom. **Niente parte da solo**: i comandi
che scrivono sul device richiedono `--yes` e vanno lanciati a mano, su tua indicazione. Questo
documento è l'analisi completa fatta in anticipo: cosa succede, cosa osservare, quando fermarsi.

Strumento: `./id115plus ota-flash <image> [--dry-run|--commit] [--yes]` (vedi `--help`).
Protocollo: [ota-protocol.md](ota-protocol.md). Build immagine: `cd firmware && make fetch && make image`
→ `firmware/build/app-ota.bin` (header 16B + codice).

---

## ⚠️ Avvertenza di fondo (leggere prima)

1. **Rischio chip sbagliato.** Il nostro `app.bin` è compilato per MM32/ARM (SDK Macrogiga
   MS1793), ma l'OTA del device è **Maxscend** e il SoC reale **non è confermato** (vedi
   [firmware-build.md](firmware-build.md)). Se il chip non è quello, un `--commit` carica codice
   che non gira → **brick** (anche con CRC corretto). Finché il SoC non è identificato, il
   `--commit` del nostro firmware è un salto nel buio.
2. **Nessuna rete di sicurezza.** Non abbiamo immagine ufficiale di ripristino (OSS revocato) né
   SWD (non si apre il device). Un brick con un solo braccialetto è **permanente**.
3. Perciò l'ordine sensato è: **handshake → dry-run → (solo con cavia o dopo aver identificato il
   chip) commit**. Il `--commit` sul device unico è la scelta che il proprietario fa consapevole.

---

## I tre modi e cosa scrivono davvero

| modo | fd02 cmd01 | fd02 cmd02 | fd01 dati | fd02 cmd03 | scrive in flash? | può brickare? |
|---|---|---|---|---|---|---|
| handshake (default) | sì | sì | **no** | no | **no** | **no** |
| `--dry-run --yes` | sì | sì | sì | sì, **crc32 errato** | sì (staging) | solo se NON c'è staging |
| `--commit --yes` | sì | sì | sì | sì, crc32 valido | sì | **sì** |

- `cmd01` = negoziazione versione, `cmd02` = codeSize: **non toccano la flash**. Per questo
  l'handshake è sicuro al 100%.
- I dati su `fd01` iniziano a scrivere nella flash (staging o app, dipende dal bootloader).

---

## Pre-flight checklist (prima di ogni tentativo)

1. **Braccialetto vicino all'adattatore** (il segnale è debole: l'OTA non regge da lontano).
2. **Batteria ≥ 50%**: `./id115plus battery` (l'app ufficiale rifiuta sotto il 50%).
3. **Baseline**: `./id115plus info` → annotare `firmware` e `flags`; `./id115plus ota-probe 10`
   → confermare che annuncia `projId=0x2a4b boot=4 stack=2 app=0x6900`. Serve per riconoscere
   "device ancora vivo e invariato" dopo il test.
4. **Immagine pronta**: `cd firmware && make image` → `firmware/build/app-ota.bin`.
5. **Link stabile**: `./id115plus status` → "controller: link up"; se no, `./id115plus keepalive`
   in un altro terminale finché regge.

---

## Passo 1 — handshake (sicuro, da fare per primo)

```
./id115plus ota-flash firmware/build/app-ota.bin
```
Invia solo version+cmd01+cmd02, **nessun byte di codice**.

**Cosa osservare:**
- `<- fd02 .. 01 ..` → **device VERSION**: deve combaciare con la baseline (projId 0x2a4b…).
- dopo il nostro `cmd01`+`cmd02`: se arriva `<- fd02 .. 02 55` = **READY 0x55** → il device
  accetta la nostra versione ed è pronto a ricevere. (Potrebbe non arrivare finché non partono i
  dati: in handshake non partono, quindi l'assenza di 0x55 qui **non** è un fallimento.)
- se il device si disconnette subito dopo cmd01 → versione **rifiutata** (projId/boot/stack non
  compatibili): fermarsi, il nostro header va corretto.

Esito atteso: nessuna scrittura in flash; device identico alla baseline. Zero rischio.

---

## Passo 2 — dry-run a CRC errato (test dello staging)

```
./id115plus ota-flash firmware/build/app-ota.bin --dry-run --yes
```
Invia tutto il codice ma con `cmd03` a **crc32 volutamente sbagliato**. Serve a scoprire **se il
bootloader fa staging**:

- Streaming completo dei dati su `fd01` (progress ogni ~2000 byte).
- `-> fd02 cmd03 crc32 ..` con il CRC corrotto.
- `<- fd02 .. 03 ..` = **CRC RESULT** (byte grezzi; l'app ufficiale lo ignora, quindi il
  significato esatto va dedotto qui).

**Verifica dopo:** riconnettere e `./id115plus info` + `ota-probe`.
- Se il device **risponde ancora e la versione è invariata** → il bootloader **ha rifiutato**
  l'immagine a CRC errato e **fa staging**: ottima notizia, il `--commit` con CRC giusto diventa
  molto meno rischioso.
- Se il device **non risponde più / non si avvia** → **NON c'è staging**: scrivere dati = scrivere
  l'app in esecuzione. In quel caso **il commit su device unico è da escludere** senza cavia.

> Il dry-run è "sicuro" **solo se** lo staging esiste — che è proprio ciò che sta testando. È il
> test meno rischioso possibile, ma non a rischio zero. Da fare con consapevolezza.

---

## Passo 3 — commit reale (solo su tuo via esplicito)

```
./id115plus ota-flash firmware/build/app-ota.bin --commit --yes
```
Invia codice + `cmd03` con CRC valido; il device verifica e **si riavvia** sulla nostra immagine.

**Precondizioni che riducono il brick (idealmente tutte):**
- [ ] SoC reale identificato e immagine compilata per quel chip (oggi **non** soddisfatto).
- [ ] dry-run ha dimostrato lo staging (rifiuto a CRC errato, device vivo).
- [ ] variante CRC32 giusta nell'header (vedi sotto).
- [ ] rete di sicurezza: **secondo braccialetto** come cavia, o immagine di ripristino.

**Cosa osservare:** streaming completo → `cmd03` → `<- fd02 .. 03 ..` → il device si riavvia.
Poi `./id115plus info`: se risponde con una versione nostra/attesa = successo; se sparisce = brick.

---

## Variante CRC (header byte 12..15) — IDENTIFICATA 2026-10-21

**È CRC-16/XMODEM** (poly 0x1021, init 0x0000), non un CRC-32. Scoperto offline dal bootloader
del SDK e dal tool ufficiale `mg_ota_head_hex.exe` (vedi docs/firmware-build.md), e coerente col
rifiuto del commit a CRC-32/zlib. `tools/mkimage.py` ora usa `xmodem` di default (16 bit nei byte
12..13 LE, 14..15 = 0). Il `--dry-run` usa comunque un CRC corrotto (rifiuto atteso e sicuro).

Resta da provare "accettato" sul device: con il CRC giusto il device **committerebbe** il nostro
codice → con architettura non confermata è rischio brick. Quindi quel test va su **cavia** o dopo
aver identificato il SoC. (Il CRC è stato dedotto dalla famiglia MS1793; il nostro è Maxscend:
stessa toolchain OTA, quasi certo stesso CRC.)

---

## Abort / recupero

- **Durante lo streaming**: `Ctrl+C`. Se non è ancora partito `cmd03`, il device non ha
  committato nulla (con staging). Riconnettere e verificare con `info`.
- **Link perso**: l'immagine non è stata completata; senza `cmd03` nessun commit.
- **Brick**: senza SWD e senza immagine ufficiale non è recuperabile via BLE. È il motivo per cui
  il `--commit` su device unico va evitato finché non c'è la cavia.

## Risultati osservati sul device (2026-10-21)

- **Handshake: OK.** Il device annuncia `projId=0x2a4b boot=4 stack=2 app=0x6900 appStack=0
  appBoot=0` (= header della nostra immagine) e accetta `cmd01`+`cmd02` senza disconnettersi.
  Compatibilità versione confermata. Device invariato dopo.
- **Entrare in modalità upgrade NON è distruttivo (scoperta chiave).** Durante un tentativo di
  dry-run interrotto su `StartNotify` (link debole, nessun dato inviato), il braccialetto ha
  mostrato **"Upgrade"**, è andato in timeout e **si è riavviato da solo sul firmware originale
  intatto** (`60.69.00.86`, verificato). → il bootloader **non cancella l'app** finché non ha
  un'immagine valida, e fa rollback in assenza di dati. Un dry-run interrotto è quindi
  recuperabile. (Il rifiuto a CRC errato con stream completo resta ancora da verificare.)
- **Link debole = ostacolo pratico.** A -84 dBm `StartNotify` va in timeout. Il tool ora ritenta
  `StartNotify` (6×), ma per lo streaming vero **il braccialetto va attaccato all'adattatore**.
- **✅ STAGING CONFERMATO (2026-10-21).** Dry-run completo: inviati **tutti i 12966 byte** di
  codice + `cmd03` con **CRC32 volutamente errato** (`db909fc4`→`24909fc4`). Il device ha
  **rifiutato** l'immagine e si è **riavviato sul firmware originale `60.69.00.86` intatto**
  (verificato). → Il bootloader fa staging: riceve l'intera immagine, verifica il CRC32, e se non
  torna **non tocca l'app in esecuzione**. Un'immagine con CRC errato/incompatibile **non bricka**.
  (Nessun notify di "CRC RESULT" osservato — perso nel rumore RF o reboot immediato; la prova è
  comportamentale: device vivo e invariato.)

  **Rischio residuo per il --commit:** lo staging protegge dai CRC errati, **non** da un'immagine
  con CRC *corretto* ma codice che non gira (es. architettura sbagliata: la nostra è MM32/ARM, SoC
  non confermato). In quel caso il device potrebbe accettare e riavviarsi su codice morto → brick,
  salvo un watchdog/rollback secondario che non conosciamo. Quindi: **CRC errato = sicuro
  (dimostrato); commit di immagine per il chip giusto = ancora da de-rischiare** (identificare il
  SoC; o fare il primo commit sulla cavia).

### Commit reale tentato (2026-10-21) — RIFIUTATO, device intatto

Stream completo (12966 B) + `READY 0x55` dal device + `cmd03` con CRC32 **valido zlib**
(`db909fc4`). Esito: il device ha **rifiutato** e gira ancora il firmware originale
(`./id115plus info` → `MSLM707 60.69.00.86`, invariato; se girasse il nostro codice, `info`
fallirebbe perché la nostra app non implementa cc00/cc02, e il nome sarebbe `ID115DIY`).

Imparato:
- **Anche un commit di immagine non combaciante è sicuro** (staging + verifica CRC confermati
  pure sul path reale, non solo col CRC volutamente errato).
- **La variante CRC32 del bootloader NON è `zlib`** (CRC zlib corretto → comunque rifiutato).
  Da provare le altre varianti (`bzip2`/`mpeg2`/`posix` in `tools/mkimage.py`, o un algoritmo
  ancora diverso). Ogni variante **sbagliata** è un rifiuto sicuro; la variante **giusta**
  committerebbe il nostro codice (e lì torna il rischio architettura: codice MM32/ARM su SoC non
  confermato → possibile brick).

> Nota: trovare la variante CRC giusta è utile ma è anche il momento in cui il device accetterebbe
> davvero il codice. Finché l'architettura non è confermata, la variante giusta trovata con il
> NOSTRO codice = rischio brick. Ideale: trovarla ricaricando l'**immagine ufficiale** del device
> (che non abbiamo) o usando la **cavia**.

### Commit CRC-16/XMODEM tentato (2026-10-21) — anch'esso RIFIUTATO, device intatto

Stream completo + `cmd03` con CRC-16/XMODEM corretto (`0xf004` → `04 f0 00 00`). Esito: **rifiutato**,
device ancora `MSLM707 60.69.00.86`. Quindi anche la variante CRC che l'analisi offline indicava
non è stata accettata. Ipotesi (non risolte senza immagine di riferimento):
- un dettaglio del CRC ancora off: **range/padding** (il tool ufficiale padda il codice e mette
  `codeSize`=paddato → forse il device vuole codeSize allineato e CRC sul paddato), init `0xFFFF`
  (ccitt-false) invece di `0x0000`, o posizione dei byte nel campo da 4.
- il device Maxscend differisce dalla famiglia MS1793 da cui è dedotto il CRC.
- `READY 0x55` **non ricevuto** in questo tentativo (nel commit zlib sì): o notifica persa (RF), o
  il device non è entrato pulito in stato "ricezione". `fd01` è solo *write-without-response*.
- Nota: a livello BLE i pacchetti write-without-response sono comunque consegnati con ritrasmissione
  di link-layer finché la connessione regge, quindi il rifiuto è verosimilmente un **mismatch del
  CRC/range**, non perdita di dati.

Terzo commit (CRC-16/XMODEM su codice **paddato a 1024**, `codeSize=13312`, crc `0xf597`): transfer
**pulito** (`READY 0x55` ricevuto) ma **rifiutato**, device ancora `MSLM707 60.69.00.86`.

**Bilancio: 5 tentativi (2 dry-run + 3 commit: zlib, xmodem, xmodem-pad1024), sempre rifiutati,
device sempre intatto.** Poiché l'ultimo transfer era pulito, non è un problema di link: **il CRC
che calcoliamo non combacia** con quello del device, con tutte le varianti provate. I gradi di
libertà residui (init 0x0000 vs 0xFFFF, posizione dei byte nel campo da 4, CRC incluso l'header,
riflessione, dimensione/fill del padding, range esatto) sono troppi per un brute-force alla cieca
con odds ragionevoli — ogni tentativo è un ciclo di ~2 min su link instabile.

**Conclusione:** il trial alla cieca sul device unico è esaurito. Per sbloccare serve **ground
truth**: (1) un'**immagine ufficiale** `_60_XX_00_86.bin` (si calcolano i CRC candidati sul suo
codice/paddato e si trova quale combacia col campo header → algoritmo+range esatti), oppure (2) la
**cavia** (aprirla: marking del chip → SoC/datasheet/SDK/flash-map e architettura; e/o dump SWD =
immagine di riferimento). Nota positiva: la protezione d'integrità del bootloader è solidissima
(5/5 rifiuti puliti, mai un brick).

## Stato attuale dei prerequisiti (2026-10-21)

- Tool `ota-flash`: **pronto** (handshake/dry-run/commit), sintassi e Python validati a secco.
- Immagine: **costruibile** (`make image`), ma per architettura **non confermata**.
- Identificazione SoC Maxscend: **mancante** (blocco principale per il commit).
- Staging bootloader: **da testare** col dry-run.
- Rete di sicurezza: **assente** (seconda unità in valutazione).
