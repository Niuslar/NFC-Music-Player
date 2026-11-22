"""Writes the case's two guides from the pictures, the drawings and case.py:
NFC-Player-Printing.html (printing and finishing each part) and NFC-Player-Assembly.html
(putting them together), and the front board's section of ../docs/index.html, the electronics guide.

    python guide.py      (needs Pillow; run pictures.py, drawings.py and render.py first)

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
REVISION = "4.2"


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
        key = (p["value"] if p["lcsc"] else p["footprint"][1], p["desc"], p["lcsc"])
        seen.setdefault(key, []).append(p["ref"])
    names = {"SW_PUSH_6mm_H5mm": f"6 × 6 mm through-hole tactile switch, {n(c.TACT_H)} mm tall (sold as 6x6x5 mm)", "IDC-Header_2x20_P2.54mm_Vertical": "2 × 20 shrouded box header, 2.54 mm, straight",
             "PinHeader_1x08_P2.54mm_Vertical": "1 × 8 straight pin header, 2.54 mm", "PinHeader_1x06_P2.54mm_Vertical": "1 × 6 straight pin header, 2.54 mm",
             "PinHeader_1x05_P2.54mm_Vertical": "1 × 5 straight pin header, 2.54 mm", "PinHeader_1x04_P2.54mm_Vertical": "1 × 4 straight pin header, 2.54 mm",
             "B5819W": "B5819W Schottky diode, SOD-123", "MMBT3904": "MMBT3904 NPN transistor, SOT-23", "1k": "1 kΩ resistor, 0603", "220": "220 Ω resistor, 0603",
             "2.2k": "2.2 kΩ resistor, 0603", "Red": "Red LED, 0603", "Orange": "Orange LED, 0603"}
    for (name, desc, lcsc), refs in seen.items():
        who = f"Board maker (LCSC {lcsc})" if lcsc else "You"
        rows.append(f"<tr><td>{', '.join(refs)}</td><td>{names.get(name, name)}</td><td class=\"num\">{len(refs)}</td><td>{who}</td><td>{html.escape(desc)}</td></tr>")
    return "<table><tr><th>On the board</th><th>Part</th><th>Qty</th><th>Fitted by</th><th>Note</th></tr>" + "".join(rows) + "</table>"


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
.guides{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.88rem;margin-bottom:10px}.guides .here{font-weight:700;color:var(--ink)}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px;background:var(--c);border:1px solid rgba(0,0,0,.15)}
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


PRINTING = "NFC-Player-Printing.html"
ASSEMBLY = "NFC-Player-Assembly.html"
ELECTRONICS = "../docs/index.html"
HERO_ALT = "Rendered case: a walnut wood-grain box with a brass front inside a thin wood rim, a lit power key, a screen, four keys and a large knob; cards in a tray on the lid and one card standing in a slot"


def hero_header(kicker, title, paragraphs):
    return (f'<header><div><div class="kicker">{kicker} · Revision {REVISION}</div><h1>{title}</h1>{paragraphs}</div>'
            f'<img src="{jpeg(HERE / "NFC-Player-Render.png", 1400, 86)}" alt="{HERO_ALT}"></header>')


def guides_nav(here):
    """Links between the three guides, shown above each case guide's own contents."""
    links = [(ELECTRONICS, "Electronics guide"), (PRINTING, "3D printing guide"), (ASSEMBLY, "Assembly guide")]
    return '<div class="guides">' + "".join(f'<span class="here">{t}</span>' if f == here else f'<a href="{f}">{t}</a>' for f, t in links) + "</div>"


def wrap(title, body):
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{CSS}</style></head><body><svg width="0" height="0" style="position:absolute"><defs><marker id="head" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="3.2" markerHeight="3.2" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#d2452d"/></marker></defs></svg>{body}<script>{JS}</script></body></html>'


