# Contributing

Thanks for taking a look. Bug reports, fixes and ideas are all welcome. For anything bigger than a small fix, open an issue first so we can agree on the approach.

## Running the player without hardware

The simulator stands in for the screen, knob, buttons, cards, USB port and Wi-Fi, so you can work on almost everything without a Pi.

macOS and Linux:

```sh
python3 -m venv .venv
.venv/bin/pip install pillow numpy python-mpd2 pytest qrcode
.venv/bin/python -m player.demo_library demo/music
.venv/bin/python -m player.main --sim
```

Windows:

```bat
py -m venv .venv
.venv\Scripts\pip install pillow numpy python-mpd2 pytest qrcode
.venv\Scripts\python -m player.demo_library demo/music
.venv\Scripts\python -m player.main --sim
```

Open `http://localhost:8137` for the simulated device and `http://localhost:8080` for the web remote. Add `--display ssd1306` to see the small OLED layout. To try your own tagged music with `--music`, also install `mutagen`.

## Tests

Run the tests before sending a change. They need no hardware, and the same tests run on every push and pull request.

```sh
.venv/bin/python -m pytest
```

On Windows, use `.venv\Scripts\python -m pytest`.

Add a test with a behaviour change. Most tests drive `player/app.py` with events and a fake playback, so a test rarely needs more than a few lines. [`tests/test_player.py`](tests/test_player.py) has examples.

## Where things are

The [README](README.md#how-it-is-put-together) has a short map of the code. In brief:

- `player/` is the software that runs on the Pi.
- `system/` is the Pi's setup script and services.
- `NFC-Player-Case/` is the case and front board.
- `docs/` and the root `index.html` are the project site.

## Changing the case or the front board

Every dimension is in [`NFC-Player-Case/case.py`](NFC-Player-Case/case.py), and the STLs, drawings, pictures, guides and front board are all generated from it. Change `case.py`, not the outputs, and then rebuild. [`NFC-Player-Case/README.md`](NFC-Player-Case/README.md) lists the tools and the order to run the scripts.

The generated files are large. Commit them when a change is finished, not after every trial run, so the repository doesn't grow with copies nobody needs.

## The project site

GitHub Pages serves the site from the root of the repository. [`index.html`](index.html) is the home page, the user manual and electronics guide are in [`docs/`](docs), and the printing and assembly guides are written into `NFC-Player-Case/` by `guide.py`. Keep the empty `.nojekyll` file: without it, Pages runs the site through Jekyll. Moving any of these pages breaks links people have already shared.
