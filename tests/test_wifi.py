import json
import queue
import urllib.error
import urllib.request

import pytest

from player import events as ev
from player import wifi as w
from player.app import App, Mode
from player.cards import Store
from player.demo_library import build
from player.knob import COUNTS_PER_REV
from player.library import Library
from player.playback import FakePlayback
from player.ui import render, tiny
from player.web import server as web

STEP = round(COUNTS_PER_REV * 15 / 360) + 1  # one list row


# ---- reading the signal ----------------------------------------------------

PROC = """Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
 wlan0: 0000   58.  -52.  -256        0      0      0      0     17        0
"""


def test_signal_from_proc():
    assert w.proc_level(PROC) == -52
    assert w.proc_level(PROC, "wlan1") is None
    assert w.proc_level(PROC.replace("58.  -52.", "0.  0.")) is None  # not associated


@pytest.mark.parametrize("dbm, bars", [(None, None), (-45, 4), (-60, 4), (-65, 3), (-75, 2), (-90, 1), (0, None)])
def test_bars(dbm, bars):
    assert w.bars_from_dbm(dbm) == bars


def test_scan_output_is_parsed_strongest_first_without_duplicates():
    out = "40:WPA2:Home\n71:WPA2:Home\n55::Cafe\n30:WPA1 WPA2:Name\\:with colon\n90:WPA2:NFC Player Setup\n20:WPA2:\n"
    assert w.parse_scan(out) == [
        {"ssid": "Home", "signal": 71, "secure": True},
        {"ssid": "Cafe", "signal": 55, "secure": False},
        {"ssid": "Name:with colon", "signal": 30, "secure": True},
    ]


@pytest.mark.parametrize("ssid, password", [("", "longenough"), ("x" * 33, "longenough"), ("Home", "short"), ("Home\n", "longenough"), (5, "longenough")])
def test_bad_networks_are_refused(ssid, password):
    with pytest.raises(w.WifiError):
        w.check_new_network(ssid, password)


def test_open_networks_need_no_password():
    assert w.check_new_network("Cafe", "") == ("Cafe", "")


# ---- the setup network -----------------------------------------------------


class Backend:
    portal_network = w.PORTAL_NETWORK
    portal_address = w.PORTAL_ADDRESS

    def __init__(self):
        self.calls = []
        self.dbm = -50
        self.ssid = "Home"
        self.good_password = "rightpassword"

    def level(self):
        return self.dbm

    def network(self):
        return self.ssid if self.dbm is not None else None

    def scan(self):
        self.calls.append("scan")
        return [{"ssid": "Home", "signal": 80, "secure": True}]

    def hotspot_up(self, password):
        self.calls.append(("up", password))

    def hotspot_down(self):
        self.calls.append("down")

    def join(self, ssid, password):
        self.calls.append(("join", ssid))
        if password != self.good_password:
            raise w.WifiError("Wrong password?")
        self.ssid = ssid

    def radio(self, on):
        self.calls.append(("radio", on))
        self.dbm = -50 if on else None


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def wifi():
    return w.Wifi(Backend(), clock=Clock(), spawn=lambda work: work())


def test_portal_opens_with_a_fresh_readable_password(wifi):
    wifi.open_portal()
    assert wifi.state == "ready" and wifi.portal_open
    assert len(wifi.password) == w.PASSWORD_LENGTH and set(wifi.password) <= set(w.PASSWORD_ALPHABET)
    assert wifi.backend.calls == ["scan", ("up", wifi.password)]  # scans before the radio becomes the hotspot
    assert wifi.bars() is None  # not on a network while it is the setup network
    first = wifi.password
    wifi.close_portal()
    wifi.open_portal()
    assert wifi.password != first


def test_only_phones_on_the_setup_network_may_choose(wifi):
    assert not wifi.allows("10.42.0.23")  # closed
    wifi.open_portal()
    assert wifi.allows("10.42.0.23")
    assert not wifi.allows("192.168.1.20") and not wifi.allows("not an address")


