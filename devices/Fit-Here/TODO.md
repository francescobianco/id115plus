# Fit-Here: da dove ripartire

Contesto: [`DOSSIER.md`](DOSSIER.md). Prima di qualunque comando OTA che scrive: sezione OTA del
[`README.md`](README.md).

## Prima di iniziare

- [ ] **Se `devices/Fit-Here/dump/flash.final.bin` non esiste: ripristinare il dump.** Su un PC nuovo
      è così. Procedura nel dossier, sezione "Ripartire da un altro PC". La password la inserisce
      l'utente a `gpg`, non va scritta in chat.
- [ ] Sul nuovo PC: `gpg`, Docker, `bluez`, `python3-dbus`, `python3-gi`.
- [ ] Sul portatile si usa il Bluetooth di bordo: tenere il braccialetto vicino e controllare RSSI
      (verso -60 dBm) e tenuta del collegamento prima di qualunque scrittura OTA.
- [ ] Se sono attivi, fermare `wrish` (`systemctl --user stop wrish`) e `btedge`, che sul portatile è
      un servizio di sistema (`sudo systemctl stop btedge`). A fine lavoro: `start`.
- [ ] Controllare che si veda `FH-DEMO`: `tools/scan.py 10`. Se non si vede, batteria scarica.

## Subito: la rete di sicurezza

- [x] **Ricarica**: la tensione sale sul caricatore col nostro firmware (`tools/fh_power.py`). Verificato
      il 2026-11-10, non seguita fino alla carica completa.
- [x] **Ritorno all'updater**: `MAC=C0:00:A1:B1:02:64 tools/phy_ota.py 4c500002=04` porta a
      `PPlusOTA`, poi `MAC=C0:00:A1:B1:02:62 tools/phy_ota.py 5833ff02=0401` torna alla demo.
      Verificato il 2026-11-09.
- [x] **Watchdog**: il comando `7f a5` blocca il ciclo principale, il braccialetto ricompare da
      solo come `PPlusOTA` dopo circa 9 s. Verificato il 2026-11-09. Copre solo i blocchi del ciclo
      principale con il watchdog già avviato.

## Poi: hardware

- [ ] Finire gli impulsi sui pin mancanti: `P17`, `P24`, `P25`, `P27`, `P31`, `P32`, `P33`, `P34`.
      Esclusi per sicurezza: `P07` (test mode), `P09`/`P10` (UART). `P11` probabilmente è il tasto.
- [x] Analisi delle chiamate rifatta sul codice stock: batteria, `P15`, I2C (tabella nel README,
      sezione "Pin dal codice stock"). Sono risultati statici, da provare sul dispositivo.
- [x] Luce dello schermo: `P34`, attivo alto.
- [x] Pin del display: RST `P01`, SCK `P31`, MOSI `P25`, DC `P00`, luce `P34` (README, "Pin dal
      codice stock"; trovati con `tools/fh_display_search.py`).
- [x] Display: init con inversione, BGR e gamma, area visibile a colonna 26, riga 1. Disegni via BLE con
      `tools/fh_draw.py`. Verificato il 2026-11-10.
- [ ] Display: cercare CS. L'init tiene bassi tutti i candidati, compreso `P11` (forse il tasto).
- [ ] Trovare il tasto.
- [x] Tensione su `P14` e caricatore su `P15` letti via BLE, provati mettendo e togliendo il caricatore.
- [ ] Identificare il controller del display e portare il driver (l'LP715 usa un JD9850).

## Poi: firmware

- [ ] Demo che vibra da sola all'avvio, la prova più semplice senza PC.
- [x] Prima schermata sul display.

- [ ] MorseOS: piano e regole di sicurezza in [`TODO_MORSEOS.md`](TODO_MORSEOS.md).

## Facoltativo

- [ ] Studiare lo stock dal dump in Ghidra (`0x20000`–`0x39aff` a `0x11020000`), sapendo che manca la
      parte SRAM.
- [ ] Correggere il dumper per non mandare frame misti, se servirà rileggere la flash.
