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
        bits = font.bits
        fw = font.w
        r, g, b = color
        for yy in range(h):
            ay = sy + yy
            by = dy + yy
            if by < 0 or by >= H:
                continue
            base = by * W
            for xx in range(w):
                ax = sx + xx
                if bits[(ay * fw + ax) >> 3] >> (7 - (ax & 7)) & 1:
                    bx = dx + xx
                    if 0 <= bx < W:
                        i = (base + bx) * 3
                        self.px[i] = r
                        self.px[i + 1] = g
                        self.px[i + 2] = b

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
    f = font or F["sans_b9"]
    w = f.width(text) + 10
    cv.rrect(x, y, w, 12, 2, bg)
    f.draw(cv, x + 5, y + 9, text, fg)
    return w


def badge(cv, x, y, text):
    """Status badge: OFFICIAL navy, CONFIRMED green, REPORTED blue, CLAIM red."""
    bg = {"OFFICIAL": NAVY, "CONFIRMED": GREEN, "REPORTED": BLUE,
          "CLAIM": RED}.get(text, GREY)
    return chip(cv, x, y, text, bg)


def num_circle(cv, cx, cy, n, r=8):
    cv.disc(cx, cy, r, WHITE)
    cv.ring(cx, cy, r, RED, 1)
    F["sans_b9"].draw_center(cv, cx, cy + 3, str(n), RED)


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
        num_circle(cv, qx, qy, n, 7)


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


def scene_hormuz(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (250, 170, 90), (214, 96, 44))
    cv.disc(x + w - 52, y + 26, 22, (255, 214, 130))
    cv.disc(x + w - 52, y + 26, 13, (255, 236, 170))
    for i in range(5):
        cv.rect(x + 20 + i * 46, y + 58 + i * 2, 34, 2, (255, 220, 150))
    # sea
    cv.vgrad(x, y + 60, w, h - 60, (24, 78, 96), (12, 44, 62))
    for i in range(4):
        cv.rect(x + 30 + i * 60, y + 68 + i * 3, 44, 2, (120, 180, 200))
    # tanker 1 (left, burning)
    hx, hy = x + 34, y + 76
    cv.rect(hx, hy, 96, 16, (52, 48, 58))
    cv.rect(hx, hy - 2, 96, 3, (150, 60, 50))
    cv.rect(hx + 70, hy - 16, 20, 14, (200, 200, 200))
    cv.rect(hx + 74, hy - 12, 4, 4, (40, 40, 40))
    cv.rect(hx + 82, hy - 12, 4, 4, (40, 40, 40))
    for i in range(3):
        cv.rect(hx + 8 + i * 20, hy - 12, 16, 10, (30, 120, 130))
    _flame(cv, hx + 26, hy - 12, 26, 30, [(240, 90, 20), (250, 160, 40), (255, 220, 110)])
    _flame(cv, hx + 78, hy - 16, 18, 22, [(240, 90, 20), (250, 160, 40)])
    _smoke(cv, hx + 26, hy - 42, 3, (60, 56, 52))
    # tanker 2 (right, burning)
    hx, hy = x + 150, y + 84
    cv.rect(hx, hy, 88, 14, (62, 56, 66))
    cv.rect(hx, hy - 2, 88, 3, (150, 60, 50))
    cv.rect(hx + 8, hy - 14, 18, 12, (210, 210, 210))
    for i in range(2):
        cv.rect(hx + 34 + i * 18, hy - 10, 14, 8, (180, 60, 40))
    _flame(cv, hx + 44, hy - 10, 24, 26, [(240, 90, 20), (250, 160, 40), (255, 220, 110)])
    _smoke(cv, hx + 44, hy - 36, 3, (60, 56, 52))
    # mines on the water
    for mx, my in ((x + 128, y + 94), (x + 216, y + 98), (x + 60, y + 96)):
        cv.disc(mx, my, 5, (20, 20, 24))
        for a, b in ((-6, 0), (6, 0), (0, -6), (-4, -4), (4, -4)):
            cv.line(mx, my, mx + a, my + b, (20, 20, 24), 1)
    _gulls(cv, x + 16, y + 18, (120, 70, 40))


