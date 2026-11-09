#!/usr/bin/env python3
"""Collect the dumper's broadcast from a raw HCI socket, with duplicate filtering off.

usage: sudo python3 fh_dump_hci.py out.bin [hci-index]

BlueZ keeps the controller's duplicate filter on, and with a fixed address that lets through
about one frame per scan, so fh_dump_rx.py cannot keep up. Needs root for the raw socket.

While it runs bluetoothd is STOPPED and the adapter reset, because pending LE connections make
the controller refuse scan commands (status 0x0c): every Bluetooth device on this adapter drops
until the end. bluetoothd is started again on exit. Close the GNOME Bluetooth panel first.
Stop with Ctrl+C. Progress goes to out.bin and out.bin.seen, shared with fh_dump_rx.py.
"""
import importlib.util
import os
import socket
import struct
import subprocess
import sys
import time

_spec = importlib.util.spec_from_file_location(
    "fh_dump_rx", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fh_dump_rx.py"))
_rx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rx)

SOL_HCI, HCI_FILTER = 0, 2
HCI_EVENT_PKT, EVT_LE_META, LE_ADV_REPORT = 0x04, 0x3e, 0x02
ADDR = bytes.fromhex("6302b1a100c0")   # C0:00:A1:B1:02:63, little endian
SCAN_MS = 0x0010                       # 10 ms interval and window: always listening


stats = {"reports": 0}
HCI_CMD_COMPLETE = 0x0e


def command_status(pkt):
    """(ocf, status) of an LE command-complete event, or None."""
    if len(pkt) >= 7 and pkt[0] == HCI_EVENT_PKT and pkt[1] == HCI_CMD_COMPLETE and pkt[5] >> 2 == 0x08:
        return (pkt[4] | pkt[5] << 8) & 0x3ff, pkt[6]
    return None


def frames_in_event(pkt):
    """Yield the 27-byte dumper frames in one raw HCI event packet."""
    if len(pkt) < 5 or pkt[0] != HCI_EVENT_PKT or pkt[1] != EVT_LE_META or pkt[3] != LE_ADV_REPORT:
        return
    pos, count = 5, pkt[4]
    for _ in range(count):
        if pos + 9 > len(pkt):
            return
        stats["reports"] += 1
        addr, dlen = pkt[pos + 2:pos + 8], pkt[pos + 8]
        data = pkt[pos + 9:pos + 9 + dlen]
        pos += 9 + dlen + 1
        if addr != ADDR:
            continue
        i = 0
        while i + 1 < len(data):
            ln = data[i]
            if ln == 0:
                break
            if data[i + 1] == 0xff and ln >= 3 and data[i + 2] | data[i + 3] << 8 == _rx.COMPANY:
                yield bytes(data[i + 4:i + 1 + ln])
            i += 1 + ln


def command(sock, ocf, params=b""):
    sock.send(struct.pack("<BHB", 1, 0x08 << 10 | ocf, len(params)) + params)
    time.sleep(0.05)


def start_scan(sock):
    command(sock, 0x0c, b"\x00\x00")     # scan off, it may be running
    command(sock, 0x0b, struct.pack("<BHHBB", 0, SCAN_MS, SCAN_MS, 0, 0))
    command(sock, 0x0c, b"\x01\x00")     # scan on, duplicate filter off


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    path, dev = sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else 0
    col = _rx.Collector()
    col.load(path)
    subprocess.run(["systemctl", "stop", "bluetooth.service"], check=False)
    subprocess.run(["hciconfig", "hci%d" % dev, "down"], check=False)
    subprocess.run(["hciconfig", "hci%d" % dev, "up"], check=True)
    time.sleep(1)
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
    sock.bind((dev,))
    sock.setsockopt(SOL_HCI, HCI_FILTER,
                    struct.pack("<IIIH2x", 1 << HCI_EVENT_PKT, 1 << HCI_CMD_COMPLETE,
                                1 << (EVT_LE_META - 32), 0))
    sock.settimeout(1)
    start_scan(sock)
    print("scanning on hci%d, Ctrl+C to stop" % dev, flush=True)

    last, last_frames = time.time(), col.frames
    try:
        while True:
            try:
                pkt = sock.recv(300)
                status = command_status(pkt)
                if status and status[0] in (0x0b, 0x0c) and status[1]:
                    print("HCI LE command 0x%02x failed: status 0x%02x" % status, flush=True)
                for frame in frames_in_event(pkt):
                    col.feed(frame)
            except socket.timeout:
                pass
            if time.time() - last >= 15:
                got, ok = col.counts()
                print("%s  %.1f frames/s  all adv reports %d  blocks %d/%d  confirmed %d  conflicts %d"
                      % (time.strftime("%H:%M:%S"), (col.frames - last_frames) / (time.time() - last),
                         stats["reports"], got, _rx.BLOCKS, ok, col.conflicts), flush=True)
                reports, stats["reports"] = stats["reports"], 0
                col.save(path)
                last, last_frames = time.time(), col.frames
                if not reports:
                    start_scan(sock)
    except KeyboardInterrupt:
        pass
    finally:
        command(sock, 0x0c, b"\x00\x00")
        col.save(path)
        got, ok = col.counts()
        print("saved %s: blocks %d/%d, confirmed %d" % (path, got, _rx.BLOCKS, ok))
        subprocess.run(["systemctl", "start", "bluetooth.service"], check=False)


if __name__ == "__main__":
    main()
