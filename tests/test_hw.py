"""Hardware drivers tested against fakes that speak the same wire protocol."""

import io
import queue

import pytest
from PIL import Image

from player import events as ev
from player.hw.inputs import Quadrature
from player.hw.pn532 import ACK, PN532, CardWatcher, Pn532Error, _REV, build_frame, parse_frame
from player.hw.st7789 import ST7789, to_rgb565
from player.hw.usb import UsbMonitor


def drain(q):
    out = []
    while not q.empty():
        out.append(q.get())
    return out


# ---- PN532 -----------------------------------------------------------------


class FakePn532Spi:
    """Behaves like a PN532 on SPI, including LSB-first bytes and the ACK handshake."""

    def __init__(self):
        self.card = None  # bytes UID, or None
        self.dead = False
        self.commands = []
        self._ack = False
        self._response = None

    def _reply(self, command, params):
        if command == 0x14:
            return b""
        if command == 0x02:
            return bytes([0x32, 1, 6, 7])
        if command == 0x32:
            return b""
        if command == 0x4A:
            if self.card is None:
                return bytes([0])
            return bytes([1, 1, 0x00, 0x44, 0x00, len(self.card)]) + self.card
        raise AssertionError(f"unexpected command {command:#x}")

    def xfer2(self, data):
        out = bytes(_REV[b] for b in data)
        reply = bytearray(len(out))
        if self.dead or not out:
            return list(reply)
        op, rest = out[0], out[1:]
        if op == 0x01:
            if rest == ACK:
                self._response = None
            elif rest[:3] == b"\x00\x00\xff":
                length = rest[3]
                body = rest[5 : 5 + length]
                assert (length + rest[4]) & 0xFF == 0 and (sum(body) + rest[5 + length]) & 0xFF == 0
                assert body[0] == 0xD4
                self.commands.append(body[1])
                data_out = self._reply(body[1], body[2:])
                payload = bytes([0xD5, body[1] + 1]) + data_out
                self._response = (
                    bytes([0, 0, 0xFF, len(payload), (-len(payload)) & 0xFF]) + payload + bytes([(-sum(payload)) & 0xFF, 0])
                )
                self._ack = True
        elif op == 0x02:
            reply[1] = 1 if (self._ack or self._response) else 0
        elif op == 0x03:
            if self._ack:
                src, self._ack = ACK, False
            else:
                src, self._response = self._response or b"", None
            reply[1 : 1 + len(src)] = src[: len(reply) - 1]
        return [_REV[b] for b in reply]


def make_reader(spi):
    t = [0.0]

    def sleep(s):
        t[0] += s

    return PN532(spi, sleep=sleep, clock=lambda: t[0])


def test_frame_round_trip_matches_known_bytes():
    # GetFirmwareVersion as given in the PN532 user manual.
    assert build_frame(0x02) == bytes([0x00, 0x00, 0xFF, 0x02, 0xFE, 0xD4, 0x02, 0x2A, 0x00])
    reply = bytes([0x00, 0x00, 0xFF, 0x06, 0xFA, 0xD5, 0x03, 0x32, 0x01, 0x06, 0x07, 0xE8, 0x00])
    assert parse_frame(reply) == bytes([0x03, 0x32, 0x01, 0x06, 0x07])
    with pytest.raises(Pn532Error):
        parse_frame(reply[:-3] + b"\x00\x00\x00")


def test_pn532_reads_uids():
    spi = FakePn532Spi()
    reader = make_reader(spi)
    assert reader.begin() == (1, 6)
    assert spi.commands == [0x14, 0x02, 0x32]
    assert reader.read_uid() is None
    spi.card = bytes.fromhex("04A1B2C3D4E5F6")  # 7-byte NTAG UID
    assert reader.read_uid() == "04A1B2C3D4E5F6"
    spi.card = bytes.fromhex("DEADBEEF")  # 4-byte MIFARE Classic UID
    assert reader.read_uid() == "DEADBEEF"


def test_pn532_missing_chip_raises():
    spi = FakePn532Spi()
    spi.dead = True
    with pytest.raises(Pn532Error):
        make_reader(spi).begin()


