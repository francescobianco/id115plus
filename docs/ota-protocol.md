# Yoho Sports (com.uthink.ring) — Firmware OTA protocol spec

Reverse-engineered from jadx-decompiled sources for the owner's own band (MSLM707,
Maxscend chip, fw `60.69.00.86`). READ-ONLY analysis of decompiled Java.

Key files (all under `.../scratchpad/apk-src/sources/com/uthink/ring/`):
- `service/BluetoothLeService.java` — GATT callbacks + both OTA state machines
- `update/Aliyun.java` — update server (Aliyun OSS) discovery + download
- `update/TelinkOta.java` — Telink block/CRC builder (NOT used on this device)
- `UpdateImage/UpdateImage.java` — watchface/image flash-write engine
- `activity/MainActivity.java` — OTA progress + the loop that drives Telink OTA
- `fragment/SettingFragment.java` — triggers the firmware update check
- `http/ApiService.java` — generic app backend (NOT firmware)

---

## 0. UUIDs and the device model

`service/BluetoothLeService.java:223-229`:
```
TELINK_SPP_DATA_OTA_SERVICE 00010203-0405-0607-0809-0a0b0c0d1912
TELINK_SPP_DATA_OTA         00010203-0405-0607-0809-0a0b0c0d2b12   (write + notify)
MAXSCEND_OTA_SERVICE        0000FD00-0000-1000-8000-00805F9B34FB
MAXSCEND_OTA_DATA           0000FD01-...  (write-without-response)   fd01
MAXSCEND_OTA_CMD            0000FD02-...  (write-without-response + notify) fd02
MAXSCEND_OTA_DESCRIPTION    00002902-...  (CCCD on fd02)
WERUN_SERVICE               0000fee7-...  (WeChat; presence only)
YOHO_DEVICE_INFO            0000cc02-...  (firmware-version characteristic)
```

OTA backend is selected in `onServicesDiscovered` (`:356-368`): if the Telink service
is present `sOtaType=1`; else if `fd00` present `sOtaType=2` (Maxscend); else `0`.
**For MSLM707 only `fd00` is present, so `sOtaType == 2` → the Maxscend path (Section 2) is
the only firmware path that runs.** Telink (Section 5) is dead code on this device.

**ffe0/ffe1/ffe2: the app never references these.** `grep` for `ffe0/ffe1` in the whole
decompiled tree hits only unrelated Google-ads classes. `fee7` (WeChat) is only *detected*
in service discovery (`:376`), never written. So ffe0 is free for your own use; the stock
app will not touch it.

### Firmware version encoding (cc02)
`:405-416` reads cc02 with `getIntValue(FORMAT_UINT8, offset)`:
```
intValue  = cc02[11]   intValue2 = cc02[12]   intValue3 = cc02[13]   intValue4 = cc02[14]
sFWVer = f("%02x.%02x.%02x.%02x", intValue2, intValue3, intValue4, intValue)
```
For raw cc02[11..14] = `86 60 69 00` → `sFWVer = "60.69.00.86"` (matches the band).
So the four dotted fields are **field0=cc02[12]=60, field1=cc02[13]=69, field2=cc02[14]=00,
field3=cc02[11]=86**, each printed as 2 hex digits. Stored to SharedPreferences key
`Constant.FIRMWARE_VERSION` (`:471-472`). `feature flags 03 00 00 00` are other cc02 bytes
parsed by the `chkHas*` helpers (screen/music/image-upgrade capability bits) — not part of OTA.

---

## 1. Update-availability check + where the image comes from

There is **no HTTP firmware API**. Firmware lives in an **Aliyun OSS bucket**, listed and
downloaded directly with embedded credentials. (`http/ApiService.java` has only
`checkNewVersion`/login/sport-upload for the app backend — unrelated to firmware.)

### OSS credentials and endpoint — `update/Aliyun.java:33-40`
```
END_POINT        = https://oss-cn-beijing.aliyuncs.com
BUCKET_OTA       = mcube-ota          (firmware .bin files)
BUCKET_APK       = android-update     (the APK itself)
ACCESS_KEY_ID    = <redacted; see tools/oss.env>
ACCESS_KEY_SECRET= <redacted; see tools/oss.env>
```
Signing: custom signer `OSSUtils.sign(ACCESS_KEY_ID, ACCESS_KEY_SECRET, stringToSign)`
(standard OSS "Authorization: OSS <AK>:<sig>" scheme). Base object URL for any key:
`https://mcube-ota.oss-cn-beijing.aliyuncs.com/<objectKey>`.

