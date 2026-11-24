"""Updates over Wi-Fi, from signed releases on GitHub.

A release has three files: the program as a tarball, a small manifest.json naming that
tarball with its SHA-256 and the version, and manifest.json.sig, an SSH signature of the
manifest. Only the manifest is signed: its hash covers the tarball, so one signature
covers both, and it can be checked before the tarball is downloaded at all.

The player does the unprivileged part here: it asks GitHub for the newest release,
checks the manifest's signature against the release keys in /etc/nfc-player/allowed_signers,
refuses anything not newer than what is running, downloads the tarball and checks its hash.
The root helper (system/nfc-player-update) then checks all of it again itself, because it
cannot trust files the player's user could have changed, writes the new version into the
slot that is not running, switches to it and restarts the player. If the new version does
not start and stay up, the helper switches back.

Updater takes an installer, so the simulator and the tests can stand in for the helper.
"""

import hashlib
import json
import re
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__

REPO = "Niuslar/NFC-Music-Player"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ALLOWED_SIGNERS = Path("/etc/nfc-player/allowed_signers")
SIGNER = "nfc-player-release"  # the name the release keys have in allowed_signers
NAMESPACE = "nfc-player-release"  # signatures made for anything else do not count
HELPER = "/usr/local/sbin/nfc-player-update"
SLOT_STATE = Path("/opt/nfc-player/state.json")  # written by the helper, readable by everyone
DOWNLOAD_DIR = Path("/var/lib/nfc-player/update")  # the helper reads the files from here
MANIFEST = "manifest.json"
SIGNATURE = "manifest.json.sig"
MAX_SMALL = 64 * 1024  # the release list, the manifest and its signature
MAX_TARBALL = 50 * 1024 * 1024
CONFIRM_AFTER = 30.0  # seconds the player must run before a new version counts as working
USER_AGENT = "nfc-player-updater"  # GitHub's API turns away requests without one
VERSION = re.compile(r"^v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})$")
TARBALL = re.compile(r"^nfc-player-\d{1,4}\.\d{1,4}\.\d{1,4}\.tar\.gz$")
BUSY = ("checking", "downloading", "verifying", "ready", "installing", "restarting")


class UpdateError(Exception):
    pass


def parse_version(text) -> tuple[int, int, int]:
    match = VERSION.match(text) if isinstance(text, str) else None
    if not match:
        raise UpdateError(f"{text!r} is not a version number")
    return tuple(int(n) for n in match.groups())


def check_manifest(data: bytes) -> dict:
    """The manifest's fields, checked; raises UpdateError if anything is off."""
    try:
        m = json.loads(data)
    except ValueError:
        raise UpdateError("The update's manifest could not be read.") from None
    if not isinstance(m, dict) or m.get("name") != "nfc-player":
        raise UpdateError("The update is not for this player.")
    parse_version(m.get("version"))
    if not isinstance(m.get("file"), str) or not TARBALL.match(m["file"]):
        raise UpdateError("The update's manifest names an unexpected file.")
    if not isinstance(m.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", m["sha256"]):
        raise UpdateError("The update's manifest has no valid checksum.")
    if not isinstance(m.get("size"), int) or not 0 < m["size"] <= MAX_TARBALL:
        raise UpdateError("The update's manifest gives an unexpected size.")
    return m


def has_keys(allowed_signers: Path) -> bool:
    try:
        lines = allowed_signers.read_text().splitlines()
    except OSError:
        return False
    return any(line.strip() and not line.lstrip().startswith("#") for line in lines)


def verify_signature(data: bytes, signature: bytes, allowed_signers: Path) -> None:
    """Raises UpdateError unless signature is a release key's signature of data."""
    if not has_keys(allowed_signers):
        raise UpdateError("Updates are not set up on this player: it has no release keys.")
    with tempfile.NamedTemporaryFile(suffix=".sig") as sig:
        sig.write(signature)
        sig.flush()
        try:
            done = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers), "-I", SIGNER, "-n", NAMESPACE, "-s", sig.name],
                input=data, capture_output=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            raise UpdateError("The update's signature could not be checked.") from None
    if done.returncode:
        raise UpdateError("The update's signature is not valid, so it was not installed.")


