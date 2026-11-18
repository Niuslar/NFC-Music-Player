"""The Setup page: hardware settings, the small OLED screen, and the hardware tests."""

import argparse
import json
import queue
import urllib.error
import urllib.request

import pytest
from PIL import Image

from player import events as ev
from player import hwconfig
from player.app import App, Mode
from player.cards import Store
from player.demo_library import build
from player.hw import selftest
from player.hw.ssd1306 import SSD1306, to_pages
from player.library import Library
from player.main import effective_config, run
from player.playback import FakePlayback, Status
from player.ui import render, tiny
from player.web import server as web

OK = {"X-Requested-With": "nfc-player", "Content-Type": "application/json"}


# ---- settings file -----------------------------------------------------------


def test_settings_round_trip_and_defaults(tmp_path):
    path = tmp_path / "hardware.json"
    assert hwconfig.load(path) == hwconfig.DEFAULTS  # no file yet
    saved = hwconfig.save(path, {"display": "ssd1306", "rotate": 180})
    assert saved == {**hwconfig.DEFAULTS, "display": "ssd1306", "rotate": 180}
    assert hwconfig.load(path) == saved
    path.write_text("{not json")
    assert hwconfig.load(path) == hwconfig.DEFAULTS  # a broken file never stops the player


@pytest.mark.parametrize("bad", [{"display": "hdmi"}, {"encoder": 3}, {"rotate": 90}, {"rotate": True}, {"encoder_reverse": "yes"}])
def test_bad_settings_are_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        hwconfig.save(tmp_path / "hardware.json", bad)


def test_command_line_options_win_over_the_file(tmp_path):
    path = tmp_path / "hardware.json"
    hwconfig.save(path, {"display": "ssd1306", "encoder": "em14"})
    args = argparse.Namespace(config=path, display=None, encoder="pec11", encoder_reverse=None, rotate=None)
    saved, running, overridden = effective_config(args)
    assert saved["encoder"] == "em14" and running["encoder"] == "pec11" and overridden == ["encoder"]
    assert running["display"] == "ssd1306"


# ---- SSD1306 driver ----------------------------------------------------------


class FakeBus:
    def __init__(self):
        self.writes = []
        self.fail = False

    def write(self, data):
        if self.fail:
            raise OSError(121, "Remote I/O error")
        self.writes.append(bytes(data))


def test_page_packing_puts_the_top_pixel_in_the_lowest_bit():
    img = Image.new("1", (128, 32))
    img.putpixel((0, 0), 1)  # page 0, column 0, bit 0
    img.putpixel((5, 9), 1)  # page 1, column 5, bit 1
    img.putpixel((127, 31), 1)  # page 3, last column, bit 7
    data = to_pages(img)
    assert len(data) == 512
    assert data[0] == 0x01 and data[128 + 5] == 0x02 and data[3 * 128 + 127] == 0x80
    assert sum(data) == 0x01 + 0x02 + 0x80


def test_oled_sends_each_frame_once_and_survives_a_bus_error():
    bus = FakeBus()
    oled = SSD1306(bus)
    init = bus.writes[0]
    assert init[0] == 0x00 and 0x8D in init and 0xAF not in init  # dark until there is a picture
    frame = tiny.message("Place a card", "to start playing")
    oled.show(frame)
    assert [len(w) for w in bus.writes[1:] if w[0] == 0x40] == [129] * 4  # the whole picture, a strip at a time
    assert bus.writes[-1] == bytes([0x00, 0xAF])  # then lit
    count = len(bus.writes)
    oled.show(frame)
    assert len(bus.writes) == count  # unchanged: nothing sent

    other = tiny.message("Turning off")
    bus.fail = True
    oled.show(other)  # e.g. the power key holding the clock line low
    assert oled.failures == 1
    bus.fail = False
    oled.show(other)
    assert bus.writes[-1][0] == 0x40  # sent once the bus works again


def test_oled_upside_down_flips_both_axes():
    bus = FakeBus()
    SSD1306(bus, rotate180=True)
    assert 0xA0 in bus.writes[0] and 0xC0 in bus.writes[0]


# ---- the small screens -------------------------------------------------------


@pytest.fixture
def small(tmp_path):
    music = tmp_path / "music"
    build(music)
    library = Library(music)
    store = Store(tmp_path / "state.json")
    app = App(library, store, FakePlayback(library), ui=tiny)
    return app, store


def _is_small(img):
    return img.size == (128, 32) and img.mode == "1"


