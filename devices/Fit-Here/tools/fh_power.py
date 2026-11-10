#!/usr/bin/env python3
"""Read the Fit-Here battery voltage and the charger input through the demo firmware.

usage: fh_power.py [SECONDS] [INTERVAL]    default: 3 readings over 6 s, one every 2 s

The battery value uses the stock firmware's divider constant (P14 x 5.5454).
Needs the adapter free: no other BLE tool at the same time.
"""
import os
import sys
import time

from gi.repository import GLib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fh_draw import Screen  # noqa: E402

MEASURE = 0x23
DIVIDER = 5.5454
FRAME = 4


class Power(Screen):
    def __init__(self):
        self.bytes = []
        super().__init__((0, 0))

    def on_event(self, interface, changed, _invalidated):
        if "Value" in changed and len(changed["Value"]) == 1:
            self.bytes.append(int(changed["Value"][0]))

    def read(self):
        """(pin mV or None, P15 level); None if no complete answer arrived."""
        self.bytes = []
        self.band.write([MEASURE])
        context = GLib.MainContext.default()
        deadline = time.time() + 5
        while len(self.bytes) < FRAME:
            if time.time() > deadline:
                return None
            if not context.iteration(False):
                time.sleep(0.002)
        marker, low, high, level = self.bytes[:FRAME]
        if marker != MEASURE:
            return None
        pin_mv = low | high << 8
        return None if pin_mv == 0xffff else pin_mv, level


def main():
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 6
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 2
    power = Power()
    end = time.time() + duration
    while True:
        result = power.read()
        stamp = time.strftime("%H:%M:%S")
        if result is None:
            print(stamp, "no answer", flush=True)
        elif result[0] is None:
            print(stamp, "ADC failed, P15 =", result[1], flush=True)
        else:
            pin_mv, level = result
            print(f"{stamp} P14 {pin_mv} mV  battery {pin_mv * DIVIDER / 1000:.3f} V  P15 {level}", flush=True)
        if time.time() >= end:
            break
        time.sleep(interval)
    power.band.dev1.Disconnect()


if __name__ == "__main__":
    main()
