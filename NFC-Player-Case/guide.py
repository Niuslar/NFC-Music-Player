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

PICS = HERE / "pictures"
REVISION = "3.3"


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
    x0, x1, z0, z1 = c.RCA_WINDOW
    key = '<div class="key"><span style="--c:#61a0db">Printed part fitted in this step</span><span style="--c:#cdcfca">Printed parts already in place</span><span style="--c:#d4a85c">Brass</span><span style="--c:#d2452d">Arrow: direction of fitting</span></div>'
    hero = HERE / "NFC-Player-Render.png"
    body = f"""
<main>
<header><div><div class="kicker">Mechanical assembly · Revision {REVISION}</div><h1>NFC Player<br>Case</h1>
<p>Charcoal printed case with a brass face set inside a thin printed rim, a card that leans back in a slot, and a tray in the lid for five spare cards.</p>
<p><strong>{n(c.W)} × {n(c.D)} × {n(c.H)} mm</strong> printed shell. Knob, keycaps, screw heads, feet and cards stand proud of it.</p></div>
<img src="{jpeg(hero, 1400, 86)}" alt="Rendered case: brass front inside a thin dark rim with a screen, four keys and a large knob; cards in a tray on the lid and one card standing in a slot"></header>
<nav><a href="#inside">What goes where</a><a href="#changes">Changes</a><a href="#measure">Measure first</a><a href="#print">Print</a><a href="#hardware">Hardware</a><a href="#controls">Keys and knob</a><a href="#assembly">Assembly</a><a href="#drawings">Drawings</a><a href="#brass">Brass</a><a href="#rebuild">Rebuild</a></nav>

<section id="inside"><h2>What goes where</h2>
<p>The numbers on each picture are explained in the list under it. Hover a number or a line to pick out the other. The bought parts are simple blocks at their nominal size and position: they show where things go and which way round, not exactly what they look like.</p>
{figure("exploded", "Exploded view from the front left. Lid lifted, front and rear panels pulled out.", "Exploded case: lid above, front panel and brass pulled forward, rear panel pulled back, electronics inside the chassis")}
{figure("layout-top", "From above with the lid off. Front at the bottom. Wire colours: yellow screen, pink NFC reader, blue knob and switches, black USB.", "Top view of the open case showing the screen, keys, knob, card guide with reader, the board stack and the wire routes")}
{figure("layout-inside", "From the rear right with the lid and rear panel off.", "Open case from behind, showing the board stack, its sockets, the card guide and reader, and the screen cradle")}
</section>

<section id="changes"><h2>Changes in revision {REVISION}</h2><table><tr><th>Area</th><th>Change</th><th>Why</th></tr>
<tr><td>Headphones</td><td>The separate {n(c.PHONES_HOLE)} mm rear jack hole and its extension lead are gone. The DAC's own 3.5 mm socket comes out through the rear window, next to its RCA sockets.</td><td>On the DAC Pro the headphone socket is on the same edge as the RCA sockets, so it already faces the window. The extra socket only added a lead from one side of the rear panel to the other. Set <code>REAR_JACK = True</code> in <code>case.py</code> to bring it back.</td></tr>
<tr><td>Screw towers</td><td>{n(c.TOWER_X)} mm wide instead of 12.</td><td>With the lid screws moved to {n(c.LID_SCREW_X[0])} mm from the sides, their pilot holes left only 0.7 mm of wall. Now there is 2.7 mm.</td></tr>
<tr><td>Keys and knob</td><td>A new section explains what to buy for them, how they are held, and how they feel, with a section drawing through a key and the encoder.</td><td>It was not clear what was printed and what was bought, or how the encoder stays put.</td></tr>
<tr><td>Pictures and drawings</td><td>New assembly pictures and dimensioned drawings, all generated from the same model as the STLs.</td><td>The previous diagrams were not to scale and their labels overlapped.</td></tr>
</table></section>

<section id="measure"><h2>Measure first</h2>
<p>Published drawings did not settle these, so each is a named value at the top of <code>case.py</code> with a sensible default. Measure your parts, change the value and <a href="#rebuild">rebuild</a> <strong>before printing the front or rear panel or cutting brass</strong>.</p>
<table><tr><th>Value</th><th>Default</th><th>What to measure</th></tr>
<tr><td><code>LCD_OFF_X</code>, <code>LCD_OFF_Z</code></td><td>{n(c.LCD_OFF_X)}, {n(c.LCD_OFF_Z)}</td><td>Where the lit area's centre sits relative to the centre of the 58 × 35 mm screen board, seen from the front. Set from Waveshare's outline drawing of the 2inch LCD Module: the picture sits about 2 mm right of centre with the pin pads on the left. Fit the board that way round, or change the sign. The cradle can be offset ±4 mm sideways and ±2 mm vertically.</td></tr>
<tr><td><code>LCD_GLASS</code></td><td>{n(c.LCD_GLASS)} mm</td><td>How far the glass stands in front of the board. It sets where the cradle's grooves are.</td></tr>
<tr><td><code>RCA_WINDOW</code></td><td>x {n(x0)}–{n(x1)}, z {n(z0)}–{n(z1)}</td><td>Assemble the Pi, splitter and DAC on 5 mm standoffs and measure where the DAC's RCA and headphone sockets come out. See the <a href="#drawings">board stack drawing</a> for the heights assumed.</td></tr>
<tr><td><code>USB_SLOT</code>, <code>USB_SCREW_PITCH</code></td><td>{n(c.USB_SLOT[0])} × {n(c.USB_SLOT[1])} mm, {n(c.USB_SCREW_PITCH)} mm</td><td>The body opening and screw spacing of your panel-mount USB-C socket.</td></tr>
</table>
<aside>Print the fit gauge first and try your encoder in it: its thread must pass {n(c.PANEL_AT_NUT + c.BRASS_T)} mm of panel and brass and still take the washer and nut.</aside>
</section>

<section id="print"><h2>Print</h2>
<p>Millimetres, 100% scale. Start with a 0.4 mm nozzle, 0.20 mm layers, four walls and 20% infill in PETG. The largest part is {n(c.W)} mm long and fits a 220 × 220 mm bed.</p>
<table><tr><th>File</th><th>Orientation and notes</th></tr>
<tr><td>fit-gauge.stl</td><td>Flat, pocket up. Print it first. It has a switch opening, the encoder hole and its pocket, 3.3, 2.55 and 2.9 mm holes, the 55.4 × 1.65 mm card slot and a corner of the brass pocket.</td></tr>
<tr><td>chassis.stl</td><td>Floor down, no support. Clear the horizontal screw pilots in the towers by hand.</td></tr>
<tr><td>lid.stl</td><td>Top surface down, with support under the two curved edges.</td></tr>
<tr><td>front.stl</td><td>Inside face down, brass pocket up, no support.</td></tr>
<tr><td>rear.stl</td><td>Flat, either face down.</td></tr>
<tr><td>card-guide.stl</td><td>Foot down, brim if needed. Keep support out of the card channel.</td></tr>
<tr><td>display-cradle.stl</td><td>Base down, as it stands in the case. No support.</td></tr></table>
</section>

<section id="hardware"><h2>Hardware</h2><ul>
<li>M3 screws that thread straight into the print (try one in the gauge first, and drive by hand): four M3 × 10 for the front (they pass the brass and panel), four M3 × 8 for the rear, four low-profile M3 × 6 for the lid (head at most 6 mm across and 1.5 mm tall), two M3 × 6 for the card guide and two for the screen cradle.</li>
<li>Four M2.5 standoffs 5 mm tall, four M2.5 × 6 screws from below, and four more on top for the Pi.</li>
<li>Keys and knob: four switches, four keycaps, an encoder and a knob, all bought. See <a href="#controls">Keys and knob</a> for exactly what to get.</li>
<li>A panel-mount USB-C socket on a short lead ending in micro-USB.</li>
<li>{n(c.BRASS_T)} mm brass sheet and thin double-sided tape. Four feet at least 5 mm tall. Foam pads, one small cable tie, and female jumper leads for the wiring.</li>
</ul></section>

<section id="controls"><h2>Keys and knob</h2>
<p>Nothing you press or turn is printed. The keys are four ordinary keyboard switches with keycaps, and the knob sits on a rotary encoder. All of them are bought parts. The printed front panel is only what they clip or bolt into, and the brass covers its face.</p>

<h3>What to buy</h3>
<table><tr><th>Part</th><th>Get</th><th>Make sure</th></tr>
<tr><td>Switches ×4</td><td>Kailh Choc <strong>V1</strong> low-profile switches</td><td>Choc V1, not Choc V2 or full-size MX: the panel's {n(c.KEY_HOLE)} mm square holes and {n(c.KEY_PLATE)} mm plate are cut for V1. Buy a spare or two.</td></tr>
<tr><td>Keycaps ×4</td><td>Choc V1 keycaps, 1u</td><td>Made for Choc V1 stems (MX keycaps will not fit), and no bigger than 17.5 × 16.5 mm. The keys sit 18 mm apart, so standard Choc-spaced caps leave a 0.5 mm gap.</td></tr>
<tr><td>Encoder</td><td>EC11-style rotary encoder with push switch: the Pi Hut one from the build guide, a Bourns PEC11R or an Alps EC11</td><td>An M7 threaded bushing at least 5 mm long, a 6 mm shaft that reaches at least 12 mm past the bushing, and a nut and washer (usually included). Try it in the fit gauge first.</td></tr>
<tr><td>Knob</td><td>Solid metal knob, up to {n(c.KNOB_D)} mm across, for a 6 mm shaft</td><td>Fixed with a set screw, and its bore matches your shaft's shape (D-flat or knurled).</td></tr>
<tr><td>Wire</td><td>Thin hook-up wire and female jumper leads</td><td>Neither part has a connector: you solder a wire to each pin.</td></tr></table>

<h3>How the keys feel</h3>
<p>The feel comes entirely from the switch you choose. All Choc V1 switches fit the same holes, so pick by feel:</p>
<table><tr><th>Type</th><th>Feel</th><th>Typical Kailh name</th></tr>
<tr><td>Linear</td><td>Smooth all the way down, no bump and no sound beyond the keycap landing.</td><td>Red</td></tr>
<tr><td>Tactile</td><td>A soft bump you can feel as it actuates, quiet.</td><td>Brown</td></tr>
<tr><td>Clicky</td><td>A bump with a crisp, audible click. Closest to a hi-fi push button.</td><td>White (light), Jade or Navy (heavier)</td></tr></table>
<p>Each has about {n(3.0)} mm of travel and a spring that pushes the key back up. Any of them works with the player, which only sees the contact close.</p>

<h3>How they are held</h3>
<ul>
<li><strong>Switches:</strong> push in from the front. Two spring clips on each switch snap behind the {n(c.KEY_PLATE)} mm plate, and the pocket behind it leaves them room. No glue or screws. To remove one, squeeze its clips from behind, or use a switch puller from the front.</li>
<li><strong>Encoder:</strong> held by its own nut. It goes in from behind with the threaded bushing through the {n(c.ENCODER_HOLE)} mm hole. On the front, a washer and then the nut clamp the brass and the {n(c.PANEL_AT_NUT)} mm of plastic between the nut and the encoder body. The body also sits in a rectangular pocket, so it cannot turn when you twist the knob.</li>
<li><strong>Locating lug:</strong> many encoders have a small lug beside the bushing, meant for a hole in a metal panel. The pocket already stops the encoder turning, so nip the lug off flush with side cutters, or the body will not sit flat.</li>
<li><strong>Knob:</strong> slides onto the shaft and is held by its set screw on the shaft's flat. Leave about 1 mm between the knob and the nut so it never rubs.</li>
</ul>
{drawing("Controls-Section.svg", "Sections through a key and through the encoder, three times full size.")}

<h3>Wiring</h3>
<p>Every key and the encoder only connect a pin to ground, so they need no resistors or power. Pin numbers are the Pi's physical pins, reached through the splitter's spare header (the same as the build guide's step 5).</p>
<table><tr><th>Part</th><th>Pin on the part</th><th>Pi pin</th></tr>
<tr><td>Previous</td><td>Either pin; the other to ground</td><td>7 (GPIO 4)</td></tr>
<tr><td>Play / pause</td><td>Either pin; the other to ground</td><td>11 (GPIO 17)</td></tr>
<tr><td>Next</td><td>Either pin; the other to ground</td><td>36 (GPIO 16)</td></tr>
<tr><td>Back</td><td>Either pin; the other to ground</td><td>32 (GPIO 12)</td></tr>
<tr><td>Keys, shared ground</td><td>One pin of every key, chained together</td><td>14 (ground)</td></tr>
<tr><td>Encoder</td><td>A, the outer pin on the three-pin side</td><td>29 (GPIO 5)</td></tr>
<tr><td>Encoder</td><td>C, the middle pin</td><td>6 (ground)</td></tr>
<tr><td>Encoder</td><td>B, the other outer pin</td><td>31 (GPIO 6)</td></tr>
<tr><td>Encoder push switch</td><td>One of the two pins on the other side</td><td>37 (GPIO 26)</td></tr>
<tr><td>Encoder push switch</td><td>The other</td><td>34 (ground)</td></tr></table>
<aside>The smooth Bourns EM14 encoder mentioned in the build guide as a later upgrade has a different bushing and body. Check its drawing against the encoder hole and pocket, and change <code>ENCODER_HOLE</code> and <code>ENCODER_BODY</code> in <code>case.py</code> before printing.</aside>
</section>

<section id="assembly"><h2>Assembly</h2>
{key}
{step(1, "Fit the brass", "step-1-brass", "Front panel with the brass about to go in. Seen from the front left.", "Front panel with the brass face held in front of its pocket",
f"<ol><li>Deburr the brass and try it in the pocket. It should drop in with a hair of clearance and sit flush with the rim.</li><li>Stick it down with thin double-sided tape, lining the screw holes up with the panel's.</li></ol>")}
{step(2, "Fit the switches and the encoder", "step-2-front", "Keys and knob from the front left. One switch, two keycaps, the washer, nut and knob are pulled forward; the encoder is pulled back.", "Front of the panel with a switch, keycaps, washer, nut and knob pulled out in the order they go on",
"<p>Solder the wires to the switches and the encoder first (see <a href=\"#controls\">Wiring</a>): it is easier before they are in the panel. Then:</p><ol><li>Push each switch in from the front until both clips snap behind the plate. From the front, left to right: previous, play/pause, next, back.</li><li>Press a keycap onto each switch's stem.</li><li>Nip off the encoder's locating lug if it has one. From behind, put the bushing through its hole so the body drops into the rectangular pocket.</li><li>On the front: washer, then nut. Tighten the nut firmly with a spanner, holding the body square in its pocket.</li><li>Slide the knob on, leaving about 1 mm clear of the nut, and tighten its set screw onto the flat of the shaft.</li></ol>",
more=[("step-2-controls", "The same panel from behind (the inside), so the knob end is on the left. One switch is out of its hole and the encoder is pulled back from its pocket.", "Inside of the front panel with switches clipped in and the encoder about to go into its pocket")])}
{step(3, "Fit the front panel and the screen", "step-3-screen", "Front left corner of the chassis from behind, with the front panel fitted and the screen lifted above its cradle.", "Screen cradle on the chassis floor behind the window, with the screen board above it ready to slide down",
"<ol><li>Screw the front panel to the chassis with four M3 × 10 screws.</li><li>Screw the cradle loosely to its two floor bosses with M3 × 6 screws.</li><li>Slide the screen board down into the grooves of both uprights, glass towards the window and connector towards you.</li><li>Look through the window and slide the cradle sideways until the lit area is centred, then tighten its screws. A foam pad between the board and the lid stops it lifting.</li></ol>")}
{step(4, "Mount the Pi, splitter and DAC", "step-4-stack", "Chassis from the front left with the front panel off for clarity, and the three boards lifted apart.", "Chassis floor with four standoffs in two slots, and the Pi, splitter and DAC stacked above them",
"<ol><li>Screw four standoffs up through the two floor slots and leave them loose.</li><li>Screw the Pi onto them, header at the front. Plug the splitter onto the Pi and the DAC onto the splitter's rear header, checking pin 1 each time.</li><li>Slide the whole stack back until the DAC's sockets sit just inside the rear window, then tighten the standoffs from below.</li></ol>")}
{step(5, "Fit the card guide and the NFC reader", "step-5-reader", "Card guide from the rear right, with the reader and cable tie pulled back.", "Card guide with its shelf, the NFC reader behind it and a cable tie",
f"<ol><li>Screw the guide to the two floor bosses with M3 × 6 screws. The slot leans back toward the top.</li><li>Set the reader's switches for SPI, then stand it on the shelf with its antenna side against the guide and its header at the top.</li><li>Hold it with one cable tie round guide and reader. The tie passes outside the card slot.</li></ol>")}
{step(6, "Wire it", "", "", "",
"<p>Every wire runs to the splitter's spare header. Follow the pin tables in the build guide (<code>docs/index.html</code>, step 5); the top view under <a href=\"#inside\">What goes where</a> shows the routes.</p><ul><li>Keep wires out from under the card tray, which comes down to 52 mm over the left two thirds of the case, and clear of the card slot.</li><li>Leave enough slack that the front panel can come off with the wires attached.</li></ul>")}
{step(7, "Fit the rear panel", "step-6-rear", "Rear of the case seen from the right, with the lid off.", "Rear panel with the window showing the DAC's RCA and headphone sockets, and the USB-C socket",
"<ol><li>Mount the USB-C socket in the rear panel and plug its lead into the Pi port marked USB (not PWR IN).</li><li>Screw the rear panel on with four M3 × 8 screws.</li><li>Check that an RCA plug and a headphone plug both seat fully through the window.</li></ol>")}
{step(8, "Close up", "step-7-close", "Finished case from the front right, with the lid lifted.", "Lid being lowered onto the case between the front and rear panels",
"<ol><li>Before closing for good, test card reading with the brass fitted and five cards in the tray.</li><li>Lower the lid between the panels and fit its four low-profile screws, by hand.</li><li>Stick the feet on, clear of the floor slots and the vents.</li></ol>")}
</section>

<section id="drawings"><h2>Drawings</h2>
<p>Generated from <code>case.py</code>, so they match the STLs. Millimetres, measured from the bottom left of each view.</p>
{drawing("Front-Panel.svg", "Front panel as built, seen from the front.")}
{drawing("Rear-Panel.svg", "Rear panel seen from behind, so the window for the DAC is on the right.")}
{drawing("Board-Stack.svg", "Side section through the board stack, seen from the left.")}
</section>

<section id="brass"><h2>Brass face</h2>
<p>Cut it from {n(c.BRASS_T)} mm brass using <a href="Brass-Front-Template.svg">Brass-Front-Template.svg</a>. It is drawn at actual size, seen from the front: print it at 100% and check the scale bar measures exactly 100 mm before using it as a pattern. It has a screen window, one slot for all four switches (the keycaps cover it), the encoder hole and four screw holes, with centre marks for a punch.</p>
{drawing("Brass-Front-Template.svg", "Brass template at actual size.")}
<p>The rectangular openings have square corners, which suits laser or waterjet cutting, or a fretsaw and file. Deburr, then try it in the printed pocket before sticking it down.</p>
</section>

<section id="rebuild"><h2>Rebuilding after a change</h2>
<p>Edit the values at the top of <code>case.py</code>, then run these from this folder in order. The first rewrites the STLs, the OpenSCAD copy and the brass outline, and reports any part that collides with another. The OpenSCAD file is a generated copy and has not been run through OpenSCAD.</p>
<p><code>/Applications/Blender.app/Contents/MacOS/Blender -b -P build.py</code><br>
<code>python3 drawings.py</code><br>
<code>/Applications/Blender.app/Contents/MacOS/Blender -b -P pictures.py</code><br>
<code>/Applications/Blender.app/Contents/MacOS/Blender -b NFC-Player-Render.blend -P render.py</code><br>
<code>../.venv/bin/python guide.py</code></p>
<p>The model checks that parts fit each other and the stand-ins. It cannot check print tolerances, your exact boards, heat, or how well the NFC reader works next to brass and stored cards: those need a bench test.</p>
</section>
</main>"""
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NFC Player Case Assembly</title><style>{CSS}</style></head><body><svg width="0" height="0" style="position:absolute"><defs><marker id="head" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="3.2" markerHeight="3.2" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#d2452d"/></marker></defs></svg>{body}<script>{JS}</script></body></html>'


if __name__ == "__main__":
    out = HERE / "NFC-Player-Assembly.html"
    out.write_text(page())
    print("wrote", out.name, f"{out.stat().st_size / 1e6:.1f} MB")