### Discovery — `Aliyun.getOTAFiles()` `:81-125`
`ListObjects` on `mcube-ota` with `max-keys=500`. For every key containing `.bin` it records:
- `OTA_FILENAME` = full object key
- `OTA_VERSION`  = `key.substring(key.length()-15, key.length()-4)` — i.e. **the 11 chars
  immediately before `.bin`**, expected form `FF_FF_FF_FF` (underscore-separated).

REST equivalent (signed): `GET https://mcube-ota.oss-cn-beijing.aliyuncs.com/?max-keys=500`.

### Decision — `Aliyun.chkOta()` `:127-166`
```
cur = FIRMWARE_VERSION.split(".")            // ["60","69","00","86"]
cur0 = cur[0]="60";  cur3 = cur[3]="86";  curN = parseInt(cur[1],16)=0x69=105
(optional remap via ConverFirmware table, see below)
for each OTA file:  ver = OTA_VERSION.split("_")   // ["60","6A","00","86"] etc.
  if ver.length==4 && cur0==ver[0] && cur3==ver[3] && curN < parseInt(ver[1],16):
      candidate = this file;  curN = that value   // picks the highest field1
```
**Update rule:** an image is "newer" iff **field0 and field3 match exactly** and **field1
(parsed as hex) is strictly greater** than the device's. field2 is ignored for the compare.

So for MSLM707 `60.69.00.86` the stock app would flash any `mcube-ota` object whose name
ends `..._60_XX_00_86.bin` with `XX` (hex) > `69`. **To fetch the official image yourself:**
list `mcube-ota`, grep keys matching `_60_*_00_86.bin`, and `GET` the one with the largest
middle field (the current/newest is likely `_60_69_00_86.bin` — the exact running build).

### Download — `Aliyun.downloadOtaFile()` `:219-260`
`GetObject(mcube-ota, objectKey)` into a `byte[]`; on completion, for `sOtaType==2` it sets
`BluetoothLeService.mxdBinBuf = bytes` (the whole .bin, header included). It is **not** CRC-
checked or signed by the app. When download reaches 100 % it broadcasts `ACTION_OTA_REQUEST`
(or `ACTION_OTA_CONFIRMED` if force). `SettingFragment` requires battery ≥ 50 % before
downloading (`:86-96`); `MainActivity` re-checks ≥ 50 % before starting the flash (`:1046-1052`).

### force / serial / convert lists — `BluetoothLeService.chkForceOTAList()` `:4015-4100`
`GetObject(mcube-ota, "force-upgrade/force upgrade.txt")` → JSON with keys `Firmware`,
`SerialFirmware`, `ConvertFirmware`. Drives forced upgrades and a version-remap table
(`ConvertFirmware`, applied in `chkOta`). Hard-coded always-force versions: `41.72.00.21`,
`43.76.00.22` (`chkForceOTA` `:4197-4206`) — not your device.

Trigger chain: SettingFragment `chkUpgrade` → `getOTAFiles()` → broadcast
`ACTION_OTA_SEARCHED` → `chkOta()` → download → `ACTION_OTA_REQUEST`/dialog →
`ACTION_OTA_CONFIRMED` → `setMxdCmdCharNotify()` starts the Maxscend flow (`MainActivity:1061-1063`).

---

## 2. Maxscend OTA flow (fd00/fd01/fd02) — the one that applies to MSLM707

### 2.1 Image header (first 16 bytes of the .bin) — `MxdFileInfo` `:4429-4452`
The downloaded .bin begins with a 16-byte metadata header that the **app consumes and then
strips** (it is NOT flashed). All multi-byte fields little-endian:
```
off 0..1  projId   (u16 LE)
off 2     boot     (u8)
off 3     stack    (u8)
off 4..5  app      (u16 LE)
off 6     appStack (u8)
off 7     appBoot  (u8)
off 8..11 codeSize (u32 LE)   // = length of the code that follows the header
off 12..15 crc32   (4 bytes)  // sent to device verbatim, app does NOT recompute
```
`mxdBinCnt` is set to `codeSize` (progress bar max). `MxdVersionInfo(byte[])` `:4413-4427`
parses the same first-8-byte layout and is reused to parse the device's reported version.