def assembly_page():
    key = '<div class="key"><span style="--c:#61a0db">Printed part fitted in this step</span><span style="--c:#cdcfca">Printed parts already in place</span><span style="--c:#d4a85c">Brass</span><span style="--c:#d2452d">Arrow: direction of fitting</span></div>'
    body = f"""
<main>
{guides_nav(ASSEMBLY)}
{hero_header("Mechanical assembly", "NFC Player<br>Case", f'''
<p>Putting the printed parts, the brass face, the built front board and the electronics together: wood-fill sides, front and lid, a brass face set inside a thin printed rim, a charcoal back, a card that leans back in a slot, and a tray in the lid for five spare cards.</p>
<p><strong>{n(c.W)} × {n(c.D)} × {n(c.H)} mm</strong> printed shell. Knob, screw heads, feet and cards stand proud of it; the key caps sit flush with the brass.</p>''')}
<nav><a href="#inside">What goes where</a><a href="#changes">Changes</a><a href="#hardware">Hardware</a><a href="#controls">Keys, knob and power key</a><a href="#assembly">Assembly</a><a href="#drawings">Drawings</a><a href="#brass">Brass</a></nav>
<aside><strong>Before you start.</strong> This guide begins with every part printed and finished. Measuring your bought parts, the fit gauge, which filament each part is printed in, slicer settings, the wood grain and staining are all in the <a href="{PRINTING}">3D printing guide</a>. Wiring and setting up the Pi on the bench, and building the front board, are in the <a href="{ELECTRONICS}">electronics guide</a>: do that first, so you know every part works before it goes in the case.</aside>

<section id="inside"><h2>What goes where</h2>
<p>The numbers on each picture are explained in the list under it. Hover a number or a line to pick out the other. The bought parts are simple blocks at their nominal size and position: they show where things go and which way round, not exactly what they look like.</p>
{figure("exploded", "Exploded view from the front left. Lid lifted, front and rear panels pulled out.", "Exploded case: lid above, front panel and brass pulled forward, rear panel pulled back, electronics inside the chassis")}
{figure("layout-top", "From above with the lid off. Front at the bottom. Grey: the ribbon. Lead colours: yellow screen, pink NFC reader, blue knob, orange power key, black USB.", "Top view of the open case showing the power key, screen, front board, keys, knob, card guide with reader, the Pi and DAC, the ribbon and the lead routes")}
{figure("layout-inside", "From the rear right with the lid and rear panel off.", "Open case from behind, showing the Pi and DAC, the ribbon plug on the DAC, the front board, the card guide and reader, and the screen bracket")}
</section>

<section id="changes"><h2>Changes in revision {REVISION}</h2><table><tr><th>Area</th><th>Change</th><th>Why</th></tr>
<tr><td>Keys</td><td>The four key caps are now one printed part, the key carrier: a thin frame that lies on the inside of the panel, with each cap hanging from two {n(c.BRIDGE_T)} mm bridges, one above it and one below. The caps no longer have a lip. See <a href="#held">How they are held</a>.</td><td>Loose caps could rattle and rock in their holes. The bridges hold each cap centred, so it does not rattle, and keep it from falling out, while the switch still gives the click.</td></tr>
<tr><td>Spacer</td><td><code>board-spacer.stl</code> is now {n(c.SPACER_T)} mm thick (was 2.5), since the carrier's {n(c.CARRIER_T)} mm frame lies under it. Its opening round each key is taller, for the bridges.</td><td>The board and its switches stay exactly where they were.</td></tr>
<tr><td>Front panel</td><td>Two {n(c.PEG_HOLE)} mm blind holes in the inside face for the carrier's pegs.</td><td>They line the carrier up, so every cap sits in the middle of its hole.</td></tr>
<tr><td>Fit gauge</td><td>A peg hole, {n(c.PEG_HOLE)} mm.</td><td>To check the pegs fit before printing the panel.</td></tr>
</section>

<section id="hardware"><h2>Hardware</h2><ul>
<li>M3 screws that thread straight into the print (try one in the <a href="{PRINTING}#gauge">fit gauge</a> first, and drive by hand): four M3 × 10 for the front (they pass the brass and panel), four M3 × 8 for the rear, four low-profile M3 × 6 for the lid (head at most 6 mm across and 1.5 mm tall), two M3 × 6 for the card guide and two for the screen bracket, each with a washer.</li><li>Four M2.5 × 5 screws to hold the screen's standoffs to its bracket (check the thread of the standoffs on your screen).</li>
<li>Four M2.5 standoffs 5 mm tall, four M2.5 × 6 screws from below, and four more on top for the Pi.</li>
<li>Three M2 × 6 pan-head screws for the front board, threaded through the spacer and the key carrier and into the panel.</li>
<li>A 40-way IDC ribbon cable for the Raspberry Pi, female at both ends with both plugs on the same side of the cable (the usual kind), as short as you can find: about 10 cm. The run is about 6 cm, and a longer cable just bows upward under the lid.</li>
<li>Keys, knob and power key: four tactile switches (they go on the board), an encoder, a knob and a lit push button, all bought; the key caps are printed, all four on one key carrier. See <a href="#controls">Keys, knob and power key</a> for exactly what to get. The front board and its parts are in the <a href="{ELECTRONICS}#board">electronics guide</a>.</li>
<li>A panel-mount USB-C socket on a short lead ending in micro-USB.</li>
<li>{n(c.BRASS_T)} mm brass sheet and thin double-sided tape. Four feet at least 5 mm tall. Foam pads, female-to-female jumper leads, and thin hook-up wire for the encoder and power key.</li>
</ul></section>

<section id="controls"><h2>Keys, knob and power key</h2>
<p>The keys are printed caps, all four on one printed key carrier, that press small tactile switches on the front board. The knob sits on a rotary encoder, and the power key is a panel push button with a light in it. Those are bought parts, held by the printed front panel, and the brass covers its face.</p>

<h3>What to buy</h3>
<table><tr><th>Part</th><th>Get</th><th>Make sure</th></tr>
<tr><td>Key switches ×4</td><td>6 × 6 mm through-hole tactile switches, {n(c.TACT_H)} mm tall with the button (often sold as "6x6x5 mm")</td><td>Four legs on a 6.5 × 4.5 mm grid, and a body {n(c.TACT_BODY_H)} mm tall. Measure one: if it is not {n(c.TACT_H)} mm from its base to the top of the button, set <code>TACT_H</code> in <code>case.py</code> and <a href="{PRINTING}#rebuild">rebuild</a>, and the spacer changes to suit. Buy plenty; they come in packs.</td></tr>
<tr><td>Encoder</td><td>EC11-style rotary encoder with push switch: the Pi Hut one from the <a href="{ELECTRONICS}#parts">electronics guide</a>, a Bourns PEC11R or an Alps EC11</td><td>An M7 threaded bushing at least 5 mm long, a 6 mm shaft that reaches at least 12 mm past the bushing, and a nut and washer (usually included). Try it in the <a href="{PRINTING}#gauge">fit gauge</a> first.</td></tr>
<tr><td>Knob</td><td>Solid metal knob, up to {n(c.KNOB_D)} mm across, for a 6 mm shaft</td><td>Fixed with a set screw, and its bore matches your shaft's shape (D-flat or knurled).</td></tr>
<tr><td>Power key</td><td>12 mm panel push button with a lit ring or power symbol, black plastic or metal</td><td><strong>Momentary</strong>, not latching or self-locking. The {n(c.POWER_HOLE)} mm hole fits a 12 mm thread; its nut at most {n(c.POWER_BODY[0])} mm across and the body at most {n(c.POWER_BODY[1])} mm deep. An LED rated 3 V, or 5–6 V (those have a resistor inside: fit a wire link for R2 on the board). A 12 V or 24 V one will not light.</td></tr>
<tr><td>Wire</td><td>Thin hook-up wire and female jumper leads</td><td>The encoder and power key have solder tags, not connectors: solder a wire to each and finish it with a female jumper end for the board's pin headers.</td></tr></table>

<h3>How the keys feel</h3>
<p>A short, firm press with a click after about {n(c.TACT_TRAVEL)} mm, like the buttons on hi-fi gear. The click comes from the switch: cheap packs differ, so if you want a crisper or lighter one, any 6 × 6 mm through-hole switch of the same height fits. The carrier's bridges bend as you press and add roughly 0.5 N, about a third of a typical switch's force, so the click still comes through. To make the keys lighter or firmer, change <code>BRIDGE_T</code> in <code>case.py</code>: the force goes with the cube of the thickness.</p>

<h3 id="held">How they are held</h3>
<ul>
<li><strong>Key caps:</strong> all four are one printed part, the key carrier. Its {n(c.CARRIER_T)} mm frame lies on the inside of the panel, and each cap sits in its {n(c.KEY_HOLE)} mm square hole, face flush with the brass. Each cap hangs from two thin bridges, one above it and one below, joined to the middle of its edge by a short tab. The bridges keep it centred in its hole, so it does not rattle, and stop it falling out. A press bends them a little. The cap's back is hollow, and the switch stands inside it, {n(c.KEY_FREE)} mm short of the back of the face. The switch clicks and pushes the cap back out. Two pegs on the frame sit in holes in the panel and line the carrier up. The board's screws clamp the carrier and the spacer to the panel, so take the board off to reach it.</li>
<li><strong>Rocking:</strong> the bridges are thin enough not to dull the click, which also means they cannot stop a cap tilting if you press hard on one edge. The panel's hole still limits that, as before, to the {n((c.KEY_HOLE - c.KEY_CAP) / 2)} mm of clearance round the cap.</li>
<li><strong>Key switches:</strong> soldered to the front of the <a href="{ELECTRONICS}#board">front board</a>, the side facing the panel. The carrier and a printed spacer between panel and board set the gap, and the board's three screws hold the lot together.</li>
<li><strong>Encoder:</strong> held by its own nut. It goes in from behind with the threaded bushing through the {n(c.ENCODER_HOLE)} mm hole. On the front, a washer and then the nut clamp the brass and the {n(c.PANEL_AT_NUT)} mm of plastic between the nut and the encoder body. The body also sits in a rectangular pocket, so it cannot turn when you twist the knob.</li>
<li><strong>Locating lug:</strong> many encoders have a small lug beside the bushing, meant for a hole in a metal panel. The pocket already stops the encoder turning, so nip the lug off flush with side cutters, or the body will not sit flat.</li>
<li><strong>Knob:</strong> slides onto the shaft and is held by its set screw on the shaft's flat. Leave about 1 mm between the knob and the nut so it never rubs.</li>
<li><strong>Power key:</strong> goes in from the front through the {n(c.POWER_HOLE)} mm hole; its nut tightens from behind. Its body reaches past the front left corner tower, which is cut away for it between {n(c.TOWER_GAP_Z[0])} and {n(c.TOWER_GAP_Z[1])} mm up.</li>
</ul>
{drawing("Key-Closeup.svg", "One key, cut through its middle with the front of the case at the top, four times full size: pulled apart in the order it goes together, and put together.")}
{drawing("Controls-Section.svg", "Sections through a key and through the encoder, three times full size.")}
<aside>The smooth Bourns EM14 encoder mentioned in the <a href="{ELECTRONICS}">electronics guide</a> as a later upgrade has a different bushing and body, and needs 5 V and two resistor dividers that the board does not have. Check its drawing against the encoder hole and pocket and change <code>ENCODER_HOLE</code> and <code>ENCODER_BODY</code> in <code>case.py</code>, and wire it as the electronics guide describes.</aside>
</section>

<section id="assembly"><h2>Assembly</h2>
{key}
{step(1, "Fit the brass", "step-1-brass", "Front panel with the brass about to go in. Seen from the front left.", "Front panel with the brass face held in front of its pocket",
f"<ol><li>Deburr the brass and try it in the pocket. It should drop in with a hair of clearance and sit flush with the rim.</li><li>Stick it down with thin double-sided tape, lining the screw holes up with the panel's.</li></ol>")}
{step(2, "Fit the power key, the key carrier and the encoder", "step-2-front", "Keys, knob and power key from the front left. The washer, nut, knob and power key are pulled forward; the encoder and the power key's nut are pulled back.", "Front of the panel with the key caps flush in the brass, and the power key, washer, nut and knob pulled out in the order they go on",
f"<p>Solder four wires to the power key and five to the encoder first, each ending in a female jumper end (see <a href=\"{ELECTRONICS}#board-leads\">What plugs in where</a> in the electronics guide). It is easier before they are in the panel. Then:</p><ol><li>Push the power key in from the front and tighten its nut from behind, with its tags pointing down or sideways.</li><li>Lay the panel face down. Lay the key carrier on it, caps down, so each cap drops into its hole and the two pegs into their holes. The frame then lies flat on the panel. From the front, left to right, the keys read previous, play/pause, next, back. Press each cap from the front: it should move in a little and spring back, without catching on the sides of its hole.</li><li>Nip off the encoder's locating lug if it has one. From behind, put the bushing through its hole so the body drops into the rectangular pocket.</li><li>On the front: washer, then nut. Tighten the nut firmly with a spanner, holding the body square in its pocket.</li><li>Slide the knob on, leaving about 1 mm clear of the nut, and tighten its set screw onto the flat of the shaft.</li></ol>",
more=[("step-2-controls", "The same panel from behind (the inside), so the knob end is on the left. The key carrier and the encoder are pulled back.", "Inside of the front panel with the power key, the key carrier held behind it with its four caps lined up with their holes, and the encoder about to go into its pocket")])}
{step(3, "Fit the spacer and the front board", "step-3-board", "The inside of the front panel from behind on the power key side, with the key carrier in place and the spacer and board pulled back together.", "Front board and spacer held behind the panel and the key carrier, the switches on the board's front lined up with the key caps, with the ribbon plug on its box header",
f"<ol><li>Build the board first: see <a href=\"{ELECTRONICS}#board\">Front board for the case</a> in the electronics guide.</li><li>Press the ribbon's plug onto the board's box header now, red stripe at the triangle. It is hard to reach once the board is on.</li><li>With the panel still face down and the carrier in place, lay the spacer on the carrier, its screw holes over the carrier's.</li><li>Lay the board on the spacer, switches down towards the caps (see the <a href=\"#held\">close-up of one key</a>).</li><li>Fit its three M2 × 6 screws, snug only: they thread into the spacer and the panel.</li><li>Turn it over and press each key: it should click, and spring back flush. A key that is already pressed in or rattles means a switch of a different height; see <code>TACT_H</code> under <a href=\"{PRINTING}#measure\">Measure first</a>.</li></ol>")}
{step(4, "Fit the front panel and the screen", "step-4-screen", "Front left corner of the chassis from behind, with the front panel fitted and the screen on its bracket, pulled back from the window.", "Screen screwed to an upright bracket on the chassis floor behind the window, its base slid back over two floor screws, with an arrow showing it pushed forward",
"<ol><li>Screw the front panel to the chassis with four M3 × 10 screws. The power key's body passes the front left corner tower through its notch.</li><li>Leave the four brass standoffs on the screen board. Screw the board to the bracket from behind with four M2.5 screws through the standoffs, glass facing away from the bracket and the socket on its open side. Leave them a little loose.</li><li>Stand the bracket behind the window, socket on the right by the knob, and put its two M3 × 6 screws and washers through the base's slots into the floor bosses, loosely.</li><li>Push the bracket forward until the glass touches the panel, then tighten its two floor screws.</li><li>Look through the window and slide the screen sideways in its slots until the lit area is centred, then tighten its four screws.</li><li>Push the lead's plug into the socket from the right, then bend the wires back towards the rear, clear of the encoder. A foam pad between the bracket and the lid stops it rattling.</li></ol>")}
{step(5, "Mount the Pi and the DAC", "step-5-stack", "Chassis from the front left with the front panel off for clarity, and the two boards lifted apart.", "Chassis floor with four standoffs in two slots, and the Pi and DAC above them",
"<ol><li>Screw four standoffs up through the two floor slots and leave them loose.</li><li>Screw the Pi onto them, header at the front. Plug the DAC straight onto the Pi, checking pin 1. The pins of its header stand up through it, ready for the ribbon.</li><li>Slide the stack back until the DAC's rear edge is {n(c.DAC_GAP)} mm from the rear panel's place (hold the panel on to check the sockets line up with its holes), then tighten the standoffs from below.</li></ol>")}
{step(6, "Fit the card guide and the NFC reader", "step-6-reader", "Card guide from the rear right, with the reader lifted out of its grooves.", "Card guide with two grooved posts behind the card slot and the NFC reader above them",
f"<ol><li>Screw the guide to the two floor bosses with M3 × 6 screws. The slot leans back toward the top.</li><li>Set the reader's switches for SPI. Slide it down into the middle pair of grooves in the two posts, antenna side toward the card and header at the top. That holds it {n(c.READER_GAP)} mm behind the card, where it reads best; this reader misses cards held right against it.</li><li>Try a card. If reads are unreliable, move the reader to the front or rear grooves ({n(c.READER_GAP + min(c.READER_SLOTS))} or {n(c.READER_GAP + max(c.READER_SLOTS))} mm). The lid stops it lifting out, so no tie or glue is needed.</li></ol>")}
{step(7, "Wire it", "step-7-wiring", "The open case from the rear left, with the lid and rear panel off.", "Open case from behind with the ribbon folded from the front board down onto the DAC, and leads from the screen, reader, knob and power key to the board",
f"<ol><li>Run the ribbon straight back from the board and bend it down onto the pins on top of the DAC, red stripe on pin 1. It needs no twist and no fold. The DAC has no notch, so check first: pin 1 is the corner pin with a square pad on the Pi, at the right-hand end seen from the front of the case. With the Pi running it reads 3.3 V, and its neighbour across the header (pin 2) reads 5 V.</li><li>Plug the leads into the board's headers as <a href=\"{ELECTRONICS}#board-leads\">What plugs in where</a> in the electronics guide says: screen to LCD, reader to NFC, knob to ENC, power key to PWR.</li><li>Keep the ribbon and leads out from under the card tray, which comes down to 52 mm over the left two thirds of the case, and clear of the card slot. Leave enough slack that the front panel can come off with everything attached.</li><li>Before closing up, run the checks in the <a href=\"{ELECTRONICS}#wiring\">electronics guide</a>: every key, the knob, the power key and its light, the screen and a card.</li></ol>")}
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

</main>"""
    return wrap("NFC Player Case Assembly", body)


