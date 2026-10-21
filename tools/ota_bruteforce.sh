#!/usr/bin/env bash
# Brute-force the MSLM707 vendor OTA checksum with a VALID DA14585 image.
#
# Rationale (docs/ota-flash-runbook.md "brute-force"): the device verifies a 4-byte checksum at
# header off 12..15 but exposes no computed value (a wrong value is rejected SILENTLY and the
# device reboots onto the intact stock firmware — confirmed non-destructive). We don't know the
# algorithm/range, so we try every candidate (tools/crc_candidates.py). A wrong candidate is
# safely rejected; the RIGHT one is accepted and the device reboots onto OUR code.
#
# !!! SAFETY !!!  This is only near-safe with GENUINELY RUNNABLE code. A correct checksum paired
# with code that does not run (wrong architecture / wrong image format / wrong load address) can
# brick the device, because the bootloader will have committed a valid-but-dead image. Do NOT run
# this with the placeholder build or any image whose format for the vendor bootloader is unproven.
# Confirm with --i-have-valid-code.
#
# Usage:
#   tools/ota_bruteforce.sh <app.bin> --i-have-valid-code [--start N] [--adv-name NAME]
#     <app.bin>   raw DA14585 code (NOT an OTA image; header is added per candidate)
#     --start N   resume from candidate index N (default 0)
#     --adv-name  our firmware's advertising name, used to positively detect an accept
#
# Between attempts it power-cycles the BT adapter and rescans (per the project's field notes on
# the flaky link). It STOPS at the first non-rejected result for you to verify the band by hand.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEV="BA:03:5C:05:4A:12"
STOCK_VER="60.69.00.86"

code=""; start=0; adv=""; ok=0; only=""; skip=""
while [ $# -gt 0 ]; do
  case "$1" in
    --i-have-valid-code) ok=1 ;;
    --start) start="$2"; shift ;;
    --adv-name) adv="$2"; shift ;;
    --only) only=",$2,"; shift ;;   # e.g. --only 0,1,11,20,21,31 : try ONLY these indices
    --skip) skip=",$2,"; shift ;;    # e.g. --skip 0,1,21,31 : skip these indices (already ruled out)
    -*) echo "unknown opt $1" >&2; exit 2 ;;
    *) code="$1" ;;
  esac; shift
done
[ -n "$code" ] && [ -f "$code" ] || { echo "usage: $0 <app.bin> --i-have-valid-code [--start N] [--adv-name NAME]" >&2; exit 2; }
if [ "$ok" != 1 ]; then
  echo "REFUSING: pass --i-have-valid-code to confirm <app.bin> is a real, runnable DA14585 build." >&2
  echo "A correct checksum with non-runnable code can brick the device (see this script's header)." >&2
  exit 3
fi

cycle_adapter() {  # power-cycle hci0 and rescan so the band is reachable again after a reboot
  busctl set-property org.bluez /org/bluez/hci0 org.bluez.Adapter1 Powered b false >/dev/null 2>&1
  sleep 2
  busctl set-property org.bluez /org/bluez/hci0 org.bluez.Adapter1 Powered b true  >/dev/null 2>&1
  sleep 2
  timeout 14 bluetoothctl --timeout 12 scan on >/dev/null 2>&1 || true
}

STOCK_NAME="MSLM707"

adv_name() {  # print the device's CURRENT advertised name (empty if not seen). Robust on a weak
              # link: hearing one adv packet beats a full connect+GATT read (which times out at -84).
  bluetoothctl remove "$DEV" >/dev/null 2>&1   # drop cache so the name reflects the live advert
  sleep 1
  timeout 22 bluetoothctl --timeout 20 scan on 2>/dev/null \
    | grep -iE "Device ${DEV}" | grep -oiE "(ID115DIY|${STOCK_NAME})" | tail -1
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
python3 "$HERE/tools/crc_candidates.py" "$code" --emit "$tmp" >/dev/null || exit 1
mapfile -t imgs < <(ls -1 "$tmp"/*.bin | sort)
echo "=== brute-force: ${#imgs[@]} candidates, code=$code, starting at index $start ==="
[ -n "$adv" ] && echo "    accept-detect: stock=$STOCK_VER OR advertising name '$adv'"

for img in "${imgs[@]}"; do
  idx="$(basename "$img" | cut -d_ -f1)"
  [ "$((10#$idx))" -lt "$start" ] && continue
  [ -n "$only" ] && case "$only" in *",$((10#$idx)),"*) : ;; *) continue ;; esac
  [ -n "$skip" ] && case "$skip" in *",$((10#$idx)),"*) continue ;; esac
  label="$(basename "$img" .bin | cut -d_ -f2-)"
  echo
  echo "=== [$idx] $label ==="
  # A candidate is only TESTED if the device confirmed the full image with READY(0x55); on this
  # weak link a commit can fail to even connect/stream. Retry until READY is seen (up to TRIES),
  # so a link failure is never mistaken for a CRC rejection.
  tested=0
  for t in $(seq 1 "${TRIES:-5}"); do
    cycle_adapter
    out="$(timeout 170 "$HERE/id115plus" ota-flash "$img" --commit --yes 2>&1)"
    echo "$out" | sed 's/^/    /'
    if echo "$out" | grep -qiE "READY \(0x55\)|ready for CRC"; then tested=1; break; fi
    echo "    (attempt $t: no READY — link failure, not a CRC verdict; retrying)"
  done
  if [ "$tested" != 1 ]; then
    echo "??? [$idx] $label — could NOT deliver the image after ${TRIES:-5} tries (link). UNTESTED."
    echo "$idx" >> "$tmp/untested.txt"
    continue
  fi
  echo "    (image verified by device; waiting for reboot...)"; sleep 6
  # Detect by ADVERTISED NAME. Stock = rejected; ID115DIY = accepted; not seen = manual check.
  nm="$(adv_name)"; [ -z "$nm" ] && { echo "    (not seen, rescanning...)"; nm="$(adv_name)"; }
  echo "    advertised name: ${nm:-<not seen>}"
  if echo "$nm" | grep -qi ID115DIY; then
    echo "!!! [$idx] $label — advertising as ID115DIY. LIKELY ACCEPTED — our firmware is running! Stopping."
    exit 0
  elif echo "$nm" | grep -qi "$STOCK_NAME"; then
    echo "    [$idx] REJECTED (CRC verified wrong; stock $STOCK_NAME advertising). Next."
  else
    echo "!!! [$idx] $label — image was verified by the device, then it is not advertising a known"
    echo "!!! name after 2 scans. Could be an ACCEPT with a dead image (brick) or RF. STOPPING for"
    echo "!!! a manual check of the band before any further flashing."
    exit 0
  fi
done
echo
if [ -s "$tmp/untested.txt" ]; then
  echo "=== done. Cleanly REJECTED where tested. UNTESTED (link failed, re-run these): "
  echo "    --only $(paste -sd, "$tmp/untested.txt")"
else
  echo "=== all candidates TESTED and REJECTED. The checksum algorithm/range is outside the tried"
  echo "    set, or the image format (load addr/entry/header) is wrong. Next: SWD dump of the cavia. ==="
fi
