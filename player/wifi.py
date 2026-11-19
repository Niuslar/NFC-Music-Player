"""Wi-Fi: how strong the signal is, and a setup network for joining a new one.

To join a new network the player stops using Wi-Fi as a client and starts its own
network instead (the Zero 2 W's radio cannot do both). Its password is made up fresh
each time and shown only on the player's screen, so only someone standing at the
player can join it. A phone joins, opens the page the player serves there, and sends
the new network's name and password. The player then leaves its setup network and
joins the new one; if that fails, the setup network comes back so the phone can try again.

On the Pi, NetworkManager does the work through a small root helper
(system/nfc-player-wifi). NetworkManager keeps the saved password; the player never
writes it down. Wifi takes a backend so the simulator and the tests can stand in for it.
"""

import ipaddress
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path

SETUP_SSID = "NFC Player Setup"
PORTAL_ADDRESS = "10.42.0.1"  # NetworkManager's own address on a hotspot it shares
PORTAL_NETWORK = ipaddress.ip_network("10.42.0.0/24")
PORTAL_SECONDS = 10 * 60  # the setup network closes by itself if nobody uses it
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i: easy to read off the screen
PASSWORD_LENGTH = 10  # about 50 bits: far beyond guessing in the minutes the network is up
HELPER = "/usr/local/sbin/nfc-player-wifi"
POLL_SECONDS = 5.0


class WifiError(Exception):
    pass


def bars_from_dbm(dbm: float | None) -> int | None:
    """1-4 bars from a signal level, or None for no connection."""
    if dbm is None or dbm >= 0:
        return None
    if dbm >= -60:
        return 4
    if dbm >= -70:
        return 3
    if dbm >= -80:
        return 2
    return 1


def proc_level(text: str, iface: str = "wlan0") -> float | None:
    """The signal level in dBm from /proc/net/wireless, or None when not connected."""
    for line in text.splitlines():
        name, _, rest = line.strip().partition(":")
        if name != iface:
            continue
        fields = rest.split()
        try:
            link, level = float(fields[1].rstrip(".")), float(fields[2].rstrip("."))
        except (IndexError, ValueError):
            return None
        return level if link > 0 and level < 0 else None
    return None


def nmcli_fields(line: str) -> list[str]:
    """Splits one line of nmcli -t output, where ':' inside a value is written '\\:'."""
    fields, field, escaped = [], "", False
    for ch in line:
        if escaped:
            field, escaped = field + ch, False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append(field)
            field = ""
        else:
            field += ch
    fields.append(field)
    return fields


def parse_scan(text: str) -> list[dict]:
    """Networks from `nmcli -t -f SIGNAL,SECURITY,SSID device wifi list`, strongest first, one per name."""
    best: dict[str, dict] = {}
    for line in text.splitlines():
        fields = nmcli_fields(line)
        if len(fields) < 3:
            continue
        ssid = ":".join(fields[2:])
        try:
            signal = int(fields[0])
        except ValueError:
            continue
        if not ssid or ssid == SETUP_SSID:
            continue
        secure = fields[1] not in ("", "--")
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = {"ssid": ssid, "signal": signal, "secure": secure}
    return sorted(best.values(), key=lambda n: -n["signal"])


