"""Writes NFC-Player-Assembly.html from the pictures, the drawings and case.py.

    ../.venv/bin/python guide.py      (needs Pillow; run pictures.py, drawings.py and render.py first)

The pictures carry no text. Each numbered marker is drawn as an overlay from
pictures/<name>.json and explained in a list beside the picture, so labels never overlap.
"""

import base64
import html
import io
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case as c  # noqa: E402

sys.path.insert(0, str(HERE / "front-board"))
import board as fb  # noqa: E402

PICS = HERE / "pictures"
BOARD_FAB = HERE / "front-board" / "fab"
REVISION = "4.1"


def n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def jpeg(path, width=1600, quality=84):
    im = Image.open(path).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def spread(points, w, h, gap=54.0, edge=26.0):
    """Moves marker positions apart so no two circles touch, keeping each near its point."""
    pos = [list(p) for p in points]
    for _ in range(200):
        moved = False
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                dx, dy = pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]
                d = math.hypot(dx, dy)
                if d < gap:
                    if d < 1e-6:
                        dx, dy, d = 1.0, 0.0, 1.0
                    push = (gap - d) / 2 + 0.5
                    pos[i][0] -= dx / d * push
                    pos[i][1] -= dy / d * push
                    pos[j][0] += dx / d * push
                    pos[j][1] += dy / d * push
                    moved = True
        for p in pos:
            p[0] = min(max(p[0], edge), w - edge)
            p[1] = min(max(p[1], edge), h - edge)
        if not moved:
            break
    return pos


def figure(name, caption, alt):
    meta = json.loads((PICS / f"{name}.json").read_text())
    w, h = meta["size"]
    anchors = [m["at"] for m in meta["marks"]]
    spots = spread(anchors, w, h)
    svg = [f'<svg class="overlay" viewBox="0 0 {w} {h}" aria-hidden="true">']
    for a in meta["arrows"]:
        (x0, y0), (x1, y1) = a["from"], a["to"]
        svg.append(f'<line class="arrow" x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}" marker-end="url(#head)"/>')
    for (ax, ay), (x, y) in zip(anchors, spots):
        if math.hypot(x - ax, y - ay) > 6:
            svg.append(f'<line class="leader" x1="{ax}" y1="{ay}" x2="{n(x)}" y2="{n(y)}"/><circle class="dot" cx="{ax}" cy="{ay}" r="5"/>')
    for i, (x, y) in enumerate(spots, 1):
        svg.append(f'<g class="mark" data-n="{i}"><circle cx="{n(x)}" cy="{n(y)}" r="21"/><text x="{n(x)}" y="{n(y + 8)}">{i}</text></g>')
    svg.append("</svg>")
    items = "".join(f'<li data-n="{i}">{html.escape(m["label"])}</li>' for i, m in enumerate(meta["marks"], 1))
    return (
        f'<figure class="pic" id="pic-{name}"><div class="frame"><img src="{jpeg(PICS / f"{name}.png")}" alt="{html.escape(alt)}" width="{w}" height="{h}">{"".join(svg)}</div>'
        f'<figcaption>{caption}</figcaption><ol class="legend">{items}</ol></figure>'
    )


def board_picture(file, caption, alt):
    return f'<figure class="pic"><div class="frame"><img src="{jpeg(BOARD_FAB / file, 1400, 86)}" alt="{html.escape(alt)}"></div><figcaption>{caption}</figcaption></figure>'


def header_table():
    """What plugs into each of the board's headers, straight from board.py."""
    leads = {
        "J2": ("Screen", "The lead that comes with the Waveshare screen: its plug into the screen, its eight female ends onto these pins, by name."),
        "J3": ("NFC reader", "Six female-to-female leads to the reader's pins of the same names. Leave its IRQ and RSTO pins free."),
        "J4": ("Knob (encoder)", "Five wires soldered to the encoder, ending in female leads. A, C and B are its three-pin side, C in the middle; the two SW pins are the push switch."),
        "J5": ("Power key", "Four wires soldered to the button. KEY and GND go to its switch tags (either way round); LED+ and LED− to its lamp tags, the right way round."),
        "J6": ("OLED (instead of the screen)", "Only if you use the 0.91-inch OLED: four leads to the OLED's pins of the same names."),
    }
    rows = []
    for ref, (title, names, nets, x1, z, value) in fb.HEADERS.items():
        what, how = leads[ref]
        pins = " · ".join(f"{i + 1} {html.escape(n)}" for i, n in enumerate(names))
        rows.append(f"<tr><td>{ref} <strong>{title}</strong></td><td>{what}</td><td><code>{pins}</code></td><td>{how}</td></tr>")
    return "<table><tr><th>Header</th><th>For</th><th>Pins, from pin 1</th><th>Lead</th></tr>" + "".join(rows) + "</table>"


