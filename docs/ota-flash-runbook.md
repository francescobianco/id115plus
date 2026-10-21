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

## Variante CRC32 (header byte 12..15)

`tools/mkimage.py` genera l'immagine con una variante scelta (`zlib` default; anche `bzip2`,
`mpeg2`, `posix`, o `wrong`). Non sappiamo quale accetti il bootloader. Strategia: il `--dry-run`
userà comunque un CRC corrotto (rifiuto atteso); per il `--commit` proveremo la variante più
probabile (`zlib`) e, se il device la rifiuta **senza** brickare (grazie allo staging), si prova
la successiva. Per questo lo staging è il prerequisito che rende iterabile la ricerca della
variante giusta.

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

## Stato attuale dei prerequisiti (2026-10-21)

- Tool `ota-flash`: **pronto** (handshake/dry-run/commit), sintassi e Python validati a secco.
- Immagine: **costruibile** (`make image`), ma per architettura **non confermata**.
- Identificazione SoC Maxscend: **mancante** (blocco principale per il commit).
- Staging bootloader: **da testare** col dry-run.
- Rete di sicurezza: **assente** (seconda unità in valutazione).
