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

- [ ] **Ricarica**: non si può verificare con la demo attuale, la cui batteria BLE è un contatore.
      Serve prima trovare il pin della batteria nel codice stock e leggere la tensione via ADC.
- [x] **Ritorno all'updater**: `MAC=C0:00:A1:B1:02:64 tools/phy_ota.py 4c500002=04` porta a
      `PPlusOTA`, poi `MAC=C0:00:A1:B1:02:62 tools/phy_ota.py 5833ff02=0401` torna alla demo.
      Verificato il 2026-11-09.
- [x] **Watchdog**: il comando `7f a5` blocca il ciclo principale, il braccialetto ricompare da
      solo come `PPlusOTA` dopo circa 9 s. Verificato il 2026-11-09. Copre solo i blocchi del ciclo
      principale con il watchdog già avviato.

## Poi: hardware

- [ ] Finire gli impulsi sui pin mancanti: `P17`, `P24`, `P25`, `P27`, `P31`, `P32`, `P33`, `P34`.
      Esclusi per sicurezza: `P07` (test mode), `P09`/`P10` (UART). `P11` probabilmente è il tasto.
- [ ] Trovare nel codice stock del dump i pin di display, tasto, sensori e carica. Attenzione: la
      prima analisi automatica delle chiamate aveva un errore nel calcolo dei salti BL (`imm -= 1<<22`
      è la correzione), da rifare.
- [ ] Identificare il controller del display e portare il driver (l'LP715 usa un JD9850).
- [ ] Leggere la batteria via ADC e gestire la carica.

## Poi: firmware

- [ ] Demo che vibra da sola all'avvio, la prova più semplice senza PC.
- [ ] Prima schermata sul display.
- [ ] Firmware vero su modello MorseOS (`../lt716`): tasto, menu, orologio.

## Facoltativo

- [ ] Studiare lo stock dal dump in Ghidra (`0x20000`–`0x39aff` a `0x11020000`), sapendo che manca la
      parte SRAM.
- [ ] Correggere il dumper per non mandare frame misti, se servirà rileggere la flash.