def test_joining_a_network(wifi):
    wifi.open_portal()
    wifi.join("Upstairs", "rightpassword")
    assert wifi.state == "joined" and wifi.joined == "Upstairs"
    assert wifi.backend.calls[-2:] == ["down", ("join", "Upstairs")]
    assert wifi.password == "" and not wifi.portal_open
    wifi.close_portal()
    assert wifi.state == "off" and wifi.network() == "Upstairs" and wifi.bars() == 4
    assert wifi.backend.calls[-1] == ("join", "Upstairs")  # nothing to take down once joined


def test_a_wrong_password_brings_the_setup_network_back(wifi):
    wifi.open_portal()
    password = wifi.password
    wifi.join("Upstairs", "nottheone")
    assert wifi.state == "failed" and wifi.portal_open
    assert "Wrong password" in wifi.message and "Upstairs" in wifi.message
    assert wifi.backend.calls[-1] == ("up", password)  # same password: the phone can rejoin as it was


def test_join_is_refused_when_the_portal_is_closed(wifi):
    with pytest.raises(w.WifiError):
        wifi.join("Home", "rightpassword")
    assert ("join", "Home") not in wifi.backend.calls


def test_an_unused_portal_closes_itself(wifi):
    wifi.open_portal()
    wifi.clock.t += w.PORTAL_SECONDS + 1
    wifi.tick()
    assert wifi.state == "off" and wifi.backend.calls[-1] == "down"


# ---- settings on the player ------------------------------------------------


@pytest.fixture(scope="module")
def music(tmp_path_factory):
    root = tmp_path_factory.mktemp("music")
    build(root)
    return root


@pytest.fixture
def rig(music, tmp_path, wifi):
    clock = Clock()
    library = Library(music)
    store = Store(tmp_path / "state.json")
    playback = FakePlayback(library, clock)
    app = App(library, store, playback, wifi=wifi)
    app.web_address = "http://nfcplayer.local"
    wifi.poll()  # main does this on a thread every few seconds

    def send(*events):
        for e in events:
            app.handle(e, clock.t)
            clock.t += 0.5
        app.tick(clock.t)

    return app, send, store, playback


def test_holding_the_knob_with_no_card_opens_settings(rig):
    app, send, *_ = rig
    send(ev.Press("knob_long"))
    assert app.mode is Mode.SETTINGS
    app.render(0)
    send(ev.Press("back"))
    assert app.mode is Mode.IDLE


def test_settings_are_not_the_card_menu(rig):
    app, send, *_ = rig
    send(ev.CardInserted("04AA"), ev.Press("knob"), ev.Press("knob"), ev.Press("knob"))  # link the first album
    send(ev.Press("knob_long"))
    assert app.mode is Mode.MENU


def test_connect_to_a_new_network_from_the_player(rig):
    app, send, *_ = rig
    send(ev.Press("knob_long"), ev.Press("knob"))  # Wi-Fi
    assert app.mode is Mode.WIFI
    send(ev.Rotate(STEP), ev.Press("knob"))  # Connect to a new network
    assert app.mode is Mode.WIFI_SETUP and app.wifi.state == "ready"
    app.render(0)
    app.wifi.join("Upstairs", "rightpassword")
    app.render(0)
    send(ev.Press("knob"))
    assert app.mode is Mode.SETTINGS and app.wifi.state == "off"


def test_back_or_a_card_closes_the_setup_network(rig):
    app, send, *_ = rig
    send(ev.Press("knob_long"), ev.Press("knob"), ev.Rotate(STEP), ev.Press("knob"))
    send(ev.Press("back"))
    assert app.mode is Mode.WIFI and app.wifi.state == "off"
    send(ev.Press("knob"))
    assert app.wifi.state == "ready"
    send(ev.CardInserted("04AA"))
    assert app.wifi.state == "off" and app.mode is Mode.LINKING


def test_switching_wifi_off_and_on(rig, tmp_path):
    app, send, store, _ = rig
    send(ev.Press("knob_long"), ev.Press("knob"))  # Settings, Wi-Fi
    assert [r[0] for r in app._wifi_rows()] == ["Wi-Fi", "Connect to a new network", "Show web player", "Back"]
    send(ev.Press("knob"))  # Wi-Fi: off
    assert app.wifi.backend.calls[-1] == ("radio", False)
    assert not store.wifi and Store(tmp_path / "state.json").wifi is False  # kept across restarts
    assert app.wifi.bars() is None and app.wifi.network() is None
    assert [r[0] for r in app._wifi_rows()] == ["Wi-Fi", "Back"]  # no network to join, no web page to show
    app.wifi.poll()
    assert app.wifi.bars() is None  # the signal is not followed while off
    app.wifi.open_portal()
    assert app.wifi.state == "off"
    send(ev.Press("knob"))  # Wi-Fi: on
    assert app.wifi.backend.calls[-1] == ("radio", True)
    assert store.wifi and app.wifi.bars() == 4 and app.wifi.network() == "Home"