def scene_space(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (8, 12, 34), (16, 30, 66))
    for sx, sy, r in ((24, 14, 1), (60, 30, 1), (120, 10, 1), (180, 22, 2),
                      (230, 12, 1), (40, 52, 1), (96, 44, 1), (150, 48, 1),
                      (210, 40, 1), (16, 70, 1), (240, 66, 1), (84, 66, 1),
                      (130, 62, 1), (200, 58, 1), (10, 40, 1), (250, 46, 1)):
        cv.disc(x + sx, y + sy, r, WHITE)
    # Earth arc at the bottom: a very large circle, only its top sliver shows.
    import math as _math
    _cx = x + w // 2
    _cy = y + h + 778
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
    cv.poly([(x + 30, y + h - 2), (x + 90, y + h - 10), (x + 150, y + h - 5),
             (x + 210, y + h - 12), (x + 250, y + h - 3), (x + 250, y + h),
             (x + 30, y + h)], (34, 140, 90))
    cv.poly([(x + 60, y + h - 1), (x + 110, y + h - 7), (x + 170, y + h - 2),
             (x + 230, y + h - 6), (x + 250, y + h - 1), (x + 250, y + h),
             (x + 60, y + h)], (60, 170, 110))
    # Tiangong station: truss + modules + solar panels
    sx, sy = x + 52, y + 34
    cv.rect(sx, sy + 12, 150, 5, (200, 200, 205))
    cv.rect(sx + 6, sy, 44, 12, (40, 90, 160))
    cv.rect(sx + 6, sy + 14, 44, 3, (30, 70, 130))
    cv.rect(sx + 58, sy - 2, 40, 12, (220, 220, 225))
    cv.rect(sx + 62, sy + 1, 8, 6, (30, 90, 160))
    cv.rect(sx + 74, sy + 1, 8, 6, (30, 90, 160))
    cv.rect(sx + 106, sy + 2, 34, 9, (200, 200, 205))
    cv.disc(sx + 140, sy + 6, 5, (230, 230, 235))
    cv.rect(sx + 2, sy + 22, 8, 10, (180, 180, 185))
    # Shenzhou capsule docking, flame trail
    cx, cy = x + 196, y + 66
    cv.poly([(cx - 6, cy - 26), (cx + 6, cy - 26), (cx + 10, cy - 6),
             (cx - 10, cy - 6)], (250, 200, 90))
    cv.rect(cx - 12, cy - 6, 24, 14, (235, 235, 238))
    cv.rect(cx - 12, cy + 8, 24, 4, (30, 90, 160))
    cv.disc(cx, cy + 1, 3, (30, 90, 160))
    cv.line(cx - 4, cy - 26, cx, cy - 34, (255, 220, 120), 2)
    cv.line(cx + 4, cy - 26, cx, cy - 34, (255, 220, 120), 2)
    # Pakistani + Chinese flags on the station module
    cv.rect(sx + 62, sy + 12, 10, 6, (0, 110, 60))
    cv.rect(sx + 74, sy + 12, 10, 6, (200, 30, 30))
    cv.disc(sx + 79, sy + 15, 1, GOLD_L)
    F["sans_b8"].draw(cv, x + 8, y + 14, "SHENZHOU-24", GOLD_L)
    F["sans_b8"].draw(cv, x + w - 58, y + 14, "TIANGONG", GOLD_L)


