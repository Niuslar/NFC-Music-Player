"""Updates over Wi-Fi: the player's side (player/update.py), the settings screens, and the root
helper's A/B slots (system/nfc-player-update), all with real SSH signatures from a throwaway key."""

import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tarfile
import urllib.error
from pathlib import Path

import pytest

from player import events as ev
from player import update as up
from player import wifi as w
from player.app import SETTINGS_ITEMS, App, Mode
from player.cards import Store
from player.demo_library import build
from player.knob import COUNTS_PER_REV
from player.library import Library
from player.playback import FakePlayback
from player.ui import render, tiny

REPO = Path(__file__).resolve().parent.parent
STEP = round(COUNTS_PER_REV * 15 / 360) + 1  # one list row

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs OpenSSH's ssh-keygen")


# ---- keys, releases and a fake GitHub ------------------------------------------------


def make_key(folder: Path, name: str) -> tuple[Path, str]:
    key = folder / name
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
    return key, key.with_suffix(".pub").read_text().strip()


def sign(key: Path, data: bytes, folder: Path) -> bytes:
    path = folder / "manifest.json"
    path.write_bytes(data)
    sig = folder / "manifest.json.sig"
    if sig.exists():
        sig.unlink()
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n", up.NAMESPACE, str(path)], check=True, capture_output=True)
    return sig.read_bytes()


