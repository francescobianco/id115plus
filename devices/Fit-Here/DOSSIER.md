# Fit-Here: dossier (aggiornato al 2026-11-09)

Riferimento tecnico completo: [`README.md`](README.md). Da dove ripartire: [`TODO.md`](TODO.md).

## In breve

Il braccialetto esegue **firmware nostro** caricato via BLE, senza aprirlo. Lo stock non c'è più e
non si può ripristinare: della flash originale resta il dump, senza la parte SRAM dello stock.

| | |
|---|---|
| Sul dispositivo ora | demo `FH-DEMO`, `C0:00:A1:B1:02:64` |
| Updater | `PPlusOTA` V3.0.7, `C0:00:A1:B1:02:62`, intatto |
| App originale (MAC) | `C0:00:A1:B1:02:61`, cancellata |
| Chip | PhyPlus PHY62xx, 512 KB (la seconda metà del dump è diversa dalla prima) |
| Prova di funzionamento | 4 vibrazioni da 500 ms su comando BLE, sentite il 2026-11-09 |

## Cosa è dimostrato

- La catena completa: build Docker, OTA con `phy_flash.py`, avvio, connessione GATT, comando, effetto
  fisico.
- Vibro su **`P23`**, attivo alto. Sull'LP715 quel pin è il controllo carica: i pin dell'LP715 non
  valgono qui.
- Dumper a beacon senza host BLE: tutta la flash letta con ogni blocco confermato due volte.

## Cosa non è dimostrato

- Il comando `04` della demo (ritorno all'updater).
- Il watchdog e la sopravvivenza del registro `0x4000f034` a un suo reset.
- La ricarica sotto il nostro firmware. Se non funziona, a batteria scarica servirà aprirlo.
- Che i pin senza effetto siano davvero inutili: si è guardato solo vibrazione o luce.

## Stock: cosa è successo

Il primo `01` all'updater ha svuotato il banco app `0x11000`–`0x1ffff`, non solo la tabella a
`0x3000`. Gli SDK più recenti cancellano solo la tabella, ma questa è una build più vecchia.
La conclusione è dedotta dal dump: banco vuoto, e nessuna tabella di salto stock in tutta la flash.

Nel dump restano codice XIP (`0x20000`–`0x39aff`), risorse, probabile file system, updater e MAC.

Dump verificato: `dump/flash.final.bin`, fuori da git,
SHA-256 `dc30a2e7619591e8bb42a365af6c3cc7f40a24f2f518adb669c0a8452ef4794f`.
Sul dispositivo la demo ha poi sovrascritto `0x20000`–`0x26fff`: **quel file è l'unica copia**.

## Comportamento dell'updater V3.0.7

Differenze dal sorgente SDK, verificate sul dispositivo:

- La partition-info deve essere di 16 byte, con CRC a 2 byte. Quella da 18 viene ignorata in silenzio.
- La validazione accetta più indirizzi di quanti ne scriva: XIP a `0x1101f000` passa la
  partition-info e poi, dopo i dati, risponde `10` (`INVALID_ADDR`). XIP a `0x11020000` funziona.
- `01` è lento e può far cadere il link: su un collegamento debole ripetere.

## Protocollo stock

`18D0` / `2D01` / `2D00` è il protocollo **Lefun**: comandi `0xAB`, risposte `0x5A`, CRC-8/MAXIM
(verificato sul frame `5a 05 01 01 6c`). Serve solo per studiare lo stock, che non gira più.

## Banco di lavoro

- **Dongle**: usare il CSR `00:1A:7D:DA:71:13` (-60 dBm, riceve tutti i frame). Il Barrot
  `04:7F:0E:64:D7:BF` arrivava a -95 dBm, ignora il filtro duplicati e si blocca.
- **`btedge` e `wrish`** (unità `systemctl --user`) disturbano l'adattatore: con loro attivi era
  spento e riacceso ogni 23 s sul vecchio dongle. Fermarli durante OTA e dump, poi riavviarli.
- **Build**: `firmware/build.sh [demo]`, SDK e-lab a commit e immagine Docker fissati.
- `tools/fh_dump_rx.py` basta con un buon dongle. `fh_dump_hci.py` (sudo) serve solo con quello scadente.

## Lezioni

- Il sorgente di un SDK più recente non descrive una build V3.0.7: prima di un comando irreversibile
  va provato, o considerato peggiore di quanto dica il sorgente.
- Quando la ricezione radio sembra un problema di software, cambiare prima il dongle.
- Un frame di advertising riscritto mentre parte può uscire misto: il dumper va corretto (una copia
  fuori dal buffer in trasmissione), e il ricevitore usa il voto a maggioranza.

## Fonti

- [FitPro-LP715-PHY6222](https://github.com/e-labInnovations/FitPro-LP715-PHY6222): SDK, build, OTA
- [phy6222_smartwatch](https://github.com/amir1387aht/phy6222_smartwatch)
- [phy6222-smartwatch-os](https://github.com/salomanov/phy6222-smartwatch-os): errori ed esperienze
- [FT100 reversing](https://github.com/0xless/FT100_fitness_bracelet_reversing) e
  [xDrip, Lefun](https://github.com/NightscoutFoundation/xDrip): protocollo stock