def _fetch(url: str, accept: str = "application/octet-stream", timeout: float = 20):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 (https only, see _https)


def _https(url) -> str:
    if not isinstance(url, str) or not url.startswith("https://"):
        raise UpdateError("The release has a download link that is not secure.")
    return url


class HelperInstaller:
    """The Pi: the root helper installs what is in DOWNLOAD_DIR, then restarts the player."""

    def __init__(self, helper: str = HELPER, state: Path = SLOT_STATE):
        self.helper, self.state = helper, state

    def install(self) -> None:
        done = subprocess.run(["sudo", "-n", self.helper, "install"], capture_output=True, text=True, timeout=600)
        if done.returncode:
            lines = (done.stderr or done.stdout).strip().splitlines()
            raise UpdateError(lines[-1] if lines else "The update could not be installed.")

    def slot_state(self) -> dict:
        try:
            data = json.loads(self.state.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def confirm(self) -> None:
        if self.slot_state().get("pending"):
            subprocess.run(["sudo", "-n", self.helper, "confirm"], capture_output=True, timeout=120, check=True)


class Updater:
    """Checks for, downloads and installs an update, on a thread. The screen follows state.

    idle -> checking -> latest | failed | error
                     -> downloading -> verifying -> ready      (the player then calls install())
                                                -> verified   (no installer: the simulator)
    ready -> installing -> restarting | error
    """

    def __init__(self, installer=None, current: str = __version__, allowed_signers: Path = ALLOWED_SIGNERS,
                 workdir: Path = DOWNLOAD_DIR, fetch=_fetch, spawn=None):
        self.installer = installer
        self.current = current
        self.allowed_signers = Path(allowed_signers)
        self.workdir = Path(workdir)
        self.fetch = fetch
        self.spawn = spawn or (lambda work: threading.Thread(target=work, daemon=True).start())
        self.state = "idle"
        self.version = ""  # the version found
        self.progress = 0  # percent downloaded
        self.message = ""
        self._run = 0  # each check gets a number; cancel() moves it on, so an old thread's results are dropped
        self._lock = threading.Lock()
        self._started_at: float | None = None
        self._confirm_sent = False

    # ---- what the player calls ------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self.state in BUSY:
                return
            self._run += 1
            run = self._run
            self.state, self.version, self.progress, self.message = "checking", "", 0, ""
        self.spawn(lambda: self._check(run))

    def fail(self, message: str) -> None:
        with self._lock:
            self._run += 1
            self.state, self.message = "error", message

    def cancel(self) -> None:
        """Back out of a check or download; once installing has begun, it carries on."""
        with self._lock:
            if self.state in ("installing", "restarting"):
                return
            self._run += 1
            self.state = "idle"

    def install(self) -> None:
        with self._lock:
            if self.state != "ready":
                return
            self.state = "installing"
            run = self._run
        self.spawn(lambda: self._install(run))

    def tick(self, now: float) -> None:
        """Once the player has been up for CONFIRM_AFTER seconds, tells the helper this version works."""
        if self._confirm_sent or self.installer is None:
            return
        if self._started_at is None:
            self._started_at = now
        elif now - self._started_at >= CONFIRM_AFTER:
            self._confirm_sent = True
            self.spawn(self._confirm)

    def failed_versions(self) -> list[str]:
        """Versions that were installed here but did not start, so the helper went back."""
        state = self.installer.slot_state() if self.installer is not None else {}
        failed = state.get("failed", [])
        return [v for v in failed if isinstance(v, str)] if isinstance(failed, list) else []

    # ---- the work, on a thread ----------------------------------------------------

    def _set(self, run: int, **fields) -> bool:
        """Updates the state unless the check was cancelled; says whether to carry on."""
        with self._lock:
            if run != self._run:
                return False
            for k, v in fields.items():
                setattr(self, k, v)
            return True

    def _small(self, url: str, accept: str = "application/octet-stream") -> bytes:
        with self.fetch(_https(url), accept) as r:
            data = r.read(MAX_SMALL + 1)
        if len(data) > MAX_SMALL:
            raise UpdateError("The release has a file that is far too large.")
        return data

    def _check(self, run: int) -> None:
        try:
            self._check_and_download(run)
        except UpdateError as e:
            self._set(run, state="error", message=str(e))
        except urllib.error.HTTPError as e:
            self._set(run, state="error", message=f"GitHub answered with an error ({e.code}). Try again later.")
        except (OSError, urllib.error.URLError, TimeoutError):
            self._set(run, state="error", message="Could not reach GitHub. Is the player online?")
        except Exception as e:  # never leave the screen on "Checking" forever
            self._set(run, state="error", message=f"Something unexpected happened: {e}")

    def _check_and_download(self, run: int) -> None:
        try:
            release = json.loads(self._small(LATEST_URL, "application/vnd.github+json"))
        except urllib.error.HTTPError as e:
            if e.code == 404:  # no release has been published yet
                self._set(run, state="latest")
                return
            raise
        except ValueError:
            raise UpdateError("GitHub's answer could not be read.") from None
        assets = {a.get("name"): a.get("browser_download_url") for a in release.get("assets", []) if isinstance(a, dict)}
        if MANIFEST not in assets or SIGNATURE not in assets:
            raise UpdateError("The newest release has no signed update in it.")
        manifest = self._small(assets[MANIFEST])
        signature = self._small(assets[SIGNATURE])
        verify_signature(manifest, signature, self.allowed_signers)
        m = check_manifest(manifest)
        version = m["version"].lstrip("v")
        if parse_version(version) <= parse_version(self.current):
            self._set(run, state="latest", version=version)
            return
        if version in self.failed_versions():
            message = f"Version {version} was installed but did not start, so the player went back to {self.current}."
            self._set(run, state="failed", version=version, message=message)
            return
        if m["file"] not in assets:
            raise UpdateError("The release is missing the file its manifest names.")
        if not self._set(run, state="downloading", version=version, progress=0):
            return
        self.workdir.mkdir(parents=True, exist_ok=True)
        for old in self.workdir.iterdir():  # an earlier download, finished or not
            if old.is_file() or old.is_symlink():
                old.unlink()
        digest, size = hashlib.sha256(), 0
        with self.fetch(_https(assets[m["file"]]), "application/octet-stream", 60) as r, open(self.workdir / m["file"], "wb") as out:
            while chunk := r.read(64 * 1024):
                size += len(chunk)
                if size > m["size"]:
                    raise UpdateError("The download is larger than the update's manifest says.")
                digest.update(chunk)
                out.write(chunk)
                if not self._set(run, progress=size * 100 // m["size"]):
                    return  # cancelled
        if not self._set(run, state="verifying"):
            return
        if size != m["size"] or digest.hexdigest() != m["sha256"]:
            raise UpdateError("The download does not match the signed manifest, so it was not installed.")
        (self.workdir / MANIFEST).write_bytes(manifest)
        (self.workdir / SIGNATURE).write_bytes(signature)
        self._set(run, state="ready" if self.installer is not None else "verified", progress=100)

    def _install(self, run: int) -> None:
        try:
            self.installer.install()
        except subprocess.TimeoutExpired:
            self._set(run, state="error", message="Installing took far too long and was stopped.")
        except (UpdateError, OSError) as e:
            self._set(run, state="error", message=str(e) or "The update could not be installed.")
        else:
            self._set(run, state="restarting")  # the helper has asked for the restart; it comes in a moment

    def _confirm(self) -> None:
        try:
            self.installer.confirm()
        except Exception as e:  # the helper's own watchdog decides; this is only worth a line in the log
            print(f"Could not confirm the update: {e}", flush=True)


class NoUpdater:
    """Stands in where there is no way to update (a computer running the player without the simulator)."""

    state, version, progress, current = "error", "", 0, __version__
    message = "Updates are not available on this player."

    def start(self) -> None:
        pass

    def fail(self, message: str) -> None:
        pass

    def cancel(self) -> None:
        pass

    def install(self) -> None:
        pass

    def tick(self, now: float) -> None:
        pass

