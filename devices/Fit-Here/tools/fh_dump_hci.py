#!/usr/bin/env python3
"""Collect the dumper's broadcast from a raw HCI socket, with duplicate filtering off.

usage: sudo python3 fh_dump_hci.py out.bin [hci-index]

BlueZ keeps the controller's duplicate filter on, and with a fixed address that lets through
about one frame per scan, so fh_dump_rx.py cannot keep up. Needs root for the raw socket.

Uses the extended scan commands when the controller takes them: a Bluetooth 5 controller on
which the kernel has used them refuses the legacy ones (status 0x0c).

While it runs bluetoothd is STOPPED and the adapter reset, so nothing else changes the scan:
every Bluetooth device on this adapter drops until the end. bluetoothd is started again on exit.
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
HCI_EVENT_PKT, HCI_CMD_COMPLETE, EVT_LE_META = 0x04, 0x0e, 0x3e
LE_ADV_REPORT, LE_EXT_ADV_REPORT = 0x02, 0x0d
OCF_SCAN_PARAMS, OCF_SCAN_ENABLE = 0x0b, 0x0c
OCF_EXT_SCAN_PARAMS, OCF_EXT_SCAN_ENABLE = 0x41, 0x42
ADDR = bytes.fromhex("6302b1a100c0")   # C0:00:A1:B1:02:63, little endian
SCAN_MS = 0x0010                       # 10 ms interval and window: always listening

stats = {"reports": 0}


def command_status(pkt):
    """(ocf, status) of an LE command-complete event, or None."""
    if len(pkt) >= 7 and pkt[0] == HCI_EVENT_PKT and pkt[1] == HCI_CMD_COMPLETE and pkt[5] >> 2 == 0x08:
        return (pkt[4] | pkt[5] << 8) & 0x3ff, pkt[6]
    return None


def adv_payloads(pkt):
    """Yield (address, advertising data) for each report in one raw HCI event packet."""
    if len(pkt) < 5 or pkt[0] != HCI_EVENT_PKT or pkt[1] != EVT_LE_META:
        return
    if pkt[3] == LE_ADV_REPORT:
        addr_at, len_at, tail = 2, 8, 1    # type, addr type, addr, len, data, rssi
    elif pkt[3] == LE_EXT_ADV_REPORT:
        addr_at, len_at, tail = 3, 23, 0   # type (2), addr type, addr, ... len, data
    else:
        return
    pos, count = 5, pkt[4]
    for _ in range(count):
        if pos + len_at + 1 > len(pkt):
            return
        stats["reports"] += 1
        dlen = pkt[pos + len_at]
        yield bytes(pkt[pos + addr_at:pos + addr_at + 6]), bytes(pkt[pos + len_at + 1:pos + len_at + 1 + dlen])
        pos += len_at + 1 + dlen + tail


def frames_in_event(pkt):
    """Yield the 27-byte dumper frames in one raw HCI event packet."""
    for addr, data in adv_payloads(pkt):
        if addr != ADDR:
            continue
        i = 0
        while i + 1 < len(data):
            ln = data[i]
            if ln == 0:
                break
            if data[i + 1] == 0xff and ln >= 3 and data[i + 2] | data[i + 3] << 8 == _rx.COMPANY:
                yield data[i + 4:i + 1 + ln]
            i += 1 + ln


def command(sock, ocf, params=b""):
    """Send an LE command and return its status, or None if no answer came in 1 s."""
    sock.send(struct.pack("<BHB", 1, 0x08 << 10 | ocf, len(params)) + params)
    end = time.time() + 1
    while time.time() < end:
        try:
            status = command_status(sock.recv(300))
        except socket.timeout:
            continue
        if status and status[0] == ocf:
            return status[1]
    return None


def start_scan(sock):
    """Start scanning, duplicate filter off. Returns a description, or raises on failure."""
    command(sock, OCF_EXT_SCAN_ENABLE, struct.pack("<BBHH", 0, 0, 0, 0))
    st = command(sock, OCF_EXT_SCAN_PARAMS, struct.pack("<BBBBHH", 0, 0, 1, 0, SCAN_MS, SCAN_MS))
    if st == 0:
        st = command(sock, OCF_EXT_SCAN_ENABLE, struct.pack("<BBHH", 1, 0, 0, 0))
        if st == 0:
            return "extended"
        raise RuntimeError("extended scan enable: status %s" % st)
    command(sock, OCF_SCAN_ENABLE, b"\x00\x00")
    st = command(sock, OCF_SCAN_PARAMS, struct.pack("<BHHBB", 0, SCAN_MS, SCAN_MS, 0, 0))
    if st:
        raise RuntimeError("legacy scan params: status %s" % st)
    st = command(sock, OCF_SCAN_ENABLE, b"\x01\x00")
    if st:
        raise RuntimeError("legacy scan enable: status %s" % st)
    return "legacy"


def stop_scan(sock, mode):
    if mode == "extended":
        command(sock, OCF_EXT_SCAN_ENABLE, struct.pack("<BBHH", 0, 0, 0, 0))
    else:
        command(sock, OCF_SCAN_ENABLE, b"\x00\x00")


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    path, dev = sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else 0
    col = _rx.Collector()
    col.load(path)
    subprocess.run(["systemctl", "stop", "bluetooth.service"], check=False)
    mode = None
    try:
        subprocess.run(["hciconfig", "hci%d" % dev, "down"], check=False)
        subprocess.run(["hciconfig", "hci%d" % dev, "up"], check=True)
        time.sleep(1)
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        sock.bind((dev,))
        sock.setsockopt(SOL_HCI, HCI_FILTER,
                        struct.pack("<IIIH2x", 1 << HCI_EVENT_PKT, 1 << HCI_CMD_COMPLETE,
                                    1 << (EVT_LE_META - 32), 0))
        sock.settimeout(1)
        try:
            mode = start_scan(sock)
        except RuntimeError as e:
            sys.exit("cannot scan: %s" % e)
        print("scanning on hci%d (%s commands), Ctrl+C to stop" % (dev, mode), flush=True)

        last, last_frames = time.time(), col.frames
        try:
            while True:
                try:
                    for frame in frames_in_event(sock.recv(300)):
                        col.feed(frame)
                except socket.timeout:
                    pass
                if time.time() - last >= 15:
                    got, ok = col.counts()
                    print("%s  %.1f frames/s  all adv reports %d  blocks %d/%d  confirmed %d  conflicts %d"
                          % (time.strftime("%H:%M:%S"),
                             (col.frames - last_frames) / (time.time() - last),
                             stats["reports"], got, _rx.BLOCKS, ok, col.conflicts), flush=True)
                    col.save(path)
                    last, last_frames = time.time(), col.frames
                    stats["reports"] = 0
        except KeyboardInterrupt:
            pass
        stop_scan(sock, mode)
        col.save(path)
        got, ok = col.counts()
        print("saved %s: blocks %d/%d, confirmed %d" % (path, got, _rx.BLOCKS, ok))
    finally:
        subprocess.run(["systemctl", "start", "bluetooth.service"], check=False)


if __name__ == "__main__":
    main()