def board_parts_table():
    rows, seen = [], {}
    for p in fb.PARTS:
        key = (p["value"] if p["ref"][0] in "DRQ" else p["footprint"][1], p["desc"])
        seen.setdefault(key, []).append(p["ref"])
    names = {"SW_PUSH_6mm_H5mm": f"6 × 6 mm through-hole tactile switch, {n(c.TACT_H)} mm tall (sold as 6x6x5 mm)", "IDC-Header_2x20_P2.54mm_Vertical": "2 × 20 shrouded box header, 2.54 mm, straight",
             "PinHeader_1x08_P2.54mm_Vertical": "1 × 8 straight pin header, 2.54 mm", "PinHeader_1x06_P2.54mm_Vertical": "1 × 6 straight pin header, 2.54 mm",
             "PinHeader_1x05_P2.54mm_Vertical": "1 × 5 straight pin header, 2.54 mm", "PinHeader_1x04_P2.54mm_Vertical": "1 × 4 straight pin header, 2.54 mm",
             "BAT43": "BAT43 Schottky diode (1N5817 also fits)", "2N3904": "2N3904 NPN transistor, TO-92", "1k": "1 kΩ resistor, ¼ W", "220": "220 Ω resistor, ¼ W"}
    for (name, desc), refs in seen.items():
        rows.append(f"<tr><td>{', '.join(refs)}</td><td>{names.get(name, name)}</td><td class=\"num\">{len(refs)}</td><td>{html.escape(desc)}</td></tr>")
    return "<table><tr><th>On the board</th><th>Part</th><th>Qty</th><th>Note</th></tr>" + "".join(rows) + "</table>"


def drawing(file, caption):
    svg = (HERE / file).read_text()
    svg = re.sub(r"<\?xml.*?\?>\s*", "", svg)
    svg = re.sub(r'width="[\d.]+mm" height="[\d.]+mm"', 'class="drawing" role="img"', svg, count=1)
    return f'<figure class="draw">{svg}<figcaption>{caption} <a href="{file}">{file}</a></figcaption></figure>'


CSS = """
:root{color-scheme:light;--ink:#1f2523;--muted:#56625c;--paper:#f6f4ee;--card:#fffefb;--line:#dcdbd1;--accent:#7a5428;--focus:#3f7fc4;--arrow:#d2452d}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:auto;padding:40px 28px 72px}
h1,h2{font-family:Georgia,"Times New Roman",serif;font-weight:500;letter-spacing:-.02em;line-height:1.1}
h1{font-size:clamp(2.6rem,6vw,4.4rem);margin:.25em 0 .3em}
h2{font-size:1.9rem;margin:0 0 .5em}
h3{font-size:1.08rem;margin:1.4em 0 .4em}
p{margin:.5em 0 1em}
a{color:#6c4826;text-underline-offset:.17em}
.kicker{font-size:.8rem;letter-spacing:.09em;text-transform:uppercase;font-weight:700;color:var(--accent)}
header{display:grid;grid-template-columns:1fr 1.15fr;gap:28px;align-items:center}
header p{color:var(--muted);max-width:38ch}
header img{width:100%;height:auto;border-radius:12px;display:block}
nav{display:flex;flex-wrap:wrap;gap:6px 18px;padding:14px 0;margin:20px 0 8px;border-bottom:1px solid var(--line);font-size:.95rem}
section{margin-top:24px;padding:28px;background:var(--card);border:1px solid var(--line);border-radius:14px}
table{width:100%;border-collapse:collapse;margin:.6em 0 1em;font-size:.93rem}
th,td{padding:.5em .6em;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
th{background:#efeee6;font-weight:650}
code{font-size:.87em;background:#efeee6;padding:.05em .3em;border-radius:4px;overflow-wrap:anywhere}
aside{background:#f1ebdd;border-left:3px solid #a37849;padding:12px 16px;margin:16px 0;border-radius:0 8px 8px 0}
.key{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:.88rem;color:var(--muted);margin:.4em 0 1em}
.key span::before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px;background:var(--c)}
.pic{margin:18px 0 8px}
.frame{position:relative;border-radius:10px;overflow:hidden;background:#f6f4ec;border:1px solid var(--line)}
.frame img{display:block;width:100%;height:auto}
.overlay{position:absolute;inset:0;width:100%;height:100%}
.mark circle{fill:#1f2523;stroke:#fff;stroke-width:3.5}
.mark text{fill:#fff;font:700 23px system-ui,sans-serif;text-anchor:middle}
.mark.on circle{fill:var(--arrow)}
.leader{stroke:#1f2523;stroke-width:2.5}
.dot{fill:#1f2523;stroke:#fff;stroke-width:1.5}
.arrow{stroke:var(--arrow);stroke-width:7;stroke-linecap:round}
figcaption{font-size:.9rem;color:var(--muted);margin:.5em .2em}
.legend{list-style:none;margin:.6em 0 0;padding:0;columns:2 300px;column-gap:28px;font-size:.93rem}
.legend li{break-inside:avoid;display:flex;gap:10px;align-items:baseline;padding:3px 4px;border-radius:6px;cursor:default}
.legend li::before{content:attr(data-n);flex:none;width:22px;height:22px;border-radius:50%;background:#1f2523;color:#fff;font-weight:700;font-size:.78rem;display:inline-grid;place-items:center;transform:translateY(5px)}
.legend li.on{background:#f3e3dc}
.step{display:grid;grid-template-columns:1fr;gap:4px;border-top:1px solid var(--line);padding-top:22px;margin-top:26px}
.step:first-of-type{border-top:0;margin-top:6px;padding-top:0}
.step h3{margin:0;font-size:1.25rem;font-family:Georgia,serif;font-weight:500}
.step h3 span{color:var(--accent);margin-right:.45em}
.step ol,.step ul{margin:.3em 0 .6em;padding-left:1.3em}
.step li{margin:.3em 0}
.draw{margin:20px 0}
.draw svg{display:block;width:100%;height:auto;background:#fff;border:1px solid var(--line);border-radius:10px}
@media(max-width:780px){header{grid-template-columns:1fr}main{padding:22px 14px 40px}section{padding:18px}th,td{padding:.4em}}
@media print{body,section{background:#fff}section{border:0;padding:0;break-inside:avoid-page}nav{display:none}.pic,.draw{break-inside:avoid}}
"""

