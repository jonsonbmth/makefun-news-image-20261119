#!/usr/bin/env python3
"""THE WORLD TODAY - one image summing up world news of Thursday 19 Nov 2026.

A one-page newspaper front page, drawn from scratch with the Python 3.13
standard library only: this program renders the masthead, headlines, story
text, a numbered world map and three photo illustrations into a single
1024x1024 PNG and writes it to /output/entry.png (or $MAKEFUN_OUTPUT_DIR).

The three hero photographs are AI-generated illustrations of the day's
events, shipped beside this file in assets/ as PNGs. The letterforms come
from grayscale glyph atlases (assets/font-*.bin, FAT1 format) rendered at
build time from the free DejaVu fonts; this file only reads those bytes,
it never needs a font engine. Everything is deterministic: the same run
always writes the same bytes.
"""

import os
import struct
import zlib

W, H = 1024, 1024
HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ palette
PAPER = (247, 243, 234)
INK = (26, 26, 26)
RED = (178, 34, 34)
GREY = (110, 108, 100)
LAND = (198, 190, 166)
WHITE = (255, 255, 255)

# ---------------------------------------------------------------- PNG codec
# Minimal decoder: 8-bit, non-interlaced, colour types 0 (grey), 2 (RGB)
# and 6 (RGBA, composited over white). Enough for the shipped hero PNGs.


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(data):
    """Return (width, height, bytearray of RGB bytes) for a small PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos = 8
    idat = bytearray()
    width = height = None
    bitdepth = ctype = interlace = None
    while pos < len(data):
        ln = struct.unpack_from(">I", data, pos)[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            width, height, bitdepth, ctype, _c, _f, interlace = \
                struct.unpack(">IIBBBBB", chunk)
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    if bitdepth != 8 or interlace != 0:
        raise ValueError("unsupported PNG: need 8-bit non-interlaced")
    nch = {0: 1, 2: 3, 6: 4}.get(ctype)
    if nch is None:
        raise ValueError("unsupported PNG colour type %r" % (ctype,))
    raw = zlib.decompress(bytes(idat))
    stride = width * nch
    out = bytearray(width * height * 3)
    prev = bytearray(stride)
    p = 0
    for y in range(height):
        f = raw[p]
        p += 1
        row = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(nch, stride):
                row[i] = (row[i] + row[i - nch]) & 255
        elif f == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = row[i - nch] if i >= nch else 0
                row[i] = (row[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = row[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                row[i] = (row[i] + _paeth(a, b, c)) & 255
        elif f != 0:
            raise ValueError("bad PNG filter %r" % (f,))
        if ctype == 2:
            out[y * width * 3:(y + 1) * width * 3] = row
        elif ctype == 6:
            dst = y * width * 3
            for i in range(width):
                r, g, b, a = row[i * 4:i * 4 + 4]
                inv = 255 - a
                out[dst] = (r * a + 255 * inv) // 255
                out[dst + 1] = (g * a + 255 * inv) // 255
                out[dst + 2] = (b * a + 255 * inv) // 255
                dst += 3
        else:  # grey
            dst = y * width * 3
            for i in range(width):
                v = row[i]
                out[dst] = out[dst + 1] = out[dst + 2] = v
                dst += 3
        prev = row
    return width, height, out


# Score table: absolute value of a byte read as a signed filter residual.
_ABS = bytes((b if b < 128 else 256 - b) for b in range(256))


def _chunk(typ, payload):
    out = struct.pack(">I", len(payload)) + typ + payload
    return out + struct.pack(">I", zlib.crc32(typ + payload) & 0xFFFFFFFF)


def encode_png(width, height, rgb):
    """Encode RGB bytes as a deterministic PNG (filter 0 or 2 per row)."""
    raw = bytearray()
    prev = bytes(width * 3)
    for y in range(height):
        row = bytes(rgb[y * width * 3:(y + 1) * width * 3])
        up = bytes((row[i] - prev[i]) & 255 for i in range(len(row)))
        if sum(up.translate(_ABS)) < sum(row.translate(_ABS)):
            raw.append(2)
            raw += up
        else:
            raw.append(0)
            raw += row
        prev = row
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2,
                                       0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    return bytes(png)


# -------------------------------------------------------------------- fonts
# FAT1 atlas: header magic + u16 count + u16 line height, then one 18-byte
# record per glyph (codepoint, xoff, yoff, w, h, advance, data offset),
# then the concatenated 8-bit grayscale bitmaps. xoff/yoff are relative
# to the pen at the text baseline: bitmap top-left is at
# (pen_x + xoff, baseline_y + yoff).


class Font:
    def __init__(self, path):
        data = open(path, "rb").read()
        if data[:4] != b"FAT1":
            raise ValueError("bad font file %s" % path)
        count, self.line_height = struct.unpack_from("<HH", data, 4)
        self.glyphs = {}
        base = 8 + count * 18
        for i in range(count):
            cp, xoff, yoff, gw, gh, adv, doff = struct.unpack_from(
                "<LhhHHHI", data, 8 + i * 18)
            self.glyphs[cp] = (xoff, yoff, gw, gh, adv, base + doff)
        self.data = data

    def width(self, s, tracking=0):
        w = 0
        for ch in s:
            g = self.glyphs.get(ord(ch))
            if g is not None:
                w += g[4] + tracking
        return w - tracking if s else 0

    def wrap(self, s, max_w, tracking=0):
        """Greedy word wrap; returns a list of lines."""
        lines = []
        cur = ""
        for word in s.split(" "):
            trial = word if not cur else cur + " " + word
            if self.width(trial, tracking) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def fit(self, s, max_w, tracking=0):
        """Truncate with '...' so the string fits max_w pixels."""
        if self.width(s, tracking) <= max_w:
            return s
        while s and self.width(s + "...", tracking) > max_w:
            s = s[:-1]
        return s + "..."

    def draw(self, cv, x, baseline, s, color, tracking=0):
        px = x
        for ch in s:
            g = self.glyphs.get(ord(ch))
            if g is None:
                continue
            xoff, yoff, gw, gh, adv, doff = g
            if gw and gh:
                cv.blend_glyph(px + xoff, baseline + yoff, gw, gh,
                               self.data, doff, color)
            px += adv + tracking
        return px


# ------------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.buf = bytearray(bytes(bg) * (w * h))

    def fill_rect(self, x, y, w, h, color):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        stride = self.w * 3
        for yy in range(y0, y1):
            o = yy * stride + x0 * 3
            self.buf[o:o + len(row)] = row

    def paste(self, img_w, img_h, rgb, x, y):
        stride = self.w * 3
        for yy in range(img_h):
            o = (y + yy) * stride + x * 3
            s = yy * img_w * 3
            self.buf[o:o + img_w * 3] = rgb[s:s + img_w * 3]

    def blend_glyph(self, x, y, gw, gh, data, doff, color):
        r, g, b = color
        buf = self.buf
        stride = self.w * 3
        for yy in range(gh):
            py = y + yy
            if py < 0 or py >= self.h:
                continue
            base = py * stride
            row_off = doff + yy * gw
            for xx in range(gw):
                px = x + xx
                if px < 0 or px >= self.w:
                    continue
                a = data[row_off + xx]
                if a == 0:
                    continue
                o = base + px * 3
                if a == 255:
                    buf[o] = r
                    buf[o + 1] = g
                    buf[o + 2] = b
                else:
                    inv = 255 - a
                    buf[o] = (r * a + buf[o] * inv) // 255
                    buf[o + 1] = (g * a + buf[o + 1] * inv) // 255
                    buf[o + 2] = (b * a + buf[o + 2] * inv) // 255

    def disc(self, cx, cy, rad, color):
        for yy in range(cy - rad, cy + rad + 1):
            dy = yy - cy
            dx = int((rad * rad - dy * dy) ** 0.5)
            self.fill_rect(cx - dx, yy, dx * 2 + 1, 1, color)


def load_image(name):
    with open(os.path.join(HERE, "assets", name), "rb") as f:
        return decode_png(f.read())


def load_font(name):
    return Font(os.path.join(HERE, "assets", "font-%s.bin" % name))


# ---------------------------------------------------------------- world map
# Coarse land grid, 96 columns x 48 rows (3.75 degrees a cell). Each entry
# is one run of land: (row, first column, last column), columns counted
# from 180W, rows from 90N. A stylised map, not a survey: it only has to
# read as the world at a glance, with the numbered dots in about the
# right places.
LAND_RUNS = [
    (3, 27, 31),
    (4, 10, 24), (4, 26, 32), (4, 55, 85),
    (5, 8, 27), (5, 27, 32), (5, 50, 88),
    (6, 8, 28), (6, 28, 30), (6, 45, 49), (6, 50, 90),
    (7, 12, 28), (7, 43, 44), (7, 45, 90),
    (8, 13, 27), (8, 43, 52), (8, 52, 90),
    (9, 13, 28), (9, 44, 90),
    (10, 14, 28), (10, 44, 88),
    (11, 14, 28), (11, 44, 84),
    (12, 13, 28), (12, 45, 53), (12, 54, 57), (12, 58, 70), (12, 72, 84),
    (12, 86, 87),
    (13, 13, 28), (13, 45, 53), (13, 54, 58), (13, 60, 70), (13, 72, 85),
    (13, 86, 88),
    (14, 13, 27), (14, 43, 53), (14, 54, 56), (14, 57, 66), (14, 68, 84),
    (15, 14, 27), (15, 43, 54), (15, 55, 57), (15, 58, 67), (15, 68, 82),
    (16, 14, 27), (16, 43, 55), (16, 58, 64), (16, 68, 80), (16, 82, 82),
    (17, 15, 20), (17, 43, 56), (17, 58, 63), (17, 68, 73), (17, 74, 79),
    (18, 16, 21), (18, 43, 56), (18, 69, 72), (18, 74, 79),
    (19, 20, 23), (19, 43, 56), (19, 70, 71), (19, 75, 79),
    (20, 21, 24), (20, 43, 58), (20, 75, 79),
    (21, 24, 30), (21, 44, 55), (21, 76, 82),
    (22, 24, 32), (22, 44, 54), (22, 76, 84),
    (23, 24, 32), (23, 44, 53), (23, 77, 85),
    (24, 24, 32), (24, 44, 53), (24, 78, 86),
    (25, 24, 31), (25, 44, 52), (25, 84, 88),
    (26, 24, 31), (26, 44, 52), (26, 53, 54),
    (27, 25, 31), (27, 45, 52), (27, 53, 54), (27, 80, 86),
    (28, 25, 30), (28, 45, 51), (28, 53, 54), (28, 79, 87),
    (29, 25, 30), (29, 45, 51), (29, 79, 87),
    (30, 25, 30), (30, 46, 50), (30, 79, 87),
    (31, 25, 29), (31, 46, 50), (31, 80, 87),
    (32, 26, 29), (32, 47, 50), (32, 80, 86),
    (33, 26, 29), (33, 81, 86), (33, 90, 91),
    (34, 26, 28), (34, 90, 91),
    (35, 26, 28),
    (36, 26, 28),
    (37, 26, 27),
    (38, 26, 27),
]

# Numbered dots: (number, grid x, grid y, pixel nudge x, pixel nudge y).
# Nudges keep close dots (Crimea/Gaza, Odisha/Dhaka, Hormuz/Riyadh) apart.
MAP_DOTS = [
    (1, 78.4, 18.0, 0, 0),      # Shenzhen
    (2, 28.3, 13.1, 0, 0),      # New York
    (3, 16.5, 14.9, 0, 0),      # Los Angeles
    (4, 57.1, 12.0, 0, -4),     # Crimea
    (5, 63.1, 16.9, 4, -2),     # Strait of Hormuz
    (6, 70.4, 18.7, -4, 3),     # Odisha
    (7, 57.2, 15.6, 7, 2),      # Gaza
    (8, 72.1, 17.7, 6, -3),     # Dhaka
    (9, 60.5, 17.4, -14, 10),   # Riyadh
    (10, 94.6, 35.0, -8, 0),    # Wellington (nudged inside the frame)
    (11, 48.6, 11.0, 0, 0),     # Paris
    (12, 30.2, 21.2, 0, 0),     # Caracas
]

MAP_KEY = [
    "1 SHENZHEN · Trilateral summit",
    "2 NEW YORK · Record $81.3bn IPO",
    "3 LOS ANGELES · GTA VI launch",
    "4 CRIMEA · Bridge hit again",
    "5 HORMUZ · Tanker struck",
    "6 ODISHA · Cyclone evacuation",
    "7 GAZA · Ground raid",
    "8 DHAKA · Lockdown",
    "9 RIYADH · Missile threat",
    "10 WELLINGTON · Test cricket",
    "11 PARIS · Street protests",
    "12 CARACAS · Oil revenue row",
]

# ------------------------------------------------------------------- content
# Every story below happened, or was first reported, on Thursday
# 19 November 2026, and was verified against at least two independent
# sources. 27 stories: 3 heroes + 6 cards + 18 in ALSO ON THURSDAY.

HERO1_KICKER = "GRAND THEFT AUTO VI · LAUNCH DAY"
HERO1_HEAD = ["VICE CITY OPENS ITS DOORS:",
              "GRAND THEFT AUTO VI LAUNCHES WORLDWIDE"]
HERO1_CAPTION = ("Fans hold their copies aloft at a midnight launch as the game "
                 "opens at midnight local time in city after city. Lucia and "
                 "Jason return players to Leonida.")

HERO2_KICKER = "MARKETS · INITIAL PUBLIC OFFERING"
HERO2_HEAD = ["ANTHROPIC'S $81.3 BILLION IPO",
              "IS THE BIGGEST IN HISTORY"]
HERO2_DECK = ("Priced at $83 a share, the AI lab is valued at about $1.5 trillion "
              "as trading begins on Nasdaq under the ticker ANT — the first "
              "frontier AI lab to go public.")

HERO3_KICKER = "DIPLOMACY · SHENZHEN, CHINA"
HERO3_HEAD = ["XI, TRUMP AND PUTIN MEET",
              "FACE TO FACE IN SHENZHEN"]
HERO3_DECK = ("The three leaders sit down together for the first time, on the "
              "margins of APEC in Shenzhen, with Ukraine, trade and artificial "
              "intelligence on the table.")

# (kicker, headline, body)
CARDS = [
    ("CRIMEA",
     "Kerch bridge hit again; traffic halted",
     "Crimea's governor closes the crossing to assess damage after a "
     "fresh attack, the second in three days."),
    ("THE GULF",
     "Tanker struck off Oman; crew safe",
     "A tanker is hit in the engine room off Khasab in the Strait of "
     "Hormuz, the latest attack on Gulf shipping."),
    ("INDIA",
     "Cyclone Akvan: Odisha evacuates 47,000",
     "Cyclone Akvan bears down on India's east coast, with a red alert in "
     "force and landfall expected on Friday."),
    ("GAZA",
     "Ground raid grinds on into second day",
     "Israeli tanks push beyond the Yellow Line as families flee Nuseirat; "
     "no end to the operation is announced."),
    ("BANGLADESH",
     "Lockdown as troops take the streets",
     "Dhaka locks down after ten days of blasts and arson across 28 "
     "districts; paramilitaries patrol the capital."),
    ("SPORT · CRICKET",
     "Bumrah strikes thrice as NZ wobble",
     "India's fast bowler takes three wickets in Wellington — New Zealand "
     "60 for 4 at lunch on day one."),
]

ALSO = [
    "Yemen missile threat toward Riyadh; Saudi all-clear",
    "Voyager 1 reaches a light-day from Earth",
    "US senators warn AI cyber threats outpace defences",
    "Four nations urge aid access to flooded Gaza",
    "US details $12bn Venezuelan oil revenue",
    "US–Philippines pursue $2bn-plus loan package",
    "Carney recalibrates Canada's China ties",
    "France braces for fourth weekend of protests",
    "Mélenchon could win French presidency",
    "Libya seizes cocaine and millions of pills in east",
    "IMF: UAE economy to grow 7.3% next year",
    "US sanctions six over Hezbollah links",
    "Panama makes 2nd arrest over journalist attack",
    "Paraguay extends Ueno Bank guarantee deadline",
    "US panel urges action on China over ship detentions",
    "Alleged Russian spy arrested over Silicon Valley firm",
    "Bukele hails action on gang leader's home in Haiti",
    "India, Israel to upgrade Barak missile system",
]

# -------------------------------------------------------------------- layout
MARGIN = 24
CONTENT = 976  # x from 24 to 1000


def _rule(cv, y, x0=MARGIN, x1=1000, thick=1, color=INK):
    cv.fill_rect(x0, y, x1 - x0, thick, color)


def _frame(cv, x, y, w, h, color=INK):
    cv.fill_rect(x, y, w, 1, color)
    cv.fill_rect(x, y + h - 1, w, 1, color)
    cv.fill_rect(x, y, 1, h, color)
    cv.fill_rect(x + w - 1, y, 1, h, color)


def build():
    cv = Canvas(W, H, PAPER)
    f_mast = load_font("serif-bold-52")
    f_h1 = load_font("serif-bold-26")
    f_h2 = load_font("serif-bold-19")
    f_card = load_font("sans-bold-13")
    f_body = load_font("sans-11")
    f_kick = load_font("sans-bold-10")

    # ---- top bar: the date, front and centre
    f_kick.draw(cv, MARGIN, 18, "THURSDAY, 19 NOVEMBER 2026", INK, tracking=1)
    right = "27 STORIES · SIX CONTINENTS · ONE PAGE"
    f_kick.draw(cv, 1000 - f_kick.width(right, tracking=1), 18, right, INK,
                tracking=1)
    _rule(cv, 24)

    # ---- masthead
    mast = "THE WORLD TODAY"
    f_mast.draw(cv, MARGIN + (CONTENT - f_mast.width(mast, tracking=2)) // 2,
                78, mast, INK, tracking=2)
    _rule(cv, 86, thick=3)
    _rule(cv, 91)

    # ---- hero 1: GTA VI launches
    f_kick.draw(cv, MARGIN, 106, HERO1_KICKER, RED, tracking=1)
    for i, line in enumerate(HERO1_HEAD):
        f_h1.draw(cv, MARGIN + (CONTENT - f_h1.width(line)) // 2,
                  132 + i * 30, line, INK)
    w1, h1, img1 = load_image("hero1.png")
    cv.paste(w1, h1, img1, MARGIN, 170)
    _frame(cv, MARGIN, 170, w1, h1)
    f_body.draw(cv, MARGIN, 356, HERO1_CAPTION, INK)

    _rule(cv, 368)

    # ---- heroes 2 and 3, side by side
    for col, (kick, head, deck, img) in enumerate((
            (HERO2_KICKER, HERO2_HEAD, HERO2_DECK, "hero2.png"),
            (HERO3_KICKER, HERO3_HEAD, HERO3_DECK, "hero3.png"))):
        x = MARGIN + col * 498
        f_kick.draw(cv, x, 384, kick, RED, tracking=1)
        for i, line in enumerate(head):
            f_h2.draw(cv, x, 408 + i * 23, line, INK)
        w, h, im = load_image(img)
        cv.paste(w, h, im, x, 440)
        _frame(cv, x, 440, w, h)
        for i, line in enumerate(f_body.wrap(deck, 478)):
            f_body.draw(cv, x, 586 + i * 14, line, INK)
    cv.fill_rect(511, 384, 1, 216, GREY)

    _rule(cv, 612)

    # ---- six story cards, 3 columns x 2 rows
    for idx, (kick, head, body) in enumerate(CARDS):
        col = idx % 3
        row = idx // 3
        x = MARGIN + col * 332
        y0 = 620 + row * 86
        f_kick.draw(cv, x, y0 + 11, kick, RED, tracking=1)
        for i, line in enumerate(f_card.wrap(head, 312)[:2]):
            f_card.draw(cv, x, y0 + 27 + i * 16, line, INK)
        for i, line in enumerate(f_body.wrap(body, 312)[:2]):
            f_body.draw(cv, x, y0 + 57 + i * 14, line, INK)
    cv.fill_rect(348, 620, 1, 160, GREY)
    cv.fill_rect(680, 620, 1, 160, GREY)

    _rule(cv, 790)

    # ---- numbered world map + key
    f_card.draw(cv, MARGIN, 804, "WHERE IT HAPPENED", INK)
    key_note = "12 PLACES ON THE MAP"
    f_kick.draw(cv, 1000 - f_kick.width(key_note, tracking=1), 804, key_note,
                GREY, tracking=1)
    map_x, map_y, map_w, map_h = MARGIN, 812, 288, 120
    for (row, x0, x1) in LAND_RUNS:
        for gx in range(x0, x1 + 1):
            cv.fill_rect(map_x + gx * 3, map_y + (row * 5) // 2, 3, 3, LAND)
    _frame(cv, map_x, map_y, map_w, map_h)
    for (num, gx, gy, dx, dy) in MAP_DOTS:
        cx = map_x + int(gx * 3) + dx
        cy = map_y + int(gy * 2.5) + dy
        label = str(num)
        rad = 7 if len(label) > 1 else 5
        cv.disc(cx, cy, rad, RED)
        tw = f_kick.width(label)
        f_kick.draw(cv, cx - tw // 2, cy + 4, label, WHITE)
    for i, item in enumerate(MAP_KEY):
        col = i // 4
        row = i % 4
        x = 336 + col * 224
        num, rest = item.split(" ", 1)
        nx = f_kick.draw(cv, x, 824 + row * 26, num, RED)
        f_body.draw(cv, nx + 4, 824 + row * 26, rest, INK)

    # ---- also on Thursday: the remaining 18 stories
    f_card.draw(cv, MARGIN, 946, "ALSO ON THURSDAY", INK)
    note = "IMAGES ARE AI-GENERATED ILLUSTRATIONS"
    f_kick.draw(cv, 1000 - f_kick.width(note, tracking=1), 946, note, GREY,
                tracking=1)
    for i, item in enumerate(ALSO):
        col = i // 6
        row = i % 6
        x = MARGIN + col * 332
        y = 960 + row * 12
        bx = f_kick.draw(cv, x, y, "•", RED)
        f_body.draw(cv, bx + 3, y, f_body.fit(item, 312 - (bx + 3 - x)), INK)

    return cv


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    cv = build()
    data = encode_png(W, H, cv.buf)
    with open(os.path.join(outdir, "entry.png"), "wb") as f:
        f.write(data)
    print("wrote %d bytes to %s/entry.png" % (len(data), outdir))


if __name__ == "__main__":
    main()
