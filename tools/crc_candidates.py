#!/usr/bin/env python3
"""Enumerate candidate checksum values + 16-byte OTA header fields for a code blob.

Offline, no device. The MSLM707's vendor secondary bootloader (DA14585) checks the 4-byte
field at header offset 12..15 against a checksum it computes over the image. We do NOT know
its algorithm or its range (the device rejects a wrong value silently — no oracle), and the
earlier "CRC-16/XMODEM" guess came from the wrong chip's SDK (MM32/Macrogiga), so it is not
trustworthy here. This tool emits every plausible (algorithm x range) candidate so the
brute-force driver (tools/ota_bruteforce.sh) can try them one by one against a VALID image
(a wrong candidate is rejected and the device stays intact; the right one is accepted and our
code runs — see docs/ota-flash-runbook.md).

Header layout (little-endian), per docs/ota-protocol.md 2.1:
    0..1 projId u16  2 boot u8  3 stack u8  4..5 app u16  6 appStack u8  7 appBoot u8
    8..11 codeSize u32   12..15 checksum (4 bytes)

Usage:
  tools/crc_candidates.py <code.bin>                 # print every candidate (algo/range -> 4-byte field)
  tools/crc_candidates.py <code.bin> --emit <dir> [header opts]   # write one OTA image per candidate
Header opts (defaults = the device's values): --projid 0x2a4b --boot 4 --stack 2 --app 0x6900
                                               --appstack 0 --appboot 0
"""
import argparse
import os
import struct
import sys


# ---- parametric CRC (covers the common 16- and 32-bit models) --------------------------
def _reflect(x, width):
    r = 0
    for i in range(width):
        if x & (1 << i):
            r |= 1 << (width - 1 - i)
    return r


def crc(data, width, poly, init, refin, refout, xorout):
    topbit = 1 << (width - 1)
    mask = (1 << width) - 1
    reg = init
    for b in data:
        if refin:
            b = _reflect(b, 8)
        reg ^= b << (width - 8)
        for _ in range(8):
            reg = ((reg << 1) ^ poly) & mask if reg & topbit else (reg << 1) & mask
    if refout:
        reg = _reflect(reg, width)
    return (reg ^ xorout) & mask


# (name, width, poly, init, refin, refout, xorout)
CRC_MODELS = [
    # 16-bit, CCITT poly 0x1021
    ("crc16/xmodem",      16, 0x1021, 0x0000, False, False, 0x0000),
    ("crc16/ccitt-false", 16, 0x1021, 0xFFFF, False, False, 0x0000),
    ("crc16/kermit",      16, 0x1021, 0x0000, True,  True,  0x0000),
    ("crc16/x25",         16, 0x1021, 0xFFFF, True,  True,  0xFFFF),
    ("crc16/mcrf4xx",     16, 0x1021, 0xFFFF, True,  True,  0x0000),
    ("crc16/genibus",     16, 0x1021, 0xFFFF, False, False, 0xFFFF),
    ("crc16/aug-ccitt",   16, 0x1021, 0x1D0F, False, False, 0x0000),
    # 16-bit, IBM/ARC poly 0x8005
    ("crc16/arc",         16, 0x8005, 0x0000, True,  True,  0x0000),
    ("crc16/modbus",      16, 0x8005, 0xFFFF, True,  True,  0x0000),
    ("crc16/usb",         16, 0x8005, 0xFFFF, True,  True,  0xFFFF),
    ("crc16/maxim",       16, 0x8005, 0x0000, True,  True,  0xFFFF),
    # 32-bit
    ("crc32/zlib",        32, 0x04C11DB7, 0xFFFFFFFF, True,  True,  0xFFFFFFFF),
    ("crc32/bzip2",       32, 0x04C11DB7, 0xFFFFFFFF, False, False, 0xFFFFFFFF),
    ("crc32/mpeg2",       32, 0x04C11DB7, 0xFFFFFFFF, False, False, 0x00000000),
    ("crc32/posix",       32, 0x04C11DB7, 0x00000000, False, False, 0xFFFFFFFF),
    ("crc32/jamcrc",      32, 0x04C11DB7, 0xFFFFFFFF, True,  True,  0x00000000),
]