ELECTRONICS_FILE = HERE.parent / "docs" / "index.html"
BOARD_MARKS = ("<!-- front-board: written by NFC-Player-Case/guide.py from board.py and case.py -->", "<!-- /front-board -->")


def board_section():
    """The front board's section of the electronics guide, which is hand-written apart from this."""
    case = "../NFC-Player-Case/"
    fab = case + "front-board/fab/"

    def pic(file, caption, alt):
        return f'<figure><img src="{fab}{file}" alt="{html.escape(alt)}" style="display:block;width:100%;height:auto"><figcaption>{caption}</figcaption></figure>'

    return f"""
<h2 id="board">Front board for the case</h2>
<p>On the bench, the parts are wired straight to the DAC's pins as in step 5. In the case, a small printed circuit board, {n(c.BOARD_X[1] - c.BOARD_X[0])} × {n(c.BOARD_Z[1] - c.BOARD_Z[0])} mm, takes the place of those jumper wires. It lies flat behind the front panel, behind the four keys, on a {n(c.SPACER_T)} mm printed spacer (see <a href="{case}{ASSEMBLY}#held">how the keys are held</a>). The keys' tactile switches are soldered to its front. A 40-way ribbon joins its box header to the pins on top of the DAC, so it reaches every pin of the Pi. The screen, NFC reader, knob and power key each plug into a labelled pin header on it. It also carries the two diodes the power key needs, a transistor that lights the power key from 5 V, and two small LEDs that light while the board is getting each supply from the Pi: orange for 3V3 and red for 5V. The small parts are surface-mount and come fitted by the board maker; you solder only the headers and the key switches.</p>
{pic("nfc-front-board-back.png", "The back of the board, where every part but the key switches goes. Seen from behind, so the keys read back, next, play, previous from left to right. The small parts at the lower left come fitted.", "Back of the front board: a 40-pin box header along the top, labelled pin headers for LCD, NFC, PWR, OLED and ENC, and small surface-mount diodes, resistors, a transistor and two LEDs marked 3V3 and 5V")}
{pic("nfc-front-board-front.png", "The front of the board, which faces the panel. Only the four key switches go on this side.", "Front of the front board, marked This side towards the panel, with the four tactile switches")}

<h3>Order it</h3>
<p>The board is drawn in KiCad by <code>NFC-Player-Case/front-board/board.py</code> from the numbers in <code>case.py</code>, so it always matches the panel. Upload <a href="{fab}nfc-front-board-gerbers.zip">nfc-front-board-gerbers.zip</a> to any board maker (JLCPCB, PCBWay, Aisler and others). Choose 2 layers, 1.6 mm FR-4, any colour and any finish.</p>
<p>To have the small parts fitted, turn on the maker's assembly service and choose assembly on the <strong>bottom</strong> side: the board's back, where the parts go, is KiCad's bottom. For JLCPCB, upload <a href="{fab}nfc-front-board-jlc-bom.csv">nfc-front-board-jlc-bom.csv</a> as the BOM and <a href="{fab}nfc-front-board-jlc-cpl.csv">nfc-front-board-jlc-cpl.csv</a> as the placement (CPL) file. The BOM gives an LCSC part number for each part, all from JLCPCB's basic range when this was written except the orange LED, an extended part that adds a small one-off fee; if one is out of stock, pick another of the same value and package. In the placement preview, check each part sits on its pads and matches its outline on the board, above all the diodes, the LEDs and the transistor, which only work one way round. Boards drawn in KiCad often show a part turned 90° or 180° there, most often on the bottom side; turn any that are wrong in the preview before you order. Assembly is only worth it for at least two boards; with set-up and postage, expect a total of roughly £20–30. The <a href="{fab}nfc-front-board-schematic.pdf">schematic</a> is a PDF, and the KiCad project in <code>NFC-Player-Case/front-board/</code> opens in KiCad 10 if you want to change anything.</p>

<h3>Parts on the board</h3>
<div class="table-wrap">{board_parts_table()}</div>

<h3>Build it</h3>
<ol>
<li>The diodes, resistors, transistor and LEDs come fitted on the back. If the power key's LED has its own resistor (one rated 5 V or 6 V), R2 can stay, and the key lights a little dimmer; bridge R2's two pads with solder for full brightness.</li>
<li>The pin headers and the 40-pin box header go on the back too: the side with the part labels. The front is marked <em>This side towards the panel</em>. Fit the box header with its notch where the board shows it, and hold each header square while you solder its first pin.</li>
<li>On the front, trim every lead to 1.5 mm or less, so the joints fit in the openings in the spacer and the key carrier.</li>
<li>Last, the four key switches on the front, in the squares marked for them. Push each fully home so it sits flat and square; a tilted switch tilts its cap. Solder them from the back, and trim their legs too.</li>
<li>With a multimeter, check there is no short between 3.3 V, 5 V and ground: pins 1, 2 and 6 of the box header.</li>
<li>Plug the ribbon onto the DAC and power the Pi: both LEDs should light, orange for 3V3 and red for 5V. If one stays dark, unplug and look for a bad joint or a reversed ribbon before plugging anything else in.</li>
</ol>

<h3 id="board-leads">What plugs in where</h3>
<div class="table-wrap">{header_table()}</div>
<p>The keys need no leads: their switches are on the board. The keys and the knob only pull a pin to ground, and the Pi's own pull-ups hold them high. The power key reaches GPIO 24 and GPIO 3 through D1 and D2, exactly as in <a href="#w-buttons">step 5</a>. GPIO 22 still switches the light, through Q1, so nothing changes in the software or in <code>config.txt</code>.</p>
<div class="note"><p>The box header sits straight in front of the Pi's header, the same way round: pin 1 on the right seen from the front, on the lower row. So the ribbon leaves the board, bends once and comes down onto the DAC's pins, with no twist or fold. The ribbon's red stripe marks pin 1 at both ends. On the board, pin 1 is at the triangle beside the box header, and its notch only lets the plug in one way. On the DAC there is no notch, so check before you push it on: pin 1 is the corner pin with a square pad on the Pi, at the right-hand end seen from the front of the case, and with the Pi running it reads 3.3 V, while its neighbour across the header (pin 2) reads 5 V.</p></div>
<p>Fitting the board in the case, and running the ribbon and leads, is in the <a href="{case}{ASSEMBLY}#assembly">assembly guide</a>.</p>
"""


