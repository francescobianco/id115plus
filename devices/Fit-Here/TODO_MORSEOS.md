# MorseOS sul Fit-Here: piano

Porting da `../lt716/firmware/morseos`. Prima di iniziare rileggere
`../lt716/firmware/morseos/INCIDENTE-0.5.5.md` e la sezione OTA del [`README.md`](README.md).

## Regole

Valgono per ogni flash.

- Un solo cambiamento rischioso per flash, con la lista di cosa cambia e di cosa può bloccare l'avvio.
- In `app_init` prima si arma l'updater e si avvia il watchdog, poi tutto il resto.
- Il codice nuovo non parte all'avvio: si attiva con un comando BLE e diventa automatico solo dopo aver
  funzionato.
- Il watchdog si alimenta solo in `app_update`, mai nelle attese. Oggi `wait_ms` lo alimenta: le sequenze
  di ricerca del display durano più di 8 s, quindi si toglie insieme a quelle.
- Un blocco prima di `app_init` non è recuperabile senza aprirlo: non toccare `lib/core` e controllare
  prima di ogni flash che le sezioni in SRAM non si sovrappongano.
- Nessuna scrittura o cancellazione della flash dal firmware.
- Limite di scrittura: `--confine 0x11000:0x2c000`. Sopra `0x27000` si sovrascrive la copia dello stock
  sul braccialetto, che resta nel dump.

## Rischi

| Rischio | Protezione | Stato |
|---|---|---|
| Blocco del ciclo principale | watchdog verso l'updater | provato |
| Firmware sbagliato, OTA interrotta | updater separato | provato |
| Eccezione del processore | watchdog | da provare (fase 1) |
| Ciclo vivo, Bluetooth morto | emergenza col tasto | manca (fase 4) |
| Blocco prima di `app_init` | non toccare l'avvio | solo per disciplina |
| Batteria scarica senza ricarica | verifica della ricarica | da provare (fase 2) |

## Fasi

Ogni fase è una flash e si chiude solo con la prova indicata.

### 1. Eccezione

- [ ] Comando `7f 5a` che esegue un'istruzione non valida nel ciclo principale. Prova: dopo circa 9 s
      compare `PPlusOTA`.

### 2. Batteria e ricarica

- [ ] Riportare via BLE la tensione su `P14` e il livello di `P15` (analisi statica, mai provati).
- [ ] Prova: con il braccialetto sul caricatore la tensione sale e `P15` cambia.

### 3. Tasto e pin del display

- [ ] Leggere i pin candidati senza pilotarli, con pull-up e pull-down alternati, e riportare i cambi di
      livello. Prova: un solo pin cambia quando si tocca il tasto.
- [ ] Smettere di pilotare gli altri candidati nell'init del display, `P11` compreso. Prova: si disegna
      ancora. Se smette, uno di loro è CS.

### 4. Emergenza col tasto

- [ ] 10 s premuto, schermo rosso, rilascio, 3 tocchi brevi entro 5 s: si va all'updater. Un tasto
      bloccato non deve attivarla.
- [ ] Prova da sola, prima di qualunque altro uso del tasto.

### 5. MorseOS di base

- [ ] Strato di compatibilità: `clock_time`, `sleep_us`, tipi `u8`/`u16`/`u32`.
- [ ] Driver con l'interfaccia di `st7735.h` (`lcd_fill`, `lcd`), sui pin noti.
- [ ] Portare `core/ui`, `lib/font`, `lib/morse`, attivati da un comando BLE.
- [ ] Portare `apps/face`, poi `apps/practice` e `apps/info`.
- [ ] Orologio: impostazione dell'ora via BLE.
- [ ] Prova: la parola TAN apre il menu. Solo dopo, avvio automatico.

### 6. Consumi

- [ ] Leggere il codice di `pwrmgr`, poi la sospensione a schermo spento, controllando watchdog e orologio
      durante il sonno. L'incidente della 0.5.5 è nato qui.

## Fuori dal porting

Comandi dumper e scrittura della flash di `core/system`, `lib/fitpro`, `apps/message`.
`lib/i2cprobe` e `apps/sensors` solo se serviranno per l'accelerometro.