def test_tiny_screen_shows_on_and_off(rig):
    app, send, store, _ = rig
    app.ui = tiny
    send(ev.Press("knob_long"), ev.Press("knob"))  # Wi-Fi page
    assert [r[2] for r in app._wifi_rows()] == ["On", "", "On", ""]
    on = app.render(0)
    right = (90, 0, 124, 11)  # the end of the first row, where its value goes
    assert on.crop(right).getbbox()
    store.web_remote = False
    send(ev.Press("knob"))  # Wi-Fi off
    assert [r[2] for r in app._wifi_rows()] == ["Off", ""]
    off = app.render(0)
    assert off.crop(right).getbbox() and off.crop(right).tobytes() != on.crop(right).tobytes()


def test_no_icon_while_wifi_is_off(rig):
    app, send, store, _ = rig
    drawn = []
    app.ui = type("UI", (), {"message": staticmethod(lambda *a: "screen"), "wifi_badge": staticmethod(lambda img, bars: drawn.append(bars) or img)})
    app.render(0)
    assert drawn == [4]
    store.wifi = False
    app.render(0)
    assert drawn == [4]


def test_wifi_stays_off_after_a_restart(music, tmp_path):
    store = Store(tmp_path / "state.json")
    store.wifi = False
    store.save()
    backend = Backend()
    wifi = w.Wifi(backend, spawn=lambda work: work())
    wifi.start_polling = lambda: None
    app = App(Library(music), Store(tmp_path / "state.json"), FakePlayback(Library(music)), wifi=wifi)
    wifi.start(enabled=app.store.wifi)
    assert backend.calls == [("radio", False)] and wifi.bars() is None
    assert app._wifi_line() == "Off" and "Off" in app._about_lines()[0]


def test_a_radio_that_will_not_switch_says_why(rig):
    app, send, *_ = rig

    def refuse(on):
        raise w.WifiError("helper missing")

    app.wifi.backend.radio = refuse
    send(ev.Press("knob_long"), ev.Press("knob"), ev.Press("knob"))
    assert "helper missing" in app._wifi_rows()[0][1]


def test_show_web_player_turns_the_remote_off_and_on(rig, tmp_path):
    app, send, store, _ = rig
    assert store.web_remote and app._wifi_rows()[2][1] == "On: http://nfcplayer.local"
    send(ev.Press("knob_long"), ev.Press("knob"), ev.Rotate(STEP), ev.Rotate(STEP), ev.Press("knob"))  # Show web player
    assert not store.web_remote and app._wifi_rows()[2][1].startswith("Off")
    assert Store(tmp_path / "state.json").web_remote is False  # kept across restarts
    app.render(0)
    send(ev.Press("knob"))
    assert store.web_remote and Store(tmp_path / "state.json").web_remote is True


def test_volume_limit(rig):
    app, send, store, playback = rig
    send(ev.Press("knob_long"), ev.Rotate(STEP), ev.Press("knob"))  # Volume limit
    assert app.mode is Mode.VOLUME_LIMIT
    store.volume = 90
    send(*[ev.Rotate(STEP)] * 5, ev.Press("knob"))  # down to 50
    assert store.max_volume == 50 and store.volume == 50 and playback.volume == 50
    assert app.mode is Mode.SETTINGS
    send(ev.WebCommand("volume", 80))
    assert store.volume == 50
    assert Store(store.path).max_volume == 50  # saved


def test_about_screen(rig):
    app, send, *_ = rig
    send(ev.Press("knob_long"), ev.Rotate(STEP), ev.Rotate(STEP), ev.Rotate(STEP), ev.Press("knob"))
    assert app.mode is Mode.ABOUT
    assert app._about[0] == "Wi-Fi: Home · strong signal"
    assert "Web remote: http://nfcplayer.local" in app._about
    assert "albums" in app._about[-1]
    app.render(0)
    send(ev.Press("back"))
    assert app.mode is Mode.SETTINGS


