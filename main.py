#!/usr/bin/env python3
"""THE WORLD TODAY -- front page for Thursday, 19 November 2026.

Pure-stdlib renderer (no network, no third-party code): reads the FAT1
bitmap fonts and the hero photos from assets/, composes a dense broadsheet
front page, and writes it to $MAKEFUN_OUTPUT_DIR/entry.png (default
/output/entry.png). Fully deterministic: the same input bytes always
produce the same output bytes.
"""
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

W, H = 1024, 1024
MARGIN = 24
CONTENT = W - 2 * MARGIN  # 976

PAPER = (247, 243, 234)
INK = (22, 22, 22)
GRAY = (96, 96, 96)
ACCENT = (139, 26, 26)      # dark red, kickers and section labels
CAPTION = (74, 74, 74)


# ------------------------------------------------------------------ fonts
# FAT1: magic b'FAT1', u16 count, u16 line height; per glyph 18 bytes
# (u32 codepoint, i16 xoff, i16 yoff, u16 w, u16 h, u16 advance, u32
# bitmap offset from bitmap start); then concatenated 8-bit glyph bitmaps.
# A glyph's bitmap top-left lands at (pen_x + xoff, baseline_y + yoff).
class Font:
    def __init__(self, name):
        with open(os.path.join(ASSETS, name), "rb") as fh:
            data = fh.read()
        assert data[:4] == b"FAT1", name
        count, self.line_height = struct.unpack_from("<HH", data, 4)
        self.glyphs = {}
        off = 8
        for _ in range(count):
            cp, xoff, yoff, w, h, adv, doff = struct.unpack_from(
                "<LhhHHHI", data, off)
            off += 18
            self.glyphs[cp] = (xoff, yoff, w, h, adv, doff)
        self.bitmaps = data[off:]

    def width(self, text):
        total = 0
        for ch in text:
            g = self.glyphs.get(ord(ch))
            total += g[4] if g else 0
        return total

    def wrap(self, text, max_width):
        """Greedy word wrap; returns a list of lines."""
        lines, cur = [], ""
        for word in text.split(" "):
            trial = word if not cur else cur + " " + word
            if self.width(trial) <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                # A single over-long word is split by characters.
                while self.width(word) > max_width:
                    cut = 1
                    while (cut < len(word)
                           and self.width(word[:cut + 1]) <= max_width):
                        cut += 1
                    lines.append(word[:cut])
                    word = word[cut:]
                cur = word
        if cur:
            lines.append(cur)
        return lines or [""]