### 2.2 Version/eligibility handshake vs the device
Device's current version arrives as a notification on fd02 (see 2.4, `value[1]==1`), parsed
as `MxdVersionInfo` from notification bytes `[2..9]`. `chkMxdOta()` `:4388-4411` then gates:
- `chkMxdBoot`: file.boot==0 OR file.boot != dev.boot
- `chkMxdStack`: file.stack==0 OR file.stack != dev.stack
- `chkMxdApp`: file.app!=0 AND (file.app==dev.app  OR (file.appStack==dev.stack && file.appBoot==dev.boot))
All three must be true to proceed (this is the app-side compatibility check; **the device does
its own check too — see Section 3**).

### 2.3 Command bytes written to fd02 (`MAXSCEND_OTA_CMD`)
| opcode | builder / `:line` | payload |
|---|---|---|
| `0x01` | `sendMxdVersionInfo` `:4327-4336` | `01, projId_lo, projId_hi, dev.boot, dev.stack, app_lo, app_hi, dev.appStack, dev.appBoot` (projId/app from file header; boot/stack/appStack/appBoot from device version) |
| `0x02` | `sendMxdCodeSize` `:4338-4349` | `02` + `codeSize[4]` (the raw header bytes 8..11, LE) |
| `0x03` | `sendMxdCrc32`   `:4363-4374` | `03` + `crc32[4]` (the raw header bytes 12..15, verbatim) |

Firmware code bytes are written to **fd01** (`MAXSCEND_OTA_DATA`) in **20-byte chunks**
(`sendMxdData` `:4351-4360`; chunking in the write-callback below). 20 bytes = default ATT MTU
(23) − 3. Writes are write-without-response.

### 2.4 Full state machine (write-ack = `onCharacteristicWrite`, notify = `onCharacteristicChanged`)
1. `setMxdCmdCharNotify(gatt)` `:4305-4318` — enable notifications on fd02 (write CCCD 2902 =
   `0100`).
2. CCCD write completes → `onDescriptorWrite` `:1044-1055`: sets `mxdDesc=true`; if a device
   version is already known and `chkMxdOta()` passes, sends cmd `0x01`.
3. Device notifies its version → `onCharacteristicChanged` `:988-996` (`value[1]==1`): build
   `mxdVersionInfo` from `value[2..9]`; if `mxdDesc && chkMxdOta()` → send cmd `0x01`.
4. cmd `0x01` write-ack → `onCharacteristicWrite` `:727-730` (`value[0]==1`) → `sendMxdCodeSize`
   (cmd `0x02`).
5. cmd `0x02` write-ack → `:731-736` (`value[0]==2`): strip the 16-byte header
   (`mxdBinBuf = copyOfRange(mxdBinBuf,16,len)`), `mxdBinIdx=0`, send first 20-byte data chunk on fd01.
6. Device notifies "ready" → `:997-1006` (`value[1]==2 && value[2]==0x55`): `mxdRecv=true`;
   if already fully sent, `sendMxdCrc32`.
7. Each fd01 data write-ack → `onCharacteristicWrite` `:747-773`: `mxdBinIdx += lastLen`;
   broadcast progress; if `mxdBinIdx != mxdBinCnt` send next chunk (`min(20, remaining)`);
   when `mxdBinIdx == mxdBinCnt` and `mxdRecv` → `sendMxdCrc32` (cmd `0x03`).
8. cmd `0x03` write-ack → `:737-740` (`value[0]==3`) → `initMxdOta()` `:4290-4302` resets all
   state. Device notifies `value[1]==3` (CRC result) → `:1017` (ignored by app).

**Offsets/sequence numbers:** none on the wire. fd01 chunks are a bare in-order byte stream;
the device tracks its own write offset. `mxdBinIdx` is purely the app's local progress
counter. The only "length" and "crc32" ever sent are the cmd `0x02` / `0x03` headers.

### 2.5 Checksum / CRC
- **codeSize**: taken verbatim from image-header bytes 8..11 (u32 LE), sent as cmd `0x02`.
- **crc32**: taken verbatim from image-header bytes 12..15, sent as cmd `0x03`. **The app
  never computes a CRC** — it trusts the value baked into the .bin header and lets the device
  verify the received code against it. So whatever CRC32 variant the Maxscend bootloader uses,
  you must put the matching 4 bytes at file offset 12..15 of your custom image (byte order as
  stored in the file; app forwards them unchanged).

