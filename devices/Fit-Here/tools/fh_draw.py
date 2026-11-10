#!/usr/bin/env python3
"""Draw on the Fit-Here display through the demo firmware (FH-DEMO).

usage: fh_draw.py [--offset X,Y] test | art | clear [RGB565] | image FILE | raw HEX

  test   frame and coloured corners, to check where the 80x160 glass sits in the panel memory
  art    a drawing made here, no input file
  clear  fills the screen, black by default
  image  scales FILE to 80x160; flat colours send fast, photos need thousands of packets
  raw    sends one controller command without resetting, e.g. raw 21

Every mode but raw resets and clears the display first.
Needs the adapter free: no other BLE tool at the same time.
"""
import argparse
import os
import sys
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
from fh_display_search import Band  # noqa: E402

WIDTH, HEIGHT = 80, 160
MEMORY_WIDTH, MEMORY_HEIGHT = 132, 162   # what the controller holds, larger than the glass
EVENTS = "4c500003"
SYNC = 0x45
SYNC_EVERY = 16     # the firmware queues 32 commands
RUNS_PER_PACKET = 6 # 3 bytes each, 20 bytes per write
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def rgb565(r, g, b):
    return (r & 0xf8) << 8 | (g & 0xfc) << 3 | b >> 3


def runs_of(image):
    """(count, colour) along the scan order, counts up to 255."""
    runs = []
    for r, g, b in image.convert("RGB").getdata():
        colour = rgb565(r, g, b)
        if runs and runs[-1][1] == colour and runs[-1][0] < 255:
            runs[-1][0] += 1
        else:
            runs.append([1, colour])
    return runs


class Screen:
    def __init__(self, offset):
        self.dx, self.dy = offset
        self.sent = 0
        self.synced = False
        self.band = Band()
        self.band.connect()
        found = [p for p, i in self.band.om.GetManagedObjects().items()
                 if p.startswith(self.band.path + "/") and "org.bluez.GattCharacteristic1" in i
                 and str(i["org.bluez.GattCharacteristic1"]["UUID"]).startswith(EVENTS)]
        if not found:
            sys.exit("events characteristic not found: this firmware is too old?")
        self.band.bus.add_signal_receiver(self.on_event, "PropertiesChanged",
                                          "org.freedesktop.DBus.Properties", path=found[0])
        dbus.Interface(self.band.bus.get_object("org.bluez", found[0]),
                       "org.bluez.GattCharacteristic1").StartNotify()
        time.sleep(1.5)   # the subscription reaches the device a moment after StartNotify returns

    def on_event(self, interface, changed, _invalidated):
        if "Value" in changed and bytes(changed["Value"]) == bytes([SYNC]):
            self.synced = True

    def send(self, data):
        self.band.write(data)
        self.sent += 1
        if self.sent % SYNC_EVERY == 0:
            self.sync()

    def sync(self):
        """Returns once the firmware has drawn everything sent so far."""
        self.synced = False
        self.band.write([SYNC])
        context = GLib.MainContext.default()
        deadline = time.time() + 10
        while not self.synced:
            if time.time() > deadline:
                sys.exit("no answer from the firmware: is this the drawing build?")
            if not context.iteration(False):
                time.sleep(0.002)

    def fill_memory(self, colour=0):
        self.send([0x42, 0, 0, MEMORY_WIDTH, MEMORY_HEIGHT, colour >> 8, colour & 255])

    def rect(self, x, y, w, h, colour):
        self.send([0x42, x + self.dx, y + self.dy, w, h, colour >> 8, colour & 255])

    def reset(self):
        self.send([0x40])
        self.fill_memory()

    def picture(self, image):
        runs = runs_of(image)
        print(len(runs), "runs,", (len(runs) + 5) // RUNS_PER_PACKET, "packets", flush=True)
        self.send([0x43, self.dx, self.dy, WIDTH, HEIGHT])
        for i in range(0, len(runs), RUNS_PER_PACKET):
            packet = [0x44]
            for count, colour in runs[i:i + RUNS_PER_PACKET]:
                packet += [count, colour >> 8, colour & 255]
            self.send(packet)
            if i % (RUNS_PER_PACKET * 80) == 0:
                print(f"  {i * 100 // len(runs)}%", flush=True)

    def close(self):
        self.sync()
        self.band.dev1.Disconnect()


def test_pattern(screen):
    white, red, green, blue = 0xffff, 0xf800, 0x07e0, 0x001f
    screen.rect(0, 0, WIDTH, 1, white)
    screen.rect(0, HEIGHT - 1, WIDTH, 1, white)
    screen.rect(0, 0, 1, HEIGHT, white)
    screen.rect(WIDTH - 1, 0, 1, HEIGHT, white)
    screen.rect(4, 4, 16, 16, red)
    screen.rect(WIDTH - 20, 4, 16, 16, green)
    screen.rect(4, HEIGHT - 20, 16, 16, blue)


def art():
    """A sun over the sea, and a greeting: flat colours keep it to a few hundred packets."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (10, 20, 70))
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"
    draw.ellipse((15, 12, 65, 62), fill=(255, 190, 0))
    draw.rectangle((0, 100, WIDTH, HEIGHT), fill=(0, 120, 160))
    for y, x in ((108, 8), (120, 38), (132, 14), (144, 44)):
        draw.line((x, y, x + 24, y), fill=(200, 240, 255), width=2)
    font = ImageFont.truetype(FONT, 24)
    draw.text((WIDTH / 2, 80), "CIAO", font=font, fill=(255, 255, 255), anchor="mm")
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offset", default="26,1", help="glass position in panel memory")
    parser.add_argument("mode", choices=["test", "art", "clear", "image", "raw"])
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    if args.mode in ("image", "raw") and not args.value:
        parser.error(args.mode + " needs a value")
    screen = Screen(tuple(int(v) for v in args.offset.split(",")))

    if args.mode == "raw":
        screen.send([0x41] + list(bytes.fromhex(args.value)))
    else:
        screen.reset()
    if args.mode == "test":
        test_pattern(screen)
    elif args.mode == "art":
        screen.picture(art())
    elif args.mode == "clear":
        screen.rect(0, 0, WIDTH, HEIGHT, int(args.value or "0", 16))
    elif args.mode == "image":
        screen.picture(Image.open(args.value).convert("RGB").resize((WIDTH, HEIGHT)))
    screen.close()
    print("done", flush=True)


if __name__ == "__main__":
    main()
