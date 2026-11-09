# Fit-Here: da dove ripartire

Contesto: [`DOSSIER.md`](DOSSIER.md). Prima di qualunque comando OTA che scrive: sezione OTA del
[`README.md`](README.md).

## Prima di iniziare

- [ ] Attaccare il dongle CSR `00:1A:7D:DA:71:13` e tenere il braccialetto vicino.
- [ ] `systemctl --user stop btedge wrish` (a fine lavoro: `start`).
- [ ] Controllare che si veda `FH-DEMO`: `tools/scan.py 10`. Se non si vede, batteria scarica.

## Subito: la rete di sicurezza

- [ ] **Copiare `dump/flash.final.bin` fuori dal PC**: è l'unica copia di quel che resta dello stock.
      SHA-256 nel dossier.
- [ ] **Ricarica**: metterlo sul caricatore con la demo attiva e vedere se il livello sale. Serve
      leggere la tensione vera, oggi non misurata (la batteria BLE della demo è un contatore).
- [ ] **Ritorno all'updater**: `MAC=C0:00:A1:B1:02:64 tools/phy_ota.py 4c500002=04`, deve comparire
      `PPlusOTA`. Poi `MAC=C0:00:A1:B1:02:62 tools/phy_ota.py 5833ff02=0401` per tornare alla demo.
- [ ] **Watchdog**: nuova build con un comando che blocca il firmware, verificare che finisca in
      `PPlusOTA`. Finché non è provato, ogni firmware nuovo può richiedere di aprirlo se si blocca.

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