def test_card_watcher_debounces_removal():
    q = queue.Queue()
    w = CardWatcher(reader=None, event_queue=q)
    for uid in ["AA", "AA", None, "AA", None, None, None, None, "BB", "CC"]:
        w.observe(uid)
    assert drain(q) == [ev.CardInserted("AA"), ev.CardRemoved(), ev.CardInserted("BB"), ev.CardInserted("CC")]


# ---- encoder ---------------------------------------------------------------

CLOCKWISE = [(1, 0), (1, 1), (0, 1), (0, 0)]  # channel A leads B


def test_quadrature_counts_a_full_turn_both_ways():
    q = Quadrature(ppr=64)
    for _ in range(64):
        for a, b in CLOCKWISE:
            q.update(a, b)
    assert q.take() == 256
    assert q.take() == 0
    for _ in range(64):
        for a, b in reversed(CLOCKWISE[:-1]):
            q.update(a, b)
        q.update(0, 0)
    assert q.take() == -256


def test_quadrature_ignores_bounce_and_scales_other_encoders():
    q = Quadrature(ppr=24, reverse=True)
    for a, b in [(1, 0), (0, 0), (1, 0), (0, 0), (1, 0)]:  # contact chatter on A
        q.update(a, b)
    assert q.take() == pytest.approx(-256 / 96)


# ---- display ---------------------------------------------------------------


class FakeSpi:
    def __init__(self):
        self.log = []

    def writebytes2(self, data):
        self.log.append((self.dc.state, bytes(data)))


class Pin:
    def __init__(self):
        self.state = None

    def on(self):
        self.state = 1

    def off(self):
        self.state = 0


def test_rgb565_packing():
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (255, 0, 0))
    img.putpixel((1, 0), (0, 255, 255))
    assert to_rgb565(img) == bytes([0xF8, 0x00, 0x07, 0xFF])


def test_display_sends_frames_once_and_lights_up():
    spi, dc, rst, bl = FakeSpi(), Pin(), Pin(), Pin()
    spi.dc = dc
    lcd = ST7789(spi, dc, rst, bl, sleep=lambda s: None)
    commands = [data[0] for state, data in spi.log if state == 0]
    assert commands == [0x01, 0x11, 0x3A, 0x36, 0x21, 0x13, 0x2A, 0x2B, 0x29]
    assert (1, bytes([0x60])) in spi.log and (1, bytes([0, 0, 1, 0x3F])) in spi.log
    assert rst.state == 1 and bl.state is None
    before = len(spi.log)
    frame = Image.new("RGB", (320, 240), (0, 0, 255))
    lcd.show(frame)
    assert spi.log[before] == (0, bytes([0x2C]))
    assert spi.log[before + 1] == (1, bytes([0x00, 0x1F]) * (320 * 240))
    assert bl.state == 1
    lcd.show(frame.copy())  # identical picture: nothing sent
    assert len(spi.log) == before + 2


# ---- USB monitor -----------------------------------------------------------


def test_usb_monitor_reports_host_and_eject(tmp_path):
    udc = tmp_path / "udc" / "3f980000.usb"
    udc.mkdir(parents=True)
    state, lun = udc / "state", tmp_path / "file"
    q = queue.Queue()
    m = UsbMonitor(q, udc_root=tmp_path / "udc", lun_file=lun)

    def step(udc_state, lun_content):
        state.write_text(udc_state + "\n")
        lun.write_text(lun_content)
        m.poll()
        return drain(q)

    assert step("not attached", "\n") == []  # charger or nothing
    assert step("configured", "\n") == [ev.UsbHost(True)]
    assert step("configured", "/srv/nfc-player/music.img\n") == []  # released to the computer
    assert step("suspended", "/srv/nfc-player/music.img\n") == []  # computer asleep
    assert step("configured", "\n") == [ev.UsbEjected()]
    assert step("configured", "/srv/nfc-player/music.img\n") == []
    assert step("not attached", "/srv/nfc-player/music.img\n") == [ev.UsbHost(False)]  # cable pulled


