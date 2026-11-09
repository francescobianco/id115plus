#!/usr/bin/env python3
"""Plan, and optionally send, an Intel hex image through the PPlusOTA updater.

usage: phy_flash.py image.hex [--bank-offset 0xB000] [--flash-kb 512] [--yes] [--pace-ms 15]

Without --yes this is a dry run: it prints the partitions and every flash sector the updater
would erase, and never touches Bluetooth. With --yes it connects to the updater
(MAC=C0:00:A1:B1:02:62 by default, already in PPlusOTA mode: see phy_ota.py 5833ff02=0102).

START (01) erases the app table at 0x3000, so the stock app stops booting from that moment.
Read the OTA section of ../README.md first.

The updater only checks addresses >= 0x11000000, so nothing on the device stops a partition
from overwriting the boot table (0x2000) or the updater itself (0x5000-0x10fff). The limits
below are enforced here for that reason.
"""
import argparse
import os
import struct
import sys
import time

XIP_MIN = 0x11011000       # below this: boot table, app table, MAC, updater
XIP_BASE = 0x11000000
SRAM_MIN = 0x1fff0000
SRAM_END = 0x1fffb300      # the updater's own RAM starts here on the LP715 dump
BANK_ADDR = 0x11011000     # SDK value for this layout, not read back from this device
BANK_SIZE = 0xf000         # 60 KB, ends where XIP code starts on the LP715
SECTOR = 0x1000
PART_MAX = 0x4000          # the updater buffers one partition in 16 KB of RAM
PACKET = 20
BURST_NONE = 0xff          # acknowledge per partition only

UPDATER_MAC = "C0:00:A1:B1:02:62"
UPDATER_NAME = "PPlusOTA"
UUID_CMD, UUID_RSP, UUID_DATA = "5833ff02", "5833ff03", "5833ff04"
RSP_START, RSP_DONE, RSP_PART_INFO, RSP_PART_DONE, RSP_BURST = 0x81, 0x83, 0x84, 0x85, 0x87

_T = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
      0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]


def crc16(data):
    """The SDK's crc16, seed 0 (checked against the partition CRCs of a stock LP715 table)."""
    crc = 0
    for b in data:
        t = _T[crc & 0xf]
        crc = ((crc >> 4) & 0xfff) ^ t ^ _T[b & 0xf]
        t = _T[crc & 0xf]
        crc = ((crc >> 4) & 0xfff) ^ t ^ _T[b >> 4]
    return crc


def read_hex(path):
    """Contiguous [address, bytearray] segments of an Intel hex file."""
    segs, base = [], 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue
            n, addr, typ = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            data = bytes.fromhex(line[9:9 + 2 * n])
            if typ == 4:
                base = int(line[9:13], 16) << 16
            elif typ == 0:
                a = base + addr
                if segs and segs[-1][0] + len(segs[-1][1]) == a:
                    segs[-1][1].extend(data)
                else:
                    segs.append([a, bytearray(data)])
    return segs


def is_xip(addr):
    return XIP_BASE <= addr < SRAM_MIN


def plan(segs, bank_offset, flash_kb):
    """(flash, run, data) per partition; raises ValueError if any limit is broken."""
    if bank_offset % SECTOR:
        # the updater skips the first partial sector, which would leave stale data under it
        raise ValueError("bank offset 0x%x is not 4 KB aligned" % bank_offset)
    xip_end = XIP_BASE + flash_kb * 1024
    parts, off = [], bank_offset
    for addr, data in segs:
        if len(data) % 4:
            data = data + bytes(4 - len(data) % 4)
        for i in range(0, len(data), PART_MAX):
            chunk, run = bytes(data[i:i + PART_MAX]), addr + i
            if is_xip(run):
                if run < XIP_MIN or run + len(chunk) > xip_end:
                    raise ValueError("XIP partition 0x%08x+0x%x outside 0x%08x-0x%08x"
                                     % (run, len(chunk), XIP_MIN, xip_end))
                parts.append((run, run, chunk))
            else:
                if not SRAM_MIN <= run or run + len(chunk) > SRAM_END:
                    raise ValueError("partition runs at 0x%08x: neither XIP nor SRAM" % run)
                if off + len(chunk) > BANK_SIZE:
                    raise ValueError("SRAM image overflows the app bank (offset 0x%x + 0x%x)"
                                     % (off, len(chunk)))
                parts.append((off, run, chunk))
                off += len(chunk) + 8   # same spacing as the stock table
    if len(parts) > 32:
        raise ValueError("%d partitions, the updater takes 32 at most" % len(parts))
    return parts


def erased_sectors(parts):
    """Flash sectors the updater erases for these partitions, plus the app table."""
    sectors = {0x3000}
    for flash, run, data in parts:
        start = flash if flash == run else BANK_ADDR + flash
        start &= 0xffffff
        first = start if start % SECTOR == 0 else (start & ~0xfff) + SECTOR
        sectors.update(range(first, (start + len(data) + 0xfff) & ~0xfff, SECTOR))
    return sorted(sectors)


def show(parts):
    for i, (flash, run, data) in enumerate(parts):
        where = "xip" if flash == run else "bank+0x%05x" % flash
        print("%2d  run 0x%08x  size 0x%04x  crc 0x%04x  %s"
              % (i, run, len(data), crc16(data), where))
    sectors = erased_sectors(parts)
    print("sectors erased (%d, %d KB):" % (len(sectors), len(sectors) * 4))
    print("  " + " ".join("0x%05x" % s for s in sectors))