def scene_cairo(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (18, 26, 58), (40, 52, 96))
    for sx, sy in ((20, 12), (70, 22), (150, 10), (210, 20), (240, 8)):
        cv.disc(x + sx, y + sy, 1, (220, 220, 200))
    # skyline
    base = y + 62
    for bx, bw, bh in ((6, 26, 26), (36, 18, 36), (58, 30, 22), (92, 16, 30),
                       (150, 24, 34), (178, 20, 24), (202, 30, 30), (236, 16, 22)):
        cv.rect(x + bx, base - bh, bw, bh, (14, 18, 40))
        for wy in range(2):
            cv.rect(x + bx + 5 + wy * 8, base - bh + 6, 3, 4, (240, 200, 110))
    # highway
    cv.rect(x, base, w, h - 62, (52, 50, 48))
    cv.rect(x, base, w, 3, (200, 200, 200))
    for i in range(6):
        cv.rect(x + 10 + i * 44, base + 34, 22, 3, (240, 220, 140))
    # overturned tanker + cab
    tx, ty = x + 96, base + 16
    cv.rect(tx, ty - 4, 62, 12, (180, 60, 40))
    cv.disc(tx + 62, ty + 2, 6, (180, 60, 40))
    cv.rect(tx - 22, ty - 2, 20, 10, (200, 200, 200))
    cv.rect(tx - 20, ty, 6, 4, (40, 60, 90))
    # cars caught in the fire
    for cxp in (x + 30, x + 196):
        cv.rect(cxp, base + 8, 26, 8, (30, 90, 140))
        cv.rect(cxp + 4, base + 2, 16, 7, (60, 120, 170))
        cv.disc(cxp + 6, base + 17, 3, (10, 10, 10))
        cv.disc(cxp + 20, base + 17, 3, (10, 10, 10))
    # the big fire
    _flame(cv, tx + 30, ty - 4, 90, 52, [(230, 70, 16), (250, 150, 40), (255, 220, 110)])
    _flame(cv, tx + 66, ty - 4, 46, 34, [(230, 70, 16), (250, 150, 40)])
    _smoke(cv, tx + 30, ty - 56, 4, (30, 28, 26))
    _smoke(cv, tx + 66, ty - 40, 3, (40, 36, 32))
    # ambulance + crowd
    ax, ay = x + 14, base + 30
    cv.rect(ax, ay, 26, 12, WHITE)
    cv.rect(ax + 18, ay + 3, 3, 6, RED)
    cv.rect(ax + 16, ay + 5, 7, 2, RED)
    for i in range(5):
        cv.disc(x + 150 + i * 10, base + 34, 2, (220, 200, 180))


# ---- mid scenes (185x66) ----
def scene_hodeidah(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (250, 200, 140), (220, 150, 80))
    cv.vgrad(x, y + 40, w, h - 40, (30, 90, 120), (18, 60, 90))
    for cxp in (10, 60, 120):
        cv.rect(x + cxp, y + 8, 34, 30, (120, 90, 60))
        cv.rect(x + cxp + 4, y + 12, 26, 4, (90, 70, 45))
        cv.rect(x + cxp + 4, y + 20, 26, 4, (90, 70, 45))
    cv.line(x + 150, y + 6, x + 170, y + 38, (40, 40, 40), 2)
    cv.line(x + 150, y + 6, x + 140, y + 38, (40, 40, 40), 2)
    cv.rect(x + 138, y + 4, 26, 4, (40, 40, 40))
    _flame(cv, x + 30, y + 40, 22, 18, [(240, 90, 20), (250, 160, 40)])
    _smoke(cv, x + 30, y + 22, 3, (70, 66, 60))
    cv.rect(x + 150, y + 46, 30, 8, (200, 200, 200))
    cv.rect(x + 156, y + 40, 12, 6, (60, 60, 60))


def scene_markets(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (14, 20, 44), (30, 40, 70))
    for gy in range(0, 5):
        cv.hline(x + 6, y + 8 + gy * 12, w - 12, (60, 70, 100))
    pts = [(x + 8, y + 12), (x + 40, y + 20), (x + 72, y + 16), (x + 104, y + 30),
           (x + 136, y + 40), (x + 168, y + 52)]
    for i in range(len(pts) - 1):
        cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], (240, 70, 60), 2)
    for pxp, pyp in pts[1:]:
        cv.disc(pxp, pyp, 2, (255, 120, 100))
    cv.rect(x + 12, y + 40, 26, 18, (20, 120, 90))
    cv.rect(x + 18, y + 46, 4, 4, GOLD_L)
    cv.rect(x + 26, y + 46, 4, 4, GOLD_L)
    cv.rect(x + 18, y + 52, 12, 2, GOLD_L)
    F["sans_b8"].draw(cv, x + 120, y + 12, "KOSPI", (255, 120, 100))


def scene_tariffs(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (150, 200, 235), (90, 150, 200))
    cv.vgrad(x, y + 42, w, h - 42, (24, 90, 130), (16, 60, 100))
    for i in range(3):
        cv.rect(x + 20 + i * 52, y + 48 + i, 36, 2, (200, 230, 245))
    # ship
    sx, sy = x + 22, y + 30
    cv.poly([(sx, sy), (sx + 140, sy), (sx + 128, sy + 14), (sx + 12, sy + 14)], (30, 30, 36))
    cv.rect(sx + 118, sy - 12, 16, 12, (220, 220, 220))
    for i, c in enumerate(((200, 60, 40), (40, 120, 180), (240, 180, 40),
                           (40, 150, 90), (180, 60, 120), (220, 120, 40))):
        cv.rect(sx + 14 + i * 18, sy - 12, 16, 12, c)
    cv.disc(x + w - 26, y + 14, 13, RED)
    F["sans_b8"].draw_center(cv, x + w - 26, y + 17, "20%", WHITE)