def test_every_screen_draws_on_the_oled(small):
    app, store = small
    shots = [app.render(0)]  # place a card
    app.handle(ev.CardInserted("04AA"), 0)
    shots.append(app.render(0))  # not linked
    app.handle(ev.Press("knob"), 0)
    shots.append(app.render(0))  # what kind
    app.handle(ev.Press("knob"), 0)
    shots.append(app.render(0))  # albums
    app.handle(ev.Press("knob"), 0)
    app.tick(1)
    shots.append(app.render(1))  # now playing
    app.handle(ev.Rotate(40), 1)
    shots.append(app.render(1))  # volume
    app.handle(ev.Press("knob"), 3)
    shots.append(app.render(3))  # tracks
    for img in shots:
        assert _is_small(img)
        assert img.getbbox() is not None  # something is drawn


def test_now_playing_fits_long_names():
    st = Status(state="pause", title="A very long track title that cannot possibly fit", elapsed=3600, duration=4000, track_count=1)
    img = tiny.now_playing("x", ("Somebody with a long name · An album", ""), None, st, None)
    assert _is_small(img)


def test_test_picture_reaches_every_edge():
    for ui in (render, tiny):
        img = ui.test_pattern().convert("L")
        assert img.getbbox() == (0, 0, *img.size)


def test_screen_test_shows_for_five_seconds(small):
    app, _ = small
    app.handle(ev.WebCommand("test_screen"), 10)
    assert app.render(14).tobytes() == tiny.test_pattern().tobytes()
    assert app.render(15.1).tobytes() != tiny.test_pattern().tobytes()


def test_restart_saves_the_card_place_then_restarts(small):
    app, store = small
    app.handle(ev.CardInserted("04AA"), 0)
    app.handle(ev.Press("knob"), 0)
    app.handle(ev.Press("knob"), 0)
    app.handle(ev.Press("knob"), 0)  # linked and playing
    events = queue.Queue()
    events.put(ev.WebCommand("restart"))
    restarted = []
    run(app, events, type("D", (), {"show": lambda self, img: restarted.append(img)})(), restart=lambda: restarted.append("restart"))
    assert restarted[-1] == "restart"
    assert restarted[-2].tobytes() == tiny.message("Restarting").tobytes()
    assert app.playback.status().state == "stop"
    assert json.loads(store.path.read_text())  # saved


def test_restart_waits_while_the_drive_is_with_a_computer(small):
    app, _ = small
    app.mode = Mode.TRANSFER
    app.handle(ev.WebCommand("restart"), 0)
    assert not app.restart_requested


# ---- input log and DAC test --------------------------------------------------


def test_input_log_keeps_a_knob_turn_as_one_line():
    t = [100.0]
    log = selftest.InputLog()
    log.add(ev.Press("play"), clock=lambda: t[0])
    for _ in range(4):
        t[0] += 0.1
        log.add(ev.Rotate(10), clock=lambda: t[0])
    log.add(ev.CardInserted("04AA"), clock=lambda: t[0])
    log.add(ev.WebCommand("toggle"), clock=lambda: t[0])  # not an input: left out
    got = log.since(0)
    assert [i["text"] for i in got["items"]] == ["Button: play", "Knob: clockwise 40", "Card in: 04AA"]
    assert got["card"] == "04AA"
    later = log.since(got["seq"])
    assert later["items"] == []
    t[0] += 0.1
    log.add(ev.Rotate(-5), clock=lambda: t[0])
    assert log.since(got["seq"])["items"][0]["text"] == "Knob: anticlockwise 5"


def test_tone_is_short_stereo_and_quiet():
    import io
    import wave

    with wave.open(io.BytesIO(selftest.tone_wav())) as w:
        assert w.getnchannels() == 2 and w.getsampwidth() == 2
        assert 1.5 < w.getnframes() / w.getframerate() < 2.5
        frames = w.readframes(w.getnframes())
    import array

    peak = max(abs(v) for v in array.array("h", frames))
    assert 3000 < peak < 5000  # about -18 dBFS


def test_dac_test_explains_a_missing_dac(tmp_path):
    conf = tmp_path / "mpd.conf"
    conf.write_text('audio_output {\n  type "null"\n  name "No DAC yet (silent)"\n}\n')
    assert not selftest.dac_test(conf=conf)["ok"]
    conf.write_text('audio_output {\n  type "alsa"\n  device "hw:CARD=DACPro"\n}\n')
    assert selftest.mpd_device(conf) == "hw:CARD=DACPro"

    class Done:
        stdout = " 0 [vc4hdmi        ]: vc4-hdmi\n"

    result = selftest.dac_test(conf=conf, run=lambda *a, **k: Done())
    assert not result["ok"] and "DACPro" in result["message"] and "vc4-hdmi" in result["message"]


# ---- web API -----------------------------------------------------------------


