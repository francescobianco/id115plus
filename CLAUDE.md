# Note per chi lavora su questo repo

- **I dispositivi si identificano col nome Bluetooth, non col nome commerciale.** "ID115",
  "ID115 Plus" ecc. coprono implementazioni diverse (chip, protocollo, OTA). Ogni dispositivo ha
  la sua cartella `devices/<nome BLE>/` con un `README.md` (MAC, chip e come è stato identificato,
  GATT, OTA) ed eventuali `tools/`. Un dispositivo nuovo va aggiunto lì e nella tabella di
  `devices/README.md`; se un nome BLE si ripete con un'implementazione diversa, usare
  `<nome>_<ultimi 2 byte del MAC>`.
- La radice del repo (`id115plus`, `docs/`, `firmware-da14585/`, `PLAN.md`) riguarda ancora
  `MSLM707`.
- Prima di qualunque comando OTA che scrive o cancella, leggere la sezione OTA del README del
  dispositivo: alcuni comandi (es. `01` nell'updater `PPlusOTA` del Fit-Here) cancellano subito la
  tabella dell'app.
