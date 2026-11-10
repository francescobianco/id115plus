# Fit-Here: dossier (aggiornato al 2026-11-10)

Riferimento tecnico completo: [`README.md`](README.md). Da dove ripartire: [`TODO.md`](TODO.md) e, per
MorseOS, [`TODO_MORSEOS.md`](TODO_MORSEOS.md).

## In breve

Il braccialetto esegue **firmware nostro** caricato via BLE, senza aprirlo. Lo stock non c'è più e
non si può ripristinare: della flash originale resta il dump, senza la parte SRAM dello stock.

| | |
|---|---|
| Sul dispositivo ora | demo `FH-DEMO`, `C0:00:A1:B1:02:64`, con disegno via BLE ed emergenza col touch |
| Updater | `PPlusOTA` V3.0.7, `C0:00:A1:B1:02:62`, intatto |
| App originale (MAC) | `C0:00:A1:B1:02:61`, cancellata |
| Chip | PhyPlus PHY62xx, 512 KB (la seconda metà del dump è diversa dalla prima) |
| Prova di funzionamento | disegni sul display inviati via BLE, visti il 2026-11-10 |
| Batteria | 4,14 V sul caricatore il 2026-11-10 alle 10:03 |
| Prossimo passo | fase 5 di `TODO_MORSEOS.md`: la prima parte di MorseOS |

Pin provati sul dispositivo:

| Pin | Funzione |
|---|---|
| `P01`, `P31`, `P25`, `P00`, `P02` | display: RST, SCK, MOSI, DC, CS (tenuto basso) |
| `P34` | luce dello schermo, attivo alto |
| `P03` | zona touch, attiva alta, guidata da un chip: non pilotare |
| `P23` | vibro, attivo alto |
| `P14` | batteria, ADC, tensione = pin × 5,5454 |
| `P15` | caricatore, 1 = presente, con pull-down |

## Cosa è dimostrato

- La catena completa: build Docker, OTA con `phy_flash.py`, avvio, connessione GATT, comando, effetto
  fisico.
- Vibro su **`P23`**, attivo alto. Sull'LP715 quel pin è il controllo carica: i pin dell'LP715 non
  valgono qui.
- Dumper a beacon senza host BLE: tutta la flash letta con ogni blocco confermato due volte.
- Il comando `04` della demo riporta a `PPlusOTA`, e `04 01` dall'updater torna alla demo.
- Il watchdog: dopo il comando di blocco `7f a5` il braccialetto ricompare da solo come `PPlusOTA`
  in circa 9 s, quindi il registro `0x4000f034` sopravvive al reset.
- Il display: 80×160 a colonna 26, riga 1 della memoria, inversione accesa, BGR, gamma `e0`/`e1` accettata.
  Controller non identificato: si comporta come un ST7735S, ma non si può rileggere.
- Un'eccezione del processore (`7f 5a`) porta a `PPlusOTA` in circa 8 s.
- La ricarica col nostro firmware: la tensione sale sul caricatore e `P15` lo segnala, su due cicli di
  stacco e riattacco.
- L'emergenza col touch: 10 s premuto, rosso, rilascio, 3 tocchi brevi portano a `PPlusOTA` senza
  Bluetooth. Anche l'annullamento funziona.
- OTA e collegamento col Bluetooth di bordo del portatile (Intel, RSSI circa -65 dBm): immagine
  completa in 38 s, e 53 letture su 53 in 2 minuti senza cadute.

## Cosa non è dimostrato

- La carica completa sotto il nostro firmware: la tensione sale sul caricatore, ma non è stata seguita fino al 100 %.
- L'emergenza attiva da sola all'avvio: è nell'ultima flash ma non è stata riprovata. Provata solo
  attivandola col comando `25 01`.
- La guardia dell'emergenza contro un tasto premuto per più di 30 s.
- Il caso reale di Bluetooth morto a ciclo vivo: l'emergenza è pensata per quello, ma il guasto non è stato simulato.
- Il LED del powerbank si spegne o lampeggia a batteria quasi piena, mentre `P15` resta a 1 e la tensione
  sale. Probabile assorbimento sotto la soglia del powerbank, non verificato.
