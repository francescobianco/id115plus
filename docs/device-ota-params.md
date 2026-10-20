# Parametri OTA rilevati dal dispositivo (Fase 2, sola lettura)

Rilevati il 2026-10-20 con `./id115plus ota-probe` (solo abilitazione notifiche su `fd02`,
nessuna scrittura di comandi OTA). Il braccialetto annuncia la propria versione **spontaneamente**
appena si abilitano le notifiche: non serve inviare alcun comando per leggerla.

## Notifica grezza

```
fd02 <- 10 01 4b 2a 04 02 00 69 00 00
```

Interpretazione (cfr. `docs/ota-protocol.md` §2.1/2.4; l'app analizza da `value[1]==1`,
byte `[2..9]`, con i campi multibyte in little-endian):

| Campo | Byte | Valore |
|---|---|---|
| prefisso | `value[0]` | `0x10` (16; probabile lunghezza/tipo, l'app lo ignora) |
| tipo | `value[1]` | `0x01` = annuncio versione |
| `projId` | `[2..3]` LE | **`0x2a4b`** |
| `boot` | `[4]` | **`4`** |
| `stack` | `[5]` | **`2`** |
| `app` | `[6..7]` LE | **`0x6900`** |
| `appStack` | `[8]` | `0` |
| `appBoot` | `[9]` | `0` |

Versione firmware da `cc02` (contesto): `60.69.00.86`.

## Conseguenze per il firmware custom

L'header a 16 byte della nostra immagine (cfr. `docs/ota-protocol.md` §2.1) deve superare il
controllo di compatibilità `chkMxdOta()` lato app **e** quello del bootloader lato dispositivo:

- `projId` dell'immagine = **`0x2a4b`** (atteso identico).
- compatibilità boot/stack: `chkMxdBoot` vuole `file.boot==0` **oppure** `file.boot != dev.boot(4)`;
  `chkMxdStack` vuole `file.stack==0` **oppure** `file.stack != dev.stack(2)`. (Logica "diverso",
  presumibilmente per decidere se aggiornare anche boot/stack: da capire bene prima di scrivere.)
- `chkMxdApp`: `file.app!=0` **e** (`file.app==dev.app(0x6900)` **oppure**
  (`file.appStack==dev.stack(2)` **e** `file.appBoot==dev.boot(4)`)).

Questi sono i vincoli che l'immagine dovrà rispettare. Il significato esatto di boot/stack/app
come indirizzi/partizioni va confermato sulla mappa di memoria dell'SDK (Fase 3).

## Verifica del protocollo

- `fd01` e `fd02` presenti; servizio `fd00` presente (è il servizio, non una caratteristica).
- Il dispositivo parla il protocollo OTA Maxscend esattamente come descritto nell'APK.
- L'annuncio versione è spontaneo: la lettura è completamente passiva e sicura.
