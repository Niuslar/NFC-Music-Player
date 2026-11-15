"""Minimal PN532 NFC reader driver over SPI, enough to read card UIDs.

The PN532 speaks LSB-first; the Pi's SPI hardware is MSB-first only, so every
byte is bit-reversed here. The spi object needs xfer2(list) -> list, as
spidev.SpiDev provides (mode 0, about 500 kHz, its own chip-select line).
"""

import threading
import time

from .. import events as ev

_REV = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
DATA_WRITE, STATUS_READ, DATA_READ = 0x01, 0x02, 0x03
HOST_TO_PN532, PN532_TO_HOST = 0xD4, 0xD5
ACK = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])
CMD_FIRMWARE, CMD_SAM_CONFIG, CMD_RF_CONFIG, CMD_LIST_TARGET = 0x02, 0x14, 0x32, 0x4A


class Pn532Error(Exception):
    pass


def build_frame(command: int, params: bytes = b"") -> bytes:
    body = bytes([HOST_TO_PN532, command]) + bytes(params)
    length = len(body)
    return bytes([0x00, 0x00, 0xFF, length, (-length) & 0xFF]) + body + bytes([(-sum(body)) & 0xFF, 0x00])


def parse_frame(raw: bytes) -> bytes:
    """Returns the payload after the direction byte (response code first)."""
    start = raw.find(b"\x00\xff")
    if start < 0 or start + 4 > len(raw):
        raise Pn532Error("no frame start")
    length, lcs = raw[start + 2], raw[start + 3]
    if (length + lcs) & 0xFF:
        raise Pn532Error("bad length checksum")
    body = raw[start + 4 : start + 4 + length + 1]  # includes data checksum
    if len(body) != length + 1 or sum(body) & 0xFF:
        raise Pn532Error("bad data checksum")
    if body[0] != PN532_TO_HOST:
        raise Pn532Error("unexpected frame direction")
    return body[1:-1]


class PN532:
    def __init__(self, spi, sleep=time.sleep, clock=time.monotonic):
        self.spi, self._sleep, self._clock = spi, sleep, clock

    # ---- transport ----------------------------------------------------------

    def _xfer(self, out: bytes) -> bytes:
        got = self.spi.xfer2([_REV[b] for b in out])
        return bytes(_REV[b] for b in got)

    def _wait_ready(self, timeout: float) -> bool:
        deadline = self._clock() + timeout
        while True:
            if self._xfer(bytes([STATUS_READ, 0]))[1] & 0x01:
                return True
            if self._clock() >= deadline:
                return False
            self._sleep(0.005)

    def _read(self, count: int) -> bytes:
        return self._xfer(bytes([DATA_READ]) + bytes(count))[1:]

    def command(self, command: int, params: bytes = b"", response_len: int = 0, timeout: float = 1.0):
        """Sends a command; returns its response data, or None if the chip stayed busy."""
        self._xfer(bytes([DATA_WRITE]) + build_frame(command, params))
        if not self._wait_ready(1.0):
            raise Pn532Error("no acknowledgement")
        if self._read(len(ACK)) != ACK:
            raise Pn532Error("bad acknowledgement")
        if not self._wait_ready(timeout):
            self._xfer(bytes([DATA_WRITE]) + ACK)  # abort the pending command
            return None
        payload = parse_frame(self._read(response_len + 9))
        if payload[0] != command + 1:
            raise Pn532Error("response to a different command")
        return payload[1:]

    # ---- commands -----------------------------------------------------------

    def begin(self) -> tuple[int, int]:
        """Wakes and configures the chip. Returns the firmware (version, revision)."""
        self.spi.xfer2([0x00])  # chip-select edge wakes it from power-down
        self._sleep(0.02)
        last = None
        for _ in range(3):
            try:
                self.command(CMD_SAM_CONFIG, bytes([0x01, 0x14, 0x01]))  # normal mode
                break
            except Pn532Error as e:
                last = e
                self._sleep(0.05)
        else:
            raise Pn532Error(f"PN532 not responding ({last})")
        fw = self.command(CMD_FIRMWARE, response_len=4)
        if not fw or fw[0] != 0x32:
            raise Pn532Error("not a PN532")
        # Give up after one retry when no card is there, so polling returns quickly.
        self.command(CMD_RF_CONFIG, bytes([0x05, 0xFF, 0x01, 0x01]))
        return fw[1], fw[2]

    def read_uid(self) -> str | None:
        """UID of the card in the field as upper-case hex, or None."""
        resp = self.command(CMD_LIST_TARGET, bytes([0x01, 0x00]), response_len=20, timeout=0.5)
        if not resp or resp[0] < 1 or len(resp) < 6:
            return None
        uid = resp[6 : 6 + resp[5]]
        return uid.hex().upper() if len(uid) == resp[5] and uid else None


class CardWatcher(threading.Thread):
    """Polls the reader and turns what it sees into CardInserted / CardRemoved events."""

    def __init__(self, reader: PN532, event_queue, interval: float = 0.2, misses_to_remove: int = 3):
        super().__init__(daemon=True)
        self.reader, self.queue = reader, event_queue
        self.interval, self.misses_to_remove = interval, misses_to_remove
        self.current: str | None = None
        self._misses = 0

    def observe(self, uid: str | None) -> None:
        if uid is None:
            if self.current is not None:
                self._misses += 1
                if self._misses >= self.misses_to_remove:  # ride out a single failed read
                    self.current = None
                    self.queue.put(ev.CardRemoved())
            return
        self._misses = 0
        if uid != self.current:
            self.current = uid
            self.queue.put(ev.CardInserted(uid))

    def run(self) -> None:
        ready = False
        while True:
            try:
                if not ready:
                    self.reader.begin()
                    ready = True
                self.observe(self.reader.read_uid())
                time.sleep(self.interval)
            except (Pn532Error, OSError) as e:
                print(f"NFC reader: {e}; retrying", flush=True)
                ready = False
                time.sleep(2)