### 2.6 Commit / reboot / abort
- No explicit "commit"/"reboot" command on the firmware path. After cmd `0x03` the device
  verifies CRC and reboots itself; the app only calls `initMxdOta()`.
- **Abort/rollback:** none in the protocol. The app's only recovery is a disconnect. If CRC
  fails the device keeps the old image (implied by having a boot + app region). `mxdReboot()`
  (`:4157-4162`, used by the *font* path) just does `gatt.disconnect()`.
- Timeouts: handled only at the UI level (`MainActivity.showOTAFailDialog` 5 s dialog). No
  per-packet ACK/timeout in the firmware data loop (fire-and-forward on write-without-response).

### 2.7 Manual-flash hooks worth knowing
- `openMxdBin()` `:4376-4386` reads `/sdcard/408061A9.bin` into `mxdBinBuf` — **DEBUG=true**
  build. It is defined but I found **no caller**, so it is dead in this build; however the
  normal path simply fills `mxdBinBuf` from OSS, so to flash your own image you only need a
  valid 16-byte header + code + correct CRC32 and drive the sequence in 2.4.

---

## 3. Device-side verification inferable from the app

- **Compatibility gate on device**: cmd `0x01` hands the device projId/app/boot/stack. The
  device replies with its own version (`value[1]==1`) and a "ready" ack `value[1]==2,
  value[2]==0x55` (`0x55` = classic "OK/go" sentinel). If the device rejected the version it
  would presumably not send `0x55`; the app has no explicit NAK handler, so a mismatch just
  stalls. Implies the bootloader enforces projId / boot / stack compatibility.
- **CRC32 check on device**: the whole point of cmd `0x03` — device validates received code
  against the header CRC32 before committing. Result returns as notify `value[1]==3` (content
  ignored by app).
- **No evidence of signature or encryption** anywhere in the app: the .bin is downloaded in
  the clear, header is plain metadata, data streamed verbatim. There is no key, no AES, no RSA/
  ECDSA handling on the firmware path. So verification appears to be **CRC32 + version-compat
  only** — i.e. no cryptographic authentication to defeat for custom firmware (good news for
  your goal, subject to the bootloader actually only checking CRC+projId).
- Code/flash layout hints: separate boot / stack / app version fields imply a bootloader +
  stack + application partition scheme; the 16-byte header's projId likely must match the
  device's to be accepted.

---

## 4. Flash/memory read-back or DFU-mode entry

- **No arbitrary memory dump / flash-read command exists.** The closest is the *font* path
  cmd `0x16` (`readFontLib` `:4167-4175`) which makes the device return a 9-byte font-region
  header (`chkFont` `:4180-4190`) — a tiny read-back of flash metadata only, and `chkFont`
  always returns `false` (buggy/dead), so even the font update never actually fires.
- **No dedicated bootloader/DFU-entry opcode.** Entry into OTA mode is implicit: enabling fd02
  notifications + the cmd `0x01` version handshake. The device already exposes fd00 in normal
  operation (no separate DFU advertisement/mode switch seen in the app).
- Font-library update (separate, asset `ziku_ota_0100116B.bin`) command set, for reference:
  `0x11` clearFlash (`:4101-4114`, header: `11, font[9..13], font[4..7], len_be[4], 6x00`),
  `0x13` finish (`:4136-4151`), `0x16` read font header. Font path reboots via `mxdReboot`
  on notify `0x13`.

---

## 5. Telink path (NOT present on MSLM707) + watchface/UpdateImage path

### 5.1 Telink (service `...1912`, char `...2b12`) — only if `sOtaType==1`
Driven by `MainActivity.TelinkOtaTask.doInBackground` `:862-882` (blind, ~100 ms/block,
write-without-response, no notifications consumed):
1. `writeOtaCharacteristic({0x01, 0xFF})` — start (`:4231-4248`); sleep 1 s.
2. For each block `n`: `writeOtaCharacteristic(TelinkOta.getBlock(n))`.
3. `writeOtaCharacteristic(TelinkOta.getEndCmd())` — end; then unbond; sleep 1 s.

