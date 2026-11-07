#!/usr/bin/env python3
"""LE scan that prints Fit-Here, its updater and other PhyPlus devices.

usage: scan.py [seconds=15] [--all]

Prints a device each time its address, name or manufacturer data changes. By default
it only shows devices with PhyPlus manufacturer data (0x0504, e.g. the `PPlusOTA`
updater), addresses starting with C0:00:A1 (this band) and devices without a name;
--all prints everything.
"""
import sys
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

PHYPLUS_ID = 0x0504

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
args = [a for a in sys.argv[1:] if not a.startswith("--")]
secs = int(args[0]) if args else 15
show_all = "--all" in sys.argv

bus = dbus.SystemBus()
adapter = dbus.Interface(bus.get_object("org.bluez", "/org/bluez/hci0"), "org.bluez.Adapter1")
adapter.SetDiscoveryFilter({"Transport": "le", "DuplicateData": True})
seen = set()


def show(p):
    addr = str(p.get("Address", "?"))
    mfr = {int(k): bytes(v).hex() for k, v in p.get("ManufacturerData", {}).items()}
    key = (addr, str(p.get("Name", "")), str(mfr))
    if key in seen:
        return
    seen.add(key)
    if show_all or PHYPLUS_ID in mfr or addr.startswith("C0:00:A1") or "Name" not in p:
        print(time.strftime("%H:%M:%S"), addr, p.get("AddressType", ""),
              "name=", p.get("Name", None), "rssi=", p.get("RSSI", None),
              "mfr=", mfr, "uuids=", [str(u)[:8] for u in p.get("UUIDs", [])], flush=True)


def added(_path, ifaces):
    if "org.bluez.Device1" in ifaces:
        show(ifaces["org.bluez.Device1"])


def changed(iface, ch, _inv, path=None):
    if iface == "org.bluez.Device1" and ("RSSI" in ch or "ManufacturerData" in ch):
        show(bus.get_object("org.bluez", path).GetAll(
            "org.bluez.Device1", dbus_interface="org.freedesktop.DBus.Properties"))


om = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
om.connect_to_signal("InterfacesAdded", added)
bus.add_signal_receiver(changed, "PropertiesChanged", "org.freedesktop.DBus.Properties",
                        path_keyword="path")
adapter.StartDiscovery()
loop = GLib.MainLoop()
GLib.timeout_add(secs * 1000, loop.quit)
loop.run()
try:
    adapter.StopDiscovery()
except dbus.DBusException:
    pass
