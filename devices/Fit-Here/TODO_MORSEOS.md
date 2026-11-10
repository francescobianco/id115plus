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
| Eccezione del processore | watchdog | provato |
| Ciclo vivo, Bluetooth morto | emergenza col tasto | manca (fase 4) |
| Blocco prima di `app_init` | non toccare l'avvio | solo per disciplina |
| Batteria scarica senza ricarica | si ricarica col nostro firmware | provato, carica completa no |

## Fasi

Ogni fase è una flash e si chiude solo con la prova indicata.

### 1. Eccezione

- [x] Comando `7f 5a` che esegue un'istruzione non valida nel ciclo principale: `PPlusOTA` compare
      circa 8 s dopo. Verificato il 2026-11-10.

### 2. Batteria e ricarica

- [x] Comando `23` e `tools/fh_power.py`: tensione su `P14` e livello di `P15`.
- [x] Prova del 2026-11-10: sul caricatore `P15` = 1 e circa 4,05 V, staccato `P15` = 0 e circa 3,96 V in
      calo, rimesso `P15` = 1 e 4,06 V. Non seguita fino alla carica completa.

### 3. Tasto e pin del display

- [x] Tasto: è una zona touch su `P03`, attiva alta, guidata dal chip touch (`tools/fh_keyfind.py`).
      Verificato il 2026-11-10.
- [x] CS del display: `P02`, tenuto basso. L'init ora guida solo RST, SCK, MOSI, DC e CS, e il display
      disegna ancora. Verificato il 2026-11-10.

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