JS = """
for (const fig of document.querySelectorAll('.pic')) {
  const marks = fig.querySelectorAll('.mark'), items = fig.querySelectorAll('.legend li');
  const set = (n, on) => { for (const el of [...marks, ...items]) if (el.dataset.n === n) el.classList.toggle('on', on); };
  for (const el of [...marks, ...items]) {
    el.addEventListener('mouseenter', () => set(el.dataset.n, true));
    el.addEventListener('mouseleave', () => set(el.dataset.n, false));
  }
}
"""


def step(num, title, picture, caption, alt, body, more=()):
    """more: further (picture, caption, alt) for the same step."""
    figs = ([figure(picture, caption, alt)] if picture else []) + [figure(*m) for m in more]
    return f'<div class="step" id="step-{num}"><h3><span>{num}</span>{title}</h3>{body}{"".join(figs)}</div>'


def page():
    jacks = c.DAC_JACKS
    key = '<div class="key"><span style="--c:#61a0db">Printed part fitted in this step</span><span style="--c:#cdcfca">Printed parts already in place</span><span style="--c:#d4a85c">Brass</span><span style="--c:#d2452d">Arrow: direction of fitting</span></div>'
    hero = HERE / "NFC-Player-Render.png"
    body = f"""
<main>
<header><div><div class="kicker">Mechanical assembly · Revision {REVISION}</div><h1>NFC Player<br>Case</h1>
<p>Charcoal printed case with a brass face set inside a thin printed rim, a card that leans back in a slot, and a tray in the lid for five spare cards.</p>
<p><strong>{n(c.W)} × {n(c.D)} × {n(c.H)} mm</strong> printed shell. Knob, screw heads, feet and cards stand proud of it; the key caps sit flush with the brass.</p></div>
<img src="{jpeg(hero, 1400, 86)}" alt="Rendered case: brass front inside a thin dark rim with a lit power key, a screen, four keys and a large knob; cards in a tray on the lid and one card standing in a slot"></header>
<nav><a href="#inside">What goes where</a><a href="#changes">Changes</a><a href="#measure">Measure first</a><a href="#print">Print</a><a href="#hardware">Hardware</a><a href="#controls">Keys, knob and power key</a><a href="#board">Front board</a><a href="#assembly">Assembly</a><a href="#drawings">Drawings</a><a href="#brass">Brass</a><a href="#rebuild">Rebuild</a></nav>

<section id="inside"><h2>What goes where</h2>
<p>The numbers on each picture are explained in the list under it. Hover a number or a line to pick out the other. The bought parts are simple blocks at their nominal size and position: they show where things go and which way round, not exactly what they look like.</p>
{figure("exploded", "Exploded view from the front left. Lid lifted, front and rear panels pulled out.", "Exploded case: lid above, front panel and brass pulled forward, rear panel pulled back, electronics inside the chassis")}
{figure("layout-top", "From above with the lid off. Front at the bottom. Grey: the ribbon. Lead colours: yellow screen, pink NFC reader, blue knob, orange power key, black USB.", "Top view of the open case showing the power key, screen, front board, keys, knob, card guide with reader, the Pi and DAC, the ribbon and the lead routes")}
{figure("layout-inside", "From the rear right with the lid and rear panel off.", "Open case from behind, showing the Pi and DAC, the ribbon plug on the DAC, the front board, the card guide and reader, and the screen bracket")}
</section>

<section id="changes"><h2>Changes in revision {REVISION}</h2><table><tr><th>Area</th><th>Change</th><th>Why</th></tr>
<tr><td>Keys</td><td>The Kailh Choc switches and their keycaps are gone. Each key is now a printed cap, {n(c.KEY_CAP)} mm square, that slides in a hole through the brass and the panel with its face flush with the brass, and presses a 6 × 6 mm tactile switch soldered to the front board. See <a href="#controls">Keys, knob and power key</a>.</td><td>Keyboard switches need 3 mm of travel in front of the panel, so their caps stood about 7.5 mm proud with a gap behind them. The tactile switches click after about {n(c.TACT_TRAVEL)} mm, like a hi-fi button.</td></tr>
<tr><td>Spacer</td><td>A new printed part, <code>board-spacer.stl</code>, {n(c.SPACER_T)} mm thick, between the panel and the front board. It has an opening round each key for the cap's lip and the switch, and openings for the board's solder joints.</td><td>It sets the switches just behind the caps. The panel itself stays {n(c.FRONT_T)} mm thick, so nothing else moves.</td></tr>
<tr><td>Front board</td><td>Revision 2: the four hot-swap sockets are replaced by the tactile switches, on the side facing the panel. Its top edge is {n(c.BOARD_Z[1])} mm up (was 53) to clear the card tray now that it sits further back. The board's screws are M2 × 6 (were M2 × 4).</td><td>The switches are soldered straight on, with no sockets.</td></tr>
<tr><td>Front panel and brass</td><td>A {n(c.KEY_HOLE)} mm square hole for each key in the panel, and {n(c.KEY_BRASS_HOLE)} mm in the brass, with rounded corners. The pockets for the switch clips and the board's solder joints are gone from the panel.</td><td>The holes guide the caps; the solder joints now sit in the spacer.</td></tr>
</section>

<section id="measure"><h2>Measure first</h2>
<p>Published drawings did not settle these, so each is a named value at the top of <code>case.py</code> with a sensible default. Measure your parts, change the value and <a href="#rebuild">rebuild</a> <strong>before printing the front or rear panel or cutting brass</strong>.</p>
<table><tr><th>Value</th><th>Default</th><th>What to measure</th></tr>
<tr><td><code>LCD_OFF_X</code>, <code>LCD_OFF_Z</code></td><td>{n(c.LCD_OFF_X)}, {n(c.LCD_OFF_Z)}</td><td>Where the lit area's centre sits relative to the centre of the 58 × 35 mm screen board, seen from the front. Set from Waveshare's outline drawing of the 2inch LCD Module: the picture sits about 2 mm right of centre with the pin pads on the left. Fit the board that way round, or change the sign. The bracket's screw slots let the screen move 2 mm either way sideways; to move it further, or up or down, change these and reprint the bracket.</td></tr>
<tr><td><code>LCD_HOLES</code>, <code>LCD_STANDOFF</code></td><td>{n(c.LCD_HOLES[0])} × {n(c.LCD_HOLES[1])} mm, {n(c.LCD_STANDOFF)} mm</td><td>The centres of the screen board's four corner holes, and how far its brass standoffs stand out behind the board. They set where the bracket's holes and upright are.</td></tr>
<tr><td><code>LCD_GLASS</code></td><td>{n(c.LCD_GLASS)} mm</td><td>How far the glass stands in front of the board. With the standoffs, it sets how far back the bracket's upright stands; the base slides {n(c.CRADLE_TRAVEL[1])} mm back and {n(c.CRADLE_TRAVEL[0])} mm forward from there.</td></tr>
<tr><td><code>DAC_JACKS</code></td><td>{"; ".join(f"{name} x {n(x)}, z {n(z)}, Ø{n(d)}" for name, x, z, d in jacks)}</td><td>Assemble the Pi and DAC on 5 mm standoffs and measure the centre of each socket: across from the case's left side and up from its underside. Check the holes pass your plugs' metal shells, not just the sockets' barrels. See the <a href="#drawings">board stack drawing</a> for the heights assumed.</td></tr>
<tr><td><code>POWER_HOLE</code>, <code>POWER_BODY</code></td><td>{n(c.POWER_HOLE)} mm; {n(c.POWER_BODY[0])} × {n(c.POWER_BODY[1])} mm</td><td>Your power key's thread, the size across its nut, and how far it reaches into the case including its solder tags.</td></tr>
<tr><td><code>USB_SLOT</code>, <code>USB_SCREW_PITCH</code></td><td>{n(c.USB_SLOT[0])} × {n(c.USB_SLOT[1])} mm, {n(c.USB_SCREW_PITCH)} mm</td><td>The body opening and screw spacing of your panel-mount USB-C socket.</td></tr>
</table>
<aside>Print the fit gauge first and try your encoder in it: its thread must pass {n(c.PANEL_AT_NUT + c.BRASS_T)} mm of panel and brass and still take the washer and nut.</aside>
</section>

<section id="print"><h2>Print</h2>
<p>Millimetres, 100% scale. Start with a 0.4 mm nozzle, 0.20 mm layers, four walls and 20% infill in PETG. The largest part is {n(c.W)} mm long and fits a 220 × 220 mm bed.</p>
<table><tr><th>File</th><th>Orientation and notes</th></tr>
<tr><td>fit-gauge.stl</td><td>Flat, pocket up. Print it first. It has a key cap's square hole, the encoder hole and its pocket, 3.3, 2.55 and 2.9 mm holes, the 55.4 × 1.65 mm card slot and a corner of the brass pocket.</td></tr>
<tr><td>chassis.stl</td><td>Floor down, no support. Clear the horizontal screw pilots in the towers by hand.</td></tr>
<tr><td>lid.stl</td><td>Top surface down, with support under the two curved edges.</td></tr>
<tr><td>front.stl</td><td>Inside face down, brass pocket up, no support.</td></tr>
<tr><td>board-spacer.stl</td><td>Flat, either face down.</td></tr>
<tr><td>keycap-previous.stl, keycap-play.stl, keycap-next.stl, keycap-back.stl</td><td>Face down, no support: the face comes out as smooth as the bed. 0.12 mm layers make the symbols sharper. Try one in the fit gauge's square hole: it should slide freely without rattling. Fill the symbols with paint if you like.</td></tr>
<tr><td>rear.stl</td><td>Flat, either face down.</td></tr>
<tr><td>card-guide.stl</td><td>Foot down, brim if needed. Keep support out of the card channel.</td></tr>
<tr><td>display-cradle.stl</td><td>Base down, as it stands in the case. No support.</td></tr></table>
</section>

<section id="hardware"><h2>Hardware</h2><ul>
<li>M3 screws that thread straight into the print (try one in the gauge first, and drive by hand): four M3 × 10 for the front (they pass the brass and panel), four M3 × 8 for the rear, four low-profile M3 × 6 for the lid (head at most 6 mm across and 1.5 mm tall), two M3 × 6 for the card guide and two for the screen bracket, each with a washer.</li><li>Four M2.5 × 5 screws to hold the screen's standoffs to its bracket (check the thread of the standoffs on your screen).</li>
<li>Four M2.5 standoffs 5 mm tall, four M2.5 × 6 screws from below, and four more on top for the Pi.</li>
<li>Three M2 × 6 pan-head screws for the front board, threaded through the spacer and into the panel.</li>
<li>A 40-way IDC ribbon cable for the Raspberry Pi, female at both ends with both plugs on the same side of the cable (the usual kind), as short as you can find: about 10 cm. The run is about 6 cm, and a longer cable just bows upward under the lid.</li>
<li>Keys, knob and power key: four tactile switches (they go on the board), an encoder, a knob and a lit push button, all bought; the key caps are printed. See <a href="#controls">Keys, knob and power key</a> for exactly what to get, and <a href="#board">Front board</a> for the board and its parts.</li>
<li>A panel-mount USB-C socket on a short lead ending in micro-USB.</li>
<li>{n(c.BRASS_T)} mm brass sheet and thin double-sided tape. Four feet at least 5 mm tall. Foam pads, female-to-female jumper leads, and thin hook-up wire for the encoder and power key.</li>
</ul></section>

<section id="controls"><h2>Keys, knob and power key</h2>
<p>The keys are printed caps that press small tactile switches on the front board. The knob sits on a rotary encoder, and the power key is a panel push button with a light in it. Those are bought parts, held by the printed front panel, and the brass covers its face.</p>

<h3>What to buy</h3>
<table><tr><th>Part</th><th>Get</th><th>Make sure</th></tr>
<tr><td>Key switches ×4</td><td>6 × 6 mm through-hole tactile switches, {n(c.TACT_H)} mm tall with the button (often sold as "6x6x5 mm")</td><td>Four legs on a 6.5 × 4.5 mm grid, and a body {n(c.TACT_BODY_H)} mm tall. Measure one: if it is not {n(c.TACT_H)} mm from its base to the top of the button, set <code>TACT_H</code> in <code>case.py</code> and rebuild, and the spacer changes to suit. Buy plenty; they come in packs.</td></tr>
<tr><td>Encoder</td><td>EC11-style rotary encoder with push switch: the Pi Hut one from the build guide, a Bourns PEC11R or an Alps EC11</td><td>An M7 threaded bushing at least 5 mm long, a 6 mm shaft that reaches at least 12 mm past the bushing, and a nut and washer (usually included). Try it in the fit gauge first.</td></tr>
<tr><td>Knob</td><td>Solid metal knob, up to {n(c.KNOB_D)} mm across, for a 6 mm shaft</td><td>Fixed with a set screw, and its bore matches your shaft's shape (D-flat or knurled).</td></tr>
<tr><td>Power key</td><td>12 mm panel push button with a lit ring or power symbol, black plastic or metal</td><td><strong>Momentary</strong>, not latching or self-locking. The {n(c.POWER_HOLE)} mm hole fits a 12 mm thread; its nut at most {n(c.POWER_BODY[0])} mm across and the body at most {n(c.POWER_BODY[1])} mm deep. An LED rated 3 V, or 5–6 V (those have a resistor inside: fit a wire link for R2 on the board). A 12 V or 24 V one will not light.</td></tr>
<tr><td>Wire</td><td>Thin hook-up wire and female jumper leads</td><td>The encoder and power key have solder tags, not connectors: solder a wire to each and finish it with a female jumper end for the board's pin headers.</td></tr></table>

<h3>How the keys feel</h3>
<p>A short, firm press with a click after about {n(c.TACT_TRAVEL)} mm, like the buttons on hi-fi gear. The click comes from the switch: cheap packs differ, so if you want a crisper or lighter one, any 6 × 6 mm through-hole switch of the same height fits.</p>

<h3 id="held">How they are held</h3>
<ul>
<li><strong>Key caps:</strong> each slides in its {n(c.KEY_HOLE)} mm square hole, face flush with the brass. A lip round its back stops it at the inside of the panel, so it cannot fall out of the front. Its back is hollow, and the switch stands inside it, {n(c.KEY_FREE)} mm short of the back of the face. The switch's button pushes the cap back out after a press. Nothing holds a cap but the panel and the board, so take the board off to change one.</li>
<li><strong>Key switches:</strong> soldered to the front of the <a href="#board">front board</a>, the side facing the panel. A printed spacer between panel and board sets the gap, and the board's three screws hold the lot together.</li>
<li><strong>Encoder:</strong> held by its own nut. It goes in from behind with the threaded bushing through the {n(c.ENCODER_HOLE)} mm hole. On the front, a washer and then the nut clamp the brass and the {n(c.PANEL_AT_NUT)} mm of plastic between the nut and the encoder body. The body also sits in a rectangular pocket, so it cannot turn when you twist the knob.</li>
<li><strong>Locating lug:</strong> many encoders have a small lug beside the bushing, meant for a hole in a metal panel. The pocket already stops the encoder turning, so nip the lug off flush with side cutters, or the body will not sit flat.</li>
<li><strong>Knob:</strong> slides onto the shaft and is held by its set screw on the shaft's flat. Leave about 1 mm between the knob and the nut so it never rubs.</li>
<li><strong>Power key:</strong> goes in from the front through the {n(c.POWER_HOLE)} mm hole; its nut tightens from behind. Its body reaches past the front left corner tower, which is cut away for it between {n(c.TOWER_GAP_Z[0])} and {n(c.TOWER_GAP_Z[1])} mm up.</li>
</ul>
{drawing("Key-Closeup.svg", "One key, cut through its middle with the front of the case at the top, four times full size: pulled apart in the order it goes together, and put together.")}
{drawing("Controls-Section.svg", "Sections through a key and through the encoder, three times full size.")}
<aside>The smooth Bourns EM14 encoder mentioned in the build guide as a later upgrade has a different bushing and body, and needs 5 V and two resistor dividers that the board does not have. Check its drawing against the encoder hole and pocket and change <code>ENCODER_HOLE</code> and <code>ENCODER_BODY</code> in <code>case.py</code>, and wire it as the build guide describes.</aside>
</section>

<section id="board"><h2>Front board</h2>
<p>A small printed circuit board, {n(c.BOARD_X[1] - c.BOARD_X[0])} × {n(c.BOARD_Z[1] - c.BOARD_Z[0])} mm, lies flat on a {n(c.SPACER_T)} mm printed spacer behind the front panel, behind the four keys. The keys' tactile switches are soldered to its front. A 40-way ribbon joins its box header to the pins on top of the DAC, so it reaches every pin of the Pi. The screen, NFC reader, knob and power key each plug into a labelled pin header on it. It also carries the two diodes the power key needs, and a transistor that lights the power key from 5 V.</p>
{board_picture("nfc-front-board-back.png", "The back of the board, where every part but the key switches goes. Seen from behind, so the keys read back, next, play, previous from left to right.", "Back of the front board: a 40-pin box header along the top, labelled pin headers for LCD, NFC, PWR, OLED and ENC, two diodes, two resistors and a transistor")}
{board_picture("nfc-front-board-front.png", "The front of the board, which faces the panel. Only the four key switches go on this side.", "Front of the front board, marked This side towards the panel, with the four tactile switches")}

<h3>Order it</h3>
<p>The board is drawn in KiCad by <code>front-board/board.py</code> from the numbers in <code>case.py</code>, so it always matches the panel. Upload <a href="front-board/fab/nfc-front-board-gerbers.zip">front-board/fab/nfc-front-board-gerbers.zip</a> to any board maker (JLCPCB, PCBWay, Aisler and others). Choose 2 layers, 1.6 mm FR-4, any colour and any finish. No assembly service is needed. Five boards usually cost a few pounds plus postage. The schematic is in <a href="front-board/fab/nfc-front-board-schematic.pdf">front-board/fab/nfc-front-board-schematic.pdf</a>, and the KiCad project in <code>front-board/</code> opens in KiCad 10 if you want to change anything.</p>

<h3>Parts on the board</h3>
{board_parts_table()}

<h3>Build it</h3>
<ol>
<li>Every part but the key switches goes on the back: the side with the part labels. The front is marked <em>This side towards the panel</em>.</li>
<li>Then the low parts: D1 and D2 with their stripe on the band printed on the board, R1 (1 kΩ), R2 (220 Ω, or a wire link if the power key's LED has its own resistor), and Q1 with its flat side on the flat of its outline.</li>
<li>Then the pin headers and the 40-pin box header, its notch where the board shows it. Hold each one square while you solder the first pin.</li>
<li>On the front, trim every lead to 1.5 mm or less, so the joints fit in the spacer's openings.</li>
<li>Last, the four key switches on the front, in the squares marked for them. Push each fully home so it sits flat and square; a tilted switch tilts its cap. Solder them from the back, and trim their legs too.</li>
<li>With a multimeter, check there is no short between 3.3 V, 5 V and ground: pins 1, 2 and 6 of the box header.</li>
</ol>

<h3>What plugs in where</h3>
{header_table()}
<p>The keys need no leads: their switches are on the board. The keys and the knob only pull a pin to ground, and the Pi's own pull-ups hold them high. The power key reaches GPIO 24 and GPIO 3 through D1 and D2, exactly as in the build guide. GPIO 22 still switches the light, through Q1, so nothing changes in the software or in <code>config.txt</code>.</p>
<aside>The box header sits straight in front of the Pi's header, the same way round: pin 1 on the right seen from the front, on the lower row. So the ribbon leaves the board, bends once and comes down onto the DAC's pins, with no twist or fold. The ribbon's red stripe marks pin 1 at both ends. On the board, pin 1 is at the triangle beside the box header, and its notch only lets the plug in one way. On the DAC there is no notch, so check before you push it on: pin 1 is the corner pin with a square pad on the Pi, at the right-hand end seen from the front of the case, and with the Pi running it reads 3.3 V, while its neighbour across the header (pin 2) reads 5 V.</aside>
</section>

<section id="assembly"><h2>Assembly</h2>
{key}
{step(1, "Fit the brass", "step-1-brass", "Front panel with the brass about to go in. Seen from the front left.", "Front panel with the brass face held in front of its pocket",
f"<ol><li>Deburr the brass and try it in the pocket. It should drop in with a hair of clearance and sit flush with the rim.</li><li>Stick it down with thin double-sided tape, lining the screw holes up with the panel's.</li></ol>")}
{step(2, "Fit the power key, the key caps and the encoder", "step-2-front", "Keys, knob and power key from the front left. The washer, nut, knob and power key are pulled forward; the encoder and the power key's nut are pulled back.", "Front of the panel with the key caps flush in the brass, and the power key, washer, nut and knob pulled out in the order they go on",
"<p>Solder four wires to the power key and five to the encoder first, each ending in a female jumper end (see <a href=\"#board\">What plugs in where</a>). It is easier before they are in the panel. Then:</p><ol><li>Push the power key in from the front and tighten its nut from behind, with its tags pointing down or sideways.</li><li>Lay the panel face down. Drop each key cap into its hole from behind, face first, until its lip stops it. From the front, left to right: previous, play/pause, next, back, so from behind they read back, next, play/pause, previous.</li><li>Nip off the encoder's locating lug if it has one. From behind, put the bushing through its hole so the body drops into the rectangular pocket.</li><li>On the front: washer, then nut. Tighten the nut firmly with a spanner, holding the body square in its pocket.</li><li>Slide the knob on, leaving about 1 mm clear of the nut, and tighten its set screw onto the flat of the shaft.</li></ol>",
more=[("step-2-controls", "The same panel from behind (the inside), so the knob end is on the left. One key cap is out of its hole and the encoder is pulled back from its pocket.", "Inside of the front panel with the power key, three key caps in their holes and one about to go in, and the encoder about to go into its pocket")])}
{step(3, "Fit the spacer and the front board", "step-3-board", "The inside of the front panel from behind on the power key side, with the spacer and board pulled back together.", "Front board and spacer held behind the panel, the switches on the board's front lined up with the key caps, with the ribbon plug on its box header",
"<ol><li>Build the board first (see <a href=\"#board\">Front board</a>).</li><li>Press the ribbon's plug onto the board's box header now, red stripe at the triangle. It is hard to reach once the board is on.</li><li>With the panel still face down and the caps in their holes, lay the spacer on the back of the panel, over the caps' lips, its screw holes over the panel's.</li><li>Lay the board on the spacer, switches down towards the caps (see the <a href=\"#held\">close-up of one key</a>).</li><li>Fit its three M2 × 6 screws, snug only: they thread into the spacer and the panel.</li><li>Turn it over and press each key: it should click, and spring back flush. A key that is already pressed in or rattles means a switch of a different height; see <code>TACT_H</code>.</li></ol>")}
{step(4, "Fit the front panel and the screen", "step-4-screen", "Front left corner of the chassis from behind, with the front panel fitted and the screen on its bracket, pulled back from the window.", "Screen screwed to an upright bracket on the chassis floor behind the window, its base slid back over two floor screws, with an arrow showing it pushed forward",
"<ol><li>Screw the front panel to the chassis with four M3 × 10 screws. The power key's body passes the front left corner tower through its notch.</li><li>Leave the four brass standoffs on the screen board. Screw the board to the bracket from behind with four M2.5 screws through the standoffs, glass facing away from the bracket and the socket on its open side. Leave them a little loose.</li><li>Stand the bracket behind the window, socket on the right by the knob, and put its two M3 × 6 screws and washers through the base's slots into the floor bosses, loosely.</li><li>Push the bracket forward until the glass touches the panel, then tighten its two floor screws.</li><li>Look through the window and slide the screen sideways in its slots until the lit area is centred, then tighten its four screws.</li><li>Push the lead's plug into the socket from the right, then bend the wires back towards the rear, clear of the encoder. A foam pad between the bracket and the lid stops it rattling.</li></ol>")}
{step(5, "Mount the Pi and the DAC", "step-5-stack", "Chassis from the front left with the front panel off for clarity, and the two boards lifted apart.", "Chassis floor with four standoffs in two slots, and the Pi and DAC above them",
"<ol><li>Screw four standoffs up through the two floor slots and leave them loose.</li><li>Screw the Pi onto them, header at the front. Plug the DAC straight onto the Pi, checking pin 1. The pins of its header stand up through it, ready for the ribbon.</li><li>Slide the stack back until the DAC's rear edge is {n(c.DAC_GAP)} mm from the rear panel's place (hold the panel on to check the sockets line up with its holes), then tighten the standoffs from below.</li></ol>")}
{step(6, "Fit the card guide and the NFC reader", "step-6-reader", "Card guide from the rear right, with the reader lifted out of its grooves.", "Card guide with two grooved posts behind the card slot and the NFC reader above them",
f"<ol><li>Screw the guide to the two floor bosses with M3 × 6 screws. The slot leans back toward the top.</li><li>Set the reader's switches for SPI. Slide it down into the middle pair of grooves in the two posts, antenna side toward the card and header at the top. That holds it {n(c.READER_GAP)} mm behind the card, where it reads best; this reader misses cards held right against it.</li><li>Try a card. If reads are unreliable, move the reader to the front or rear grooves ({n(c.READER_GAP + min(c.READER_SLOTS))} or {n(c.READER_GAP + max(c.READER_SLOTS))} mm). The lid stops it lifting out, so no tie or glue is needed.</li></ol>")}
{step(7, "Wire it", "step-7-wiring", "The open case from the rear left, with the lid and rear panel off.", "Open case from behind with the ribbon folded from the front board down onto the DAC, and leads from the screen, reader, knob and power key to the board",
"<ol><li>Run the ribbon straight back from the board and bend it down onto the pins on top of the DAC, red stripe on pin 1. It needs no twist and no fold.</li><li>Plug the leads into the board's headers as the table under <a href=\"#board\">What plugs in where</a> says: screen to LCD, reader to NFC, knob to ENC, power key to PWR.</li><li>Keep the ribbon and leads out from under the card tray, which comes down to 52 mm over the left two thirds of the case, and clear of the card slot. Leave enough slack that the front panel can come off with everything attached.</li><li>Before closing up, run the checks in the build guide: every key, the knob, the power key and its light, the screen and a card.</li></ol>")}
{step(8, "Fit the rear panel", "step-8-rear", "Rear of the case seen from the right, with the lid off.", "Rear panel with the DAC's RCA and headphone sockets in their own round holes, and the USB-C socket",
"<ol><li>Mount the USB-C socket in the rear panel and plug its lead into the Pi port marked USB (not PWR IN).</li><li>Screw the rear panel on with four M3 × 8 screws.</li><li>Check that an RCA plug and a headphone plug both seat fully through their holes.</li></ol>")}
{step(9, "Close up", "step-9-close", "Finished case from the front right, with the lid lifted.", "Lid being lowered onto the case between the front and rear panels",
"<ol><li>Before closing for good, test card reading with the brass fitted and five cards in the tray.</li><li>Lower the lid between the panels and fit its four low-profile screws, by hand.</li><li>Stick the feet on, clear of the floor slots and the vents.</li></ol>")}
</section>

<section id="drawings"><h2>Drawings</h2>
<p>Generated from <code>case.py</code>, so they match the STLs. Millimetres, measured from the bottom left of each view.</p>
{drawing("Front-Panel.svg", "Front panel as built, seen from the front.")}
{drawing("Rear-Panel.svg", "Rear panel seen from behind, so the holes for the DAC's sockets are on the right.")}
{drawing("Board-Stack.svg", "Side section through the Pi and DAC, with the front board and the ribbon, seen from the left.")}
</section>

<section id="brass"><h2>Brass face</h2>
<p>Cut it from {n(c.BRASS_T)} mm brass using <a href="Brass-Front-Template.svg">Brass-Front-Template.svg</a>. It is drawn at actual size, seen from the front: print it at 100% and check the scale bar measures exactly 100 mm before using it as a pattern. It has the power key's hole, a screen window, a {n(c.KEY_BRASS_HOLE)} mm square hole with rounded corners for each key, the encoder hole and four screw holes, with centre marks for a punch.</p>
{drawing("Brass-Front-Template.svg", "Brass template at actual size.")}
<p>The screen window has square corners and the key holes rounded ones, which suits laser or waterjet cutting, or a fretsaw and file. The key caps show any wobble in the key holes, so file them to the line. Deburr, then try it in the printed pocket before sticking it down.</p>
</section>

<section id="rebuild"><h2>Rebuilding after a change</h2>
<p>Edit the values at the top of <code>case.py</code>, then run these from this folder in order. The first rewrites the STLs, the OpenSCAD copy and the brass outline, and reports any part that collides with another. The OpenSCAD file is a generated copy and has not been run through OpenSCAD.</p>
<p><code>/Applications/Blender.app/Contents/MacOS/Blender -b -P build.py</code><br>
<code>(cd front-board && /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 board.py)</code><br>
<code>/Applications/Blender.app/Contents/MacOS/Blender -b -P keycaps.py</code><br>
<code>/Applications/Blender.app/Contents/MacOS/Blender -b -P wood.py</code> (only for the wood-grain version)<br>
<code>python3 drawings.py</code><br>
<code>/Applications/Blender.app/Contents/MacOS/Blender -b -P pictures.py</code><br>
<code>/Applications/Blender.app/Contents/MacOS/Blender -b NFC-Player-Render.blend -P render.py</code><br>
<code>../.venv/bin/python guide.py</code></p>
<p>The second line redraws and reroutes the front board, runs KiCad's electrical and design rules checks, and rewrites its Gerber files. Run it whenever you move the keys, the screws or the board's outline. The model checks that parts fit each other and the stand-ins. It cannot check print tolerances, your exact boards, heat, or how well the NFC reader works next to brass and stored cards: those need a bench test.</p>
</section>
</main>"""
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NFC Player Case Assembly</title><style>{CSS}</style></head><body><svg width="0" height="0" style="position:absolute"><defs><marker id="head" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="3.2" markerHeight="3.2" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#d2452d"/></marker></defs></svg>{body}<script>{JS}</script></body></html>'


if __name__ == "__main__":
    out = HERE / "NFC-Player-Assembly.html"
    out.write_text(page())
    print("wrote", out.name, f"{out.stat().st_size / 1e6:.1f} MB")
