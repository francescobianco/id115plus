# id115plus

Controllo di un braccialetto **ID115 Plus** (con sensore cardiaco ottico, protocollo Yoho Sports / uThink)
da Linux via Bluetooth LE, senza l'app ufficiale.

## Dispositivo

| Campo | Valore |
|---|---|
| Modello | ID115 Plus **con sensore cardiaco ottico (PPG) sul retro** (confermato fisicamente) |
| Nome BLE | `MSLM707` (l'app Yoho Sports cerca dispositivi con nome che inizia per `MS`) |
| MAC | `BA:03:5C:05:4A:12` (public, già abbinato) |
| Firmware | `60.69.00.86` (da `cc02`) |
| Chip | Maxscend (servizio OTA `fd00`) |
| App ufficiale | Yoho Sports (`com.uthink.ring`), APK in `files/apk/` |

Stesso protocollo del braccialetto `MSF0` di `../id115` (da cui è stato portato lo script).
Non è compatibile con la ID115U di `../id115u` (protocollo IDO/VeryFit, servizio `0af0`):
stessa forma, elettronica e protocollo diversi.

Flag funzioni in `cc02` (byte 15–18): `03 00 00 00` → più sport e "KMD" sì; pressione,
temperatura, meteo, musica no.

> **Nota importante (hardware ≠ firmware stock).** Il braccialetto **ha fisicamente un
> sensore di battito ottico (PPG)**, ma il firmware stock **non lo espone** (bit battito a zero nei
> flag). Quindi "no battito" qui vale solo per lo *stock*: è una funzione hardware disponibile che
> il firmware custom può abilitare. Da tenere presente per il lavoro sul firmware (c'è un sensore
> PPG da pilotare, verosimilmente su I2C, non assumere un retro "cieco").

## Uso rapido

```shell
./id115plus info                    # nome, firmware, funzioni supportate
./id115plus battery                 # batteria: %, stato
./id115plus settime                 # imposta l'orologio all'ora locale
./id115plus find                    # vibrazione "trova braccialetto"
./id115plus notify ciao             # notifica WhatsApp (max 48 caratteri)
./id115plus notify -t sms ciao      # altri tipi: sms wechat qq facebook twitter instagram line
./id115plus call "Mamma"            # chiamata in arrivo, chiusa dopo 10 s
./id115plus call -s 30 3331234567   # chiamata che squilla 30 s
./id115plus alarms                  # programma le sveglie da alarms.txt (max 3 orari)
./id115plus vibration on            # vibrazione sulle notifiche
./id115plus longsit on 45           # promemoria sedentarietà ogni 45 minuti
./id115plus selfie on               # modalità fotocamera: scuotere la band per scattare
./id115plus profile gender=male age=40 height=178 weight=75 steps=10000
./id115plus display format=datetime lift=on lang=it
./id115plus live                    # eventi in tempo reale per 60 s (0 = fino a Ctrl+C)
./id115plus sync                    # scarica lo storico attività (poi la band lo cancella)
./id115plus reset --yes             # ripristino impostazioni di fabbrica
./id115plus raw 0801                # comando grezzo su cc06
./id115plus read cc02               # lettura grezza di una caratteristica
```

Variabili d'ambiente: `MAC`, `RETRIES` (default 5), `HCI` (default `hci0`).

### Connessione e ripristino

Il segnale è debole (RSSI ~ -93 dBm) e la connessione cade spesso. Inoltre `bluetoothd` può
restare convinto che la band sia connessa (`Connected: yes`) quando il link radio non c'è più
(`hcitool con` vuoto): ogni chiamata GATT risponde `Not connected` e `Disconnect` va in timeout.

Per questo lo script controlla il link reale con `hcitool con` e, se una connessione,
lettura o scrittura fallisce, ritenta salendo di livello:

1. nuova connessione
2. `Disconnect` e nuova connessione
3. spegnimento e riaccensione dell'adattatore (`Powered` false/true via D-Bus, come
   `bluetoothctl power off` / `power on`, senza sudo; scollega anche gli altri dispositivi BT)

fino a `RETRIES` volte. `live` e `sync` si riconnettono e ripartono se il link cade.

```shell
./id115plus status          # stato secondo BlueZ e secondo il controller
./id115plus keepalive 10    # tiene su la connessione, controllo ogni 10 s, fino a Ctrl+C
```

