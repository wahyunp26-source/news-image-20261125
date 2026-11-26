#!/usr/bin/env python3
"""news-image-20261125: one image summing up Wednesday 25 November 2026.

Pure Python stdlib. No network. Deterministic: two runs write identical
bytes. Writes exactly $MAKEFUN_OUTPUT_DIR/entry.png (1024x1024, <=1 MiB).

The page is drawn from scratch with a small vector canvas and real type set
from glyph atlases packed in assets_blob.py (built at build time from system
Liberation fonts; PIL is build-time only and never imported here).
"""
import base64
import json
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assets_blob

W = 1024
H = 1024

# ---------------------------------------------------------------- palette
PAPER = (250, 244, 230)
PAPER2 = (243, 235, 212)
INK = (24, 22, 18)
RED = (178, 34, 28)
RED_D = (148, 25, 20)
NAVY = (16, 28, 54)
NAVY2 = (26, 42, 76)
GOLD = (198, 150, 44)
GOLD_L = (232, 196, 110)
GREY = (96, 90, 78)
GREY_L = (168, 160, 144)
LINE = (206, 196, 172)
WHITE = (255, 255, 255)
TEAL = (14, 110, 110)
RUST = (176, 84, 32)
GREEN = (34, 110, 66)
BLUE = (36, 84, 160)
PURPLE = (104, 72, 148)
ORANGE = (214, 116, 28)
SKY = (158, 196, 224)

# ---------------------------------------------------------------- fonts
_DATA = json.loads(zlib.decompress(base64.b64decode(assets_blob.BLOB)))
_CHARS = _DATA["chars"]
_INDEX = {ch: i for i, ch in enumerate(_CHARS)}


class Font:
    def __init__(self, spec):
        self.name = spec
        d = _DATA["fonts"][spec]
        self.w = d["w"]
        self.h = d["h"]
        self.ascent = d["ascent"]
        self.descent = d["descent"]
        self.size = d["size"]
        self.pad = d["pad"]
        raw = zlib.decompress(base64.b64decode(d["blob"]))
        self.bits = raw
        self.glyphs = d["glyphs"]

    def width(self, text):
        total = 0
        for ch in text:
            g = self.glyphs[_INDEX[ch]]
            total += g[4]
        return total

    def draw(self, cv, x, baseline, text, color):
        cx = x
        for ch in text:
            g = self.glyphs[_INDEX[ch]]
            cw, chh, adv, bx, by = g[2], g[3], g[4], g[5], g[6]
            if cw and chh:
                gx = cx + bx
                gy = baseline + by
                cv.blit(self, g[0], g[1], cw, chh, gx, gy, color)
            cx += adv
        return cx

    def draw_center(self, cv, cx, baseline, text, color):
        return self.draw(cv, cx - self.width(text) // 2, baseline, text, color)


F = {name: Font(name) for name in _DATA["fonts"]}


def wrap(text, font, max_w):
    """Word-boundary wrap only. Raises if any single word cannot fit:
    a split word is a layout bug, never silently hyphenated."""
    lines = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for wd in words:
            if font.width(wd) > max_w:
                raise ValueError(f"word too wide for {font.name}: {wd!r}")
            trial = wd if not cur else cur + " " + wd
            if font.width(trial) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
    return lines


def draw_lines(cv, font, x, y, lines, color, leading=None):
    if leading is None:
        leading = font.size + 3
    for i, ln in enumerate(lines):
        font.draw(cv, x, y + i * leading + font.ascent, ln, color)
    return y + len(lines) * leading


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self):
        self.px = bytearray(W * H * 3)
        self.fill(PAPER)

    def fill(self, color):
        r, g, b = color
        row = bytes((r, g, b)) * W
        self.px[:] = row * H

    def set(self, x, y, color):
        if 0 <= x < W and 0 <= y < H:
            i = (y * W + x) * 3
            self.px[i] = color[0]
            self.px[i + 1] = color[1]
            self.px[i + 2] = color[2]

    def blit(self, font, sx, sy, w, h, dx, dy, color):
        # font.bits is an 8-bit coverage map: 0 = no ink, 255 = solid,
        # anything between blends for smooth anti-aliased letter edges.
        bits = font.bits
        fw = font.w
        r, g, b = color
        px = self.px
        for yy in range(h):
            ay = sy + yy
            by = dy + yy
            if by < 0 or by >= H:
                continue
            base = by * W
            arow = ay * fw + sx
            for xx in range(w):
                a = bits[arow + xx]
                if a:
                    bx = dx + xx
                    if 0 <= bx < W:
                        i = (base + bx) * 3
                        if a == 255:
                            px[i] = r
                            px[i + 1] = g
                            px[i + 2] = b
                        else:
                            ia = 255 - a
                            px[i] = (r * a + px[i] * ia) // 255
                            px[i + 1] = (g * a + px[i + 1] * ia) // 255
                            px[i + 2] = (b * a + px[i + 2] * ia) // 255

    def rect(self, x, y, w, h, color):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(W, x + w)
        y1 = min(H, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        r, g, b = color
        row = bytes((r, g, b)) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * W + x0) * 3
            self.px[i:i + len(row)] = row

    def rrect(self, x, y, w, h, rad, color):
        self.rect(x + rad, y, w - 2 * rad, h, color)
        self.rect(x, y + rad, w, h - 2 * rad, color)
        for cx, cy in ((x + rad, y + rad), (x + w - rad - 1, y + rad),
                       (x + rad, y + h - rad - 1), (x + w - rad - 1, y + h - rad - 1)):
            self.disc(cx, cy, rad, color)

    def hline(self, x, y, w, color):
        self.rect(x, y, w, 1, color)

    def vline(self, x, y, h, color):
        self.rect(x, y, 1, h, color)

    def line(self, x0, y0, x1, y1, color, thick=1):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            if thick <= 1:
                self.set(x0, y0, color)
            else:
                self.rect(x0 - thick // 2, y0 - thick // 2, thick, thick, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def disc(self, cx, cy, rad, color):
        for yy in range(cy - rad, cy + rad + 1):
            dy = yy - cy
            dx = int((rad * rad - dy * dy) ** 0.5)
            self.rect(cx - dx, yy, 2 * dx + 1, 1, color)

    def ring(self, cx, cy, rad, color, thick=1):
        for t in range(thick):
            r = rad - t
            for yy in range(cy - r, cy + r + 1):
                dy = yy - cy
                dx = int((r * r - dy * dy) ** 0.5)
                self.set(cx - dx, yy, color)
                self.set(cx + dx, yy, color)

    def poly(self, pts, color):
        pts = [(int(px), int(py)) for px, py in pts]
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(H - 1, max(ys)) + 1):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.rect(int(xs[k]), y, max(1, int(xs[k + 1]) - int(xs[k])), 1, color)

    def vgrad(self, x, y, w, h, top, bottom):
        for i in range(h):
            t = i / max(1, h - 1)
            c = tuple(int(top[j] + (bottom[j] - top[j]) * t) for j in range(3))
            self.rect(x, y + i, w, 1, c)

    def hgrad(self, x, y, w, h, left, right):
        for i in range(w):
            t = i / max(1, w - 1)
            c = tuple(int(left[j] + (right[j] - left[j]) * t) for j in range(3))
            self.rect(x + i, y, 1, h, c)

    def frame(self, x, y, w, h, color, thick=1):
        self.rect(x, y, w, thick, color)
        self.rect(x, y + h - thick, w, thick, color)
        self.rect(x, y, thick, h, color)
        self.rect(x + w - thick, y, thick, h, color)


# ---------------------------------------------------------------- png
def write_png(cv, path):
    raw = bytearray()
    stride = W * 3
    prev = bytearray(stride)
    for y in range(H):
        row = cv.px[y * stride:(y + 1) * stride]
        filt = bytearray(stride)
        for i in range(stride):
            left = row[i - 3] if i >= 3 else 0
            filt[i] = (row[i] - left) & 0xFF
        raw.append(1)
        raw.extend(filt)
        prev = row
    comp = zlib.compress(bytes(raw), 9)

    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)

# ---------------------------------------------------------------- helpers
def chip(cv, x, y, text, bg, fg=WHITE, font=None):
    f = font or F["sans_b11"]
    w = f.width(text) + 12
    cv.rrect(x, y, w, 16, 3, bg)
    f.draw(cv, x + 6, y + 12, text, fg)
    return w


def badge(cv, x, y, text):
    """Status badge: OFFICIAL navy, CONFIRMED green, REPORTED blue, CLAIM red."""
    bg = {"OFFICIAL": NAVY, "CONFIRMED": GREEN, "REPORTED": BLUE,
          "CLAIM": RED}.get(text, GREY)
    return chip(cv, x, y, text, bg)


def num_circle(cv, cx, cy, n, r=9):
    cv.disc(cx, cy, r, WHITE)
    cv.ring(cx, cy, r, RED, 1)
    F["sans_b11"].draw_center(cv, cx, cy + 4, str(n), RED)


# Tiny flags (14x10) drawn from simple band/cross/disc patterns.
FLAGS = {
    "VA": ("v", [WHITE, (240, 210, 60)]),
    "CO": ("h", [(252, 210, 0), (0, 60, 160), (200, 30, 30)]),
    "RU": ("h", [WHITE, (0, 80, 180), (200, 30, 30)]),
    "US": ("us", None),
    "UA": ("h", [(0, 110, 200), (250, 210, 0)]),
    "SA": ("h", [(0, 110, 60), WHITE, (0, 110, 60)]),
    "IR": ("h", [(0, 130, 70), WHITE, (200, 30, 30)]),
    "GB": ("gb", None),
    "PL": ("h", [WHITE, (220, 40, 60)]),
    "LY": ("h", [(200, 30, 30), (20, 20, 20), (0, 120, 60)]),
    "AU": ("au", None),
    "TW": ("tw", None),
    "IN": ("h", [(255, 150, 40), WHITE, (0, 130, 60)]),
    "NO": ("no", None),
    "CN": ("cn", None),
    "IL": ("il", None),
    "PS": ("ps", None),
    "YE": ("h", [(200, 30, 30), WHITE, (20, 20, 20)]),
    "EG": ("h", [(200, 30, 30), WHITE, (20, 20, 20)]),
    "PK": ("pk", None),
    "BD": ("bd", None),
    "ID": ("h", [(220, 40, 40), WHITE]),
    "KR": ("kr", None),
    "JP": ("jp", None),
    "DE": ("h", [(20, 20, 20), (220, 40, 40), (250, 200, 0)]),
    "FR": ("v", [(0, 60, 160), WHITE, (220, 40, 40)]),
    "SE": ("se", None),
    "TR": ("tr", None),
    "NG": ("v", [(0, 130, 70), WHITE, (0, 130, 70)]),
    "SY": ("h", [(200, 30, 40), WHITE, (20, 20, 20)]),
    "PR": ("h", [(200, 30, 40), WHITE, (0, 60, 160), WHITE, (200, 30, 40)]),
}


