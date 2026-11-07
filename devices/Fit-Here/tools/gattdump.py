#!/usr/bin/env python3
"""Connect to a BLE device and print its GATT table, reading every readable value.

usage: gattdump.py <MAC>

Talks to BlueZ over D-Bus (python3-dbus). If BlueZ does not know the device yet it
runs a discovery of up to 30 s first. Leaves the device connected.
"""
import sys
import time

import dbus

MAC = sys.argv[1]
bus = dbus.SystemBus()
path = "/org/bluez/hci0/dev_" + MAC.replace(":", "_")
om = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
adapter = dbus.Interface(bus.get_object("org.bluez", "/org/bluez/hci0"), "org.bluez.Adapter1")


def objects():
    return om.GetManagedObjects()


if path not in objects():
    adapter.StartDiscovery()
    for _ in range(30):
        time.sleep(1)
        if path in objects():
            break
    adapter.StopDiscovery()

dev = bus.get_object("org.bluez", path)
props = dbus.Interface(dev, "org.freedesktop.DBus.Properties")
for _ in range(5):
    try:
        dbus.Interface(dev, "org.bluez.Device1").Connect()
        break
    except dbus.DBusException as e:
        print("connect error:", e)
        time.sleep(2)
for _ in range(20):
    if props.Get("org.bluez.Device1", "ServicesResolved"):
        break
    time.sleep(0.5)

d = props.GetAll("org.bluez.Device1")
print("Name", d.get("Name"), "RSSI", d.get("RSSI"), "Modalias", d.get("Modalias"))
print("UUIDs", [str(u) for u in d.get("UUIDs", [])])
for p, ifaces in sorted(objects().items()):
    if not p.startswith(path + "/"):
        continue
    if "org.bluez.GattService1" in ifaces:
        print("SERVICE", ifaces["org.bluez.GattService1"]["UUID"], p[len(path):])
    if "org.bluez.GattCharacteristic1" in ifaces:
        c = ifaces["org.bluez.GattCharacteristic1"]
        flags = [str(f) for f in c["Flags"]]
        val = ""
        if "read" in flags:
            try:
                v = bytes(dbus.Interface(bus.get_object("org.bluez", p),
                                         "org.bluez.GattCharacteristic1").ReadValue({}))
                val = v.hex() + "  " + repr(v)
            except dbus.DBusException as e:
                val = "ERR " + str(e)[:60]
        print("   CHAR", c["UUID"], flags, val)
    if "org.bluez.GattDescriptor1" in ifaces:
        desc = ifaces["org.bluez.GattDescriptor1"]["UUID"]
        val = ""
        if str(desc).startswith("00002901"):   # user description: readable text
            try:
                val = repr(bytes(dbus.Interface(bus.get_object("org.bluez", p),
                                                "org.bluez.GattDescriptor1").ReadValue({})))
            except dbus.DBusException as e:
                val = "ERR " + str(e)[:60]
        print("      DESC", desc, val)