def scene_solomons(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (240, 230, 200), (210, 190, 150))
    cv.rect(x + 60, y + 10, 66, 44, WHITE)
    cv.frame(x + 60, y + 10, 66, 44, INK)
    cv.rect(x + 66, y + 16, 54, 3, RED)
    for i in range(4):
        cv.rect(x + 66, y + 24 + i * 6, 54 - i * 8, 2, GREY)
    cv.poly([(x + 104, y + 44), (x + 118, y + 54), (x + 104, y + 54)], GOLD)
    flag(cv, x + 14, y + 12, 26, 16, "AU")
    cv.rect(x + 14, y + 34, 26, 16, (0, 110, 90))
    cv.disc(x + 27, y + 42, 3, GOLD_L)
    cv.disc(x + 20, y + 38, 1, WHITE)
    cv.disc(x + 33, y + 46, 1, WHITE)
    cv.line(x + 150, y + 58, x + 150, y + 30, (34, 110, 66), 2)
    for a in (-30, 0, 30):
        cv.line(x + 150, y + 32, x + 150 + int(14 * (a / 30.0)), y + 22 - abs(a) // 6,
                (34, 110, 66), 2)


def scene_ukenergy(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (250, 230, 190), (230, 200, 150))
    cv.rect(x + 16, y + 26, 52, 30, (190, 120, 70))
    cv.poly([(x + 10, y + 28), (x + 42, y + 8), (x + 74, y + 28)], (150, 60, 40))
    cv.rect(x + 36, y + 40, 12, 16, (60, 40, 30))
    for wxp in (22, 52):
        cv.rect(x + wxp, y + 32, 10, 10, (255, 240, 170))
    cv.poly([(x + 96, y + 12), (x + 84, y + 30), (x + 94, y + 30), (x + 84, y + 48),
             (x + 100, y + 26), (x + 90, y + 26)], (250, 200, 0))
    cv.rect(x + 120, y + 16, 52, 34, WHITE)
    cv.frame(x + 120, y + 16, 52, 34, INK)
    F["sans_b9"].draw(cv, x + 126, y + 28, "BILL", GREY)
    F["sans_b10"].draw(cv, x + 126, y + 44, "2,166", RED)


def scene_gaza(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (240, 210, 170), (200, 160, 110))
    base = y + 56
    for bx, bw, bh in ((8, 30, 26), (42, 22, 34), (68, 34, 20), (106, 26, 30)):
        cv.rect(x + bx, base - bh, bw, bh, (120, 105, 85))
        for wy in range(2):
            cv.rect(x + bx + 5 + wy * 9, base - bh + 6, 4, 5, (60, 50, 40))
    cv.rect(x + 150, base - 48, 10, 48, (100, 88, 72))
    cv.disc(x + 155, base - 48, 5, (100, 88, 72))
    cv.rect(x + 152, base - 32, 6, 5, (240, 190, 100))
    cv.poly([(x + 40, base), (x + 60, base - 14), (x + 90, base - 8), (x + 110, base)],
            (150, 130, 105))
    _smoke(cv, x + 70, base - 20, 3, (210, 190, 165))


def scene_ukraine(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (40, 40, 60), (20, 20, 34))
    for txp, th in ((16, 40), (48, 48), (86, 36), (120, 44)):
        cv.rect(x + txp, y + 56 - th, 16, th, (120, 120, 130))
        cv.rect(x + txp + 4, y + 52 - th, 8, 4, (90, 90, 100))
        cv.line(x + txp + 8, y + 52 - th, x + txp + 8, y + 44 - th, (200, 200, 200), 1)
    cv.rect(x + 140, y + 40, 30, 16, (150, 150, 160))
    cv.disc(x + 155, y + 48, 7, (90, 90, 100))
    _flame(cv, x + 56, y + 22, 24, 16, [(240, 90, 20), (250, 160, 40)])
    _flame(cv, x + 128, y + 24, 18, 13, [(240, 90, 20), (250, 160, 40)])
    _smoke(cv, x + 56, y + 6, 3, (70, 66, 60))
    cv.rect(x, y + 56, w, 10, (30, 28, 26))


