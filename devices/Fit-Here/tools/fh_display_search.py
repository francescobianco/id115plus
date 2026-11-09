#!/usr/bin/env python3
"""Search the display pins by hand: every Enter tries the next RST/SCK/MOSI combination.

usage: fh_display_search.py [--log FILE] [--dc RST SCK MOSI [--color RGB565]]

With --dc the reset, clock and data pins are given and every Enter tries the next DC pin: the right
one paints a band of that colour, in a row that depends on the pin. The panel keeps its memory, so
changing --color between runs shows the exact step that writes the band.

Needs the demo firmware running (FH-DEMO) and the adapter free: no other BLE tool at the same time.

At the prompt:
  Enter   next combination
  ok      the arrow is on screen: logs the current combination as SEEN
  r       send the current combination again
  b       go back to the previous combination
  q       quit, turning the screen light off

Every combination sent is written to the log, and a later run skips those already tried.
"""
import argparse
import os
import subprocess
import sys
import time

import dbus

MAC = "C0:00:A1:B1:02:64"
CTRL = "4c500002"
# P01 first: the arrow showed up in the runs with reset on P01
RESET_ORDER = [1, 2, 24, 25, 33, 32, 31, 27, 26, 3, 0, 11]
PINS = [24, 25, 33, 32, 31, 27, 26, 3, 2, 1, 0, 11]
MIN_INTERVAL = 0.6     # a trial blocks the firmware for about 0.4 s
DEFAULT_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "display_search.log")


class Band:
    def __init__(self):
        self.bus = dbus.SystemBus()
        self.path = "/org/bluez/hci0/dev_" + MAC.replace(":", "_")
        self.om = dbus.Interface(self.bus.get_object("org.bluez", "/"),
                                 "org.freedesktop.DBus.ObjectManager")
        self.char = None

    def connect(self):
        for attempt in range(1, 16):
            print("connecting, attempt", attempt, flush=True)
            # a scan in its own process right before connecting is what works on this adapter
            subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "scan.py"), "3"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if self.path not in self.om.GetManagedObjects():
                continue
            dev = self.bus.get_object("org.bluez", self.path)
            dev1 = dbus.Interface(dev, "org.bluez.Device1")
            props = dbus.Interface(dev, "org.freedesktop.DBus.Properties")
            try:
                if not props.Get("org.bluez.Device1", "Connected"):
                    dev1.Connect(timeout=15)
                for _ in range(50):
                    if props.Get("org.bluez.Device1", "ServicesResolved"):
                        break
                    time.sleep(0.2)
                else:
                    continue
                self.dev1 = dev1
                found = [p for p, i in self.om.GetManagedObjects().items()
                         if p.startswith(self.path + "/") and "org.bluez.GattCharacteristic1" in i
                         and str(i["org.bluez.GattCharacteristic1"]["UUID"]).startswith(CTRL)]
                if not found:
                    sys.exit("control characteristic not found: is the demo running?")
                self.char = dbus.Interface(self.bus.get_object("org.bluez", found[0]),
                                           "org.bluez.GattCharacteristic1")
                print("connected", flush=True)
                return
            except dbus.DBusException as e:
                print("  failed:", str(e)[-45:], flush=True)
                time.sleep(1)
        sys.exit("could not connect to FH-DEMO")

    def write(self, data):
        try:
            self.char.WriteValue(dbus.ByteArray(bytes(data)), {"type": "request"})
        except dbus.DBusException:
            print("link lost, reconnecting", flush=True)
            self.connect()
            self.char.WriteValue(dbus.ByteArray(bytes(data)), {"type": "request"})

    def close(self):
        try:
            self.char.WriteValue(dbus.ByteArray(bytes([0x21, 0])), {"type": "request"})
            print("screen light off", flush=True)
        except dbus.DBusException:
            print("could not turn the screen light off", flush=True)
        try:
            self.dev1.Disconnect()
        except dbus.DBusException:
            pass


def all_combinations():
    return [(r, s, m) for r in RESET_ORDER for s in PINS if s != r
            for m in PINS if m not in (r, s)]


def dc_combinations(rst, sck, mosi):
    return [(rst, sck, mosi, d) for d in PINS if d not in (rst, sck, mosi)]


def already_sent(path):
    sent = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                p = line.split()
                if p[1:2] == ["sent"]:
                    sent.add(tuple(int(v) for v in p[2:]))
    return sent


def describe(combo):
    text = "RST P%02d  SCK P%02d  MOSI P%02d" % combo[:3]
    return text + ("  DC P%02d" % combo[3] if len(combo) > 3 else "")


def main():
    ap = argparse.ArgumentParser(description="Search the display pins by hand")
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--dc", nargs=3, type=int, metavar=("RST", "SCK", "MOSI"))
    ap.add_argument("--color", type=lambda v: int(v, 16), default=0x07e0,
                    help="RGB565 band colour in hex, default 07e0")
    args = ap.parse_args()
    log_path = os.path.abspath(args.log + ".dc" if args.dc else args.log)

    done = already_sent(log_path)
    candidates = dc_combinations(*args.dc) if args.dc else all_combinations()
    combos = [c for c in candidates if c not in done]
    if not combos:
        sys.exit("every combination is already in " + log_path)
    print(len(done), "already tried,", len(combos), "to go. Log:", log_path)

    band = Band()
    band.connect()
    log = open(log_path, "a", buffering=1)
    last_send = 0.0

    def stamp():
        return time.strftime("%Y-%m-%dT%H:%M:%S")

    def send(index):
        nonlocal last_send
        wait = MIN_INTERVAL - (time.time() - last_send)
        if wait > 0:
            time.sleep(wait)
        combo = combos[index]
        band.write([0x31, *combo, args.color >> 8, args.color & 0xff] if args.dc else [0x30, *combo])
        last_send = time.time()
        log.write("%s sent %s\n" % (stamp(), " ".join(map(str, combo))))
        print("[%d/%d]  %s" % (index + 1, len(combos), describe(combo)), flush=True)

    index = 0
    try:
        send(index)
        while True:
            try:
                answer = input("Invio = prossima, ok = vista, r = ripeti, b = indietro, q = esci > ")
            except EOFError:
                break
            answer = answer.strip().lower()
            if answer == "":
                if index + 1 >= len(combos):
                    print("combinazioni finite")
                    break
                index += 1
                send(index)
            elif answer == "ok":
                log.write("%s SEEN %s\n" % (stamp(), " ".join(map(str, combos[index]))))
                print("*** SEGNATA:", describe(combos[index]), flush=True)
            elif answer == "r":
                send(index)
            elif answer == "b":
                index = max(0, index - 1)
                send(index)
            elif answer == "q":
                break
            else:
                print("comando non riconosciuto")
    except KeyboardInterrupt:
        print()
    finally:
        band.close()
        log.close()


if __name__ == "__main__":
    main()
