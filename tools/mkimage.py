#!/usr/bin/env python3
"""Build a Maxscend OTA image (16-byte header + code) for the MSLM707 band.

Offline tool, no device involved. Header layout (little-endian), per docs/ota-protocol.md
section 2.1:

    off 0..1   projId    u16 LE
    off 2      boot       u8
    off 3      stack      u8
    off 4..5   app        u16 LE
    off 6      appStack   u8
    off 7      appBoot    u8
    off 8..11  codeSize   u32 LE   (length of the code after the header)
    off 12..15 crc        4 bytes  (the device verifies the received code against this)

Device parameters observed in Fase 2 (docs/device-ota-params.md) are the defaults:
projId=0x2a4b boot=4 stack=2 app=0x6900 appStack=0 appBoot=0.

CRC ALGORITHM (identified 2026-10-21, see docs/firmware-build.md "Algoritmo CRC"):
the Macrogiga/Maxscend OTA family uses **CRC-16/XMODEM** (poly 0x1021, init 0x0000,
non-reflected), NOT a CRC-32. Evidence: the SDK bootloader app-OTA/main-boot.c computes
CRC16(code, size, init=0) with the 0x1021 CCITT table and stores it as 2 bytes; the official
header tool mg_ota_head_hex.exe embeds the same table and prints "CRC = 0x%04X" (16-bit).
A full on-device commit with CRC-32/zlib was REJECTED, consistent with this.

For a 16-bit CRC the value goes in header bytes 12..13 (LE), bytes 14..15 = 0x0000. CRC-32
variants (kept for reference / fallback) fill all 4 bytes. 'wrong' deliberately corrupts the
CRC for a safe dry-run (the device rejects and keeps the running firmware).

Usage:
  tools/mkimage.py <code.bin> <out.bin> [--crc VARIANT] [--projid 0x2a4b] [--boot 4]
                   [--stack 2] [--app 0x6900] [--appstack 0] [--appboot 0]
  tools/mkimage.py <code.bin> --crc-only        # just print all candidate CRCs of the code
VARIANT: xmodem (default) | ccitt-false | zlib | bzip2 | mpeg2 | posix | wrong
"""
import argparse
import struct
import sys
import zlib

CRC16_NAMES = ("xmodem", "ccitt-false")
CRC32_NAMES = ("zlib", "bzip2", "mpeg2", "posix")


def crc16_variant(data, name):
    """CRC-16/CCITT family (poly 0x1021, non-reflected, MSB-first)."""
    if name == "xmodem":       # init 0x0000, xorout 0x0000
        return _crc16(data, 0x0000)
    if name == "ccitt-false":  # init 0xFFFF, xorout 0x0000
        return _crc16(data, 0xFFFF)
    raise SystemExit(f"unknown crc16 variant: {name}")


def _crc16(data, init):
    crc = init
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _CCITT[((crc >> 8) ^ b) & 0xFF]
    return crc & 0xFFFF


_CCITT = [0] * 256
for _i in range(256):
    _c = _i << 8
    for _ in range(8):
        _c = ((_c << 1) ^ 0x1021) & 0xFFFF if _c & 0x8000 else (_c << 1) & 0xFFFF
    _CCITT[_i] = _c


def crc32_variant(data, name):
    """A few common CRC-32 variants (reference/fallback)."""
    if name == "zlib":   # CRC-32/ISO-HDLC: refl, init/xorout 0xFFFFFFFF
        return zlib.crc32(data) & 0xFFFFFFFF
    if name == "bzip2":  # CRC-32/BZIP2: no reflect, init/xorout 0xFFFFFFFF
        return _crc32(data, 0x04C11DB7, 0xFFFFFFFF, False, 0xFFFFFFFF)
    if name == "mpeg2":  # CRC-32/MPEG-2: no reflect, init 0xFFFFFFFF, xorout 0
        return _crc32(data, 0x04C11DB7, 0xFFFFFFFF, False, 0x00000000)
    if name == "posix":  # CRC-32/CKSUM: no reflect, init 0, xorout 0xFFFFFFFF
        return _crc32(data, 0x04C11DB7, 0x00000000, False, 0xFFFFFFFF)
    raise SystemExit(f"unknown crc32 variant: {name}")


def _crc32(data, poly, init, refl, xorout):
    crc = init
    for b in data:
        if refl:
            crc ^= b
            for _ in range(8):
                crc = (crc >> 1) ^ (poly if crc & 1 else 0)
        else:
            crc ^= b << 24
            for _ in range(8):
                crc = ((crc << 1) ^ poly) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc ^ xorout


def crc_bytes(code, name):
    """Return (printable_value, 4-byte little-endian header field) for a crc variant."""
    if name == "wrong":                      # safe dry-run: a value nothing will match
        v = crc16_variant(code, "xmodem") ^ 0xFFFF
        return v, struct.pack("<H", v) + b"\x00\x00"
    if name in CRC16_NAMES:
        v = crc16_variant(code, name)
        return v, struct.pack("<H", v) + b"\x00\x00"
    if name in CRC32_NAMES:
        v = crc32_variant(code, name)
        return v, struct.pack("<I", v)
    raise SystemExit(f"unknown crc variant: {name}")


def build(code, crc_name, projid, boot, stack, app, appstack, appboot):
    val, crcfield = crc_bytes(code, crc_name)
    header = struct.pack("<HBBHBBI", projid, boot, stack, app, appstack, appboot, len(code))
    header += crcfield
    return header + code, val


def main():
    ap = argparse.ArgumentParser(add_help=True, usage=__doc__)
    ap.add_argument("code")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--crc", default="xmodem")
    ap.add_argument("--projid", type=lambda x: int(x, 0), default=0x2A4B)
    ap.add_argument("--boot", type=lambda x: int(x, 0), default=4)
    ap.add_argument("--stack", type=lambda x: int(x, 0), default=2)
    ap.add_argument("--app", type=lambda x: int(x, 0), default=0x6900)
    ap.add_argument("--appstack", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--appboot", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--crc-only", action="store_true")
    a = ap.parse_args()

    code = open(a.code, "rb").read()
    print(f"code: {len(code)} bytes")
    print("  CRC-16 (identified family algorithm):")
    for name in CRC16_NAMES:
        print(f"    crc16/{name:11}: {crc16_variant(code, name):04x}")
    print("  CRC-32 (reference/fallback):")
    for name in CRC32_NAMES:
        print(f"    crc32/{name:11}: {crc32_variant(code, name):08x}")
    if a.crc_only or not a.out:
        return
    img, val = build(code, a.crc, a.projid, a.boot, a.stack, a.app, a.appstack, a.appboot)
    width = 4 if (a.crc in CRC16_NAMES or a.crc == "wrong") else 8
    open(a.out, "wb").write(img)
    print(f"wrote {a.out}: {len(img)} bytes  (header 16 + code {len(code)}), "
          f"crc/{a.crc}={val:0{width}x}"
          + ("  [DELIBERATELY WRONG CRC]" if a.crc == "wrong" else ""))


if __name__ == "__main__":
    main()