def test_each_click_of_the_clicky_encoder_is_two_volume_steps_and_one_list_item():
    from player.hw.inputs import VOLUME_STEPS_PER_REV
    from player.knob import list_scaler, volume_scaler

    q = Quadrature(ppr=24)
    vol, lst = volume_scaler(VOLUME_STEPS_PER_REV["pec11"]), list_scaler()
    t = 0.0
    for direction in (CLOCKWISE, [(0, 1), (1, 1), (1, 0), (0, 0)]):
        sign = 1 if direction is CLOCKWISE else -1
        for _ in range(12):  # slow, separate clicks
            for a, b in direction:
                q.update(a, b)
            t += 0.5
            counts = q.take()
            assert vol.feed(counts, t) == 2 * sign
            assert lst.feed(counts, t) == sign


def test_mpd_without_a_volume_control_does_not_crash():
    from mpd import CommandError

    from player.library import Track
    from player.playback import MpdPlayback

    class FakeClient:
        mixer = False

        def __init__(self):
            self.calls = []

        def connect(self, host, port):
            pass

        def setvol(self, v):
            if not self.mixer:
                raise CommandError("[5@0] {setvol} No mixer")
            self.calls.append(("setvol", v))

        def clear(self):
            pass

        def add(self, path):
            pass

        def command_list_ok_begin(self):
            pass

        def command_list_end(self):
            pass

        def status(self):
            return {"playlistlength": "1"}

        def play(self, track):
            self.calls.append(("play", track))

    p = MpdPlayback()
    p._client = client = FakeClient()
    p.set_volume(30)  # no DAC yet: must not raise
    p.set_volume(35)
    assert client.calls == []
    client.mixer = True  # the DAC appears
    p.play((Track("Artist/Album/01 Song.flac", "Song"),))
    assert client.calls == [("play", 0), ("setvol", 35)]


def test_prev_and_next_scan_while_held_and_skip_on_a_short_press():
    from player.hw.inputs import Buttons
    from player.hw.sim.server import _to_event

    q = queue.Queue()
    b = Buttons.__new__(Buttons)  # the press logic, without gpiozero
    b.queue, b._held = q, {}
    b.released("next")  # short press: sent on release
    b.held("next")  # held: repeats while the button stays down...
    b.held("next")
    b.released("next")  # ...and nothing more when it comes up
    b.held("knob")
    b.released("knob")
    b.held("back")
    b.released("back")
    assert [q.get_nowait().button for _ in range(q.qsize())] == ["next", "next_hold", "next_hold", "knob_long", "back_long"]
    assert _to_event({"type": "press", "button": "back_long"}) == ev.Press("back_long")
    assert _to_event({"type": "press", "button": "prev_hold"}) == ev.Press("prev_hold")


def test_simulator_power_key():
    from player.hw.sim.server import _to_event

    assert _to_event({"type": "press", "button": "power"}) == ev.Press("power")


def test_simulator_power_cycle_goes_dark_and_waits_for_the_power_key(monkeypatch):
    from player.hw.sim import server

    display = server.SimDisplay()
    events = queue.Queue()
    for e in (ev.Press("play"), ev.CardInserted("04AA"), ev.Press("power")):
        events.put(e)
    started = []
    monkeypatch.setattr(server.os, "execv", lambda exe, argv: started.append(argv))
    server.power_cycle(display, events, shutdown_seconds=0)()
    frame = Image.open(io.BytesIO(display.png()))
    assert frame.getextrema() == ((0, 0), (0, 0), (0, 0))  # dark
    assert events.empty() and len(started) == 1 and started[0][1:3] == ["-m", "player.main"]


def test_card_watcher_says_when_the_reader_is_ready():
    class Reader:
        tries = 0

        def begin(self):
            self.tries += 1
            if self.tries == 1:
                raise Pn532Error("not awake yet")  # a reader that is slow to start at boot

        def read_uid(self):
            return None

    w = CardWatcher(reader=Reader(), event_queue=queue.Queue())
    w.start()
    assert not w.ready.is_set()
    assert w.ready.wait(5)
