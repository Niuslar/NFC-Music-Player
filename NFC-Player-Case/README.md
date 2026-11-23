# NFC Player Case

The 3D-printed case for the NFC Album Player, and the small circuit board behind its keys. To print and build it, read the [3D printing guide](https://niuslar.github.io/NFC-Music-Player/NFC-Player-Case/NFC-Player-Printing.html) and the [assembly guide](https://niuslar.github.io/NFC-Music-Player/NFC-Player-Case/NFC-Player-Assembly.html). This page is for changing the design.

Every dimension is in [`case.py`](case.py). The other scripts read it, and everything else in this folder is generated from them, so a change always starts in `case.py`. Do not edit the outputs by hand: the next rebuild overwrites them.

## What is here

**Source**

| File | What it does |
|---|---|
| [`case.py`](case.py) | Every dimension and shape, in millimetres. The values marked MEASURE depend on the parts you bought. |
| [`build.py`](build.py) | Builds the STLs and the OpenSCAD copy with Blender, and checks that no two parts collide. |
| [`keycaps.py`](keycaps.py) | The key carrier: four key caps on one printed frame. `build.py` builds it too. |
| [`wood.py`](wood.py) | Optional: carves wood grain from your own `wood-grain.png` into the sides of the chassis. |
| [`drawings.py`](drawings.py) | Draws the dimensioned SVGs. Plain Python, no Blender. |
| [`pictures.py`](pictures.py) | Draws the assembly pictures for the guides. |
| [`render.py`](render.py) | Renders the hero picture, using the scene in `NFC-Player-Render.blend`. |
| [`guide.py`](guide.py) | Writes the printing and assembly guides, and the front board's section of the [electronics guide](../docs/index.html). |
| [`NFC-Player-Render.blend`](NFC-Player-Render.blend) | The render scene: camera, lights, materials and stand-ins for the bought parts. |
| [`front-board/board.py`](front-board/board.py) | Draws, routes and checks the front board in KiCad, and writes the files to order it. |

**Generated, and kept in the repository**

| File | Made by |
|---|---|
| [`STL/`](STL) | `build.py` and `keycaps.py`. These are the parts to print. |
| [`NFC-Player-Case.scad`](NFC-Player-Case.scad) | `build.py`. A copy for OpenSCAD users, not yet tried in OpenSCAD. |
| `Front-Panel.svg`, `Rear-Panel.svg`, `Board-Stack.svg`, `Controls-Section.svg`, `Key-Closeup.svg` | `drawings.py` |
| [`NFC-Player-Render.png`](NFC-Player-Render.png) | `render.py` |
| [`NFC-Player-Printing.html`](NFC-Player-Printing.html), [`NFC-Player-Assembly.html`](NFC-Player-Assembly.html) | `guide.py`. These pages are part of the project site. |
| `front-board/nfc-front-board.*` and [`front-board/fab/`](front-board/fab) | `board.py`. The KiCad project, the checks, and the Gerbers, BOM and placement files to order the board. |

**Generated, only on your computer** (listed in `.gitignore`): `parts.blend`, `pictures/` and the `*-wood.stl` files.

## What you need

Three free programs, on Windows, macOS or Linux:

- [Blender](https://www.blender.org/download/). The scripts were made with Blender 5.2. The commands below call it `blender`: put it on your PATH, or type the full path to the program instead.
- [KiCad](https://www.kicad.org/download/) 10 or later, only for the front board.
- Python 3 with Pillow (`pip install pillow`). Your Python may be called `python`, `python3` or `py`.

`board.py` needs the Python that comes with KiCad, because it uses KiCad's `pcbnew` module. On Windows, run it from the KiCad Command Prompt. On Linux, use the system `python3` that KiCad installs into. On macOS, use the `python3` bundled with KiCad.

## Rebuilding after a change

Edit `case.py`, then run these from this folder, in this order:

```sh
blender -b -P build.py
```

This rewrites the STLs and the OpenSCAD copy, and reports any part that collides with another.

```sh
cd front-board
python board.py
cd ..
```

Do this with KiCad's Python, whenever you move the keys, the screws or the board's outline. It redraws and reroutes the board, runs KiCad's electrical and design rules checks, and rewrites the files in `fab/`.

```sh
blender -b -P wood.py
```

This one is only needed for the wood-grain chassis.

```sh
python drawings.py
```

```sh
blender -b -P pictures.py
```

```sh
blender -b NFC-Player-Render.blend -P render.py
```

```sh
python guide.py
```

The checks in `build.py` prove that the parts fit each other and the stand-ins for the boards. They cannot check print tolerances, your exact boards, heat, or how well the NFC reader works next to stored cards. Those need a bench test.

The STLs, render and guides are large. Commit regenerated copies when a change is finished, not after every trial run: each copy stays in the repository's history for good.