`TelinkOta.getBlock(n)` `:76-110`: `[n_lo, n_hi, 16 data bytes (last block right-padded with
0xFF), crc_lo, crc_hi]` = 20 bytes. CRC is **CRC-16** (`CRC_16` `:112-125`): table `{0,0xA001}`,
init `0xFFFF`, LSB-first over the 2 index + 16 data bytes → this is CRC-16/MODBUS (poly 0x8005
reflected). `getEndCmd` `:69-74`: `{0x02, 0xFF, (blocks-1)_lo, (blocks-1)_hi, ~lo, ~hi}`.
`getCodeSize` reads Telink-header bytes 24..27 (u32 LE). **N/A to your device.**

### 5.2 Watchface/image upload (`UpdateImage.java`) — writes to flash over the SAME Maxscend fd00/fd01/fd02
`BluetoothLeService:4846` calls `updateImage.setUUID(gatt, FD00, FD02(cmd), FD01(data))`, so
on MSLM707 this reuses the Maxscend characteristics but a **different opcode set (0xF0–0xF7)**.
This path *does* write image data into device flash at a chosen address, so it is a second
flash-write vector worth knowing:

- Setup handshake (`setParam` `:521-546`, `parseData` `:154-213`):
  `0xF0 {0xF0,0x10,0x20}` set speed; `0xF1` get speed; `0xF4 {0xF4,0x96}` set MTU (0x96=150);
  `0xF3` get MTU → reply `0xF3`, app uses `mtu = (b1&0xFF)>=128 ? b1-3 : 20`.
- Image header cmd `0xF6` (`writeBinhead` `:248-255`), 18 bytes, mixed byte orders:
  `F6, file_type, WIDTH, HEIGHT, 0, 0, 0x10, len_be[4], checksum_be[2], address_be[4], page`
  (`len` = image length, u32 **big-endian**; `address` = target flash address, u32 BE; `page`).
  Concatenated-image variant `0xF6` (`writeConcatHead` `:239-246`) for `file_type==7`.
- Device replies `0xF6` (`-10`): `[1]==0` → "can't update"; else bytes `[2..5]` = **offset
  (u32 BE)**, `[6..7]` = **buffersize (u16 BE)**. App then streams data on fd01 in `mtu`-sized
  chunks (`writepackage` `:296-328`) until `offset >= imageLen`, respecting the device-dictated
  per-burst `buffersize`.
- Finish cmd `0xF7` (`-9`) (`writeFinish` `:280-298`). Device final notify `0xF7`: `[1]!=0` =
  success (`:168-180`).
- **Checksum = plain 8-bit additive sum of all image bytes** (`setBinData` `:421-431`,
  accumulated into an int), transmitted as the 16-bit BE `checksum` field in the `0xF6` header.
  No CRC, no signature. App enforces `image size <= flashSize` client-side
  (`OnlineImageFragment:168`, `CustomDetailFragment:354`); `flashSize`/dimensions come from
  `setFWInfo` per fw-version table (`BluetoothLeService:460-470`, e.g. 114688 or 258048 bytes).

---

## Quick reference — bytes to reproduce the MSLM707 firmware flash

1. Fetch image: signed `GET https://mcube-ota.oss-cn-beijing.aliyuncs.com/?max-keys=500`
   (AK/SK from `tools/oss.env`), pick key `..._60_XX_00_86.bin`,
   `GET` it. The .bin = 16-byte header (projId/boot/stack/app/appStack/appBoot/codeSize_LE/
   crc32) + code.
2. Enable notify on fd02 (CCCD=0100). Wait for device version notify (`xx 01 ...`).
3. fd02 ← `01 projIdLo projIdHi boot stack appLo appHi appStack appBoot`
4. fd02 ← `02` + codeSize[4 LE]
5. fd01 ← code in 20-byte chunks (strip the 16-byte header first); device sends `xx 02 55` when ready.
6. fd02 ← `03` + crc32[4] (verbatim from header off 12..15). Device verifies, reboots.

Uncertain / to confirm on-device: exact CRC32 variant expected by the Maxscend bootloader (app
only forwards header bytes, never computes it); whether the device enforces projId/boot/stack
(strongly implied, not provable from the app); meaning of the device-version notification's
leading byte (`value[0]`) — the app only switches on `value[1]`. No signature/encryption found,
but that is an absence-of-evidence inference from the app, not a guarantee about the bootloader.