A mano, dal più leggero al più drastico: `bluetoothctl power off && bluetoothctl power on`,
`sudo hciconfig hci0 down && sudo hciconfig hci0 up`, `sudo systemctl restart bluetooth`.

Lo script parla con BlueZ via D-Bus (`busctl`): si connette da solo se serve, ogni scrittura
attende la conferma, quindi niente `sleep` né errori `InProgress`. Il braccialetto deve essere
già abbinato. `live` e `sync` ricevono le notifiche di `cc04` con un helper Python incorporato
(dipendenze: `python3-dbus`, `python3-gi`).

Opzioni di `profile` (default dell'app): `gender=male|female` (male), `age` (20), `height` cm (170),
`weight` kg (60), `steps` obiettivo (8000), `unit=km|mi` (km), `hand=left|right` (left).
Opzioni di `display`: `format=time|datetime` (time), `lift=on|off` (off), `lang` (it), `bp=on|off` (off). `alarms.txt` ha lo stesso formato di `../id115u`, ma qui i giorni vanno da domenica
(bit 0) a sabato (bit 6) e gli orari distinti sono al massimo 3.

## Protocollo

Servizio `cc00`:

| UUID | Uso |
|---|---|
| `cc01` | info utente |
| `cc02` | info dispositivo (lettura): firmware = byte 12.13.14.11, flag funzioni byte 15–18 |
| `cc03` | batteria (lettura/notifica): byte 0 = %, byte 7 = stato (01 = in carica) |
| `cc04` | notifiche: eventi in tempo reale e storico attività |
| `cc05` | sincronizzazione vecchio protocollo (firmware con byte 13 di `cc02` ≤ 73) |
| `cc06` | comandi (scrittura) |

### Comandi su `cc06`

Tutti ricavati dall'APK; "verificato" = la band ha mostrato l'effetto o risposto come previsto.

| Comando | Byte | Note |
|---|---|---|
| Trova braccialetto | `08 01` | verificato: vibra |
| Notifica | `F2 <tipo> <caratteri totali> <seq> <8 caratteri UTF-16LE>` | verificato; un pacchetto ogni 8 caratteri, max 48 |
| Chiamata in arrivo | `F2 03 <caratteri totali> <seq> <nome o numero UTF-16LE>` | come una notifica di tipo `03` |
| Fine chiamata | `F2 03 00` | |
| Imposta ora | `04 00 <anno-2000> <mese> <giorno> <ora> <min> <sec>` | verificato con `sync` |
| Sveglie | `0C <attive> [<on> <ora> <min> <giorni>] ×3` | vedi sotto |
| Vibrazione | `01 <on>` | |
| Sedentarietà | `07 <on> <minuti u16 LE>` | |
| Selfie | `09 <on>` | scuotendo la band arriva un evento su `cc04` |
| Profilo | `F1 01 <sesso> <età> <altezza> <peso> <mano> <unità> <obiettivo passi u16 LE>` | sesso 0 = M; unità 0 = km |
| Display | `F1 02 01 <formato> 01 01 01 01 01 <alza per vedere> 01 01 <lingua> <pressione>` | formato 0 = ora, 1 = ora+data |
| Ripristino | `F1 03 18 01` | impostazioni di fabbrica |
| Sincronizzazione | `F4 00` | vedi sotto |
| Risposta "trova telefono" | `F3 18` | da inviare quando la band manda `F3 18` |

Tipi notifica (dall'APK): `03` chiamata, `10` SMS, `11` WeChat, `12` QQ, `13` Facebook,
`14` Twitter, `15` WhatsApp, `16` Instagram, `17` Line.

Codici lingua (risorsa `language_code` dell'APK): `0` en, `1` zh, `2` es, `3` fr, `4` pt, `5` ja,
`6` de, `7` nl, `8` ru, `9` pl, `10` tr, `11` cs, `12` ms/sk, `13` en-MY, `14` th, `15` ar,
`16` zh-TW, `17` it, `18` ko.

### Eventi in tempo reale (`cc04`)

Primi due byte = flag (u16 LE), salvo i pacchetti che iniziano con `F1`/`F3`/`F4`/`F5`:

| Condizione | Significato |
|---|---|
| flag bit 3 | selfie (band scossa in modalità fotocamera) |
| flag bit 2 | promemoria sedentarietà |
| flag bit 5 | battito, byte 10 (hardware presente, ma non emesso dal firmware stock) |
| flag bit 6, flag = `0x80` | log grezzi accelerometro / sonno |
| altrimenti | byte 2 = stato, byte 3–6 = passi totali (u32 LE) |
| `F3 18` | la band cerca il telefono |

### Storico attività (`F4`)

Dopo `F4 00` su `cc06` la band risponde su `cc04`; ogni pacchetto va confermato:

1. `F4 01 <aa mm gg hh mm ss>`: ora base dei record (tutto zero = nessun record) → confermare con `F4 01`
2. `F4 02 <seq u16 LE> <n>` + n record da 5 byte `<stato> <minuti dalla base u16 LE> <passi u16 LE>` → `F4 02 <seq>`
3. `F4 03 <stato> <minuti u16> <passi u16> <aa mm gg hh mm ss>`: stato attuale e da quando → `F4 03`

I record confermati vengono cancellati dalla band. Il significato dei codici di stato non è decodificato.

### Sveglie

Massimo **3 sveglie**, scritte tutte insieme in un pacchetto da 14 byte:

```
0C 01 | 01 07 00 3E | 01 07 0F 3E | 01 07 1E 3E
```

- byte 1: `01` se c'è almeno una sveglia
- per ogni slot: `on` (`01`/`00`), ora, minuti, giorni
- giorni: bit 0 = domenica, bit 1 = lunedì … bit 6 = sabato (lun–ven = `0x3E`)

L'esempio sopra (07:00, 07:15, 07:30 lun–ven) è quello attualmente programmato.

### Display

Il comando display (`F1 02 …`) regola solo formato ora, alza-per-vedere, lingua e pressione.
Nell'app non esiste una regolazione della luminosità.

### Non implementato

Presenti nell'app ma non esposti dal firmware stock (flag di `cc02` a zero) o rischiosi:
meteo, musica, rubrica, battito/pressione/temperatura, aggiornamento firmware e quadranti
(servizio Maxscend `fd00`). Nota: il **battito** è un caso a parte — il sensore ottico c'è
davvero sull'hardware, è lo stock a non attivarlo (vedi sopra).

## Uso con bluetoothctl

```shell
bluetoothctl
connect BA:03:5C:05:4A:12

# Batteria
menu gatt
select-attribute 0000cc03-0000-1000-8000-00805f9b34fb
read

# Trova braccialetto (vibrazione)
select-attribute 0000cc06-0000-1000-8000-00805f9b34fb
write "0x08 0x01 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00"

# Notifica WhatsApp "ciao"
write "0xF2 0x15 0x04 0x00 0x63 0x00 0x69 0x00 0x61 0x00 0x6F 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00"
```

Se il braccialetto è già connesso tramite BlueZ, `gatttool` risponde "Device or resource busy":
usare `bluetoothctl` (menu gatt). Tra due `write` lasciare qualche secondo, altrimenti
BlueZ risponde `org.bluez.Error.InProgress`.

Con batteria scarica il braccialetto continua ad annunciarsi (RSSI ~ -96 dBm) ma la connessione
fallisce: ricaricarlo prima di diagnosticare altro.

## File

| Percorso | Contenuto |
|---|---|
| `id115plus` | script di controllo |
| `alarms.txt` | sveglie applicate da `./id115plus alarms` |

L'APK di Yoho Sports usato per ricavare il protocollo e i vecchi script di prova restano in `../id115/files/`.

### Batteria su questo firmware

Su `60.69.00.86` la lettura di `cc03` restituisce `00 13 06 01 0c 00 00 01 00 00 00 86 60 69 00 03 …`,
che somiglia più al contenuto di `cc02` (firmware ai byte 11–14) che a un pacchetto batteria:
`./id115plus battery` mostra quindi "0% charging", valore probabilmente non affidabile. Da verificare.

## Vedi anche

`../id115`: lo stesso protocollo per il braccialetto `MSF0` (`BA:03:5C:0B:21:E1`), con l'APK.

`../id115u`: script e documentazione per una ID115U (protocollo IDO/VeryFit, servizio `0af0`),
non compatibile con questo braccialetto.
