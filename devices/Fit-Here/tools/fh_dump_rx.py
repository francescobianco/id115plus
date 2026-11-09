#!/usr/bin/env python3
"""Collect the flash broadcast by the Fit-Here dumper (../firmware/dumper).

usage: fh_dump_rx.py out.bin

Listens to C0:00:A1:B1:02:63 and stores every frame. Progress is saved in out.bin and
out.bin.seen, so it can be stopped and restarted, also across several runs of the dumper.
Stop with Ctrl+C. Blocks never received stay 0xFF in out.bin: check the final count.

A block is "confirmed" once two receptions agree.
"""
import os
import sys
import time

FLASH_SIZE = 0x80000
BLOCK = 24
BLOCKS = (FLASH_SIZE + BLOCK - 1) // BLOCK
COMPANY = 0x4648
MAC = "C0:00:A1:B1:02:63"


class Collector:
    def __init__(self):
        self.data = bytearray(b"\xff" * (BLOCKS * BLOCK))
        self.seen = bytearray(BLOCKS)
        self.conflicts = 0
        self.frames = 0

    def feed(self, frame):
        """frame: the 27 bytes after the company id (index LE, pass, 24 bytes of flash)."""
        if len(frame) != 3 + BLOCK:
            return
        i = frame[0] | frame[1] << 8
        if i >= BLOCKS:
            return
        self.frames += 1
        off, payload = i * BLOCK, bytes(frame[3:])
        if self.seen[i] and self.data[off:off + BLOCK] != payload:
            self.conflicts += 1
            self.seen[i] = 0
        self.data[off:off + BLOCK] = payload
        self.seen[i] = min(self.seen[i] + 1, 255)

    def counts(self):
        return sum(1 for s in self.seen if s), sum(1 for s in self.seen if s >= 2)

    def load(self, path):
        if os.path.exists(path) and os.path.exists(path + ".seen"):
            with open(path, "rb") as f:
                self.data[:] = f.read().ljust(BLOCKS * BLOCK, b"\xff")[:BLOCKS * BLOCK]
            with open(path + ".seen", "rb") as f:
                self.seen[:] = f.read().ljust(BLOCKS, b"\0")[:BLOCKS]

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.data[:FLASH_SIZE])
        with open(path + ".seen", "wb") as f:
            f.write(self.seen)


def run(path):
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib

    col = Collector()
    col.load(path)
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = dbus.Interface(bus.get_object("org.bluez", "/org/bluez/hci0"),
                             "org.bluez.Adapter1")
    dev_path = "/org/bluez/hci0/dev_" + MAC.replace(":", "_")

    def take(mdata):
        for company, value in mdata.items():
            if int(company) == COMPANY:
                col.feed(bytes(value))

    def on_change(_iface, changed, _inv):
        if "ManufacturerData" in changed:
            take(changed["ManufacturerData"])

    def on_added(path_, ifaces):
        if str(path_) == dev_path and "org.bluez.Device1" in ifaces:
            take(ifaces["org.bluez.Device1"].get("ManufacturerData", {}))

    bus.add_signal_receiver(on_change, "PropertiesChanged", "org.freedesktop.DBus.Properties",
                            path=dev_path)
    bus.add_signal_receiver(on_added, "InterfacesAdded", "org.freedesktop.DBus.ObjectManager")
    adapter.SetDiscoveryFilter({"Transport": "le", "DuplicateData": dbus.Boolean(True)})
    adapter.StartDiscovery()

    def report():
        got, ok = col.counts()
        print("%s frames %d  blocks %d/%d  confirmed %d  conflicts %d"
              % (time.strftime("%H:%M:%S"), col.frames, got, BLOCKS, ok, col.conflicts), flush=True)
        col.save(path)
        return True

    GLib.timeout_add_seconds(15, report)
    print("listening for", MAC, flush=True)
    try:
        GLib.MainLoop().run()
    except KeyboardInterrupt:
        pass
    finally:
        adapter.StopDiscovery()
        report()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    run(sys.argv[1])
