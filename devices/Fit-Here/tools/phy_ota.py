#!/usr/bin/env python3
"""Send raw commands to the PhyPlus OTA service (5833ff01-...) and print the notifications.

usage: phy_ota.py [--unsafe] <char>=<hex> [<char>=<hex> ...]

  <char> is the first 8 hex digits of the characteristic UUID:
    5833ff02  command (write with response)
    5833ff04  data, updater only (write without response)
    00002d01  stock app protocol, Fit-Here app only (write without response)
  Responses come from 5833ff03 and, on the app, from 00002d00.

  MAC=C0:00:A1:B1:02:61  stock app (default)
  MAC=C0:00:A1:B1:02:62  updater `PPlusOTA` (app MAC + 1)

Examples (see ../README.md):
  phy_ota.py 5833ff02=02                          # app: INFO -> BD addr + "V3.0.7"
  phy_ota.py 5833ff02=0102                        # app: reboot into the updater
  MAC=C0:00:A1:B1:02:62 phy_ota.py 5833ff02=0401  # updater: back to the app on disconnect

Command 01 sent to the UPDATER (START_OTA) erases the app table at 0x3000: the stock app
no longer boots until a full image has been written. It is refused unless --unsafe is given.
"""
import os
import sys
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

APP_MAC = "C0:00:A1:B1:02:61"
UPDATER_NAME = "PPlusOTA"

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
unsafe = "--unsafe" in sys.argv
steps = [a for a in sys.argv[1:] if not a.startswith("--")]
if not steps:
    sys.exit(__doc__)
MAC = os.environ.get("MAC", APP_MAC)

bus = dbus.SystemBus()
path = "/org/bluez/hci0/dev_" + MAC.replace(":", "_")
dev = bus.get_object("org.bluez", path)
props = dbus.Interface(dev, "org.freedesktop.DBus.Properties")
if not props.Get("org.bluez.Device1", "Connected"):
    dbus.Interface(dev, "org.bluez.Device1").Connect()
while not props.Get("org.bluez.Device1", "ServicesResolved"):
    time.sleep(0.3)
dev_props = props.GetAll("org.bluez.Device1")
# the updater advertises as PPlusOTA with PhyPlus manufacturer data (0x0504); the app uses 0x00c0
is_updater = (str(dev_props.get("Name", "")) == UPDATER_NAME
              or 0x0504 in {int(k) for k in dev_props.get("ManufacturerData", {})})
print("connected to", MAC, "(updater)" if is_updater else "(app)", flush=True)

objs = dbus.Interface(bus.get_object("org.bluez", "/"),
                      "org.freedesktop.DBus.ObjectManager").GetManagedObjects()
chars = {str(i["org.bluez.GattCharacteristic1"]["UUID"])[:8]: p for p, i in objs.items()
         if p.startswith(path + "/") and "org.bluez.GattCharacteristic1" in i}


def char(short):
    return dbus.Interface(bus.get_object("org.bluez", chars[short]), "org.bluez.GattCharacteristic1")


def on_notify(short):
    def handler(_iface, changed, _inv):
        if "Value" in changed:
            v = bytes(changed["Value"])
            print(time.strftime("%H:%M:%S"), short, "<", v.hex(), repr(v), flush=True)
    return handler


for short in ("5833ff03", "00002d00"):
    if short in chars:
        bus.add_signal_receiver(on_notify(short), "PropertiesChanged",
                                "org.freedesktop.DBus.Properties", path=chars[short])
        char(short).StartNotify()

loop = GLib.MainLoop()


def next_step():
    if not steps:
        GLib.timeout_add(2500, loop.quit)
        return False
    short, hexdata = steps.pop(0).split("=")
    data = bytes.fromhex(hexdata)
    if is_updater and short == "5833ff02" and data[:1] == b"\x01" and not unsafe:
        print("REFUSED: 01 in the updater erases the app table (pass --unsafe)", flush=True)
        return True
    no_response = short in ("5833ff04", "00002d01")
    print(time.strftime("%H:%M:%S"), short, ">", hexdata, flush=True)
    try:
        char(short).WriteValue(dbus.ByteArray(data),
                               {"type": "command" if no_response else "request"})
    except dbus.DBusException as e:
        # 0x0e right after `01 02` on the app is expected: it resets before acking
        print("   write error:", str(e)[-60:], flush=True)
    return True


GLib.timeout_add(1500, next_step)
loop.run()
