#!/usr/bin/env python3
"""Find the Fit-Here key: prints every level change on the candidate pins, read without driving them.

usage: fh_keyfind.py [SECONDS]    default 20

The firmware alternates pull-up and pull-down every 0.5 s. Run it once without touching anything to
see which pins change by themselves, then again while pressing the key.
Needs the demo firmware running and the adapter free.
"""
import os
import sys
import time
from collections import Counter

from gi.repository import GLib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fh_draw import Screen  # noqa: E402

WATCH = 0x24


class Watch(Screen):
    def __init__(self):
        self.counts = Counter()
        super().__init__((0, 0))

    def on_event(self, interface, changed, _invalidated):
        if "Value" not in changed or len(changed["Value"]) != 1:
            return
        value = int(changed["Value"][0])
        pin, pull, level = value & 0x3f, "down" if value & 0x40 else "up", value >> 7
        self.counts[pin, pull] += 1
        print(f"{time.strftime('%H:%M:%S')} P{pin:02d} -> {level}  (pull-{pull})", flush=True)


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20
    watch = Watch()
    watch.band.write([WATCH, 1])
    print(f"watching for {seconds:.0f} s", flush=True)
    context = GLib.MainContext.default()
    end = time.time() + seconds
    while time.time() < end:
        if not context.iteration(False):
            time.sleep(0.005)
    watch.band.write([WATCH, 0])
    print("changes per pin:", dict(watch.counts) or "none", flush=True)
    watch.band.dev1.Disconnect()


if __name__ == "__main__":
    main()