def write_board_section():
    page = ELECTRONICS_FILE.read_text()
    a, b = BOARD_MARKS
    head, rest = page.split(a)
    _, tail = rest.split(b)
    ELECTRONICS_FILE.write_text(head + a + board_section() + b + tail)
    print("wrote the front board section of", ELECTRONICS_FILE.relative_to(HERE.parent))


WOOD_DEPTH = float(re.search(r"^GRAIN_DEPTH = ([\d.]+)", (HERE / "wood.py").read_text(), re.M).group(1))  # wood.py needs Blender to import
# The finishes the printed parts come in, and the swatch shown for each.
WOOD_PLA = ("Wood-fill PLA", "#7b4f32", "stained walnut")
PETG = ("PETG", "#2b2d2e", "charcoal")
PETG_ANY = ("PETG", "#b9bbb5", "any colour")


def swatch(finish):
    name, colour, shade = finish
    return f'<span class="sw" style="--c:{colour}"></span>{name}, {shade}'


def printing_page():
    jacks = c.DAC_JACKS
    wood, petg, any_ = swatch(WOOD_PLA), swatch(PETG), swatch(PETG_ANY)
    parts = [  # part, files, finish, where it shows
        ("Chassis", "<code>chassis.stl</code>, or <code>chassis-wood.stl</code> with carved grain", wood, "The two sides and the bottom edges."),
        ("Lid", "<code>lid.stl</code>", wood, "The whole top, with the card tray and the card slot."),
        ("Front panel", "<code>front.stl</code>, or <code>front-wood.stl</code> with carved grain", wood, f"The {n(c.RIM)} mm rim round the brass, and the panel's edges."),
        ("Rear panel", "<code>rear.stl</code>", petg, "The back, with the sockets."),
        ("Key carrier", "<code>key-carrier.stl</code>", petg, "The four key faces, flush in the brass. PETG because its bridges have to bend."),
        ("Card guide", "<code>card-guide.stl</code>", petg, "Inside, but you look down onto it through the card slot, so print it dark."),
        ("Board spacer", "<code>board-spacer.stl</code>", any_, "Hidden behind the front panel."),
        ("Screen bracket", "<code>display-cradle.stl</code>", any_, "Hidden behind the screen."),
        ("Fit gauge", "<code>fit-gauge.stl</code>", wood, "A test piece, not part of the case. Print it first, in the wood-fill you will use: nearly every hole it tests is in a wood-fill part."),
    ]
    part_rows = "".join(f"<tr><td><strong>{a}</strong></td><td>{b}</td><td>{f}</td><td>{d}</td></tr>" for a, b, f, d in parts)
    intro = (f"<p>Eight printed parts in two finishes: wood-fill PLA for the sides, front and lid, and charcoal PETG for the back, the keys and the card guide. "
             f"Which filament each part takes, how it lies on the bed, the settings, the wood grain and how to finish it.</p>"
             f"<p>The largest part, the chassis, is {n(c.W)} × {n(c.D)} mm and fits a 220 × 220 mm bed. Every file is in millimetres; print at 100%.</p>")
    body = f"""
<main>
{guides_nav(PRINTING)}
{hero_header("3D printing", "NFC Player<br>Case Printing", intro)}
<nav><a href="#parts">Parts and finishes</a><a href="#measure">Measure first</a><a href="#gauge">Fit gauge</a><a href="#settings">Settings</a><a href="#each">Each part</a><a href="#grain">Wood grain</a><a href="#finish">Finishing</a><a href="#rebuild">Rebuild</a></nav>
<aside><strong>Not printed yet.</strong> The case has been designed and checked in the model, but not yet printed. The settings below are starting points for a 0.4 mm nozzle, not tested values: print the fit gauge first and adjust from what it shows. Once the parts are printed and finished, the <a href="{ASSEMBLY}">assembly guide</a> puts them together.</aside>

<section id="parts"><h2>Parts and finishes</h2>
<p>Print one of each. The parts you see from outside are wood-fill: PLA filled with wood fibre, sanded and stained after printing. The parts that have to bend or take wear are PETG, which is tougher. The parts nobody sees can be any colour of PETG you have.</p>
<table><tr><th>Part</th><th>File in <code>STL/</code></th><th>Filament</th><th>Where it shows</th></tr>{part_rows}</table>
<p>The brass face is cut from sheet, not printed: see <a href="{ASSEMBLY}#brass">Brass face</a> in the assembly guide.</p>
</section>

<section id="measure"><h2>Measure first</h2>
<p>Published drawings did not settle these, so each is a named value at the top of <code>case.py</code> with a sensible default. Measure your parts, change the value and <a href="#rebuild">rebuild</a> <strong>before printing the front or rear panel or cutting brass</strong>.</p>
<table><tr><th>Value</th><th>Default</th><th>What to measure</th></tr>
<tr><td><code>LCD_OFF_X</code>, <code>LCD_OFF_Z</code></td><td>{n(c.LCD_OFF_X)}, {n(c.LCD_OFF_Z)}</td><td>Where the lit area's centre sits relative to the centre of the 58 × 35 mm screen board, seen from the front. Set from Waveshare's outline drawing of the 2inch LCD Module: the picture sits about 2 mm right of centre with the pin pads on the left. Fit the board that way round, or change the sign. The bracket's screw slots let the screen move 2 mm either way sideways; to move it further, or up or down, change these and reprint the bracket.</td></tr>
<tr><td><code>LCD_HOLES</code>, <code>LCD_STANDOFF</code></td><td>{n(c.LCD_HOLES[0])} × {n(c.LCD_HOLES[1])} mm, {n(c.LCD_STANDOFF)} mm</td><td>The centres of the screen board's four corner holes, and how far its brass standoffs stand out behind the board. They set where the bracket's holes and upright are.</td></tr>
<tr><td><code>LCD_GLASS</code></td><td>{n(c.LCD_GLASS)} mm</td><td>How far the glass stands in front of the board. With the standoffs, it sets how far back the bracket's upright stands; the base slides {n(c.CRADLE_TRAVEL[1])} mm back and {n(c.CRADLE_TRAVEL[0])} mm forward from there.</td></tr>
<tr><td><code>DAC_JACKS</code></td><td>{"; ".join(f"{name} x {n(x)}, z {n(z)}, Ø{n(d)}" for name, x, z, d in jacks)}</td><td>Assemble the Pi and DAC on 5 mm standoffs and measure the centre of each socket: across from the case's left side and up from its underside. Check the holes pass your plugs' metal shells, not just the sockets' barrels. See the <a href="{ASSEMBLY}#drawings">board stack drawing</a> for the heights assumed.</td></tr>
<tr><td><code>POWER_HOLE</code>, <code>POWER_BODY</code></td><td>{n(c.POWER_HOLE)} mm; {n(c.POWER_BODY[0])} × {n(c.POWER_BODY[1])} mm</td><td>Your power key's thread, the size across its nut, and how far it reaches into the case including its solder tags.</td></tr>
<tr><td><code>USB_SLOT</code>, <code>USB_SCREW_PITCH</code></td><td>{n(c.USB_SLOT[0])} × {n(c.USB_SLOT[1])} mm, {n(c.USB_SCREW_PITCH)} mm</td><td>The body opening and screw spacing of your panel-mount USB-C socket.</td></tr>
<tr><td><code>TACT_H</code></td><td>{n(c.TACT_H)} mm</td><td>Your key switches, from the base of the body to the top of the button. It sets the board spacer's thickness, so the keys neither rattle nor sit pressed in.</td></tr>
</table>
</section>

<section id="gauge"><h2>Fit gauge</h2>
<p>A small plate, 90 × 36 × {n(c.FRONT_T)} mm, with one of every fit that matters. Print it flat, brass pocket up, in wood-fill PLA on exactly the settings you will use for the case, and try your parts in it before printing anything large. If you print the card guide in PETG, a second gauge in PETG checks its card slot too; it is a small print.</p>
<table><tr><th>Feature</th><th>Size</th><th>Try in it</th><th>It should</th></tr>
<tr><td>Square hole</td><td>{n(c.KEY_HOLE)} mm</td><td>A key cap: print the key carrier early, or check with calipers that its caps are {n(c.KEY_CAP)} mm</td><td>Slide freely without rattling.</td></tr>
<tr><td>Blind round hole</td><td>{n(c.PEG_HOLE)} mm</td><td>A peg of the key carrier</td><td>Go in with a light push.</td></tr>
<tr><td>Encoder hole and pocket</td><td>{n(c.ENCODER_HOLE)} mm; {n(c.ENCODER_BODY[0])} × {n(c.ENCODER_BODY[1])} mm</td><td>The encoder, from the pocket side</td><td>Sit flat in the pocket without turning, with enough thread through {n(c.PANEL_AT_NUT + c.BRASS_T)} mm of panel and brass for the washer and nut.</td></tr>
<tr><td>Three round holes</td><td>{n(c.CLEAR_M3)}, {n(c.PILOT_M3)}, {n(c.CLEAR_M25)} mm</td><td>An M3 screw in the first two, an M2.5 screw in the third</td><td>{n(c.CLEAR_M3)}: the M3 passes freely, as through the panels and the lid. {n(c.PILOT_M3)}: it cuts its own thread, firmly, driven by hand, as into the chassis. {n(c.CLEAR_M25)}: the M2.5 passes, as through the floor slots under the Pi.</td></tr>
<tr><td>Card slot</td><td>{n(c.CHANNEL_W)} × {n(c.CHANNEL_T)} mm</td><td>A card</td><td>Slide through freely, without catching.</td></tr>
<tr><td>Corner of the brass pocket</td><td>{n(c.BRASS_T)} mm deep, {n(c.RIM)} mm rim</td><td>A corner of your brass sheet</td><td>Drop in flush with the rim.</td></tr>
</table>
<p>If a hole is too tight, first try your slicer's hole or XY compensation, which changes nothing else. If that is not enough, change the matching value in <code>case.py</code> (for example <code>KEY_HOLE</code>, <code>PILOT_M3</code> or <code>CHANNEL_T</code>) and <a href="#rebuild">rebuild</a>. Try your stain and finish on the gauge too, before the case: see <a href="#finish">Finishing</a>.</p>
</section>

<section id="settings"><h2>Settings</h2>
<p>For a 0.4 mm nozzle. Check the temperatures against your spool's label: wood-fill in particular varies from brand to brand.</p>
<table><tr><th>Setting</th><th>{wood}</th><th>{petg}</th></tr>
<tr><td>Nozzle</td><td>0.4 mm. Wood fibre is mildly abrasive, so a hardened or plated nozzle lasts longer. A larger nozzle clogs less but cannot draw the carved grain.</td><td>0.4 mm</td></tr>
<tr><td>Layer height</td><td>0.20 mm</td><td>0.20 mm. The key carrier must be 0.20 mm: each bridge is exactly two layers.</td></tr>
<tr><td>Walls</td><td>4</td><td>4</td></tr>
<tr><td>Top and bottom layers</td><td>5 and 4</td><td>5 and 4</td></tr>
<tr><td>Infill</td><td>20%, gyroid or grid</td><td>20%, gyroid or grid</td></tr>
<tr><td>Nozzle temperature</td><td>Usually 190–220 °C. Hotter prints come out darker, so keep it the same for all three wood parts.</td><td>Usually 230–250 °C</td></tr>
<tr><td>Bed</td><td>55–60 °C</td><td>70–80 °C. On smooth PEI, use glue stick as a release, or PETG can pull flakes out of the sheet.</td></tr>
<tr><td>Part cooling</td><td>Full, after the first layers</td><td>30–50%</td></tr>
<tr><td>Retraction</td><td>Short and not too fast. Wood-fill clogs when it is pulled back hot too far.</td><td>As usual for your printer</td></tr>
<tr><td>Outer wall speed</td><td>Slow, about 40 mm/s, for clean sides and grain</td><td>As usual</td></tr>
<tr><td>Seam</td><td>Aligned, on an edge that does not show; see each part below</td><td>Aligned or rear</td></tr>
</table>
<aside>Wood-fill can clog if it sits hot in the nozzle without moving. Don't leave the printer paused or idling hot with it loaded, and when you change to PETG, purge it with a little plain PLA first.</aside>
</section>

<section id="each"><h2>Each part</h2>
<p>Every STL is already the way up it prints. No part needs support except the lid.</p>
<table><tr><th>File</th><th>Filament</th><th>On the bed</th><th>Notes</th></tr>
<tr><td>fit-gauge.stl</td><td>{wood}</td><td>Flat, pocket up</td><td>Print it first. See <a href="#gauge">Fit gauge</a>.</td></tr>
<tr><td>chassis.stl or chassis-wood.stl</td><td>{wood}</td><td>Floor down. No support</td><td>The bottom edges are 45° chamfers so they print clean. Put the seam at a rear corner, where the rear panel's edge hides it. The horizontal screw pilots in the corner towers can sag a little at the top: clear them by running an M3 screw into each by hand.</td></tr>
<tr><td>lid.stl</td><td>{wood}</td><td>Top surface down</td><td>Support from the bed under the two curved edges only. The top of the case is the face on the bed, so it takes the finish of your bed sheet: a smooth sheet for a smooth top. The lid has no carved grain; the stain gives it its colour.</td></tr>
<tr><td>front.stl or front-wood.stl</td><td>{wood}</td><td>Inside face down, brass pocket up. No support</td><td>The rim round the brass is only {n(c.RIM)} mm wide, so keep the outer walls slow. Put the seam on the bottom edge. Check the two blind peg holes and the {n(c.PILOT_M2)} mm board screw pilots are open.</td></tr>
<tr><td>rear.stl</td><td>{petg}</td><td>Flat, either face down</td><td>The face on the bed takes the bed sheet's finish, so put the outside down if you want it to match the top.</td></tr>
<tr><td>key-carrier.stl</td><td>{petg}</td><td>Back down, key faces up. No support</td><td>PETG, not PLA: PLA is stiffer and more brittle, so its bridges are more likely to crack. Use 0.20 mm layers, so each bridge is exactly two layers ({n(c.BRIDGE_T)} mm). Ironing the top layer gives smoother key faces. The slots beside the bridges are only {n(c.BRIDGE_GAP)} mm wide, so check that the first layer has not closed them, and clear any that have with a sharp knife.</td></tr>
<tr><td>card-guide.stl</td><td>{petg}</td><td>Foot down</td><td>Brim if it lifts. Keep any support out of the card channel.</td></tr>
<tr><td>board-spacer.stl</td><td>{any_}</td><td>Flat, either face down</td><td>Only {n(c.SPACER_T)} mm thick. Check its openings round the keys are clean.</td></tr>
<tr><td>display-cradle.stl</td><td>{any_}</td><td>Base down, as it stands in the case. No support</td><td>Check the slots in its base are open, so it can slide.</td></tr>
</table>
</section>

<section id="grain"><h2>Wood grain (optional)</h2>
<p>The plain <code>chassis.stl</code> and <code>front.stl</code> already look like wood once they are printed in wood-fill and stained. For a grain you can see and feel, <code>wood.py</code> carves one into them from a picture of wood you choose:</p>
<ol>
<li>Save a picture of wood grain as <code>wood-grain.png</code> in this folder, with the grain running across it from side to side. Dark parts are cut deepest. Neither the picture nor the grained STLs are in the repository: they are large, and they come from your own picture.</li>
<li>Run <code>blender -b -P build.py</code>, then <code>blender -b -P wood.py</code>, from this folder (see <a href="#rebuild">Rebuilding</a> for what you need). It writes <code>STL/chassis-wood.stl</code> and <code>STL/front-wood.stl</code>.</li>
<li>Print those instead of the plain ones, the same way up and on the same settings.</li>
</ol>
<p>The grain is cut at most {n(WOOD_DEPTH)} mm deep, and only inwards, so every face where parts meet keeps its size. It goes into the chassis's two sides and bottom chamfers and the front panel's edges, and fades out near the floor and the top, so the first layer stays clean and the lid sits flush. Nothing is cut into a face that prints on the bed or over support. By default the grain runs across the top and down the sides, like a waterfall edge; set <code>WOOD_GRAIN=front-to-back</code> to run it along the sides instead, or <code>WOOD_IMAGE</code> to try another picture without replacing yours.</p>
<aside>The grain is drawn by the outer wall. Turn off fuzzy skin, and any slicer setting that drops detail smaller than the nozzle. Slow outer walls help most.</aside>
</section>

<section id="finish"><h2>Finishing</h2>
<h3>Every part</h3>
<ul>
<li>Pick off any strings, and check every hole and slot against what the <a href="#gauge">fit gauge</a> showed.</li>
<li>Don't drill the screw pilots out: the M3 and M2 screws cut their own thread in them. Drive each screw in once by hand before assembly, so it goes in easily later.</li>
</ul>
<h3>Wood-fill parts: chassis, lid and front</h3>
<ol>
<li>Sand lightly by hand, along the grain, with 240 then 400 grit, just enough to take the fuzz off the layer lines. Go gently on the grained parts: the grain is only {n(WOOD_DEPTH)} mm deep.</li>
<li>Wipe on a wood stain (the render shows walnut) and wipe it off again after a minute or so. It soaks into the fibre and gathers in the carved grain and the layer lines, darkening them, which is what brings the grain out. A second coat makes it darker.</li>
<li>Let it dry fully, then seal with wax, hard wax oil or a matt clear coat.</li>
<li>Keep stain and finish out of the key holes, the encoder hole and the screw pilots. There is only {n((c.KEY_HOLE - c.KEY_CAP) / 2)} mm round each key cap, and a thick coat inside a key hole makes the key stick. Keep it thin in the brass pocket too, so the brass still sits flush.</li>
</ol>
<p>Try the stain on the fit gauge first: wood-fill takes stain differently from brand to brand.</p>
<h3>Key carrier</h3>
<p>The symbols are cut 0.6 mm into the key faces. Fill them with paint if you like, a light colour on the charcoal, and wipe the faces clean before it dries. Keep paint out of the slots beside the bridges, or they will stick.</p>
<h3>Other PETG parts</h3>
<p>Nothing more to do once they are cleaned up.</p>
</section>

<section id="rebuild"><h2>Rebuilding after a change</h2>
<p>You need three free programs, on Windows, macOS or Linux: <a href="https://www.blender.org/download/">Blender</a> (the scripts were made with Blender 5.2), <a href="https://www.kicad.org/download/">KiCad</a> 10 or later, and Python 3 with Pillow (<code>pip install pillow</code>). The commands below call Blender <code>blender</code>: put it on your PATH, or type the full path to the program instead. <code>python</code> is your own Python 3 (it may be <code>python3</code> or <code>py</code> on your system), except for <code>board.py</code>, which needs the Python that comes with KiCad: on Windows, run it from the KiCad Command Prompt; on Linux, use the system <code>python3</code> that KiCad installs into; on macOS, the <code>python3</code> inside KiCad.app.</p>
<p>Edit the values at the top of <code>case.py</code>, then run these from the <code>NFC-Player-Case</code> folder in order. The first rewrites the STLs, the key carrier from <code>keycaps.py</code> among them, the OpenSCAD copy and the brass outline, and reports any part that collides with another. The OpenSCAD file is a generated copy and has not been run through OpenSCAD.</p>
<ol>
<li><code>blender -b -P build.py</code></li>
<li>In the <code>front-board</code> folder, with KiCad's Python: <code>python board.py</code></li>
<li><code>blender -b -P wood.py</code> (only for the wood-grain version)</li>
<li><code>python drawings.py</code></li>
<li><code>blender -b -P pictures.py</code></li>
<li><code>blender -b NFC-Player-Render.blend -P render.py</code></li>
<li><code>python guide.py</code></li>
</ol>
<p>The second step redraws and reroutes the front board, runs KiCad's electrical and design rules checks, and rewrites its Gerber files. Run it whenever you move the keys, the screws or the board's outline. The last step writes this guide, the assembly guide and the front board's section of the electronics guide. The model checks that parts fit each other and the stand-ins. It cannot check print tolerances, your exact boards, heat, or how well the NFC reader works next to brass and stored cards: those need a bench test.</p>
</section>
</main>"""
    return wrap("NFC Player Case Printing", body)


if __name__ == "__main__":
    for name, make in ((ASSEMBLY, assembly_page), (PRINTING, printing_page)):
        out = HERE / name
        out.write_text(make())
        print("wrote", out.name, f"{out.stat().st_size / 1e6:.1f} MB")
    write_board_section()