def scene_bangladesh(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (250, 235, 200), (225, 200, 150))
    cv.rect(x + 12, y + 18, 70, 38, (180, 90, 60))
    cv.rect(x + 82, y + 6, 10, 50, (150, 70, 50))
    cv.rect(x + 78, y + 2, 18, 6, (150, 70, 50))
    for wxp in (20, 40, 60):
        cv.rect(x + wxp, y + 26, 12, 10, (255, 240, 170))
    cv.rect(x + 20, y + 42, 54, 4, (120, 60, 40))
    cv.line(x + 100, y + 14, x + 172, y + 14, (90, 70, 50), 1)
    for i, c in enumerate(((220, 60, 50), (40, 120, 180), (240, 180, 40), (40, 150, 90))):
        cv.rect(x + 106 + i * 17, y + 14, 14, 16, c)
    cv.rect(x + 118, y + 40, 52, 16, (0, 130, 70))
    F["sans_b9"].draw(cv, x + 124, y + 51, "17,000", WHITE)


def scene_sudan(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (250, 210, 150), (210, 160, 100))
    base = y + 56
    for bx, bw, bh in ((10, 34, 20), (50, 28, 26), (84, 36, 18)):
        cv.rect(x + bx, base - bh, bw, bh, (170, 140, 100))
        cv.poly([(x + bx - 2, base - bh), (x + bx + bw // 2, base - bh - 10),
                 (x + bx + bw + 2, base - bh)], (140, 90, 60))
    _flame(cv, x + 64, base - 26, 18, 16, [(240, 90, 20), (250, 160, 40)])
    _smoke(cv, x + 64, base - 42, 3, (90, 84, 76))
    cv.rect(x + 140, y + 12, 22, 6, (60, 60, 60))
    cv.rect(x + 146, y + 18, 10, 4, (60, 60, 60))
    cv.disc(x + 144, y + 15, 2, (30, 30, 30))
    cv.disc(x + 158, y + 15, 2, (30, 30, 30))
    cv.line(x + 140, y + 20, x + 132, y + 34, (120, 110, 100), 1)
    cv.line(x + 162, y + 20, x + 170, y + 34, (120, 110, 100), 1)


def scene_java(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (200, 220, 200), (120, 160, 110))
    cv.poly([(x, y + 66), (x + 40, y + 20), (x + 80, y + 66)], (60, 110, 70))
    cv.poly([(x + 90, y + 66), (x + 130, y + 26), (x + 170, y + 66)], (50, 100, 60))
    cv.rect(x + 70, y + 30, 44, 36, (40, 34, 28))
    cv.rect(x + 78, y + 38, 28, 28, (24, 60, 90))
    cv.vgrad(x + 78, y + 52, 28, 14, (60, 140, 190), (30, 90, 140))
    cv.rect(x + 66, y + 26, 52, 5, (90, 70, 50))
    cv.disc(x + 92, y + 24, 5, (240, 200, 40))
    cv.rect(x + 30, y + 50, 16, 10, (220, 160, 40))
    cv.rect(x + 34, y + 46, 8, 5, (220, 160, 40))
    for i in range(3):
        cv.rect(x + 130 + i * 14, y + 52 + (i % 2) * 4, 10, 6, (90, 70, 50))

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
    ("-6.2%", "Kospi close, worst in AI sell-off"),
    ("30+", "killed in Cairo tanker fire"),
    ("50,183", "Dow close, up 0.3%"),
    ("20%", "top US tariff rate, on China"),
    ("+26%", "UK energy price cap, January"),
    ("490,334", "Russian war dead, leaked data"),
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
    dict(n=5, place="SEOUL · TOKYO · TAIPEI", field="ASIA · MARKETS",
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


# ---------------------------------------------------------------- layout
def draw_page(cv):
    # top bar
    cv.rect(0, 0, W, 20, NAVY)
    F["sans_b10"].draw(cv, 28, 14, "THE WORLD IN ONE DAY", GOLD_L)
    right = "37 STORIES · 7 REGIONS · ALL FROM WEDNESDAY 25 NOVEMBER 2026"
    F["sans_b9"].draw(cv, 996 - F["sans_b9"].width(right), 14, right, WHITE)
    cv.rect(0, 20, W, 2, GOLD)

    # masthead
    title = "Wednesday 25 November 2026"
    tw = F["serif_b56"].width(title)
    assert tw <= 968, f"masthead too wide: {tw}"
    F["serif_b56"].draw(cv, 28, 24 + F["serif_b56"].ascent, title, INK)
    F["serif_i13"].draw(cv, 28, 96, SUBHEAD, RED)
    cv.hline(28, 104, 968, LINE)

    # region chips
    cx = 28
    for name, count, color in REGIONS:
        label = f"{name} {count}"
        w = F["sans_b9"].width(label) + 12
        cv.rrect(cx, 110, w, 16, 3, color)
        F["sans_b9"].draw(cv, cx + 6, 121, label, WHITE)
        cx += w + 6

    # UTC strip (drop the last beat if it would overflow)
    beats = list(TIMELINE)
    while True:
        parts = []
        for t, s in beats:
            parts.append((t, s))
        total = F["sans_b10"].width("THE DAY IN UTC") + 14
        for t, s in beats:
            total += F["sans_b10"].width(t) + 5 + F["sans_r10"].width(s) + 12
        if total <= 968 or len(beats) <= 5:
            break
        beats.pop()
    cv.rect(28, 134, 968, 22, NAVY)
    cx = 38
    cx = F["sans_b10"].draw(cv, cx, 149, "THE DAY IN UTC", GOLD_L) + 12
    for t, s in beats:
        cx = F["sans_b10"].draw(cv, cx, 149, t, GOLD_L) + 5
        cx = F["sans_r10"].draw(cv, cx, 149, s, WHITE) + 12

    # ---- heroes + numbers panel
    hy = 164
    hw = 258
    for i, hro in enumerate(HEROES):
        x = 28 + i * (hw + 8)
        cv.rect(x, hy, hw, 20, RED)
        cv.disc(x + 12, hy + 10, 8, WHITE)
        F["sans_b9"].draw_center(cv, x + 12, hy + 13, str(hro["n"]), RED)
        F["sans_b11"].draw(cv, x + 26, hy + 14, hro["place"], WHITE)
        cv.rect(x, hy + 20, hw, 2, GOLD)
        hro["scene"](cv, x, hy + 22, hw, 100)
        cv.frame(x, hy + 22, hw, 100, (120, 110, 90))
        # stat chip inside scene, top right
        chip(cv, x + hw - F["sans_b9"].width(hro["stat"]) - 14, hy + 26,
             hro["stat"], (20, 20, 20))
        ky = hy + 128
        F["sans_b9"].draw(cv, x, ky, hro["field"], RED)
        bw = badge(cv, x + hw - F["sans_b9"].width(hro["status"]) - 10, ky - 3,
                   hro["status"])
        hl = wrap(hro["headline"], F["serif_b20"], hw)
        assert len(hl) <= 2, f"hero headline too long: {hro['headline']}"
        draw_lines(cv, F["serif_b20"], x, ky + 14, hl, INK, 22)
        dl = wrap(hro["deck"], F["serif_r12"], hw)
        assert len(dl) <= 2, f"hero deck too long: {hro['deck']}"
        draw_lines(cv, F["serif_r12"], x, ky + 60, dl, INK, 14)
        # label sits below the LAST deck line, computed from real metrics:
        # deck last baseline + deck descent + label ascent + 4px clear gap
        last_base = ky + 60 + (len(dl) - 1) * 14 + F["serif_r12"].ascent
        wy = (last_base + F["serif_r12"].descent
              + F["sans_b9"].ascent + 4)
        F["sans_b9"].draw(cv, x, wy, "WHY IT MATTERS", RED)
        wl = wrap(hro["why"], F["serif_i11"], hw)
        assert len(wl) <= 1, f"hero why too long: {hro['why']}"
        draw_lines(cv, F["serif_i11"], x, wy + 12, wl, INK, 13)
        F["sans_r8"].draw(cv, x, hy + 272, hro["source"], GREY)

    # numbers panel (hero row only)
    px, py, pw, ph = 830, 164, 166, 276
    cv.rect(px, py, pw, ph, NAVY)
    cv.rect(px, py, pw, 3, GOLD)
    F["sans_b10"].draw(cv, px + 12, py + 18, "THE DAY IN NUMBERS", GOLD_L)
    cv.hline(px + 12, py + 26, pw - 24, (80, 90, 120))
    for i, (num, cap) in enumerate(NUMBERS):
        iy = py + 34 + i * 40
        F["serif_b22"].draw(cv, px + 12, iy + 20, num, GOLD_L)
        cl = wrap(cap, F["sans_r8"], pw - 24)
        assert len(cl) <= 1, f"number caption too long: {cap}"
        F["sans_r8"].draw(cv, px + 12, iy + 34, cl[0], WHITE)
        if i:
            cv.hline(px + 12, iy - 5, pw - 24, (80, 90, 120))

    # ---- mids: two uniform rows of five
    mw = 185
    for row in range(2):
        for col in range(5):
            m = MIDS[row * 5 + col]
            x = 28 + col * 194
            y = 446 + row * 156
            m["scene"](cv, x, y, mw, 66)
            cv.frame(x, y, mw, 66, (120, 110, 90))
            chip(cv, x + mw - F["sans_b9"].width(m["stat"]) - 12, y + 4,
                 m["stat"], (20, 20, 20))
            num_circle(cv, x + 11, y + 11, m["n"], 7)
            py2 = y + 68
            F["sans_b9"].draw(cv, x, py2, m["place"], RED)
            badge(cv, x + mw - F["sans_b9"].width(m["status"]) - 10, py2 - 3,
                  m["status"])
            F["sans_b9"].draw(cv, x, py2 + 11, m["field"], GREY)
            hl = wrap(m["headline"], F["serif_b15"], mw)
            assert len(hl) <= 2, f"mid headline too long: {m['headline']}"
            draw_lines(cv, F["serif_b15"], x, py2 + 24, hl, INK, 16)
            dl = wrap(m["deck"], F["serif_r11"], mw)
            assert len(dl) <= 2, f"mid deck too long: {m['deck']}"
            draw_lines(cv, F["serif_r11"], x, py2 + 55, dl, INK, 12)

    # ---- bottom: map + briefs
    by = 762
    F["sans_b11"].draw(cv, 28, by + 11, "ALSO ON WEDNESDAY 25 NOVEMBER", RED)
    F["sans_b11"].draw(cv, 428, by + 11, "WHERE IT HAPPENED", NAVY)
    cap = "numbered pins = stories 1-13 · dots = briefs 14-37"
    F["sans_r9"].draw(cv, 996 - F["sans_r9"].width(cap), by + 11, cap, GREY)
    cv.hline(28, by + 16, 968, LINE)
    draw_map(cv, 28, 778, 380, 172, PINS)
    draw_brief_dots(cv, 28, 778, 380, 172,
                    [(n, lon, lat) for n, _, _, _, lon, lat in BRIEFS])

    col_w = 278
    for k, (n, place, flg, text, lon, lat) in enumerate(BRIEFS):
        col = 0 if k < 12 else 1
        j = k if k < 12 else k - 12
        bx = 428 + col * 288
        byy = 778 + j * 15
        cv.rrect(bx, byy, 16, 11, 2, RED)
        F["sans_b9"].draw_center(cv, bx + 8, byy + 9, str(n), WHITE)
        flag(cv, bx + 20, byy + 1, 14, 10, flg)
        tx = bx + 38
        full = place + ": " + text
        lines = wrap(full, F["sans_r9"], col_w - 38)
        assert len(lines) <= 1, f"brief too long for one line: {full}"
        # bold the place on the first line
        F["sans_b9"].draw(cv, tx, byy + 9, place + ":", RED)
        rest_w = F["sans_b9"].width(place + ": ")
        first = lines[0][len(place) + 2:]
        F["sans_r9"].draw(cv, tx + rest_w, byy + 9, first, INK)
        if len(lines) > 1:
            F["sans_r9"].draw(cv, tx, byy + 20, lines[1], INK)

    # ---- date check + footer
    dy = 960
    cv.frame(28, dy, 968, 40, RED, 2)
    cv.rect(28, dy, 96, 40, RED)
    F["sans_b11"].draw_center(cv, 76, dy + 17, "DATE CHECK", WHITE)
    F["sans_b11"].draw_center(cv, 76, dy + 31, "25 NOV 2026", WHITE)
    dl = wrap(DATE_CHECK, F["serif_r11"], 968 - 116)
    assert len(dl) <= 2, "date check too long"
    draw_lines(cv, F["serif_r11"], 136, dy + 15, dl, INK, 14)
    fl = wrap(FOOTER, F["sans_r8"], 968)
    assert len(fl) <= 2, "footer too long"
    draw_lines(cv, F["sans_r8"], 28, dy + 52, fl, GREY, 10)


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
