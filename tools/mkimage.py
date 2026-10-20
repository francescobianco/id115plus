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
    off 12..15 crc32      4 bytes  (verified by the device; variant still unknown)

Device parameters observed in Fase 2 (docs/device-ota-params.md) are the defaults:
projId=0x2a4b boot=4 stack=2 app=0x6900 appStack=0 appBoot=0.

Since the exact CRC32 variant the bootloader checks is not yet known, this tool can emit
the image with any of several candidate CRC variants (or a deliberately wrong CRC for a
safe dry-run), and prints all candidates so they can be compared against a reference image.

Usage:
  tools/mkimage.py <code.bin> <out.bin> [--crc VARIANT] [--projid 0x2a4b] [--boot 4]
                   [--stack 2] [--app 0x6900] [--appstack 0] [--appboot 0]
  tools/mkimage.py <code.bin> --crc-only        # just print candidate CRCs of the code
VARIANT: zlib (default) | bzip2 | mpeg2 | posix | wrong   (see crc32 table printed at run)
"""
import argparse
import struct
import sys
import zlib


def crc32_variant(data, name):
    """A few common CRC-32 variants. 'wrong' is zlib with bits flipped (for a safe dry-run)."""
    if name == "zlib":  # CRC-32/ISO-HDLC: refin/refout, init/xorout 0xFFFFFFFF
        return zlib.crc32(data) & 0xFFFFFFFF
    if name == "bzip2":  # CRC-32/BZIP2: no reflect, init/xorout 0xFFFFFFFF
        return _crc(data, 0x04C11DB7, 0xFFFFFFFF, False, 0xFFFFFFFF)
    if name == "mpeg2":  # CRC-32/MPEG-2: no reflect, init 0xFFFFFFFF, xorout 0
        return _crc(data, 0x04C11DB7, 0xFFFFFFFF, False, 0x00000000)
    if name == "posix":  # CRC-32/CKSUM: no reflect, init 0, xorout 0xFFFFFFFF
        return _crc(data, 0x04C11DB7, 0x00000000, False, 0xFFFFFFFF)
    if name == "wrong":
        return (zlib.crc32(data) ^ 0xFFFFFFFF) & 0xFFFFFFFF
    raise SystemExit(f"unknown crc variant: {name}")


def _crc(data, poly, init, refl, xorout):
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


def build(code, crc_name, projid, boot, stack, app, appstack, appboot):
    crc = crc32_variant(code, crc_name)
    header = struct.pack("<HBBHBBI", projid, boot, stack, app, appstack, appboot, len(code))
    header += struct.pack("<I", crc)  # crc32 stored little-endian; swap here if a ref says BE
    return header + code, crc


def main():
    ap = argparse.ArgumentParser(add_help=True, usage=__doc__)
    ap.add_argument("code")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--crc", default="zlib")
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
    for name in ("zlib", "bzip2", "mpeg2", "posix"):
        print(f"  crc32/{name:6}: {crc32_variant(code, name):08x}")
    if a.crc_only or not a.out:
        return
    img, crc = build(code, a.crc, a.projid, a.boot, a.stack, a.app, a.appstack, a.appboot)
    open(a.out, "wb").write(img)
    print(f"wrote {a.out}: {len(img)} bytes  (header 16 + code {len(code)}), "
          f"crc32/{a.crc}={crc:08x}"
          + ("  [DELIBERATELY WRONG CRC]" if a.crc == "wrong" else ""))


if __name__ == "__main__":
    main()