class Updater:
    def __init__(self, mac, pace):
        import dbus
        import dbus.mainloop.glib
        from gi.repository import GLib
        self.dbus, self.ctx, self.pace = dbus, GLib.MainContext.default(), pace
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()
        path = "/org/bluez/hci0/dev_" + mac.replace(":", "_")
        dev = self.bus.get_object("org.bluez", path)
        props = dbus.Interface(dev, "org.freedesktop.DBus.Properties")
        if not props.Get("org.bluez.Device1", "Connected"):
            dbus.Interface(dev, "org.bluez.Device1").Connect()
        while not props.Get("org.bluez.Device1", "ServicesResolved"):
            time.sleep(0.3)
        info = props.GetAll("org.bluez.Device1")
        if str(info.get("Name", "")) != UPDATER_NAME:
            sys.exit("%s is not %s: refusing to send" % (mac, UPDATER_NAME))
        objs = dbus.Interface(self.bus.get_object("org.bluez", "/"),
                              "org.freedesktop.DBus.ObjectManager").GetManagedObjects()
        self.chars = {str(i["org.bluez.GattCharacteristic1"]["UUID"])[:8]: p
                      for p, i in objs.items()
                      if p.startswith(path + "/") and "org.bluez.GattCharacteristic1" in i}
        self.rsp = []
        self.bus.add_signal_receiver(self._notify, "PropertiesChanged",
                                     "org.freedesktop.DBus.Properties",
                                     path=self.chars[UUID_RSP])
        self._char(UUID_RSP).StartNotify()
        time.sleep(1.5)   # let the link settle: START blocks the device during a sector erase

    def _char(self, short):
        return self.dbus.Interface(self.bus.get_object("org.bluez", self.chars[short]),
                                   "org.bluez.GattCharacteristic1")

    def _notify(self, _iface, changed, _inv):
        if "Value" in changed:
            self.rsp.append(bytes(changed["Value"]))

    def command(self, data):
        self._char(UUID_CMD).WriteValue(self.dbus.ByteArray(bytes(data)), {"type": "request"})

    def data(self, chunk):
        self._char(UUID_DATA).WriteValue(self.dbus.ByteArray(chunk), {"type": "command"})
        if self.pace:
            time.sleep(self.pace)
        while self.ctx.pending():
            self.ctx.iteration(False)
        for r in self.rsp:
            if r[0]:
                raise RuntimeError("updater error during data: " + r.hex())

    def expect(self, want, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            while self.ctx.pending():
                self.ctx.iteration(False)
            while self.rsp:
                r = self.rsp.pop(0)
                if r[0]:
                    raise RuntimeError("updater error: " + r.hex())
                if len(r) > 1 and r[1] == want:
                    return
                if len(r) > 1 and r[1] != RSP_BURST:
                    raise RuntimeError("expected 0x%02x, got %s" % (want, r.hex()))
            time.sleep(0.01)
        raise RuntimeError("no 0x%02x from the updater in %d s" % (want, timeout))


def send(parts, mac, pace):
    up = Updater(mac, pace)
    up.command([0x01, len(parts), BURST_NONE])
    up.expect(RSP_START)
    for i, (flash, run, data) in enumerate(parts):
        print("partition %d/%d" % (i + 1, len(parts)), flush=True)
        # 16 bytes, CRC as u16: this updater (V3.0.7) ignores the 18-byte form of newer SDKs
        up.command(struct.pack("<BBIIIH", 0x02, i, flash, run, len(data), crc16(data)))
        up.expect(RSP_PART_INFO)
        print("  accepted, sending %d bytes" % len(data), flush=True)
        for off in range(0, len(data), PACKET):
            up.data(bytes(data[off:off + PACKET]))
        up.expect(RSP_DONE if i == len(parts) - 1 else RSP_PART_DONE, timeout=30)
    print("all partitions written; reboot with: MAC=%s phy_ota.py 5833ff02=0401" % mac)


def main():
    ap = argparse.ArgumentParser(description="PPlusOTA image planner and sender")
    ap.add_argument("image")
    ap.add_argument("--bank-offset", type=lambda s: int(s, 0), default=0,
                    help="where SRAM partitions go in the app bank (default 0: over the stock ones)")
    ap.add_argument("--flash-kb", type=int, default=512, choices=(256, 512))
    ap.add_argument("--confine", metavar="LOW:HIGH",
                    help="refuse the image if it erases flash outside LOW:HIGH (0x3000 excepted)")
    ap.add_argument("--pace-ms", type=int, default=15)
    ap.add_argument("--yes", action="store_true", help="really send: erases the app table")
    args = ap.parse_args()
    try:
        parts = plan(read_hex(args.image), args.bank_offset, args.flash_kb)
    except ValueError as e:
        sys.exit("REFUSED: %s" % e)
    show(parts)
    if args.confine:
        low, high = (int(x, 0) for x in args.confine.split(":"))
        outside = [s for s in erased_sectors(parts) if s != 0x3000 and not low <= s < high]
        if outside:
            sys.exit("REFUSED: erases outside the allowed range: "
                     + " ".join("0x%05x" % s for s in outside))
    if not args.yes:
        print("dry run: nothing sent (--yes to send)")
        return
    try:
        send(parts, os.environ.get("MAC", UPDATER_MAC), args.pace_ms / 1000)
    except Exception as e:   # includes D-Bus errors: a dropped link shows up as ATT 0x0e
        sys.exit("FAILED: %s\nThe updater stays available: fix the cause and send again." % e)


if __name__ == "__main__":
    main()