- Un blocco prima che `app_init` avvii il watchdog, o un'immagine che non parte affatto.
- Che i pin senza effetto siano davvero inutili: si è guardato solo vibrazione o luce.

## Stock: cosa è successo

Il primo `01` all'updater ha svuotato il banco app `0x11000`–`0x1ffff`, non solo la tabella a
`0x3000`. Gli SDK più recenti cancellano solo la tabella, ma questa è una build più vecchia.
La conclusione è dedotta dal dump: banco vuoto, e nessuna tabella di salto stock in tutta la flash.

Nel dump restano codice XIP (`0x20000`–`0x39aff`), risorse, probabile file system, updater e MAC.

Dump verificato: `dump/flash.final.bin`, fuori da git,
SHA-256 `dc30a2e7619591e8bb42a365af6c3cc7f40a24f2f518adb669c0a8452ef4794f`.
Sul dispositivo la demo ha poi sovrascritto `0x20000`–`0x27fff`: **quel file è l'unica copia**.

## Ripartire da un altro PC

Il dump è in git solo cifrato: `dump-2026-11-09.tar.gz.gpg` (AES256, password in possesso
dell'utente, non nel repo e non in chat). `dump/` è ignorata da git e sul nuovo PC non esiste.

```shell
devices/Fit-Here/tools/restore_dump.sh   # gpg chiede la password, lo script verifica l'hash
```

Servono anche `gpg`, Docker (`firmware/build.sh` scarica da solo l'SDK), `bluez`, `python3-dbus`,
`python3-gi` e il braccialetto. Il portatile usa il Bluetooth di bordo: prima di
scrivere controllare il segnale (`tools/scan.py`, RSSI verso -60 dBm a braccialetto vicino) e che
una connessione alla demo regga. BlueZ del nuovo PC non conosce i dispositivi: fare
una scansione con `tools/scan.py` prima di `phy_ota.py` o `phy_flash.py`.

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
- **Dopo `04 01` all'updater** serve `bluetoothctl disconnect C0:00:A1:B1:02:62`: l'updater riparte solo alla
  disconnessione e, finché BlueZ resta collegato, il braccialetto sembra sparito da ogni scansione.
- **Il segnale conta**: a -82 dBm la connessione cade subito, a -65 dBm la OTA riesce. La connessione alla
  demo fallisce spesso al primo colpo: una scansione subito prima, e ripetere.
- **Scrittura**: `--confine 0x11000:0x2c000`. L'immagine arriva oggi a `0x27fff`.
- **Strumenti**: `tools/fh_draw.py` (disegni), `tools/fh_power.py` (batteria e caricatore),
  `tools/fh_keyfind.py` (cambi di livello sui pin candidati).
- `tools/fh_dump_rx.py` basta con un buon dongle. `fh_dump_hci.py` (sudo) serve solo con quello scadente.

## Lezioni

- Il sorgente di un SDK più recente non descrive una build V3.0.7: prima di un comando irreversibile
  va provato, o considerato peggiore di quanto dica il sorgente.
- Quando la ricezione radio sembra un problema di software, cambiare prima il dongle.
- Un test con due stati alternati va campionato con un passo diverso dal periodo di alternanza, e un pin
  sospetto va isolato da solo: la prova alternata ha dato buchi ambigui, quella su un pin per volta il CS.
- Il firmware può aver finito e il braccialetto sembrare morto: prima di allarmarsi controllare le
  connessioni aperte di BlueZ.
- Un frame di advertising riscritto mentre parte può uscire misto: il dumper va corretto (una copia
  fuori dal buffer in trasmissione), e il ricevitore usa il voto a maggioranza.

## Fonti

- [FitPro-LP715-PHY6222](https://github.com/e-labInnovations/FitPro-LP715-PHY6222): SDK, build, OTA
- [phy6222_smartwatch](https://github.com/amir1387aht/phy6222_smartwatch)
- [phy6222-smartwatch-os](https://github.com/salomanov/phy6222-smartwatch-os): errori ed esperienze
- [FT100 reversing](https://github.com/0xless/FT100_fitness_bracelet_reversing) e
  [xDrip, Lefun](https://github.com/NightscoutFoundation/xDrip): protocollo stock
