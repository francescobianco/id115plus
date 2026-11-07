# devices

Una sottocartella per dispositivo, **col nome Bluetooth (il nome che annuncia in BLE)**, non col
nome commerciale.

Il motivo: "ID115", "ID115 Plus" e simili sono nomi commerciali sotto cui si vendono braccialetti
con la stessa forma ma elettronica, chip e protocollo diversi. Il nome BLE (insieme a PnP ID,
servizi GATT e manufacturer data) distingue davvero un'implementazione dall'altra, ed è la prima
cosa che si vede con una scansione. Se lo stesso nome BLE dovesse comparire con implementazioni
diverse, aggiungere un suffisso col MAC: `<nome>_<ultimi 2 byte del MAC>`.

Ogni cartella ha un `README.md` con: nome BLE, MAC, chip e come è stato identificato, servizi
GATT, protocollo OTA ed eventuali strumenti in `tools/`.

| Nome BLE | MAC | Chip | Protocollo / OTA | Dove |
|---|---|---|---|---|
| [`MSLM707`](MSLM707/) | `BA:03:5C:05:4A:12` | Dialog DA14585 | Yoho Sports (`cc00`), OTA `fd00` | questo repo (radice) |
| [`Fit-Here`](Fit-Here/) | `C0:00:A1:B1:02:61` | PhyPlus PHY62xx | `18D0` (`0x5A`), OTA PhyPlus `5833ff01`, updater `PPlusOTA` | qui |
| `MSF0` | `BA:03:5C:0B:21:E1` | — | Yoho Sports (`cc00`) | `../id115` |
| `ID115U` | `E7:84:6B:69:A2:8A` | — | IDO/VeryFit (`0af0`) | `../id115u` |
| `716` | `FF:FF:CF:10:70:E9` | Telink TLSR8232 | FitPro (Nordic UART), OTA Telink | `../lt716` |