# ---- the icon ---------------------------------------------------------------


def test_icon_shows_on_the_screen(rig):
    app, send, *_ = rig
    corner = (270, 0, 320, 24)
    connected = app.render(0).crop(corner)
    app.wifi.backend.dbm = None
    app.wifi.poll()
    disconnected = app.render(0).crop(corner)
    assert connected.getbbox() and disconnected.getbbox()
    assert connected.tobytes() != disconnected.tobytes()


def test_tiny_icon_never_covers_text():
    clear = tiny.wifi_badge(tiny.message("Place a card", "to start playing"), 3)
    assert clear.crop(tiny.BADGE).getbbox()
    busy = tiny.list_screen("", [("A very long title that runs right across", "")], 0)
    assert tiny.wifi_badge(busy.copy(), 3).tobytes() == busy.tobytes()


def test_join_screens_draw():
    for ui in (render, tiny):
        ui.wifi_join(w.SETUP_SSID, "abcdefghjk", w.PORTAL_ADDRESS)
        ui.wifi_join(w.SETUP_SSID, "abcdefghjk", w.PORTAL_ADDRESS, "Could not join Home. Wrong password?")


# ---- the page ---------------------------------------------------------------


@pytest.fixture
def site(tmp_path, music):
    backend = Backend()
    backend.portal_network = None  # let the test's own address in
    wifi = w.Wifi(backend, spawn=lambda work: work())
    library = Library(music)
    writer = web.MusicWriter(lambda: None, idle_seconds=0.05)
    shared = web.Shared()
    server = web.start(queue.Queue(), shared, library, writer, port=0, bind="127.0.0.1", wifi=wifi)
    base = f"http://127.0.0.1:{server.server_address[1]}"

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None

    opener = urllib.request.build_opener(NoRedirect)

    def call(method, path, body=None, host=None):
        headers = {"X-Requested-With": "nfc-player"}
        if host:
            headers["Host"] = host
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body else None, method=method, headers=headers)
        try:
            with opener.open(req, timeout=5) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    yield call, wifi, shared
    server.shutdown()
    server.server_close()


def test_page_only_works_while_the_setup_network_is_open(site):
    call, wifi, _ = site
    status, body, _ = call("GET", "/api/wifi")
    assert json.loads(body)["state"] == "closed"
    status, _, _ = call("POST", "/api/wifi", {"ssid": "Home", "password": "rightpassword"})
    assert status == 403
    status, _, _ = call("GET", "/")
    assert status == 200  # the remote, as usual


def test_web_remote_off_refuses_all_but_the_setup_page(site):
    call, wifi, shared = site
    shared.enabled = False
    status, body, _ = call("GET", "/")
    assert status == 503 and b"turned off" in body
    for method, path in (("GET", "/api/state"), ("GET", "/api/library"), ("POST", "/api/command"), ("PUT", "/api/upload?path=A/b.flac"), ("GET", "/setup")):
        assert call(method, path, {"action": "toggle"})[0] == 503, path
    wifi.open_portal()
    status, body, _ = call("GET", "/api/wifi")
    assert status == 200 and json.loads(body)["state"] == "ready"
    shared.enabled = True
    assert call("GET", "/api/state")[0] == 200


def test_phones_on_the_setup_network_are_sent_to_the_page_and_can_join(site):
    call, wifi, _ = site
    wifi.open_portal()
    status, _, headers = call("GET", "/generate_204", host="connectivitycheck.gstatic.com")
    assert status == 302 and headers["Location"].endswith("/wifi")
    status, _, headers = call("GET", "/")
    assert status == 302
    status, body, _ = call("GET", "/api/wifi")
    assert json.loads(body)["networks"][0]["ssid"] == "Home"
    status, body, _ = call("POST", "/api/wifi", {"ssid": "", "password": ""})
    assert status == 400
    status, body, _ = call("POST", "/api/wifi", {"ssid": "Home", "password": "rightpassword"})
    assert status == 200 and wifi.state == "joined"