def flag(cv, x, y, w, h, code):
    spec = FLAGS.get(code)
    if spec is None:
        cv.rect(x, y, w, h, GREY)
        return
    kind, cols = spec
    if kind == "h":
        n = len(cols)
        for i, c in enumerate(cols):
            cv.rect(x, y + i * h // n, w, h // n + (1 if i == n - 1 else 0), c)
    elif kind == "v":
        n = len(cols)
        for i, c in enumerate(cols):
            cv.rect(x + i * w // n, y, w // n + (1 if i == n - 1 else 0), h, c)
    elif kind == "us":
        for i in range(7):
            cv.rect(x, y + i * h // 7, w, h // 7 + 1,
                    (190, 30, 40) if i % 2 == 0 else WHITE)
        cv.rect(x, y, w // 2, h * 4 // 7, NAVY)
    elif kind == "gb":
        cv.rect(x, y, w, h, NAVY)
        cv.rect(x + w // 2 - 1, y, 3, h, WHITE)
        cv.rect(x, y + h // 2 - 1, w, 3, WHITE)
        cv.rect(x + w // 2, y, 1, h, (200, 30, 40))
        cv.rect(x, y + h // 2, w, 1, (200, 30, 40))
    elif kind == "au":
        cv.rect(x, y, w, h, NAVY2)
        cv.disc(x + w - 3, y + 2, 1, WHITE)
        cv.disc(x + w - 5, y + 6, 1, WHITE)
        cv.disc(x + 3, y + h - 3, 1, WHITE)
    elif kind == "tw":
        cv.rect(x, y, w, h, (200, 30, 30))
        cv.rect(x, y, w // 2, h // 2, NAVY)
        cv.disc(x + w // 4, y + h // 4, 2, WHITE)
    elif kind == "cn":
        cv.rect(x, y, w, h, (200, 30, 30))
        cv.disc(x + 3, y + 3, 1, GOLD_L)
        cv.disc(x + 6, y + 2, 1, GOLD_L)
    elif kind == "il":
        cv.rect(x, y, w, h, WHITE)
        cv.rect(x, y, w, 2, BLUE)
        cv.rect(x, y + h - 2, w, 2, BLUE)
        cv.disc(x + w // 2, y + h // 2, 2, BLUE)
    elif kind == "ps":
        cv.rect(x, y, w, h // 3, (20, 20, 20))
        cv.rect(x, y + h // 3, w, h // 3, WHITE)
        cv.rect(x, y + 2 * h // 3, w, h // 3, (0, 130, 60))
        cv.poly([(x, y), (x + w // 2, y + h // 2), (x, y + h)], RED)
    elif kind == "pk":
        cv.rect(x, y, w, h, (0, 110, 60))
        cv.rect(x, y, w // 4, h, WHITE)
        cv.disc(x + w * 2 // 3, y + h // 2, 2, WHITE)
    elif kind == "bd":
        cv.rect(x, y, w, h, (0, 120, 70))
        cv.disc(x + w // 2, y + h // 2, 3, (220, 40, 40))
    elif kind == "kr":
        cv.rect(x, y, w, h, WHITE)
        cv.disc(x + w // 2, y + h // 2 - 1, 2, (200, 30, 30))
        cv.disc(x + w // 2, y + h // 2 + 1, 2, BLUE)
    elif kind == "jp":
        cv.rect(x, y, w, h, WHITE)
        cv.disc(x + w // 2, y + h // 2, 3, (200, 30, 40))
    elif kind == "no":
        cv.rect(x, y, w, h, (200, 30, 40))
        cv.rect(x + w // 3 - 1, y, 4, h, WHITE)
        cv.rect(x, y + h // 2 - 1, w, 4, WHITE)
        cv.rect(x + w // 3, y, 2, h, NAVY)
        cv.rect(x, y + h // 2, w, 2, NAVY)
    elif kind == "se":
        cv.rect(x, y, w, h, (0, 100, 170))
        cv.rect(x + w // 3 - 1, y, 3, h, (250, 210, 0))
        cv.rect(x, y + h // 2 - 1, w, 3, (250, 210, 0))
    elif kind == "tr":
        cv.rect(x, y, w, h, (220, 30, 40))
        cv.disc(x + w // 2, y + h // 2, 3, WHITE)
        cv.disc(x + w // 2 + 1, y + h // 2, 2, (220, 30, 40))


# ---------------------------------------------------------------- world map
# Fine land bitmap for the dotted world map: 120 cols x 48 rows covering
# lon -180..180 and lat 75..-55 (3 deg lon x ~2.7 deg lat per cell).
# '#' is land. Each row is written as twelve 10-column blocks.
LANDMAP = [
    ".....#####" "##........" "....#..#.." "#........." "....######" "#........." ".........." ".........." ".........." "...#####.." ".........." "...#####..",
    "....######" "####....##" "##########" "#...#####." "..########" "##........" ".......###" "##########" "####..####" "##########" "##########" "##########",
    "....######" "#####..###" "##########" "#...#####." "...#######" "#........." "......####" "##########" "####..####" "##########" "##########" "##########",
    "...#######" "######.###" "##########" "#....####." "....######" "...###...." "....######" "##########" "##########" "##########" "##########" "##########",
    "....######" "######.###" "########.." "....######" ".....####." "...###...." "..########" "##########" "##########" "##########" "##########" "##########",
    ".....#####" "##########" "#########." "....######" "......##.." ".........." ".#########" "##########" "##########" "##########" "##########" "##########",
    "........##" "######.###" "##########" "...#######" "##........" "........##" "...#######" "##########" "##########" "##########" "##########" "###.......",
    ".........." "....###..#" "##########" "##########" "##........" ".......###" "##########" "##########" "##########" "##########" "##########" "####......",
    ".........." ".........#" "##########" "##########" "###......." "........##" "##########" "##########" "##########" "##########" "##########" "###.......",
    ".........." ".........#" "##########" "##########" "##........" "........##" "##########" "##########" "##########" "##########" "##########" "..........",
    ".........." ".........#" "##########" "##########" "#........." "........##" "##########" "######...#" "##########" "##########" "##########" "..........",
    ".........." "........##" "##########" "##########" "#........." ".......###" "##########" "######...#" "##########" "##########" "##########" "..........",
    ".........." "........##" "##########" "##########" ".........." ".......###" "##########" "##########" "##########" "##########" "##########" "..........",
    ".........." "........##" "##########" "##########" ".........." ".......###" "#..##..##." "##########" "##########" "##########" "#########." "..........",
    ".........." "........##" "##########" "##########" ".........." ".......##." "....##.##." "##########" "##########" "##########" "#########." "..........",
    ".........." ".........." "##########" "##########" ".........." "......####" "#######..." "#######..." "##########" "##########" "########.." "..........",
    ".........." ".........." "##########" "##########" ".........." ".....#####" "##########" "##########" "##########" "##########" "#######..." "..........",
    ".........." ".........." "......####" "##..#....." ".........." "....######" "##########" "##########" "##########" "##########" "#####....." "..........",
    ".........." ".........." "....######" "####......" ".........." "...#######" "##########" "##########" "##########" "#########." "#........." "..........",
    ".......#.." ".........." "....######" "#..###...." ".........." "...#######" "##########" "##########" "##########" "#########." "#........." "..........",
    ".......#.." ".........." ".....#####" "#........." ".........." "...#######" "##########" "#########." "...#######" ".########." ".........." "..........",
    ".........." ".........." ".......###" "###......." ".........." "....######" "##########" "##########" "....#####." "..#######." "##........" "..........",
    ".........." ".........." ".........." "..########" "#........." "...#######" "##########" "########.." ".....####." "....#####." "##........" "..........",
    ".........." ".........." ".........." "....######" "####......" "...#######" "##########" "########.." ".........." "....##...." "###......." "..........",
    ".........." ".........." ".........." ".....#####" "####......" "....######" "##########" "#######..." "......##.." "..####.##." "##........" "..........",
    ".........." ".........." ".........." ".....#####" "######...." "......####" "##########" "########.." ".........." "..###.####" "##........" "..........",
    ".........." ".........." ".........." ".....#####" "######...." ".........." "...#######" "####......" ".........." "...#######" "##..##...." "..........",
    ".........." ".........." ".........." ".....#####" "#######..." ".........." "...#######" "#####....." ".........." "...###.###" "....######" "..........",
    ".........." ".........." ".........." "....######" "#########." ".........." "...#######" "####......" ".........." "....#####." "....######" "..........",
    ".........." ".........." ".........." "....######" "#########." ".........." "....######" "####......" ".........." ".....####." ".....#####" "..........",
    ".........." ".........." ".........." "....######" "#########." ".........." "....######" "###......." ".........." ".....####." ".###...#.." "..........",
    ".........." ".........." ".........." "....######" "#########." ".........." "....######" "####......" ".........." ".........." ".#######.." "..........",
    ".........." ".........." ".........." "....######" "########.." ".........." "...#######" "####.##..." ".........." "........##" "#########." "..........",
    ".........." ".........." ".........." ".....#####" "########.." ".........." "...#######" "###..##..." ".........." "........##" "##########" "..........",
    ".........." ".........." ".........." ".......###" "########.." ".........." "...#######" "##...##..." ".........." ".......###" "##########" "##........",
    ".........." ".........." ".........." ".......###" "#######..." ".........." "...#######" "##...##..." ".........." ".......###" "##########" "##........",
    ".........." ".........." ".........." ".......###" "######...." ".........." "...#######" "#....#...." ".........." ".......###" "##########" "##........",
    ".........." ".........." ".........." ".......###" "#####....." ".........." "...######." "#....#...." ".........." ".......###" "##########" "##........",
    ".........." ".........." ".........." ".......###" "###......." ".........." "...######." ".##......." ".........." ".......###" "##########" "###.......",
    ".........." ".........." ".........." ".......###" "##........" ".........." "...#######" "#........." ".........." "........##" "##########" "###.......",
    ".........." ".........." ".........." ".......###" "##........" ".........." "......####" ".........." ".........." "........##" "##########" "##......##",
    ".........." ".........." ".........." "......###." ".........." ".........." ".........." ".........." ".........." ".........." ".......###" "#.......##",
    ".........." ".........." ".........." "......###." ".........." ".........." ".........." ".........." ".........." ".........." ".........#" "......####",
    ".........." ".........." ".........." "......###." ".........." ".........." ".........." ".........." ".........." ".........." ".........#" ".....###..",
    ".........." ".........." ".........." "......##.." ".........." ".........." ".........." ".........." ".........." ".........." ".........." ".....##...",
    ".........." ".........." ".........." "......##.." ".........." ".........." ".........." ".........." ".........." ".........." ".........." "..........",
    ".........." ".........." ".........." ".......##." ".........." ".........." ".........." ".........." ".........." ".........." ".........." "..........",
    ".........." ".........." ".........." ".......##." ".........." ".........." ".........." ".........." ".........." ".........." ".........." "..........",
]

_LAND_W = 120
_LAND_H = 48


def _on_land(lon, lat):
    c = int((lon + 180) / 360 * _LAND_W)
    r = int((75 - lat) / 130 * _LAND_H)
    if 0 <= c < _LAND_W and 0 <= r < _LAND_H:
        return LANDMAP[r][c] == "#"
    return False


def draw_map(cv, x, y, w, h, pins):
    """Fine dotted world map (lon -180..180, lat 75..-55) with pins.
    One small dot per land cell of LANDMAP, so the coasts read as dotted
    continent shapes instead of blocks. pins: list of (n, lon, lat, dx,
    dy) where dx,dy offset the number disc."""
    cv.rect(x, y, w, h, (238, 231, 210))
    cv.frame(x, y, w, h, LINE)
    for r in range(_LAND_H):
        gy = y + int((r + 0.5) / _LAND_H * h)
        row = LANDMAP[r]
        for c in range(_LAND_W):
            if row[c] == "#":
                gx = x + int((c + 0.5) / _LAND_W * w)
                cv.disc(gx, gy, 1, (120, 108, 88))
    for n, lon, lat, dx, dy in pins:
        px = x + int((lon + 180) / 360 * w)
        py = y + int((75 - lat) / 130 * h)
        qx, qy = px + dx, py + dy
        cv.disc(px, py, 2, RED)
        if dx or dy:
            cv.line(px, py, qx, qy, RED, 1)
        num_circle(cv, qx, qy, n, 8)


def draw_brief_dots(cv, x, y, w, h, briefs):
    """Small red dots for brief items (no numbers) at their lon/lat."""
    for _, lon, lat in briefs:
        px = x + int((lon + 180) / 360 * w)
        py = y + int((75 - lat) / 130 * h)
        cv.disc(px, py, 2, RED)

# ---------------------------------------------------------------- scenes
def _flame(cv, cx, base, w, h, cols):
    """Layered flame tongues above (cx, base); cols = outer->inner colors."""
    for i, c in enumerate(cols):
        fw = w * (1 - i * 0.28)
        fh = h * (1 - i * 0.22)
        cv.poly([(cx - fw / 2, base), (cx - fw * 0.28, base - fh * 0.7),
                 (cx, base - fh), (cx + fw * 0.3, base - fh * 0.62),
                 (cx + fw / 2, base)], c)


def _smoke(cv, x, y, n, col, r0=7):
    for i in range(n):
        cv.disc(x + i * 7 - n * 3, y - i * 9, r0 + i * 2, col)


def _gulls(cv, x, y, col):
    cv.line(x, y, x + 4, y - 3, col, 1)
    cv.line(x + 4, y - 3, x + 8, y, col, 1)
    cv.line(x + 12, y + 2, x + 15, y - 1, col, 1)
    cv.line(x + 15, y - 1, x + 18, y + 2, col, 1)


def _cloud(cv, x, y, col, s=1):
    """Flat puffy cloud: three overlapping discs on a flat base."""
    cv.disc(x, y, 5 * s, col)
    cv.disc(x + 7 * s, y - 2 * s, 6 * s, col)
    cv.disc(x + 14 * s, y, 5 * s, col)
    cv.rect(x - 4 * s, y, 22 * s, 3 * s, col)


def _waves(cv, x, y, n, col, gap=26, wlen=15):
    for i in range(n):
        cv.rect(x + i * gap, y + (i % 2) * 3, wlen, 2, col)


def _person(cv, x, y, col, s=1):
    """Tiny standing figure: head disc + body + legs, ~11*s tall."""
    cv.disc(x, y, 2 * s, col)
    cv.rect(x - 1, y + 2 * s, 2 * s + 1, 5 * s, col)
    cv.line(x, y + 7 * s, x - 2 * s, y + 10 * s, col, 1)
    cv.line(x, y + 7 * s, x + 2 * s, y + 10 * s, col, 1)


def _windows(cv, x, y, cols, rows, col, cw=4, ch=5, gx=8, gy=9):
    for r in range(rows):
        for c in range(cols):
            cv.rect(x + c * gx, y + r * gy, cw, ch, col)


def scene_hormuz(cv, x, y, w, h):
    # sunset sky + sun with rays + clouds
    cv.vgrad(x, y, w, h, (250, 170, 90), (216, 102, 48))
    cv.disc(x + w - 52, y + 20, 15, (255, 214, 130))
    cv.disc(x + w - 52, y + 20, 9, (255, 238, 175))
    for dx, dy in ((-22, 0), (22, 0), (0, -20), (-16, -14), (16, -14)):
        cv.line(x + w - 52 + dx // 2, y + 20 + dy // 2,
                x + w - 52 + dx, y + 20 + dy, (255, 220, 150), 2)
    _cloud(cv, x + 18, y + 10, (252, 196, 130))
    _cloud(cv, x + 128, y + 6, (250, 186, 118))
    _gulls(cv, x + 84, y + 14, (120, 70, 40))
    # sea
    cv.vgrad(x, y + 42, w, h - 42, (24, 78, 96), (12, 44, 62))
    _waves(cv, x + 14, y + 48, 4, (120, 180, 200), gap=58)
    _waves(cv, x + 40, y + 66, 3, (96, 156, 180), gap=64)
    # distant third ship, a dark silhouette on the horizon
    cv.rect(x + 196, y + 38, 36, 5, (90, 60, 50))
    cv.rect(x + 210, y + 33, 8, 5, (90, 60, 50))
    cv.line(x + 214, y + 33, x + 214, y + 28, (90, 60, 50), 1)
    # tanker 1 (left, burning): hull, deck stripe, 3 tank domes, bridge
    hx, hy = x + 22, y + 52
    cv.rect(hx, hy, 102, 13, (52, 48, 58))
    cv.rect(hx, hy - 2, 102, 3, (150, 60, 50))
    for i in range(3):
        cv.rect(hx + 8 + i * 20, hy - 11, 16, 9, (30, 120, 130))
        cv.rect(hx + 8 + i * 20, hy - 11, 16, 2, (24, 96, 106))
    cv.rect(hx + 74, hy - 15, 22, 13, (205, 205, 205))
    cv.rect(hx + 78, hy - 12, 4, 4, (40, 40, 40))
    cv.rect(hx + 86, hy - 12, 4, 4, (40, 40, 40))
    cv.rect(hx + 80, hy - 5, 5, 3, (120, 40, 30))
    cv.line(hx + 96, hy - 15, hx + 96, hy - 21, (60, 56, 52), 1)
    _flame(cv, hx + 24, hy - 11, 24, 26, [(240, 90, 20), (250, 160, 40), (255, 220, 110)])
    _flame(cv, hx + 82, hy - 15, 16, 18, [(240, 90, 20), (250, 160, 40)])
    _smoke(cv, hx + 24, hy - 26, 3, (60, 56, 52))
    # wake behind tanker 1
    cv.line(hx - 2, hy + 10, hx - 14, hy + 13, (150, 200, 215), 1)
    cv.line(hx - 2, hy + 12, hx - 10, hy + 15, (150, 200, 215), 1)
    # tanker 2 (right, burning)
    hx, hy = x + 146, y + 58
    cv.rect(hx, hy, 86, 11, (62, 56, 66))
    cv.rect(hx, hy - 2, 86, 3, (150, 60, 50))
    cv.rect(hx + 6, hy - 12, 17, 10, (212, 212, 212))
    cv.rect(hx + 9, hy - 10, 4, 3, (40, 40, 40))
    for i in range(2):
        cv.rect(hx + 32 + i * 18, hy - 9, 14, 7, (180, 60, 40))
    _flame(cv, hx + 48, hy - 9, 22, 22, [(240, 90, 20), (250, 160, 40), (255, 220, 110)])
    _smoke(cv, hx + 48, hy - 32, 3, (60, 56, 52))
    # oil slick trailing from tanker 1
    for i in range(4):
        cv.disc(x + 108 + i * 9, y + 68 - (i % 2) * 2, 3, (16, 34, 44))
    # mines on the water, with spikes and sinker chains
    for mx, my in ((x + 130, y + 62), (x + 224, y + 66), (x + 56, y + 70)):
        cv.disc(mx, my, 4, (20, 20, 24))
        for a, b in ((-5, 0), (5, 0), (0, -5), (-3, -3), (3, -3)):
            cv.line(mx, my, mx + a, my + b, (20, 20, 24), 1)
        cv.line(mx, my + 4, mx, my + 8, (20, 20, 24), 1)


def scene_space(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (8, 12, 34), (16, 30, 66))
    for sx, sy, r in ((24, 14, 1), (60, 30, 1), (120, 10, 1), (180, 22, 2),
                      (230, 12, 1), (40, 52, 1), (96, 44, 1), (150, 48, 1),
                      (210, 40, 1), (16, 70, 1), (240, 66, 1), (84, 66, 1),
                      (130, 62, 1), (200, 58, 1), (10, 40, 1), (250, 46, 1),
                      (70, 8, 1), (160, 32, 1), (36, 24, 1), (222, 30, 1)):
        cv.disc(x + sx, y + sy, r, WHITE)
    cv.disc(x + 150, y + 16, 1, GOLD_L)
    cv.disc(x + 52, y + 40, 1, GOLD_L)
    # Earth arc at the bottom: a very large circle, only its top sliver shows.
    import math as _math
    _cx = x + w // 2
    _cy = y + h + 752
    _r = 800
    _pts = []
    for _xx in range(x, x + w + 1, 8):
        _dx = _xx - _cx
        _yy = _cy - int(_math.sqrt(max(0, _r * _r - _dx * _dx)))
        _pts.append((_xx, _yy))
    _pts += [(x + w, y + h), (x, y + h)]
    cv.poly(_pts, (44, 140, 190))
    _pts2 = []
    for _xx in range(x, x + w + 1, 8):
        _dx = _xx - _cx
        _yy = _cy - int(_math.sqrt(max(0, _r * _r - _dx * _dx))) + 6
        _pts2.append((_xx, _yy))
    _pts2 += [(x + w, y + h), (x, y + h)]
    cv.poly(_pts2, (28, 110, 170))
    # cloud swirls + land on the visible arc
    cv.poly([(x + 30, y + h - 2), (x + 90, y + h - 10), (x + 150, y + h - 5),
             (x + 210, y + h - 12), (x + 250, y + h - 3), (x + 250, y + h),
             (x + 30, y + h)], (34, 140, 90))
    cv.poly([(x + 60, y + h - 1), (x + 110, y + h - 7), (x + 170, y + h - 2),
             (x + 230, y + h - 6), (x + 250, y + h - 1), (x + 250, y + h),
             (x + 60, y + h)], (60, 170, 110))
    for cxp, cyp in ((52, h - 16), (128, h - 13), (196, h - 17)):
        cv.disc(x + cxp, y + cyp, 4, (235, 244, 250))
        cv.disc(x + cxp + 6, y + cyp + 1, 3, (235, 244, 250))
    # Tiangong station: truss + gridded solar arrays + modules + antenna
    sx, sy = x + 44, y + 26
    cv.rect(sx, sy + 10, 158, 4, (200, 200, 205))
    for ax in (sx, sx + 112):
        cv.rect(ax, sy + 2, 42, 11, (40, 90, 160))
        for gx in range(1, 4):
            cv.vline(ax + gx * 10, sy + 2, 11, (28, 66, 120))
        cv.hline(ax, sy + 7, 42, (28, 66, 120))
    cv.rect(sx + 50, sy, 38, 12, (222, 222, 226))
    cv.rect(sx + 54, sy + 3, 7, 6, (30, 90, 160))
    cv.rect(sx + 66, sy + 3, 7, 6, (30, 90, 160))
    cv.rect(sx + 94, sy + 2, 14, 8, (200, 200, 205))
    cv.disc(sx + 112, sy + 6, 4, (232, 232, 236))
    cv.line(sx + 66, sy, sx + 66, sy - 7, (200, 200, 205), 1)
    cv.disc(sx + 66, sy - 9, 2, (240, 200, 90))
    # Pakistani + Chinese flags on the main module
    cv.rect(sx + 54, sy + 13, 10, 6, (0, 110, 60))
    cv.rect(sx + 67, sy + 13, 10, 6, (200, 30, 30))
    cv.disc(sx + 72, sy + 16, 1, GOLD_L)
    # Shenzhou capsule closing in horizontally: nose cone, window, thruster
    cx, cy = x + 218, y + 46
    cv.rrect(cx - 24, cy - 7, 36, 14, 6, (235, 235, 238))
    cv.poly([(cx - 24, cy - 6), (cx - 38, cy), (cx - 24, cy + 6)],
            (250, 200, 90))
    cv.disc(cx - 10, cy, 3, (30, 90, 160))
    cv.rect(cx + 4, cy - 7, 5, 14, (30, 90, 160))
    cv.poly([(cx + 12, cy - 4), (cx + 22, cy), (cx + 12, cy + 4)],
            (255, 190, 80))
    cv.poly([(cx + 12, cy - 2), (cx + 17, cy), (cx + 12, cy + 2)],
            (255, 230, 150))
    cv.ring(cx - 48, cy, 3, (120, 220, 160), 1)
    cv.line(cx - 48, cy - 6, cx - 48, cy + 6, (120, 220, 160), 1)
    cv.line(cx - 54, cy, cx - 42, cy, (120, 220, 160), 1)
    F["sans_b11"].draw(cv, x + 8, y + 14, "SHENZHOU-24", GOLD_L)
    F["sans_b11"].draw(cv, x + w - 8 - F["sans_b11"].width("TIANGONG"),
                       y + 14, "TIANGONG", GOLD_L)


def scene_cairo(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (18, 26, 58), (40, 52, 96))
    for sx, sy in ((20, 12), (70, 22), (150, 10), (210, 20), (240, 8), (110, 16)):
        cv.disc(x + sx, y + sy, 1, (220, 220, 200))
    # crescent moon
    cv.disc(x + 232, y + 14, 7, (240, 226, 170))
    cv.disc(x + 236, y + 12, 6, (24, 32, 62))
    # skyline with lit windows, a minaret and a dome
    base = y + 44
    for bx, bw, bh in ((4, 24, 22), (32, 16, 30), (52, 26, 18), (82, 14, 26),
                       (170, 22, 28), (196, 18, 20), (218, 26, 24)):
        cv.rect(x + bx, base - bh, bw, bh, (14, 18, 40))
        _windows(cv, x + bx + 4, base - bh + 5, 2, 2, (240, 200, 110),
                 cw=3, ch=4, gx=8, gy=8)
    cv.rect(x + 128, base - 38, 7, 38, (14, 18, 40))
    cv.disc(x + 131, base - 38, 5, (14, 18, 40))
    cv.disc(x + 131, base - 45, 2, (240, 200, 110))
    cv.rect(x + 142, base - 16, 24, 16, (14, 18, 40))
    cv.disc(x + 154, base - 16, 9, (14, 18, 40))
    # ring road
    cv.rect(x, base, w, h - 44, (52, 50, 48))
    cv.rect(x, base, w, 3, (200, 200, 200))
    for i in range(6):
        cv.rect(x + 10 + i * 44, base + 22, 22, 3, (240, 220, 140))
    # streetlight
    cv.line(x + 66, base + 26, x + 66, base + 4, (30, 30, 30), 2)
    cv.line(x + 66, base + 4, x + 74, base + 4, (30, 30, 30), 1)
    cv.disc(x + 75, base + 5, 2, (255, 230, 150))
    # overturned tanker + cab
    tx, ty = x + 96, base + 10
    cv.rect(tx, ty - 4, 62, 12, (180, 60, 40))
    cv.rect(tx + 4, ty - 1, 54, 2, (140, 44, 30))
    cv.disc(tx + 62, ty + 2, 6, (180, 60, 40))
    cv.rect(tx - 22, ty - 2, 20, 10, (200, 200, 200))
    cv.rect(tx - 20, ty, 6, 4, (40, 60, 90))
    cv.disc(tx + 10, ty + 10, 3, (10, 10, 10))
    cv.disc(tx + 48, ty + 10, 3, (10, 10, 10))
    # cars caught near the fire
    for cxp, cyp in ((x + 28, base + 4), (x + 198, base + 6)):
        cv.rect(cxp, cyp, 26, 8, (30, 90, 140))
        cv.rect(cxp + 4, cyp - 6, 16, 7, (60, 120, 170))
        cv.rect(cxp + 7, cyp - 5, 5, 4, (190, 220, 240))
        cv.disc(cxp + 6, cyp + 9, 3, (10, 10, 10))
        cv.disc(cxp + 20, cyp + 9, 3, (10, 10, 10))
    # the big fire: three teardrop flames along the tank + a glow line
    cv.rect(tx - 4, ty - 6, 70, 4, (250, 150, 40))
    _flame(cv, tx + 28, ty - 4, 34, 44, [(230, 70, 16), (250, 150, 40), (255, 220, 110)])
    _flame(cv, tx + 58, ty - 4, 22, 30, [(230, 70, 16), (250, 150, 40)])
    _flame(cv, tx + 2, ty - 4, 15, 20, [(230, 70, 16), (250, 150, 40)])
    _smoke(cv, tx + 28, ty - 40, 2, (30, 28, 26), r0=4)
    _smoke(cv, tx + 58, ty - 30, 2, (40, 36, 32), r0=3)
    # ambulance with cross + fire crew figures
    ax, ay = x + 12, base + 18
    cv.rect(ax, ay, 27, 12, WHITE)
    cv.rect(ax + 19, ay + 3, 3, 6, RED)
    cv.rect(ax + 17, ay + 5, 7, 2, RED)
    cv.disc(ax + 6, ay + 13, 3, (10, 10, 10))
    cv.disc(ax + 21, ay + 13, 3, (10, 10, 10))
    for i in range(4):
        _person(cv, x + 168 + i * 11, base + 20, (220, 200, 180))
    cv.line(x + 160, base + 30, x + 128, base + 16, (200, 60, 40), 2)


# ---- mid scenes (185x52) ----
def scene_hodeidah(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (250, 200, 140), (224, 158, 88))
    cv.disc(x + 164, y + 10, 7, (255, 226, 150))
    cv.vgrad(x, y + 34, w, h - 34, (30, 90, 120), (18, 60, 90))
    _waves(cv, x + 8, y + 44, 4, (140, 200, 220), gap=46, wlen=12)
    # container stacks with ribbed sides, three colours
    for sx, cols in ((6, ((180, 90, 50), (40, 110, 150))),
                     (52, ((60, 140, 90), (180, 90, 50), (200, 160, 60))),
                     (98, ((40, 110, 150), (150, 70, 90)))):
        for i, c in enumerate(cols):
            by = y + 30 - (len(cols) - i) * 9
            cv.rect(x + sx, by, 40, 9, c)
            for rx in range(4):
                cv.vline(x + sx + 5 + rx * 9, by + 1, 7, (70, 58, 44))
            cv.rect(x + sx, by, 40, 1, (255, 255, 255))
    # one dock crane by the ship: mast, jib, back-stay, cable and hook block
    cv.line(x + 170, y + 40, x + 170, y + 22, (40, 40, 40), 3)
    cv.line(x + 170, y + 22, x + 138, y + 27, (40, 40, 40), 2)
    cv.line(x + 170, y + 22, x + 179, y + 34, (40, 40, 40), 1)
    cv.line(x + 146, y + 25, x + 146, y + 33, (40, 40, 40), 1)
    cv.rect(x + 143, y + 33, 7, 5, (200, 160, 60))
    # ship hull at the quay + smoke from a struck stack
    cv.poly([(x + 116, y + 40), (x + 168, y + 40), (x + 162, y + 47),
             (x + 122, y + 47)], (52, 48, 58))
    cv.rect(x + 150, y + 34, 12, 6, (200, 200, 200))
    _flame(cv, x + 26, y + 21, 18, 13, [(240, 90, 20), (250, 160, 40)])
    _smoke(cv, x + 26, y + 20, 3, (70, 66, 60), r0=3)
    _gulls(cv, x + 60, y + 6, (120, 80, 40))


def scene_markets(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (14, 20, 44), (30, 40, 70))
    for gy in range(5):
        cv.hline(x + 6, y + 6 + gy * 10, w - 12, (60, 70, 100))
    for gx in range(6):
        cv.vline(x + 6 + gx * 30, y + 6, 40, (44, 54, 84))
    pts = [(x + 8, y + 20), (x + 38, y + 26), (x + 68, y + 20), (x + 98, y + 30),
           (x + 128, y + 38), (x + 158, y + 45)]
    for i in range(len(pts) - 1):
        cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], (240, 70, 60), 2)
    for pxp, pyp in pts[1:]:
        cv.disc(pxp, pyp, 2, (255, 120, 100))
    # a faint green counter-line underneath
    gpts = [(x + 8, y + 40), (x + 48, y + 37), (x + 88, y + 39), (x + 128, y + 35)]
    for i in range(len(gpts) - 1):
        cv.line(gpts[i][0], gpts[i][1], gpts[i + 1][0], gpts[i + 1][1],
                (60, 180, 110), 1)
    # candlesticks, red then green
    for cxp, top, bot, c in ((143, 8, 22, (240, 70, 60)),
                             (156, 14, 26, (240, 70, 60)),
                             (169, 18, 30, (60, 180, 110))):
        cv.line(x + cxp + 4, y + top - 4, x + cxp + 4, y + bot + 4, c, 1)
        cv.rect(x + cxp, y + top, 9, bot - top, c)
    # falling arrow + chip icon
    cv.line(x + 96, y + 30, x + 112, y + 42, (240, 70, 60), 2)
    cv.poly([(x + 106, y + 44), (x + 118, y + 44), (x + 112, y + 36)],
            (240, 70, 60))
    cv.rect(x + 10, y + 34, 20, 15, (20, 120, 90))
    cv.rect(x + 15, y + 38, 10, 7, (16, 84, 64))
    for pxp in (12, 26):
        cv.disc(x + pxp, y + 36, 1, GOLD_L)
        cv.disc(x + pxp, y + 47, 1, GOLD_L)
    F["sans_b11"].draw(cv, x + 30, y + 13, "KOSPI", (255, 120, 100))


def scene_tariffs(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (150, 200, 235), (96, 156, 204))
    cv.disc(x + 10, y + 8, 6, (255, 240, 170))
    cv.vgrad(x, y + 32, w, h - 32, (24, 90, 130), (16, 60, 100))
    _waves(cv, x + 12, y + 42, 4, (200, 230, 245), gap=48, wlen=13)
    _gulls(cv, x + 52, y + 8, (70, 100, 130))
    # container ship: hull, bridge with windows and flag, two container rows
    sx, sy = x + 14, y + 26
    cv.poly([(sx, sy), (sx + 138, sy), (sx + 126, sy + 13), (sx + 12, sy + 13)],
            (30, 30, 36))
    cv.rect(sx + 116, sy - 13, 17, 13, (222, 222, 222))
    cv.rect(sx + 119, sy - 10, 4, 4, (40, 60, 90))
    cv.rect(sx + 126, sy - 10, 4, 4, (40, 60, 90))
    cv.line(sx + 124, sy - 13, sx + 124, sy - 19, (30, 30, 36), 1)
    cv.rect(sx + 124, sy - 19, 7, 4, (200, 40, 40))
    cols = ((200, 60, 40), (40, 120, 180), (240, 180, 40),
            (40, 150, 90), (180, 60, 120), (220, 120, 40))
    for i, c in enumerate(cols[:3]):
        cv.rect(sx + 10 + i * 34, sy - 11, 32, 11, c)
        cv.vline(sx + 20 + i * 34, sy - 11, 11, (60, 50, 44))
        cv.vline(sx + 30 + i * 34, sy - 11, 11, (60, 50, 44))
    for i, c in enumerate(cols[3:]):
        cv.rect(sx + 10 + i * 34, sy - 22, 32, 11, c)
        cv.vline(sx + 20 + i * 34, sy - 22, 11, (60, 50, 44))
        cv.vline(sx + 30 + i * 34, sy - 22, 11, (60, 50, 44))
    # dock crane silhouette behind the ship
    cv.line(x + 168, y + 40, x + 168, y + 8, (52, 66, 84), 3)
    cv.line(x + 168, y + 8, x + 138, y + 8, (52, 66, 84), 2)
    cv.line(x + 146, y + 8, x + 146, y + 18, (52, 66, 84), 1)
    cv.rect(x + 143, y + 18, 6, 5, (52, 66, 84))
    cv.disc(x + w - 24, y + 13, 13, RED)
    F["sans_b11"].draw_center(cv, x + w - 24, y + 17, "20%", WHITE)


def scene_solomons(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (240, 230, 200), (214, 194, 154))
    cv.disc(x + 168, y + 9, 6, (250, 214, 120))
    # the treaty document: title bar, ruled lines, gold seal with ribbons
    cv.rect(x + 56, y + 7, 68, 40, WHITE)
    cv.frame(x + 56, y + 7, 68, 40, INK)
    cv.rect(x + 62, y + 12, 56, 3, RED)
    for i in range(4):
        cv.rect(x + 62, y + 20 + i * 6, 56 - i * 9, 2, GREY)
    cv.disc(x + 108, y + 38, 6, GOLD)
    cv.disc(x + 108, y + 38, 3, GOLD_L)
    cv.poly([(x + 104, y + 42), (x + 108, y + 50), (x + 110, y + 43)], RED)
    cv.poly([(x + 112, y + 42), (x + 114, y + 50), (x + 109, y + 43)], BLUE)
    # a pen resting on the document corner
    cv.line(x + 118, y + 44, x + 132, y + 30, (30, 30, 40), 2)
    cv.poly([(x + 130, y + 28), (x + 134, y + 30), (x + 131, y + 33)],
            (30, 30, 40))
    # the two flags: Australia and the Solomons
    flag(cv, x + 12, y + 8, 28, 17, "AU")
    cv.rect(x + 12, y + 29, 28, 17, (0, 110, 90))
    cv.poly([(x + 12, y + 29), (x + 40, y + 29), (x + 12, y + 46)],
            (40, 90, 170))
    cv.line(x + 12, y + 44, x + 40, y + 31, GOLD_L, 2)
    for fx, fy in ((17, 33), (24, 37), (31, 41)):
        cv.disc(x + fx, y + fy, 1, WHITE)
    cv.vline(x + 11, y + 7, 40, (90, 70, 50))
    # palm tree on the right
    cv.line(x + 158, y + 48, x + 155, y + 26, (110, 80, 50), 3)
    for a, b in ((-14, -8), (-7, -11), (0, -12), (8, -11), (14, -7)):
        cv.line(x + 155, y + 26, x + 155 + a, y + 26 + b, (34, 110, 66), 2)
    cv.disc(x + 152, y + 29, 3, (120, 90, 40))
    cv.disc(x + 158, y + 30, 3, (120, 90, 40))


def scene_ukenergy(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (250, 230, 190), (232, 204, 156))
    cv.rect(x, y + 44, w, 8, (150, 170, 90))
    for gx in (8, 40, 150, 172):
        cv.line(x + gx, y + 46, x + gx - 2, y + 41, (90, 130, 60), 1)
        cv.line(x + gx + 3, y + 46, x + gx + 4, y + 41, (90, 130, 60), 1)
    # house: brick walls, roof, smoking chimney, door, cross-framed windows
    cv.rect(x + 14, y + 24, 54, 22, (190, 120, 70))
    for ry in range(3):
        cv.hline(x + 14, y + 30 + ry * 6, 54, (168, 104, 60))
    cv.poly([(x + 8, y + 26), (x + 41, y + 8), (x + 74, y + 26)], (150, 60, 40))
    cv.rect(x + 54, y + 10, 8, 12, (150, 90, 60))
    cv.disc(x + 59, y + 6, 3, (200, 190, 175))
    cv.disc(x + 63, y + 3, 2, (200, 190, 175))
    cv.rect(x + 36, y + 34, 11, 12, (60, 40, 30))
    cv.disc(x + 44, y + 40, 1, GOLD_L)
    for wxp in (19, 52):
        cv.rect(x + wxp, y + 29, 11, 10, (255, 240, 170))
        cv.vline(x + wxp + 5, y + 29, 10, (120, 80, 50))
        cv.hline(x + wxp, y + 34, 11, (120, 80, 50))
    # low fence in front of the house
    for fxp in range(5):
        cv.rect(x + 12 + fxp * 15, y + 42, 3, 7, (120, 90, 60))
    cv.rect(x + 12, y + 44, 62, 2, (120, 90, 60))
    # lightning bolt between house and bill
    cv.poly([(x + 94, y + 6), (x + 82, y + 24), (x + 91, y + 24), (x + 82, y + 44),
             (x + 100, y + 20), (x + 90, y + 20)], (250, 200, 0))
    # the bill itself, with ruled lines and the new cap figure
    cv.rect(x + 118, y + 8, 56, 38, WHITE)
    cv.frame(x + 118, y + 8, 56, 38, INK)
    F["sans_b11"].draw(cv, x + 124, y + 20, "BILL", GREY)
    cv.rect(x + 124, y + 24, 44, 2, GREY_L)
    cv.rect(x + 124, y + 29, 34, 2, GREY_L)
    F["sans_b12"].draw(cv, x + 124, y + 43, "£2,166", RED)


def scene_gaza(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (226, 206, 178), (198, 176, 140))
    cv.disc(x + 168, y + 10, 6, (246, 226, 170))
    base = y + 46
    # damaged blocks with window grids; the second has a bitten corner
    for bx, bw, bh, cols in ((6, 30, 34, 2), (42, 34, 28, 2), (82, 26, 38, 2)):
        cv.rect(x + bx, base - bh, bw, bh, (168, 158, 140))
        _windows(cv, x + bx + 5, base - bh + 6, cols, 2, (70, 64, 56),
                 cw=5, ch=6, gx=11, gy=11)
    cv.poly([(x + 66, base - 28), (x + 76, base - 28), (x + 76, base - 18)],
            (226, 206, 178))
    # minaret with a cracked shaft
    cv.rect(x + 148, base - 40, 9, 40, (168, 158, 140))
    cv.disc(x + 152, base - 40, 6, (150, 140, 122))
    cv.line(x + 150, base - 30, x + 154, base - 22, (90, 84, 74), 1)
    cv.line(x + 154, base - 22, x + 151, base - 14, (90, 84, 74), 1)
    # rubble pile with scattered debris blocks
    cv.poly([(x + 96, base), (x + 116, base - 13), (x + 140, base)],
            (140, 130, 112))
    for rx, ry, rw in ((102, -4, 7), (118, -8, 6), (128, -3, 8), (110, -1, 5)):
        cv.rect(x + rx, base + ry, rw, 4, (120, 112, 96))
    cv.rect(x, base, w, h - 46, (176, 164, 138))
    # drifting dust + smoke from the second block
    for dxp, dyp in ((58, 30), (96, 36), (24, 38)):
        cv.disc(x + dxp, y + dyp, 7, (216, 200, 168))
        cv.disc(x + dxp + 8, y + dyp + 2, 5, (216, 200, 168))
    _smoke(cv, x + 58, base - 22, 3, (120, 112, 100), r0=3)
    _gulls(cv, x + 120, y + 8, (120, 110, 92))


def scene_ukraine(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (40, 40, 60), (20, 20, 34))
    for sx, sy in ((30, 8), (90, 12), (150, 6), (60, 20), (170, 18)):
        cv.disc(x + sx, y + sy, 1, (200, 200, 210))
    base = y + 44
    # refinery towers joined by pipe runs, with ladders and warning lights
    for txp, th in ((14, 30), (44, 32), (78, 27), (110, 34)):
        cv.rect(x + txp, base - th, 15, th, (120, 120, 130))
        cv.rect(x + txp + 3, base - th - 4, 9, 4, (90, 90, 100))
        cv.line(x + txp + 12, base - th + 4, x + txp + 12, base - 4,
                (200, 200, 200), 1)
        for ry in range(3):
            cv.hline(x + txp + 10, base - th + 8 + ry * 8, 4, (200, 200, 200))
        cv.disc(x + txp + 7, base - th - 6, 1, (240, 60, 40))
    cv.hline(x + 20, base - 24, 100, (160, 160, 170))
    cv.hline(x + 20, base - 14, 100, (160, 160, 170))
    # dome storage tanks on the right
    for dxp in (140, 162):
        cv.rect(x + dxp, base - 12, 20, 12, (150, 150, 160))
        cv.disc(x + dxp + 10, base - 12, 8, (150, 150, 160))
        cv.rect(x + dxp, base - 13, 20, 2, (120, 120, 130))
    _flame(cv, x + 51, base - 32, 22, 11, [(240, 90, 20), (250, 160, 40)])
    _flame(cv, x + 150, base - 20, 16, 12, [(240, 90, 20), (250, 160, 40)])
    # ground + perimeter fence
    cv.rect(x, base, w, h - 44, (30, 28, 26))
    for fxp in range(6):
        cv.rect(x + 8 + fxp * 30, base + 2, 2, 6, (90, 88, 80))
    cv.rect(x + 6, base + 3, w - 12, 1, (90, 88, 80))
    cv.rect(x + 6, base + 6, w - 12, 1, (90, 88, 80))


def scene_bangladesh(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (250, 235, 200), (225, 200, 150))
    cv.disc(x + 168, y + 9, 6, (250, 214, 120))
    # garment factory: lit window grid, chimney, door, sign band
    cv.rect(x + 10, y + 16, 76, 30, (180, 90, 60))
    cv.rect(x + 80, y + 4, 10, 42, (150, 70, 50))
    cv.rect(x + 76, y + 1, 18, 6, (150, 70, 50))
    _windows(cv, x + 17, y + 22, 3, 2, (255, 240, 170), cw=9, ch=7, gx=15, gy=12)
    cv.rect(x + 66, y + 34, 10, 12, (90, 50, 36))
    cv.rect(x + 14, y + 40, 62, 4, (120, 60, 40))
    for dpx in (20, 34, 48, 62):
        cv.disc(x + dpx, y + 42, 1, GOLD_L)
    # clothes line with five garments on pegs
    cv.line(x + 100, y + 12, x + 176, y + 12, (90, 70, 50), 1)
    for i, (c, gh) in enumerate((((220, 60, 50), 15), ((40, 120, 180), 11),
                                 ((240, 180, 40), 14), ((40, 150, 90), 10),
                                 ((200, 90, 140), 13))):
        gx = x + 104 + i * 15
        cv.rect(gx, y + 12, 12, gh, c)
        cv.disc(gx + 2, y + 12, 1, (60, 50, 40))
        cv.disc(gx + 10, y + 12, 1, (60, 50, 40))
    # the new wage on a green board + three workers below
    cv.rect(x + 102, y + 34, 58, 15, (0, 130, 70))
    cv.frame(x + 102, y + 34, 58, 15, (0, 100, 52))
    F["sans_b11"].draw_center(cv, x + 131, y + 45, "17,000", WHITE)
    for pxp in (18, 34, 50):
        _person(cv, x + pxp, y + 38, (60, 44, 36))


def scene_sudan(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (250, 210, 150), (210, 160, 100))
    cv.disc(x + 18, y + 9, 7, (252, 230, 170))
    base = y + 44
    # three mud houses with doors and windows
    for bx, bw, bh in ((8, 32, 19), (46, 27, 24), (79, 34, 17)):
        cv.rect(x + bx, base - bh, bw, bh, (170, 140, 100))
        cv.poly([(x + bx - 2, base - bh), (x + bx + bw // 2, base - bh - 9),
                 (x + bx + bw + 2, base - bh)], (140, 90, 60))
        cv.rect(x + bx + bw // 2 - 3, base - 10, 7, 10, (90, 64, 40))
        cv.rect(x + bx + 4, base - bh + 5, 5, 5, (90, 70, 46))
    _flame(cv, x + 59, base - 24, 17, 15, [(240, 90, 20), (250, 160, 40)])
    _smoke(cv, x + 59, base - 22, 2, (90, 84, 76), r0=3)
    # flat-top acacia tree
    cv.line(x + 130, base, x + 128, base - 22, (110, 80, 50), 3)
    cv.line(x + 129, base - 14, x + 120, base - 20, (110, 80, 50), 2)
    for dxp in (108, 122, 136, 148):
        cv.disc(x + dxp, base - 24, 8, (96, 130, 70))
    # two people running from the strike zone
    _person(cv, x + 120, base - 11, (70, 52, 40))
    _person(cv, x + 132, base - 11, (70, 52, 40))
    # the drone overhead: body, four rotors, camera, dashed drop lines
    cv.rect(x + 34, y + 5, 20, 5, (60, 60, 60))
    cv.rect(x + 39, y + 10, 10, 3, (60, 60, 60))
    cv.disc(x + 44, y + 14, 2, (200, 40, 40))
    for rx in (30, 54):
        cv.disc(x + rx, y + 4, 2, (90, 90, 90))
        cv.disc(x + rx, y + 11, 2, (90, 90, 90))
    for dyp in range(2):
        cv.disc(x + 38, y + 19 + dyp * 5, 1, (120, 110, 100))
        cv.disc(x + 50, y + 19 + dyp * 5, 1, (120, 110, 100))
    # dust at ground level
    for dxp in (30, 90, 150):
        cv.disc(x + dxp, base + 3, 5, (222, 190, 140))


def scene_java(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (200, 220, 200), (120, 160, 110))
    cv.disc(x + 168, y + 9, 6, (250, 230, 160))
    # terraced hills: two slopes with contour lines
    cv.poly([(x, y + 52), (x + 38, y + 16), (x + 78, y + 52)], (60, 110, 70))
    cv.poly([(x + 92, y + 52), (x + 128, y + 22), (x + 172, y + 52)], (50, 100, 60))
    for t in range(3):
        yy = y + 28 + t * 8
        cv.line(x + 12 + t * 4, yy, x + 62 - t * 4, yy, (44, 92, 56), 1)
        cv.line(x + 104 + t * 4, y + 32 + t * 7, x + 158 - t * 4, y + 32 + t * 7,
                (40, 86, 52), 1)
    # flooded mine mouth: timber frame, dark opening, water, lamp
    cv.rect(x + 64, y + 20, 48, 32, (40, 34, 28))
    cv.rect(x + 70, y + 26, 36, 26, (24, 60, 90))
    cv.vgrad(x + 70, y + 38, 36, 14, (60, 140, 190), (30, 90, 140))
    cv.rect(x + 60, y + 16, 56, 5, (90, 70, 50))
    cv.rect(x + 62, y + 21, 4, 31, (90, 70, 50))
    cv.rect(x + 110, y + 21, 4, 31, (90, 70, 50))
    cv.disc(x + 88, y + 13, 5, (240, 200, 40))
    cv.disc(x + 88, y + 13, 2, (255, 240, 170))
    # stream running out of the mine
    cv.line(x + 88, y + 52, x + 80, y + 51, (90, 170, 210), 2)
    cv.line(x + 80, y + 51, x + 66, y + 52, (90, 170, 210), 2)
    # rescue truck with beacon
    cv.rect(x + 10, y + 38, 26, 10, (230, 120, 30))
    cv.rect(x + 30, y + 41, 8, 7, (200, 100, 24))
    cv.rect(x + 31, y + 42, 5, 4, (190, 220, 240))
    cv.disc(x + 20, y + 36, 2, (240, 60, 40))
    cv.disc(x + 16, y + 49, 3, (20, 20, 20))
    cv.disc(x + 30, y + 49, 3, (20, 20, 20))
    # three helmeted rescuers + a rope line to the frame
    for pxp in (124, 138, 152):
        _person(cv, x + pxp, y + 38, (40, 60, 90))
        cv.disc(x + pxp, y + 37, 3, (250, 200, 40))
    cv.line(x + 112, y + 18, x + 146, y + 10, (90, 70, 50), 1)
    cv.disc(x + 146, y + 10, 2, (60, 50, 40))
    # trees and rocks in the foreground
    for txp in (44, 164):
        cv.rect(x + txp, y + 40, 3, 10, (90, 66, 44))
        cv.disc(x + txp + 1, y + 36, 6, (44, 100, 58))
        cv.disc(x + txp - 3, y + 40, 4, (44, 100, 58))
    for rx, ry in ((56, 47), (118, 48), (24, 48)):
        cv.rect(x + rx, y + ry, 9, 5, (110, 100, 88))

# ---------------------------------------------------------------- data
REGIONS = [
    ("EUROPE", 11, NAVY), ("ASIA", 8, TEAL), ("MIDDLE EAST", 7, RUST),
    ("AFRICA", 4, GREEN), ("N. AMERICA", 4, BLUE), ("OCEANIA", 2, PURPLE),
    ("S. AMERICA", 1, ORANGE),
]

TIMELINE = [
    ("00:08", "Hodeidah hit"),
    ("00:18", "Shenzhou-24 up"),
    ("00:30", "Australia CPI 4.9%"),
    ("03:56", "Shenzhou-24 docks"),
    ("06:30", "Cartagena freed"),
    ("06:35", "Crews meet"),
    ("EVENING", "Cairo fire"),
]

NUMBERS = [
    ("-6.2%", "Kospi close in AI sell-off"),
    ("30+", "killed in Cairo tanker fire"),
    ("50,183", "Dow close, up 0.3%"),
    ("20%", "top US tariff rate, on China"),
    ("+26%", "UK energy cap, January"),
    ("490,334", "Russian war dead, leaked"),
]

HEROES = [
    dict(n=1, place="STRAIT OF HORMUZ", field="MIDDLE EAST · ENERGY",
         headline="Two tankers hit mines and burn in Hormuz",
         deck="Iran's Guards say the tankers took an unauthorised route and struck mines; no names or casualties given.",
         why="A fifth of seaborne oil passes here.",
         source="IRGC statement · Reuters", status="CLAIM", stat="2 TANKERS",
         scene=scene_hormuz),
    dict(n=2, place="JIUQUAN, CHINA", field="ASIA · SPACE",
         headline="Pakistan's first astronaut docks at Tiangong",
         deck="Shenzhou-24 carried Muhammad Zeeshan Ali, 40, to China's station, the first foreigner aboard.",
         why="China's station takes its first foreign crew.",
         source="CMSA · Reuters · Nature", status="OFFICIAL", stat="00:18 GMT",
         scene=scene_space),
    dict(n=3, place="GIZA, EGYPT", field="AFRICA · DISASTER",
         headline="Fuel tanker fire kills 30 on Cairo ring road",
         deck="A tanker overturned above a tunnel in Al-Warraq and exploded; dozens of cars burned, 25 hurt.",
         why="The toll is preliminary and may rise.",
         source="Egypt Health Ministry · AP", status="CONFIRMED", stat="30+ KILLED",
         scene=scene_cairo),
]

MIDS = [
    dict(n=4, place="HODEIDAH", field="MIDDLE EAST · WAR",
         headline="Coalition strikes Hodeidah port",
         deck="Strikes follow evacuation order; 4 drones downed over Ras Tanura.",
         status="CONFIRMED", stat="4 DRONES", scene=scene_hodeidah),
    dict(n=5, place="SEOUL · TOKYO", field="ASIA · MARKETS",
         headline="AI doubts sink Asian chip stocks",
         deck="Kospi -6.2%, Nikkei -2.8%; Dow edges up to 50,183.",
         status="REPORTED", stat="-6.2%", scene=scene_markets),
    dict(n=6, place="WASHINGTON", field="N. AMERICA · TRADE",
         headline="US proposes tariffs on 14 economies",
         deck="China faces top 20% rate; EU, Japan, Korea capped at 15%.",
         status="OFFICIAL", stat="14 ECONOMIES", scene=scene_tariffs),
    dict(n=7, place="CANBERRA", field="OCEANIA · DIPLOMACY",
         headline="Solomons signs security pact with Australia",
         deck="Treaty bars any foreign base; Canberra is primary partner.",
         status="CONFIRMED", stat="NO BASES", scene=scene_solomons),
    dict(n=8, place="LONDON", field="EUROPE · ENERGY",
         headline="UK energy price cap to jump 26% in January",
         deck="Typical bill rises £1,723 to £2,166 a year, Ofgem says.",
         status="CONFIRMED", stat="+26%", scene=scene_ukenergy),
    dict(n=9, place="GAZA CITY", field="MIDDLE EAST · WAR",
         headline="Israeli strike kills Hamas security chief",
         deck="Colonel Abuelouf, his wife and two daughters die in Gaza City.",
         status="CONFIRMED", stat="4 KILLED", scene=scene_gaza),
    dict(n=10, place="SAMARA REGION", field="EUROPE · WAR",
         headline="Ukrainian drones hit two Rosneft refineries",
         deck="Syzran and Kuibyshev hit; one killed, 145 drones downed.",
         status="REPORTED", stat="2 REFINERIES", scene=scene_ukraine),
    dict(n=11, place="DHAKA", field="ASIA · LABOUR",
         headline="Garment wage rises 36% after protests",
         deck="Minimum pay set at 17,000 taka ($139) from December.",
         status="CONFIRMED", stat="17,000 TAKA", scene=scene_bangladesh),
    dict(n=12, place="ED DAMAZIN", field="AFRICA · WAR",
         headline="RSF drones kill 19 civilians in Sudan",
         deck="Strikes hit Damazin homes and Roseires dam, rights group says.",
         status="REPORTED", stat="19 KILLED", scene=scene_sudan),
    dict(n=13, place="BOGOR", field="ASIA · DISASTER",
         headline="Nine dead in flooded Java gold pit",
         deck="Rescuers hunt 17 trapped miners in a 100-metre shaft.",
         status="CONFIRMED", stat="9 DEAD", scene=scene_java),
]

# (n, place, flag, text, lon, lat)
BRIEFS = [
    (14, "VATICAN", "VA", "Pope calls COP31 failure 'troubling'.", 12, 42),
    (15, "CARTAGENA", "CO", "All hostages freed; one captor killed.", -75, 10),
    (16, "MOSCOW", "RU", "BBC: leak puts Russian war dead at 490,334.", 37, 56),
    (17, "WASHINGTON", "US", "Hack hits CIA and ODNI unclassified data.", -77, 39),
    (18, "KYIV", "UA", "Russian drones kill 7, hit power plants.", 30, 50),
    (19, "JAZAN", "SA", "Houthi projectile hits Saudi port; minor damage.", 42, 17),
    (20, "TEHRAN", "IR", "US tells citizens to leave Iran at once.", 51, 36),
    (21, "NEW YORK", "US", "Dow up 0.3% to 50,183; Nasdaq off 0.6%.", -74, 41),
    (22, "PARIS", "FR", "Eurostar cancels 8 trains in surprise strike.", 2, 49),
    (23, "WARSAW", "PL", "Poland plans no-fly zone after drone entry.", 21, 52),
    (24, "BENGHAZI", "LY", "Two Libyan officers die of Merkury wounds.", 20, 32),
    (25, "SYDNEY", "AU", "Australia inflation jumps to 4.9%.", 151, -34),
    (26, "TAIPEI", "TW", "Taiwan confident of keeping 15% US tariff.", 121, 25),
    (27, "NEW DELHI", "IN", "India denies excess capacity in tariff row.", 77, 29),
    (28, "OSLO", "NO", "Norway hails US tariff exemption.", 11, 60),
    (29, "BEIJING", "CN", "China calls overcapacity claim 'a false issue'.", 116, 40),
    (30, "BORGU", "NG", "Militants kill 30+ in Niger state villages.", 5, 10),
    (31, "PARIS", "FR", "Barrot tells Putin to drop 'colonial delusion'.", 2, 49),
    (32, "TOKYO", "JP", "Japan targets No. 3 AI spot behind US, China.", 140, 36),
    (33, "HASAKA", "SY", "IS attack kills 2 security men, 5 hurt.", 41, 36),
    (34, "SAN JUAN", "PR", "Barreto first mother to win Miss Universe.", -66, 18),
    (35, "LONDON", "GB", "UK pressed to veto Nusseibeh for UN top job.", 0, 51),
    (36, "RIYADH", "SA", "Houthis claim PIF tower hit; 11 hurt.", 47, 25),
    (37, "LILLE", "FR", "Decathlon breach exposes 130,000 customers.", 3, 51),
]

PINS = [
    (1, 56, 27, 14, -10), (2, 100, 40, 12, -12), (3, 31, 30, -16, -14),
    (4, 43, 15, -12, 12), (5, 127, 37, 14, -8), (6, -77, 39, -14, -10),
    (7, 149, -35, 12, 10), (8, 0, 51, -14, -12), (9, 34, 31, 16, 10),
    (10, 50, 53, 10, -12), (11, 90, 24, 12, 10), (12, 34, 12, -18, -12),
    (13, 107, -6, 12, -8),
]

DATE_CHECK = ("Every story above happened or was first reported on Wednesday "
              "25 November 2026 (UTC). Left out because they happened earlier: "
              "Dell's record Q3 (Tue 24 Nov) · Huawei convicted (Tue 24 Nov) · "
              "Sinner knee surgery (Tue 24 Nov).")

FOOTER = ("HOW SURE: OFFICIAL = an authority's own figure · REPORTED = the "
          "day's wires · CLAIM = one side's account. Scenes are drawn "
          "illustrations. Sources: Reuters, AP, CNN, AFP, CMSA, Ofgem, ABS, BBC.")

SUBHEAD = ("Two tankers burn in the Strait of Hormuz · Pakistan's first "
           "astronaut docks at Tiangong · 30 die in a Cairo tanker fire")


def wrap_brief(place, text, w):
    """Wrap one brief: line 1 starts with the bold 'PLACE: ' prefix, so its
    regular part gets w minus the bold prefix width; later lines are plain
    regular at full width. Returns the list of regular-text lines (line 1
    excludes the prefix)."""
    fb, fr = F["sans_b11"], F["sans_r11"]
    words = text.split()
    lines = []
    cap = w - fb.width(place + ": ")
    cur = ""
    i = 0
    while i < len(words):
        trial = words[i] if not cur else cur + " " + words[i]
        if fr.width(trial) <= cap or not cur:
            cur = trial
            i += 1
        else:
            lines.append(cur)
            cur = ""
            cap = w
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- layout
def draw_page(cv):
    # top bar
    cv.rect(0, 0, W, 20, NAVY)
    F["sans_b11"].draw(cv, 28, 14, "THE WORLD IN ONE DAY", GOLD_L)
    right = "37 STORIES · 7 REGIONS · ALL FROM WEDNESDAY 25 NOVEMBER 2026"
    F["sans_r11"].draw(cv, 996 - F["sans_r11"].width(right), 14, right, WHITE)
    cv.rect(0, 20, W, 2, GOLD)

    # masthead
    title = "Wednesday 25 November 2026"
    tw = F["serif_b56"].width(title)
    assert tw <= 968, f"masthead too wide: {tw}"
    F["serif_b56"].draw(cv, 28, 22 + F["serif_b56"].ascent, title, INK)
    F["serif_i14"].draw(cv, 28, 90, SUBHEAD, RED)
    cv.hline(28, 98, 968, LINE)

    # region chips
    cx = 28
    for name, count, color in REGIONS:
        label = f"{name} {count}"
        w = F["sans_b11"].width(label) + 12
        cv.rrect(cx, 104, w, 19, 3, color)
        F["sans_b11"].draw(cv, cx + 6, 117, label, WHITE)
        cx += w + 6
    assert cx - 6 <= 996, "region chips overflow"

    # UTC strip (drop the last beat if it would overflow)
    beats = list(TIMELINE)
    while True:
        total = F["sans_b11"].width("THE DAY IN UTC") + 14
        for t, s in beats:
            total += F["sans_b11"].width(t) + 5 + F["sans_r11"].width(s) + 12
        if total <= 968 or len(beats) <= 5:
            break
        beats.pop()
    cv.rect(28, 130, 968, 25, NAVY)
    cx = 38
    cx = F["sans_b11"].draw(cv, cx, 146, "THE DAY IN UTC", GOLD_L) + 12
    for t, s in beats:
        cx = F["sans_b11"].draw(cv, cx, 146, t, GOLD_L) + 5
        cx = F["sans_r11"].draw(cv, cx, 146, s, WHITE) + 12

    # ---- heroes + numbers panel
    hy = 162
    hw = 258
    for i, hro in enumerate(HEROES):
        x = 28 + i * (hw + 8)
        cv.rect(x, hy, hw, 22, RED)
        num_circle(cv, x + 13, hy + 11, hro["n"], 9)
        F["sans_b12"].draw(cv, x + 28, hy + 15, hro["place"], WHITE)
        cv.rect(x, hy + 22, hw, 2, GOLD)
        hro["scene"](cv, x, hy + 24, hw, 76)
        cv.frame(x, hy + 24, hw, 76, (120, 110, 90))
        # stat chip inside scene, top right
        chip(cv, x + hw - F["sans_b11"].width(hro["stat"]) - 18, hy + 28,
             hro["stat"], (20, 20, 20))
        F["sans_b11"].draw(cv, x, hy + 114, hro["field"], RED)
        badge(cv, x + hw - F["sans_b11"].width(hro["status"]) - 12, hy + 102,
              hro["status"])
        hl = wrap(hro["headline"], F["serif_b20"], hw)
        assert len(hl) <= 2, f"hero headline too long: {hro['headline']}"
        draw_lines(cv, F["serif_b20"], x, hy + 120, hl, INK, 23)
        dl = wrap(hro["deck"], F["serif_r13"], hw)
        assert len(dl) <= 3, f"hero deck too long: {hro['deck']}"
        draw_lines(cv, F["serif_r13"], x, hy + 172, dl, INK, 16)
        F["sans_b11"].draw(cv, x, hy + 232, "WHY IT MATTERS", RED)
        wl = wrap(hro["why"], F["serif_i12"], hw)
        assert len(wl) <= 1, f"hero why too long: {hro['why']}"
        draw_lines(cv, F["serif_i12"], x, hy + 236, wl, INK, 15)
        F["sans_r11"].draw(cv, x, hy + 262, hro["source"], GREY)

    # numbers panel (hero row only)
    px, py, pw, ph = 826, 162, 170, 264
    cv.rect(px, py, pw, ph, NAVY)
    cv.rect(px, py, pw, 3, GOLD)
    F["sans_b12"].draw(cv, px + 12, py + 16, "THE DAY IN NUMBERS", GOLD_L)
    cv.hline(px + 12, py + 24, pw - 24, (80, 90, 120))
    for i, (num, cap) in enumerate(NUMBERS):
        iy = py + 32 + i * 38
        F["serif_b22"].draw(cv, px + 12, iy + 20, num, GOLD_L)
        cl = wrap(cap, F["sans_r11"], pw - 24)
        assert len(cl) <= 1, f"number caption too long: {cap}"
        F["sans_r11"].draw(cv, px + 12, iy + 33, cl[0], WHITE)
        if i:
            cv.hline(px + 12, iy - 6, pw - 24, (80, 90, 120))

    # ---- mids: two uniform rows of five
    mw = 185
    for row in range(2):
        for col in range(5):
            m = MIDS[row * 5 + col]
            x = 28 + col * 194
            y = 436 + row * 154
            m["scene"](cv, x, y, mw, 52)
            cv.frame(x, y, mw, 52, (120, 110, 90))
            chip(cv, x + mw - F["sans_b11"].width(m["stat"]) - 16, y + 4,
                 m["stat"], (20, 20, 20))
            num_circle(cv, x + 12, y + 12, m["n"], 9)
            F["sans_b11"].draw(cv, x, y + 65, m["place"], RED)
            badge(cv, x + mw - F["sans_b11"].width(m["status"]) - 12, y + 53,
                  m["status"])
            F["sans_b11"].draw(cv, x, y + 76, m["field"], GREY)
            hl = wrap(m["headline"], F["serif_b18"], mw)
            assert len(hl) <= 2, f"mid headline too long: {m['headline']}"
            draw_lines(cv, F["serif_b18"], x, y + 81, hl, INK, 20)
            dl = wrap(m["deck"], F["serif_r13"], mw)
            assert len(dl) <= 2, f"mid deck too long: {m['deck']}"
            draw_lines(cv, F["serif_r13"], x, y + 124, dl, INK, 15)

    # ---- bottom: map + briefs
    F["sans_b12"].draw(cv, 28, 758, "WHERE IT HAPPENED", NAVY)
    F["sans_b12"].draw(cv, 344, 758, "ALSO ON WEDNESDAY 25 NOVEMBER", RED)
    cap = "numbered pins = stories 1-13 · dots = briefs 14-37"
    F["sans_r11"].draw(cv, 996 - F["sans_r11"].width(cap), 758, cap, GREY)
    cv.hline(28, 764, 968, LINE)
    draw_map(cv, 28, 770, 300, 180, PINS)
    draw_brief_dots(cv, 28, 770, 300, 180,
                    [(n, lon, lat) for n, _, _, _, lon, lat in BRIEFS])

    # briefs: two columns, split so both columns end at about the same height
    text_w = 282
    wrapped = []
    for (n, place, flg, text, lon, lat) in BRIEFS:
        lines = wrap_brief(place, text, text_w)
        assert len(lines) <= 2, f"brief wraps past 2 lines: {place}"
        wrapped.append((n, place, flg, lines, 14 + 13 * (len(lines) - 1)))
    total_h = sum(it[4] for it in wrapped)
    best_k, best_max = len(wrapped), total_h
    acc = 0
    for k in range(1, len(wrapped)):
        acc += wrapped[k - 1][4]
        if max(acc, total_h - acc) < best_max:
            best_k, best_max = k, max(acc, total_h - acc)
    assert best_max <= 182, f"brief columns too tall: {best_max}"
    for col, group in enumerate((wrapped[:best_k], wrapped[best_k:])):
        bx = 344 + col * 326
        top = 770
        for (n, place, flg, lines, ih) in group:
            cv.rrect(bx, top, 20, 15, 2, RED)
            F["sans_b11"].draw_center(cv, bx + 10, top + 12, str(n), WHITE)
            flag(cv, bx + 24, top + 2, 16, 11, flg)
            tx = bx + 44
            F["sans_b11"].draw(cv, tx, top + 11, place + ":", RED)
            pw_ = F["sans_b11"].width(place + ": ")
            F["sans_r11"].draw(cv, tx + pw_, top + 11, lines[0], INK)
            if len(lines) > 1:
                F["sans_r11"].draw(cv, tx, top + 24, lines[1], INK)
            top += ih

    # ---- date check + footer
    dy = 957
    cv.frame(28, dy, 968, 40, RED, 2)
    cv.rect(28, dy, 104, 40, RED)
    F["sans_b12"].draw_center(cv, 80, dy + 17, "DATE CHECK", WHITE)
    F["sans_b11"].draw_center(cv, 80, dy + 31, "25 NOV 2026", WHITE)
    dl = wrap(DATE_CHECK, F["serif_r12"], 848)
    assert len(dl) <= 2, "date check too long"
    draw_lines(cv, F["serif_r12"], 140, dy + 7, dl, INK, 15)
    fl = wrap(FOOTER, F["sans_r11"], 968)
    assert len(fl) <= 2, "footer too long"
    draw_lines(cv, F["sans_r11"], 28, dy + 42, fl, GREY, 11)


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if not outdir:
        sys.stderr.write("MAKEFUN_OUTPUT_DIR is not set\n")
        return 2
    os.makedirs(outdir, exist_ok=True)
    cv = Canvas()
    draw_page(cv)
    path = os.path.join(outdir, "entry.png")
    size = write_png(cv, path)
    sys.stdout.write(f"wrote {path} ({size} bytes)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