def tarball(version: str, extra=None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        files = {"player/__init__.py": f'__version__ = "{version}"\n'.encode(), "player/main.py": b"print('hello')\n",
                 "system/allowed_signers": b"# none\n", "pyproject.toml": b"[project]\n"}
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o644
            tar.addfile(info, io.BytesIO(data))
        for info, data in extra or []:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return buf.getvalue()


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    folder = tmp_path_factory.mktemp("keys")
    key, public = make_key(folder, "release")
    stranger, _ = make_key(folder, "stranger")
    allowed = folder / "allowed_signers"
    allowed.write_text(f'# release keys\n{up.SIGNER} namespaces="{up.NAMESPACE}" {public}\n')
    return {"key": key, "stranger": stranger, "allowed": allowed, "folder": folder}


class Release:
    """One release on a fake GitHub: what fetch() serves."""

    def __init__(self, keys, version="0.2.0", signer=None, tamper=False):
        self.tar = tarball(version)
        name = f"nfc-player-{version}.tar.gz"
        self.manifest = json.dumps({"name": "nfc-player", "version": version, "file": name, "size": len(self.tar),
                                    "sha256": hashlib.sha256(self.tar).hexdigest()}).encode()
        self.sig = sign(signer or keys["key"], self.manifest, keys["folder"])
        if tamper:
            self.tar = self.tar[:-1] + bytes([self.tar[-1] ^ 1])
        self.files = {f"https://dl/{name}": self.tar, "https://dl/manifest.json": self.manifest, "https://dl/manifest.json.sig": self.sig}
        assets = [{"name": url.rsplit("/", 1)[1], "browser_download_url": url} for url in self.files]
        self.files[up.LATEST_URL] = json.dumps({"tag_name": f"v{version}", "assets": assets}).encode()
        self.asked: list[str] = []

    def fetch(self, url, accept="", timeout=0):
        self.asked.append(url)
        if url not in self.files:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return io.BytesIO(self.files[url])


class FakeInstaller:
    def __init__(self, failed=()):
        self.installed = 0
        self.failed = list(failed)
        self.error = None

    def install(self):
        if self.error:
            raise up.UpdateError(self.error)
        self.installed += 1

    def slot_state(self):
        return {"failed": self.failed}

    def confirm(self):
        pass


def updater(keys, tmp_path, release, installer=None, current="0.1.0"):
    return up.Updater(installer, current=current, allowed_signers=keys["allowed"], workdir=tmp_path / "update",
                      fetch=release.fetch, spawn=lambda work: work())


# ---- the player's side --------------------------------------------------------------


def test_versions_compare_as_numbers():
    assert up.parse_version("v0.10.0") > up.parse_version("0.9.9")
    with pytest.raises(up.UpdateError):
        up.parse_version("1.0")


def test_a_newer_signed_release_is_downloaded_and_checked(keys, tmp_path):
    release = Release(keys)
    u = updater(keys, tmp_path, release, FakeInstaller())
    u.start()
    assert u.state == "ready" and u.version == "0.2.0" and u.progress == 100
    assert (tmp_path / "update" / "nfc-player-0.2.0.tar.gz").read_bytes() == release.tar
    assert (tmp_path / "update" / "manifest.json.sig").read_bytes() == release.sig
    u.install()
    assert u.state == "restarting" and u.installer.installed == 1


def test_the_same_version_is_not_offered(keys, tmp_path):
    u = updater(keys, tmp_path, Release(keys, "0.1.0"))
    u.start()
    assert u.state == "latest"


def test_no_release_yet_means_up_to_date(keys, tmp_path):
    release = Release(keys)
    release.files.pop(up.LATEST_URL)
    u = updater(keys, tmp_path, release)
    u.start()
    assert u.state == "latest"


def test_a_release_signed_by_another_key_is_refused_before_downloading(keys, tmp_path):
    release = Release(keys, signer=keys["stranger"])
    u = updater(keys, tmp_path, release, FakeInstaller())
    u.start()
    assert u.state == "error" and "signature" in u.message
    assert not any(url.endswith(".tar.gz") for url in release.asked)


def test_a_changed_tarball_is_refused(keys, tmp_path):
    u = updater(keys, tmp_path, Release(keys, tamper=True), FakeInstaller())
    u.start()
    assert u.state == "error" and "does not match" in u.message


def test_a_player_with_no_keys_refuses_updates(keys, tmp_path):
    empty = tmp_path / "allowed_signers"
    empty.write_text("# nothing yet\n")
    u = up.Updater(FakeInstaller(), current="0.1.0", allowed_signers=empty, workdir=tmp_path, fetch=Release(keys).fetch, spawn=lambda work: work())
    u.start()
    assert u.state == "error" and "no release keys" in u.message


def test_a_version_that_failed_here_is_not_tried_again(keys, tmp_path):
    u = updater(keys, tmp_path, Release(keys), FakeInstaller(failed=["0.2.0"]))
    u.start()
    assert u.state == "failed" and "went back to 0.1.0" in u.message


def test_cancelling_drops_a_check_that_is_still_running(keys, tmp_path):
    later = []
    u = up.Updater(FakeInstaller(), current="0.1.0", allowed_signers=keys["allowed"], workdir=tmp_path, fetch=Release(keys).fetch, spawn=later.append)
    u.start()
    u.cancel()
    later[0]()  # the thread finishes after the screen was left
    assert u.state == "idle"


def test_offline_is_a_plain_message(keys, tmp_path):
    def offline(url, accept="", timeout=0):
        raise urllib.error.URLError("no route")

    u = up.Updater(None, current="0.1.0", allowed_signers=keys["allowed"], workdir=tmp_path, fetch=offline, spawn=lambda work: work())
    u.start()
    assert u.state == "error" and "Could not reach GitHub" in u.message


def test_the_new_version_confirms_once_it_has_been_up_a_while(keys, tmp_path):
    confirmed = []
    installer = FakeInstaller()
    installer.confirm = lambda: confirmed.append(1)
    u = updater(keys, tmp_path, Release(keys), installer)
    u.tick(10.0)
    u.tick(10.0 + up.CONFIRM_AFTER - 1)
    assert not confirmed
    u.tick(10.0 + up.CONFIRM_AFTER)
    u.tick(10.0 + up.CONFIRM_AFTER + 5)
    assert confirmed == [1]


# ---- the settings screens -------------------------------------------------------------


@pytest.fixture(scope="module")
def music(tmp_path_factory):
    root = tmp_path_factory.mktemp("music")
    build(root)
    return root


@pytest.fixture
def rig(music, tmp_path, keys):
    library = Library(music)
    store = Store(tmp_path / "state.json")
    playback = FakePlayback(library)
    wifi = w.Wifi(w.SimBackend(), spawn=lambda work: work())
    wifi.poll()
    release = Release(keys)
    installer = FakeInstaller()
    later = []
    u = up.Updater(installer, current="0.1.0", allowed_signers=keys["allowed"], workdir=tmp_path / "update", fetch=release.fetch, spawn=later.append)
    app = App(library, store, playback, wifi=wifi, updater=u)
    t = [100.0]

    def send(*events):
        for e in events:
            app.handle(e, t[0])
            t[0] += 0.5
        app.tick(t[0])

    def work():  # lets the updater's threads run, one after another
        while later:
            later.pop(0)()
        app.tick(t[0])

    def open_update():
        send(ev.Press("knob_long"), *[ev.Rotate(STEP)] * SETTINGS_ITEMS.index("Firmware update"), ev.Press("knob"))

    return app, send, work, open_update, installer, store


def screens(app):
    for ui in (render, tiny):
        app.ui = ui
        app.render(0)
    app.ui = render


def test_firmware_update_checks_downloads_and_installs(rig):
    app, send, work, open_update, installer, _ = rig
    open_update()
    assert app.mode is Mode.UPDATE and app.updater.state == "checking"
    screens(app)
    work()  # check and download: ready, and the next tick hands it to the installer
    assert app.updater.state == "installing"
    screens(app)
    work()
    assert installer.installed == 1 and app.updater.state == "restarting"
    screens(app)
    send(ev.Press("back"))
    assert app.mode is Mode.UPDATE  # nothing to back out of now


def test_a_card_while_installing_waits_for_the_restart(rig):
    app, send, work, open_update, installer, store = rig
    open_update()
    later_install = app.updater.spawn
    app.updater.spawn = lambda job: None  # hold the install so it stays "installing"
    work()
    app.updater.spawn = later_install
    assert app.updater.state == "installing"
    send(ev.CardInserted("04AA"), ev.WebCommand("play_album", app.library.albums[0].key))
    assert app.mode is Mode.UPDATE and app.album is None and app.card == "04AA"


def test_a_card_during_the_check_cancels_it(rig):
    app, send, work, open_update, installer, store = rig
    open_update()
    send(ev.CardInserted("04AA"))
    work()
    assert app.mode is not Mode.UPDATE and app.updater.state == "idle" and installer.installed == 0


def test_back_during_the_check_returns_to_settings(rig):
    app, send, work, open_update, *_ = rig
    open_update()
    send(ev.Press("back"))
    assert app.mode is Mode.SETTINGS and SETTINGS_ITEMS[app.selected] == "Firmware update"
    work()
    assert app.updater.state == "idle"


def test_no_wifi_says_so_without_checking(rig):
    app, send, work, open_update, *_ = rig
    app.wifi.backend.bars = None
    app.wifi.poll()
    open_update()
    assert app.updater.state == "error" and "not connected" in app.updater.message
    screens(app)
    send(ev.Press("knob"))
    assert app.mode is Mode.SETTINGS


def test_an_install_that_fails_is_shown(rig):
    app, send, work, open_update, installer, _ = rig
    installer.error = "The update's signature is not valid."
    open_update()
    work()
    work()
    assert app.updater.state == "error" and "signature" in app.updater.message
    screens(app)
    send(ev.Press("knob"))
    assert app.mode is Mode.SETTINGS


def test_settings_and_about_show_the_version(rig):
    app, send, *_ = rig
    send(ev.Press("knob_long"))
    screens(app)
    app._about = app._about_lines()
    assert "Version 0.1.0" in app._about and "albums" in app._about[-1]


# ---- the root helper: A/B slots -------------------------------------------------------


@pytest.fixture
def helper(tmp_path, keys, monkeypatch):
    loader = importlib.machinery.SourceFileLoader("nfc_player_update", str(REPO / "system" / "nfc-player-update"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    h = importlib.util.module_from_spec(spec)
    loader.exec_module(h)
    h.ROOT = tmp_path / "opt"
    h.DOWNLOAD_DIR = tmp_path / "download"
    h.KEYS = tmp_path / "etc" / "allowed_signers"
    h.KEYS.parent.mkdir()
    shutil.copy(keys["allowed"], h.KEYS)
    h.ROOT.mkdir()
    h.DOWNLOAD_DIR.mkdir()
    h.calls = []
    monkeypatch.setattr(h, "restart_player", lambda: h.calls.append("restart"))
    monkeypatch.setattr(h, "start_watchdog", lambda: h.calls.append("watchdog"))
    monkeypatch.setattr(h, "stop_watchdog", lambda: h.calls.append("stop watchdog"))
    source = tmp_path / "checkout"
    (source / "player").mkdir(parents=True)
    (source / "player" / "__init__.py").write_text('__version__ = "0.1.0"\n')
    (source / "system").mkdir()
    (source / "system" / "allowed_signers").write_text("# none\n")
    h.cmd_install_dir(source)  # what setup.sh does
    return h


def download(h, release: Release) -> None:
    m = json.loads(release.manifest)
    (h.DOWNLOAD_DIR / m["file"]).write_bytes(release.tar)
    (h.DOWNLOAD_DIR / "manifest.json").write_bytes(release.manifest)
    (h.DOWNLOAD_DIR / "manifest.json.sig").write_bytes(release.sig)


def test_setup_installs_into_a_slot(helper):
    assert helper.active_slot() in helper.SLOTS and helper.slot_version(helper.active_slot()) == "0.1.0"


def test_an_update_goes_into_the_other_slot_and_is_kept_once_confirmed(helper, keys, tmp_path):
    old = helper.active_slot()
    download(helper, Release(keys))
    helper.cmd_install()
    new = helper.active_slot()
    assert new != old and helper.slot_version(new) == "0.2.0" and helper.slot_version(old) == "0.1.0"
    assert helper.load_state()["pending"]["version"] == "0.2.0" and helper.calls[-1] == "restart"
    assert (helper.ROOT / new / "release.json").is_file()
    helper.cmd_boot()
    assert helper.load_state()["pending"]["starts"] == 1 and "watchdog" in helper.calls
    helper.cmd_confirm()
    assert helper.load_state()["pending"] is None and helper.active_slot() == new
    helper.cmd_boot()  # later starts change nothing
    assert helper.active_slot() == new


def test_a_version_that_keeps_failing_to_start_is_rolled_back(helper, keys):
    old = helper.active_slot()
    download(helper, Release(keys))
    helper.cmd_install()
    for _ in range(helper.MAX_STARTS):
        helper.cmd_boot()
        assert helper.active_slot() != old
    helper.cmd_boot()
    state = helper.load_state()
    assert helper.active_slot() == old and state["pending"] is None and state["failed"] == ["0.2.0"]
    download(helper, Release(keys))
    with pytest.raises(helper.Refused, match="already failed"):
        helper.cmd_install()


def test_a_version_that_never_confirms_is_rolled_back_by_the_watchdog(helper, keys):
    old = helper.active_slot()
    download(helper, Release(keys))
    helper.cmd_install()
    helper.cmd_boot()
    helper.cmd_watchdog()
    assert helper.active_slot() == old and helper.calls[-1] == "restart"


def test_confirming_installs_new_release_keys(helper, keys, tmp_path):
    _, public = make_key(tmp_path, "new")
    release = Release(keys)
    # The same release, with new keys in it.
    new_keys = f"{helper.SIGNER} {public}\n".encode()
    info = tarfile.TarInfo("system/allowed_signers")
    info.size = len(new_keys)
    buf = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(release.tar), mode="r:gz") as src, tarfile.open(fileobj=buf, mode="w:gz") as dst:
        for m in src.getmembers():
            if m.name != "system/allowed_signers":
                dst.addfile(m, src.extractfile(m))
        dst.addfile(info, io.BytesIO(new_keys))
    release.tar = buf.getvalue()
    m = json.loads(release.manifest)
    m.update(size=len(release.tar), sha256=hashlib.sha256(release.tar).hexdigest())
    release.manifest = json.dumps(m).encode()
    release.sig = sign(keys["key"], release.manifest, keys["folder"])
    download(helper, release)
    helper.cmd_install()
    assert helper.KEYS.read_bytes() != new_keys  # not before it has proved it starts
    helper.cmd_confirm()
    assert helper.KEYS.read_bytes() == new_keys


@pytest.mark.parametrize("kind", ["older", "stranger", "tampered"])
def test_the_helper_checks_everything_itself(helper, keys, kind):
    release = {"older": lambda: Release(keys, "0.0.9"), "stranger": lambda: Release(keys, signer=keys["stranger"]),
               "tampered": lambda: Release(keys, tamper=True)}[kind]()
    download(helper, release)
    before = helper.active_slot()
    with pytest.raises(helper.Refused):
        helper.cmd_install()
    assert helper.active_slot() == before and not helper.load_state().get("pending")


def test_the_helper_does_not_follow_links_the_player_planted(helper, keys, tmp_path):
    download(helper, Release(keys))
    secret = tmp_path / "secret"
    secret.write_text("root only")
    (helper.DOWNLOAD_DIR / "manifest.json").unlink()
    (helper.DOWNLOAD_DIR / "manifest.json").symlink_to(secret)
    with pytest.raises(helper.Refused, match="not a plain file"):
        helper.cmd_install()


def _member(name, kind=tarfile.REGTYPE, data=b"x", link=""):
    info = tarfile.TarInfo(name)
    info.type, info.linkname = kind, link
    info.size = len(data) if kind == tarfile.REGTYPE else 0
    return info, data if kind == tarfile.REGTYPE else None


@pytest.mark.parametrize("member", [
    _member("../evil.py"),
    _member("/etc/evil"),
    _member("player/../../evil"),
    _member("player/link", tarfile.SYMTYPE, link="/etc/shadow"),
    _member("player/hard", tarfile.LNKTYPE, link="player/__init__.py"),
    _member("home/evil"),
])
def test_unpacking_refuses_anything_but_plain_files_in_place(helper, tmp_path, member):
    path = tmp_path / "bad.tar.gz"
    path.write_bytes(tarball("0.2.0", [member]))
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(helper.Refused):
        helper.unpack(path, dest)
    assert not (tmp_path / "evil.py").exists()


def test_unpacking_a_git_archive_like_the_release_tool_makes(helper, tmp_path):
    if not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    path = tmp_path / "release.tar.gz"
    subprocess.run(["git", "archive", "--format=tar.gz", f"--output={path}", "HEAD", "player", "system", "pyproject.toml"], cwd=REPO, check=True)
    dest = tmp_path / "dest"
    dest.mkdir()
    helper.unpack(path, dest)
    assert (dest / "player" / "main.py").is_file() and os.access(dest / "system" / "setup.sh", os.X_OK)