def local_address() -> str | None:
    """This device's address on the network it is on. Sends nothing."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            address = s.getsockname()[0]
    except OSError:
        return None
    return None if address.startswith("127.") else address


def check_new_network(ssid, password) -> tuple[str, str]:
    """Cleans what the setup page sent; raises WifiError with a message for the page."""
    if not isinstance(ssid, str) or not isinstance(password, str):
        raise WifiError("Send a network name and a password")
    if not ssid or len(ssid.encode()) > 32:
        raise WifiError("A network name is 1 to 32 characters")
    if password and not 8 <= len(password) <= 63:
        raise WifiError("A Wi-Fi password is 8 to 63 characters, or empty for an open network")
    if any(c in s for s in (ssid, password) for c in "\r\n\0"):
        raise WifiError("The name or password has a character that cannot be used")
    return ssid, password


class NetworkManagerBackend:
    """The Pi: NetworkManager through the root helper, and the kernel's signal level."""

    portal_network = PORTAL_NETWORK
    portal_address = PORTAL_ADDRESS

    def __init__(self, iface: str = "wlan0", helper: str = HELPER):
        self.iface, self.helper = iface, helper

    def _helper(self, *args: str, stdin: str = "", timeout: float = 60) -> str:
        done = subprocess.run(["sudo", "-n", self.helper, *args], input=stdin, capture_output=True, text=True, timeout=timeout)
        if done.returncode:
            raise WifiError(done.stderr.strip() or f"Wi-Fi helper failed ({args[0]})")
        return done.stdout

    def level(self) -> float | None:
        try:
            return proc_level(Path("/proc/net/wireless").read_text(), self.iface)
        except OSError:
            return None

    def network(self) -> str | None:
        try:
            out = subprocess.run(
                ["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi", "list", "ifname", self.iface, "--rescan", "no"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        for line in out.splitlines():
            fields = nmcli_fields(line)
            if fields[0] == "yes" and len(fields) > 1:
                return ":".join(fields[1:]) or None
        return None

    def scan(self) -> list[dict]:
        return parse_scan(self._helper("scan"))

    def hotspot_active(self) -> bool:
        try:
            out = subprocess.run(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        return "nfc-player-setup" in out.splitlines()

    def hotspot_up(self, password: str) -> None:
        self._helper("hotspot-up", stdin=password + "\n")

    def hotspot_down(self) -> None:
        self._helper("hotspot-down")

    def join(self, ssid: str, password: str) -> None:
        # Name and password go to the helper on stdin, never on a command line.
        try:
            self._helper("join", stdin=f"{ssid}\n{password}\n", timeout=90)
        except WifiError as e:
            raise WifiError(friendly_error(str(e))) from None


def friendly_error(raw: str) -> str:
    text = raw.lower()
    if "secrets were required" in text or "802-1x" in text or "psk" in text or "password" in text:
        return "Wrong password?"
    if "no network with ssid" in text or "not found" in text:
        return "The network was not found. Is it in range, and on 2.4 GHz?"
    if "timeout" in text or "timed out" in text:
        return "The network did not answer in time."
    return raw.splitlines()[-1] if raw else "It did not connect."


class SimBackend:
    """Stands in for NetworkManager in the simulator: networks that join unless the password is 'wrongpassword'."""

    portal_network = None  # the simulator only listens on localhost, so any visitor may use the page
    portal_address = "localhost:8080"

    def __init__(self):
        self.bars = 3
        self.ssid = "Home"
        self.delay = 1.5

    def level(self) -> float | None:
        return None if self.bars is None else {1: -85, 2: -75, 3: -65, 4: -50}[self.bars]

    def network(self) -> str | None:
        return self.ssid if self.bars is not None else None

    def scan(self) -> list[dict]:
        time.sleep(self.delay)
        return [
            {"ssid": "Home", "signal": 78, "secure": True},
            {"ssid": "Upstairs", "signal": 52, "secure": True},
            {"ssid": "Cafe guest", "signal": 30, "secure": False},
        ]

    def hotspot_up(self, password: str) -> None:
        self._saved = (self.bars, self.ssid)
        self.bars = None
        time.sleep(self.delay)

    def hotspot_down(self) -> None:
        self.bars, self.ssid = getattr(self, "_saved", (3, "Home"))

    def join(self, ssid: str, password: str) -> None:
        time.sleep(self.delay * 2)
        if password == "wrongpassword":
            raise WifiError("Wrong password?")
        self.bars, self.ssid = 3, ssid


def _spawn(work) -> None:
    threading.Thread(target=work, daemon=True).start()


class Wifi:
    """The signal for the screen, and the setup network's progress for the screen and the page.

    portal states: off, starting, ready (waiting for the phone), joining, joined, failed
    (back to waiting, with a message). Slow work runs on a thread; everything here is safe
    to call from the main loop and the web server at once.
    """

    def __init__(self, backend, clock=time.monotonic, spawn=_spawn):
        self.backend, self.clock, self.spawn = backend, clock, spawn
        self._lock = threading.Lock()
        self._busy = threading.Lock()  # one NetworkManager change at a time
        self._level: float | None = None
        self._network: str | None = None
        self.state = "off"
        self.password = ""
        self.networks: list[dict] = []
        self.message = ""
        self.joined = ""
        self._deadline = 0.0

    # ---- signal ------------------------------------------------------------

    def poll(self) -> None:
        """Reads the signal and network name. main calls this on a thread every few seconds."""
        if self.state != "off":
            return  # the radio is busy being the setup network
        level = self.backend.level()
        with self._lock:
            newly = level is not None and self._level is None
            self._level = level
        if newly:
            self.refresh_network()  # just connected: learn the name now rather than on the next round

    def refresh_network(self) -> None:
        with self._lock:
            self._network = self.backend.network() if self._level is not None else None

    def start_polling(self, seconds: float = POLL_SECONDS) -> None:
        def loop():
            n = 0
            while True:
                try:
                    if n % 6 == 0:
                        self.refresh_network()  # the name rarely changes; ask NetworkManager less often
                    self.poll()
                except Exception as e:  # never let the icon stop the player
                    print(f"wifi: {e}", flush=True)
                n += 1
                time.sleep(seconds)

        threading.Thread(target=loop, daemon=True).start()

    def bars(self) -> int | None:
        if self.state in ("starting", "ready", "failed", "joining", "closing"):
            return None  # the radio is the setup network, not on one
        with self._lock:
            return bars_from_dbm(self._level)

    def network(self) -> str | None:
        with self._lock:
            return self._network if self._level is not None else None

    # ---- setup network -----------------------------------------------------

    @property
    def portal_open(self) -> bool:
        return self.state in ("ready", "failed")

    def open_portal(self) -> None:
        if self.state != "off":
            return
        self.state, self.message, self.joined = "starting", "", ""
        self.password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))

        def work():
            with self._busy:
                try:
                    self.networks = self.backend.scan()  # before the radio is taken over
                except Exception as e:
                    print(f"wifi: scan failed: {e}", flush=True)
                    self.networks = []
                if self.state != "starting":
                    return  # cancelled meanwhile
                try:
                    self.backend.hotspot_up(self.password)
                except Exception as e:
                    self.state, self.message = "error", f"Could not start the setup network: {e}"
                    return
                if self.state != "starting":
                    return  # cancelled while it started: close_portal takes it down
                self._deadline = self.clock() + PORTAL_SECONDS
                self.state = "ready"

        self.spawn(work)

    def _down(self) -> None:
        try:
            self.backend.hotspot_down()
        except Exception as e:
            print(f"wifi: {e}", flush=True)

    def close_portal(self) -> None:
        """Leaves the setup network and goes back to a saved one. Safe to call in any state."""
        state, self.state = self.state, "closing"
        if state in ("off", "closing"):
            self.state = state
            return

        def work():
            with self._busy:  # waits for a start or a join that is still running
                if state != "joined":
                    self._down()  # harmless when it is not up
                self.password, self.networks = "", []
                self.state = "off"
                self.refresh_network()

        self.spawn(work)

    def join(self, ssid, password) -> None:
        """From the setup page: leave the setup network and join this one. Raises WifiError if refused."""
        ssid, password = check_new_network(ssid, password)
        with self._lock:
            if not self.portal_open:
                raise WifiError("The setup network is not open. Start it again from the player's settings.")
            self.state, self.message = "joining", ""

        def work():
            with self._busy:
                self._down()
                try:
                    self.backend.join(ssid, password)
                except Exception as e:
                    self.message = f"Could not join {ssid}. {e}"
                    try:
                        self.backend.hotspot_up(self.password)
                    except Exception as e2:
                        self.state, self.message = "error", f"{self.message} The setup network did not come back: {e2}"
                        return
                    self._deadline = self.clock() + PORTAL_SECONDS
                    self.state = "failed"
                    return
                self.joined, self.password, self.networks = ssid, "", []
                with self._lock:
                    self._level, self._network = self.backend.level(), ssid
                self.state = "joined"

        self.spawn(work)

    def tick(self) -> None:
        """Closes a setup network nobody used."""
        if self.portal_open and self.clock() > self._deadline:
            self.close_portal()

    def allows(self, client: str) -> bool:
        """Whether a visitor at this address may use the setup page: only phones on the setup network."""
        if not self.portal_open:
            return False
        net = self.backend.portal_network
        if net is None:
            return True
        try:
            return ipaddress.ip_address(client) in net
        except ValueError:
            return False

    def page_state(self) -> dict:
        return {"state": self.state, "networks": self.networks if self.portal_open else [], "message": self.message}

    def address(self) -> str:
        return self.backend.portal_address

    def start(self) -> None:
        """At start-up: takes down a setup network left over from before a restart, then follows the signal."""
        def work():
            with self._busy:
                try:
                    if getattr(self.backend, "hotspot_active", lambda: False)():
                        self._down()
                except Exception as e:
                    print(f"wifi: {e}", flush=True)
            self.start_polling()

        self.spawn(work)


class NoWifi:
    """For when Wi-Fi is not managed by the player (tests, or a Mac running without the simulator)."""

    state = "off"
    portal_open = False
    password = networks = message = joined = ""

    def bars(self):
        return None

    def network(self):
        return None

    def open_portal(self):
        self.state = "error"
        self.message = "Wi-Fi setup is not available here."

    def close_portal(self):
        self.state = "off"

    def tick(self):
        pass

    def allows(self, client):
        return False

    def address(self):
        return PORTAL_ADDRESS