@pytest.fixture
def site(tmp_path):
    music = tmp_path / "music"
    build(music)
    library = Library(music)
    events = queue.Queue()
    shared = web.Shared()
    writer = web.MusicWriter(lambda: None)
    log = selftest.InputLog()
    setup = web.Setup(tmp_path / "hardware.json", hwconfig.DEFAULTS, hardware={"screen": "ok", "nfc": "OSError: no reader"}, inputs=log, dac_test=lambda: {"ok": True, "message": "played"})
    server = web.start(events, shared, library, writer, port=0, bind="127.0.0.1", setup=setup)
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    yield call, events, log, tmp_path / "hardware.json"
    server.shutdown()
    server.server_close()


def test_setup_page_and_state(site):
    call, *_ = site
    status, body = call("GET", "/setup")
    assert status == 200 and b"Setup" in body
    status, body = call("GET", "/api/setup")
    state = json.loads(body)
    assert state["saved"] == hwconfig.DEFAULTS and state["restart_needed"] == []
    assert state["hardware"]["nfc"].startswith("OSError") and "ssd1306" in state["choices"]["display"]
    assert b"/setup" in call("GET", "/")[1]  # the remote links to it


def test_saving_settings_asks_for_a_restart(site):
    call, events, _, path = site
    assert call("POST", "/api/setup", {"display": "ssd1306"})[0] == 403  # without the header
    status, body = call("POST", "/api/setup", {"display": "ssd1306"}, OK)
    assert status == 200 and json.loads(body)["restart_needed"] == ["display"]
    assert json.loads(path.read_text())["display"] == "ssd1306"
    assert call("POST", "/api/setup", {"rotate": 45}, OK)[0] == 400
    assert call("POST", "/api/restart", {}, OK)[0] == 200
    assert events.get_nowait() == ev.WebCommand("restart")


def test_tests_through_the_api(site):
    call, events, log, _ = site
    status, body = call("POST", "/api/test", {"part": "screen"}, OK)
    assert status == 200 and events.get_nowait() == ev.WebCommand("test_screen")
    assert json.loads(call("POST", "/api/test", {"part": "dac"}, OK)[1]) == {"ok": True, "message": "played"}
    assert call("POST", "/api/test", {"part": "toaster"}, OK)[0] == 400
    log.add(ev.Press("back"))
    got = json.loads(call("GET", "/api/inputs?after=0")[1])
    assert got["items"][0]["text"] == "Button: back"
    assert json.loads(call("GET", f"/api/inputs?after={got['seq']}")[1])["items"] == []


def test_missing_i2c_says_how_to_turn_it_on(monkeypatch):
    from player.hw import ssd1306

    def no_device(path, flags):
        raise FileNotFoundError(2, "No such file or directory", path)

    monkeypatch.setattr(ssd1306.os, "open", no_device)
    with pytest.raises(FileNotFoundError, match="setup.sh"):
        ssd1306.open_bus(1)


class FakeOled(FakeBus):
    """Keeps a copy of the screen's memory, following the addressing commands."""

    def __init__(self):
        super().__init__()
        self.ram = bytearray(512)
        self.window = (0, 127, 0, 3)

    def write(self, data):
        super().write(data)
        if data[0] == 0x00 and len(data) == 7 and data[1] == 0x21:
            self.window = (data[2], data[3], data[5], data[6])
        elif data[0] == 0x40:
            c0, c1, p0, p1 = self.window
            cells = [(p, c) for p in range(p0, p1 + 1) for c in range(c0, c1 + 1)]
            for (p, c), byte in zip(cells, data[1:]):
                self.ram[p * 128 + c] = byte


def test_a_new_second_sends_only_the_changed_columns():
    bus = FakeOled()
    oled = SSD1306(bus)
    st = Status(state="play", title="Small Hours", elapsed=3, duration=25, track_count=1)
    oled.show(tiny.now_playing("x", ("0415", ""), None, st, None))
    before = len(bus.writes)
    st = Status(state="play", title="Small Hours", elapsed=4, duration=25, track_count=1)
    frame = tiny.now_playing("x", ("0415", ""), None, st, None)
    oled.show(frame)
    sent = [w for w in bus.writes[before:] if w[0] == 0x40]
    assert 0 < sum(len(w) - 1 for w in sent) < 64  # a few columns of the time, not 512 bytes
    assert bytes(bus.ram) == to_pages(frame)  # and the screen ends up exactly right


def test_after_a_bus_error_the_whole_screen_is_sent_again():
    bus = FakeOled()
    oled = SSD1306(bus)
    oled.show(tiny.message("One"))
    bus.fail = True
    oled.show(tiny.message("Two"))
    bus.fail = False
    bus.ram[:] = bytes(512)  # whatever got there half-sent
    frame = tiny.message("Two")
    oled.show(frame)
    assert bytes(bus.ram) == to_pages(frame)