def simple_sums(data):
    """Additive / xor checksums some basic bootloaders use."""
    return {
        "sum8":   sum(data) & 0xFF,
        "sum16":  sum(data) & 0xFFFF,
        "sum32":  sum(data) & 0xFFFFFFFF,
        "xor8":   _xor8(data),
    }


def _xor8(data):
    x = 0
    for b in data:
        x ^= b
    return x


def field_bytes(value, width):
    """4-byte header field (12..15): value LE in its own width, zero-padded to 4 bytes."""
    if width == 16:
        return struct.pack("<H", value & 0xFFFF) + b"\x00\x00"
    if width == 32:
        return struct.pack("<I", value & 0xFFFFFFFF)
    if width == 8:
        return bytes([value & 0xFF]) + b"\x00\x00\x00"
    raise ValueError(width)


def ranges(code, header12):
    """Plausible byte ranges the device might checksum. header12 = header bytes 0..11 (no crc)."""
    return {
        "code":        bytes(code),                         # most likely: code only
        "hdr+code":    bytes(header12) + bytes(code),       # 12-byte header (no crc) + code
        "code+size":   bytes(code) + struct.pack("<I", len(code)),
    }


def candidates(code, header12):
    """Yield (label, 4-byte-field) for every (algo x range)."""
    for rname, data in ranges(code, header12).items():
        for name, w, poly, init, rin, rout, xout in CRC_MODELS:
            v = crc(data, w, poly, init, rin, rout, xout)
            yield (f"{name}@{rname}", field_bytes(v, w), f"{v:0{w // 4}x}")
        for name, v in simple_sums(data).items():
            w = 8 if name == "sum8" or name == "xor8" else (16 if name == "sum16" else 32)
            yield (f"{name}@{rname}", field_bytes(v, w), f"{v:0{max(2, w // 4)}x}")


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("code")
    ap.add_argument("--emit", metavar="DIR", help="write one OTA image per candidate into DIR")
    ap.add_argument("--projid", type=lambda x: int(x, 0), default=0x2A4B)
    ap.add_argument("--boot", type=lambda x: int(x, 0), default=4)
    ap.add_argument("--stack", type=lambda x: int(x, 0), default=2)
    ap.add_argument("--app", type=lambda x: int(x, 0), default=0x6900)
    ap.add_argument("--appstack", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--appboot", type=lambda x: int(x, 0), default=0)
    a = ap.parse_args()

    code = open(a.code, "rb").read()
    header12 = struct.pack("<HBBHBBI", a.projid, a.boot, a.stack, a.app, a.appstack, a.appboot, len(code))

    cands = list(candidates(code, header12))
    print(f"code: {len(code)} bytes  ->  {len(cands)} candidates "
          f"({len(CRC_MODELS) + 4} algos x {len(ranges(code, header12))} ranges)")
    if a.emit:
        os.makedirs(a.emit, exist_ok=True)
    seen = {}
    idx = 0
    for label, field, pretty in cands:
        key = field.hex()
        dup = f"  (== {seen[key]})" if key in seen else ""
        seen.setdefault(key, label)
        print(f"  [{idx:02d}] {label:28} value={pretty:8} field12_15={field.hex(' ')}{dup}")
        if a.emit:
            img = header12 + field + code
            safe = label.replace("/", "-").replace("@", "_")
            with open(os.path.join(a.emit, f"{idx:02d}_{safe}.bin"), "wb") as f:
                f.write(img)
        idx += 1
    if a.emit:
        print(f"wrote {idx} images to {a.emit}/  (header 16 + code {len(code)})")


if __name__ == "__main__":
    main()
