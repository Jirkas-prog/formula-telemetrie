"""RTCM 3 source for the rover. Network and radio reads run outside the logger."""
import ipaddress
from pathlib import Path
import re
import socket
import time

import serial


DEFAULT_RTK = dict(source="off", host="", port=5015, radio="", baud=115200,
                   relay=False, relay_host="", relay_port=5016)
BAUD = (9600, 19200, 38400, 57600, 115200, 230400, 460800)
RADIOS = Path("/dev/serial/by-id")


def radio_names():
    return sorted(p.name for p in RADIOS.glob("*")
                  if not p.name.lower().startswith("usb-septentrio") and p.is_char_device())


def address(value, needed):
    if not value and not needed:
        return
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError:
        raise ValueError("Zadej IPv4 adresu zařízení.") from None
    if ip.is_multicast or ip.is_unspecified or int(ip) == 0xffffffff:
        raise ValueError("Zadej adresu jednoho zařízení.")


def validate(cfg):
    if cfg.keys() != DEFAULT_RTK.keys() or cfg["source"] not in ("off", "tcp", "serial"):
        raise ValueError("Neplatné nastavení zdroje RTCM.")
    if type(cfg["relay"]) is not bool or type(cfg["baud"]) is not int or cfg["baud"] not in BAUD:
        raise ValueError("Neplatné parametry rádia nebo předávání.")
    if any(type(cfg[k]) is not int or not 1 <= cfg[k] <= 65535 for k in ("port", "relay_port")):
        raise ValueError("Port musí být v rozsahu 1 až 65535.")
    for key in ("host", "radio", "relay_host"):
        if not isinstance(cfg[key], str):
            raise ValueError("Neplatná adresa zařízení.")
    address(cfg["host"], cfg["source"] == "tcp")
    address(cfg["relay_host"], cfg["relay"])
    radio = cfg["radio"]
    if radio and (not re.fullmatch(r"[a-zA-Z0-9_:.+\-]{1,240}", radio)
                  or radio in (".", "..") or radio.lower().startswith("usb-septentrio")):
        raise ValueError("Neplatný identifikátor sériového rádia.")
    if cfg["source"] == "serial" and not radio:
        raise ValueError("Vyber sériové rádio.")


def _crc_entry(value):
    value <<= 16
    for _ in range(8):
        value = (value << 1) ^ (0x1864CFB if value & 0x800000 else 0)
    return value & 0xffffff


TABLE = tuple(map(_crc_entry, range(256)))


def crc24q(data):
    value = 0
    for b in data:
        value = ((value << 8) & 0xffffff) ^ TABLE[(value >> 16) ^ b]
    return value


class Frames:
    def __init__(self):
        self.buffer = bytearray()
        self.bad = 0

    def feed(self, chunk):
        buf = self.buffer
        buf.extend(chunk)
        while buf:
            start = buf.find(b"\xd3")
            if start < 0:
                buf.clear()
                return
            del buf[:start]
            if len(buf) < 3:
                return
            length = ((buf[1] & 3) << 8) + buf[2]
            if buf[1] & 0xfc or length < 2:
                del buf[:1]
                continue
            end = length + 6
            if len(buf) < end:
                return
            pkt = bytes(buf[:end])
            if crc24q(pkt[:-3]) != int.from_bytes(pkt[-3:], "big"):
                self.bad += 1
                del buf[:1]
                continue
            del buf[:end]
            yield pkt


class CorrectionLink:
    def __init__(self, logger):
        self.logger = logger
        self.version = 0
        self.reset()

    def reset(self):
        self.version += 1
        self.connected = False
        self.error = self.relay_error = ""
        self.last_frame = self.last_usb = self.message = None
        self.received = self.sent = self.relayed = self.bad = 0

    def status(self):
        return dict(connected=self.connected, received=self.received, sent=self.sent,
                    relayed=self.relayed, bad=self.bad, message=self.message,
                    age_s=time.monotonic()-self.last_frame if self.last_frame else None,
                    usb_age_s=time.monotonic()-self.last_usb if self.last_usb else None,
                    error=self.error, relay_error=self.relay_error)

    def transfer(self, cfg, version):
        if cfg["source"] == "tcp":
            source = socket.create_connection((cfg["host"], cfg["port"]), timeout=1)
            source.settimeout(.3)
        else:
            if cfg["radio"] not in radio_names():
                raise OSError("Čekám na připojení USB rádia.")
            source = serial.Serial(str(RADIOS / cfg["radio"]), cfg["baud"], timeout=.3, exclusive=True)
        parser = Frames()
        with source, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as outgoing:
            outgoing.setblocking(False)
            while not self.logger.stop_event.is_set():
                with self.logger.lock:
                    if version != self.version:
                        return
                    self.connected = True
                try:
                    if cfg["source"] == "tcp":
                        data = source.recv(4096)
                        if not data:
                            raise OSError("Základna ukončila spojení.")
                    else:
                        data = source.read(min(4096, max(1, source.in_waiting)))
                except TimeoutError:
                    continue
                packets = list(parser.feed(data))
                with self.logger.lock:
                    if version != self.version:
                        return
                    self.bad += parser.bad
                    parser.bad = 0
                    for packet in packets:
                        self.received += 1
                        self.message = (packet[3] << 4) | (packet[4] >> 4)
                        self.last_frame = time.monotonic()
                        if cfg["relay"]:
                            try:
                                outgoing.sendto(packet, (cfg["relay_host"], cfg["relay_port"]))
                                self.relayed += 1
                                self.relay_error = ""
                            except OSError as exc:
                                self.relay_error = str(exc)
                        try:
                            self.logger.send_rtcm(packet)
                            self.sent += 1
                            self.last_usb = time.monotonic()
                            self.error = ""
                        except OSError as exc:
                            self.error = str(exc)
                            # Repeat receiver configuration at most once per retry interval.
                            if self.logger.data is not None:
                                raise

    def run(self):
        while not self.logger.stop_event.is_set():
            with self.logger.lock:
                cfg = self.logger.rtk
                version = self.version
            if cfg["source"] != "off":
                try:
                    self.transfer(cfg, version)
                except (OSError, ValueError) as exc:
                    with self.logger.lock:
                        if version == self.version:
                            self.connected = False
                            self.error = str(exc)
            self.logger.stop_event.wait(1)