# -------------------------------------------------------------------- PNG
# Minimal reader: 8-bit, non-interlaced, colour types 2 (RGB) and 6 (RGBA).
def read_png(path):
    with open(path, "rb") as fh:
        data = fh.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    pos, idat = 8, bytearray()
    width = height = ctype = None
    while pos < len(data):
        size, kind = struct.unpack_from(">I4s", data, pos)
        chunk = data[pos + 8:pos + 8 + size]
        if kind == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(
                ">IIBBBBB", chunk)
            assert depth == 8 and interlace == 0 and ctype in (2, 6), path
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
        pos += 12 + size
    channels = 3 if ctype == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    px = bytearray(width * height * 3)
    prev = bytearray(stride)
    p = 0
    for y in range(height):
        ftype = raw[p]
        p += 1
        row = bytearray(raw[p:p + stride])
        p += stride
        if ftype == 1:  # Sub
            for i in range(channels, stride):
                row[i] = (row[i] + row[i - channels]) & 255
        elif ftype == 2:  # Up
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 255
        elif ftype == 3:  # Average
            for i in range(stride):
                a = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + (a + prev[i]) // 2) & 255
        elif ftype == 4:  # Paeth
            for i in range(stride):
                a = row[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 255
        if channels == 3:
            px[y * width * 3:(y + 1) * width * 3] = row
        else:
            for x in range(width):
                r, g, b, a = row[x * 4:x * 4 + 4]
                o = (y * width + x) * 3
                px[o:o + 3] = bytes((r, g, b)) if a else bytes(PAPER)
        prev = row
    return width, height, bytes(px)


def write_png(path, width, height, px):
    stride = width * 3
    body = bytearray()
    for y in range(height):
        body.append(0)
        body += px[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(body), 9)

    def chunk(kind, payload):
        out = struct.pack(">I", len(payload)) + kind + payload
        return out + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(bytes(png))


# ------------------------------------------------------------------ canvas
class Page:
    def __init__(self):
        self.px = bytearray(PAPER) * (W * H)

    def rect(self, x, y, w, h, color):
        r, g, b = color
        for yy in range(max(0, y), min(H, y + h)):
            row = yy * W * 3
            for xx in range(max(0, x), min(W, x + w)):
                o = row + xx * 3
                self.px[o] = r
                self.px[o + 1] = g
                self.px[o + 2] = b

    def hline(self, x, y, w, color=INK, thick=1):
        self.rect(x, y, w, thick, color)

    def vline(self, x, y, h, color=INK, thick=1):
        self.rect(x, y, thick, h, color)

    def paste(self, x, y, w, h, px):
        for yy in range(h):
            if y + yy >= H:
                break
            src = yy * w * 3
            dst = ((y + yy) * W + x) * 3
            self.px[dst:dst + w * 3] = px[src:src + w * 3]

    def text(self, x, baseline, font, s, color=INK):
        pen = x
        r, g, b = color
        for ch in s:
            gl = font.glyphs.get(ord(ch))
            if gl is None:
                continue
            xoff, yoff, w, h, adv, doff = gl
            if w and h:
                gx, gy = pen + xoff, baseline + yoff
                for yy in range(h):
                    if gy + yy < 0 or gy + yy >= H:
                        continue
                    for xx in range(w):
                        if gx + xx < 0 or gx + xx >= W:
                            continue
                        a = font.bitmaps[doff + yy * w + xx]
                        if not a:
                            continue
                        o = ((gy + yy) * W + gx + xx) * 3
                        self.px[o] = (r * a + self.px[o] * (255 - a)) // 255
                        self.px[o + 1] = (g * a + self.px[o + 1] * (255 - a)) // 255
                        self.px[o + 2] = (b * a + self.px[o + 2] * (255 - a)) // 255
            pen += adv
        return pen - x


# ----------------------------------------------------------------- layout
F52 = Font("font-serif-bold-52.bin")
F26 = Font("font-serif-bold-26.bin")
F19 = Font("font-serif-bold-19.bin")
B13 = Font("font-sans-bold-13.bin")
S11 = Font("font-sans-11.bin")
B10 = Font("font-sans-bold-10.bin")

COL_TOP = 438
COL_BOTTOM = 998
COL_W = 315
COL_X = [MARGIN, MARGIN + COL_W + 16, MARGIN + 2 * (COL_W + 16)]


class Column:
    """One text column; blocks stack from the top, heights measured exactly."""

    def __init__(self, page, x):
        self.page = page
        self.x = x
        self.y = COL_TOP
        self.overflow = []

    def _check(self, label, need):
        if self.y + need > COL_BOTTOM:
            self.overflow.append(label)
            return False
        return True

    def section(self, title):
        if not self._check("section:" + title, 20):
            return
        self.page.text(self.x, self.y + 11, B10, title, ACCENT)
        self.page.hline(self.x, self.y + 16, COL_W, INK, 2)
        self.y += 20

    def hero(self, img, headline, caption, summary):
        """Headline (serif 19) + photo + caption + one-line summary."""
        lines = F19.wrap(headline, COL_W)
        need = len(lines) * 23 + img[1] + 13 + 13 + 14
        if not self._check("hero:" + headline[:30], need):
            return
        for ln in lines:
            self.page.text(self.x, self.y + 18, F19, ln)
            self.y += 23
        self.page.paste(self.x, self.y, img[0], img[1], img[2])
        self.y += img[1] + 3
        cap = S11.wrap(caption, COL_W)
        for ln in cap[:1]:
            self.page.text(self.x, self.y + 9, S11, ln, CAPTION)
            self.y += 13
        for ln in S11.wrap(summary, COL_W)[:1]:
            self.page.text(self.x, self.y + 10, S11, ln)
            self.y += 13
        self.page.hline(self.x, self.y + 4, COL_W, GRAY, 1)
        self.y += 10

    def full(self, headline, summary):
        """Bold headline + 1-2 line summary."""
        hlines = B13.wrap(headline, COL_W)
        slines = S11.wrap(summary, COL_W)
        need = len(hlines) * 16 + len(slines) * 13 + 7
        if not self._check("full:" + headline[:30], need):
            return
        for ln in hlines:
            self.page.text(self.x, self.y + 12, B13, ln)
            self.y += 16
        for ln in slines:
            self.page.text(self.x, self.y + 10, S11, ln)
            self.y += 13
        self.y += 7

    def brief(self, headline):
        """Bold headline only (the headline itself carries the story)."""
        hlines = B13.wrap(headline, COL_W)
        need = len(hlines) * 16 + 6
        if not self._check("brief:" + headline[:30], need):
            return
        for ln in hlines:
            self.page.text(self.x, self.y + 12, B13, ln)
            self.y += 16
        self.y += 6


# -------------------------------------------------------------- the news
# Every story verified from reporting published on 19 November 2026.
LEAD_HEAD = ["Trump, Xi and Putin hold first three-way summit",
             "Peace declaration follows 90 minutes of talks"]
LEAD_SUMMARY = (
    "Donald Trump, Xi Jinping and Vladimir Putin met for 90 minutes on the "
    "sidelines of APEC in Shenzhen, the first three-way summit of the "
    "American, Chinese and Russian leaders. Their joint declaration pledges "
    "dialogue on nuclear risks, UN reform and stable energy flows — but no "
    "deal on Ukraine or Iran.")
LEAD_CAPTION = (
    "The three leaders in Shenzhen on Thursday. The joint declaration says a "
    "nuclear war 'must never be fought'.")

# (kind, headline, summary-or-caption) per column.
COL1 = [
    ("section", "WORLD", None),
    ("hero", "UN court: Myanmar committed genocide",
     "The International Court of Justice in The Hague.",
     "First verdict of its kind by the UN's top court."),
    ("full", "Ukraine hits Crimean Bridge for third time in a week",
     "Russia says Kyiv struck the bridge again this week."),
    ("full", "Israel pushes ground operation beyond Gaza 'Yellow Line'",
     "Four nations urge aid access to flooded Gaza."),
    ("brief", "Houthi missile damages Riyadh tower"),
    ("brief", "Troops mass on Ethiopia-Eritrea border"),
    ("brief", "Drones drive Sudan's civilian toll"),
    ("brief", "Bangladesh unrest: shutdown, arson"),
    ("brief", "IAEA: North Korea expands uranium work"),
    ("brief", "Turkey sentences Imamoglu in CHP case"),
    ("brief", "Denmark OKs Arctic security deal with US"),
    ("brief", "EU proposes 45bn euro loan for Ukraine"),
    ("brief", "EU to send asylum seekers to Rwanda"),
    ("brief", "IMF unlocks $2.3bn for Egypt"),
    ("brief", "Australia jobless rate hits 4.9%"),
]

COL2 = [
    ("section", "WORLD", None),
    ("hero", "Iran strikes Gulf states after US raid",
     "Interceptors over a Gulf capital at night.",
     "Trump says the US will 'see what happens' after Jan 1."),
    ("brief", "US and Venezuela restore military ties"),
    ("brief", "Nigeria seeks justice for 37 dead miners"),
    ("brief", "Eisenkot to form Israel's government"),
    ("brief", "Military plane crash in Siberia kills 19"),
    ("brief", "LPG tanker sinks off Bulgaria after strike"),
    ("brief", "Atmospheric river drenches California"),
    ("brief", "Cyclone Akvan nears India's east coast"),
    ("brief", "COP31 deadlock persists in Antalya"),
    ("section", "MARKETS", None),
    ("full", "Dow falls 561 as Fed minutes rattle Wall Street",
     "S&P 500 falls for a fifth straight day."),
    ("brief", "Nvidia beats, halts AI chips to China"),
    ("brief", "Philippine shares hit five-year low"),
    ("brief", "Auto surge lifts India's Nifty"),
    ("brief", "Bitcoin nears $64,000 as outflows grow"),
]

COL3 = [
    ("section", "TECH & SCIENCE", None),
    ("hero", "Anthropic's $81bn IPO sets record",
     "Traders cheer the biggest listing in history.",
     "The AI lab behind Claude debuts at $83 a share."),
    ("full", "GTA VI goes on sale after 13-year wait",
     "Rockstar's long-awaited epic launches worldwide."),
    ("brief", "Waymo pulls taxis off US freeways"),
    ("brief", "US loses measles elimination status"),
    ("brief", "Ebola vaccines to be trialled in DR Congo"),
    ("brief", "Webb confirms rare star merger"),
    ("brief", "Liver kept alive outside body 7 weeks"),
    ("brief", "EU Commission hit by major cyberattack"),
    ("section", "SPORT & CULTURE", None),
    ("brief", "Chelsea beat PSG 1-0 to reach last eight"),
    ("brief", "Alcaraz beats Medvedev, into ATP semis"),
    ("brief", "Pochettino starts at Man Utd"),
    ("brief", "Ash Barty to enter tennis Hall of Fame"),
    ("brief", "'Human' is Cambridge's word of the year"),
    ("brief", "Assadi wins National Book Award"),
]


# ------------------------------------------------------------------- build
def build_page():
    page = Page()

    title = "THE WORLD TODAY"
    page.text((W - F52.width(title)) // 2, 64, F52, title)
    page.hline(MARGIN, 76, CONTENT, INK, 3)

    left = "THURSDAY, 19 NOVEMBER 2026"
    right = "WORLD EDITION  •  43 STORIES  •  SIX CONTINENTS"
    page.text(MARGIN, 94, B10, left)
    page.text(W - MARGIN - B10.width(right), 94, B10, right)
    page.hline(MARGIN, 100, CONTENT, INK, 1)

    page.text(MARGIN, 120, B10, "SHENZHEN — THE TRILATERAL SUMMIT", ACCENT)
    y = 146
    for ln in LEAD_HEAD:
        page.text(MARGIN, y, F26, ln)
        y += 31

    hero1 = read_png(os.path.join(ASSETS, "hero1.png"))
    page.paste(MARGIN, 186, hero1[0], hero1[1], hero1[2])
    page.text(MARGIN, 390, S11, LEAD_CAPTION, CAPTION)
    y = 406
    for ln in S11.wrap(LEAD_SUMMARY, CONTENT):
        page.text(MARGIN, y, S11, ln)
        y += 13
    page.hline(MARGIN, 432, CONTENT, INK, 2)

    for gx in (COL_X[1] - 8, COL_X[2] - 8):
        page.vline(gx, COL_TOP, COL_BOTTOM - COL_TOP, GRAY, 1)

    heroes = [read_png(os.path.join(ASSETS, "hero%d.png" % n))
              for n in (2, 3, 4)]
    overflow = []
    for idx, blocks in enumerate((COL1, COL2, COL3)):
        col = Column(page, COL_X[idx])
        for block in blocks:
            kind = block[0]
            if kind == "section":
                col.section(block[1])
            elif kind == "hero":
                col.hero(heroes[idx], block[1], block[2], block[3])
            elif kind == "full":
                col.full(block[1], block[2])
            elif kind == "brief":
                col.brief(block[1])
        overflow.extend(col.overflow)
        print("column %d ends at y=%d (bottom %d)" % (idx + 1, col.y,
                                                      COL_BOTTOM))
    if overflow:
        print("OVERFLOW (%d items did not fit):" % len(overflow))
        for item in overflow:
            print("  -", item)

    # Footer.
    page.hline(MARGIN, 1004, CONTENT, INK, 1)
    foot = "THE WORLD TODAY  •  Thursday, 19 November 2026  •  All stories from reporting of the day"
    page.text((W - S11.width(foot)) // 2, 1018, S11, foot, GRAY)
    return page, overflow


def main():
    page, overflow = build_page()
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "entry.png")
    write_png(out, W, H, bytes(page.px))
    print("wrote %s (%d bytes)" % (out, os.path.getsize(out)))
    if overflow:
        print("WARNING: %d items overflowed the columns" % len(overflow))


if __name__ == "__main__":
    main()
