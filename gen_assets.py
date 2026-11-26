#!/usr/bin/env python3
"""Build-time glyph-atlas generator for the news-image-20261125 entry.

Renders Liberation fonts (system-installed, never downloaded) into
anti-aliased 8-bit grayscale glyph atlases and packs them as a
zlib+base64 blob in assets_blob.py.

Each glyph is rasterised at SS x its target size with PIL (which draws
with grayscale anti-aliasing) and then box-downsampled to the exact
target ink box. The stored atlas is therefore a true coverage map:
0 = no ink, 255 = solid ink, values between = smooth edge. The runtime
blends with that coverage, so letterforms print like real newspaper
type instead of the jagged 1-bit stamps an earlier version used.

This file runs ONLY at build time. The runtime entry (main.py) is pure
Python stdlib and never imports PIL.
"""
import base64
import json
import zlib

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/liberation/"

# (atlas name, font file, pixel size)
SPECS = [
    ("serif_b56", "LiberationSerif-Bold.ttf", 56),
    ("serif_b22", "LiberationSerif-Bold.ttf", 22),
    ("serif_b20", "LiberationSerif-Bold.ttf", 20),
    ("serif_b15", "LiberationSerif-Bold.ttf", 15),
    ("serif_r12", "LiberationSerif-Regular.ttf", 12),
    ("serif_r11", "LiberationSerif-Regular.ttf", 11),
    ("serif_i13", "LiberationSerif-Italic.ttf", 13),
    ("serif_i11", "LiberationSerif-Italic.ttf", 11),
    ("sans_b11", "LiberationSans-Bold.ttf", 11),
    ("sans_b10", "LiberationSans-Bold.ttf", 10),
    ("sans_b9", "LiberationSans-Bold.ttf", 9),
    ("sans_b8", "LiberationSans-Bold.ttf", 8),
    ("sans_r10", "LiberationSans-Regular.ttf", 10),
    ("sans_r9", "LiberationSans-Regular.ttf", 9),
    ("sans_r8", "LiberationSans-Regular.ttf", 8),
]

# Every character the page ever draws: printable ASCII plus the few extras
# used in the layout (em dash, en dash, minus, middot, pound, times, degree).
CHARS = "".join(chr(c) for c in range(32, 127)) + "\u2014\u2013\u2212\u00b7\u00a3\u00d7\u00b0"

PAD = 2
SS = 4  # supersample factor for glyph rasterisation


def build_atlas(name, path, size):
    font = ImageFont.truetype(FONT_DIR + path, size)
    font_big = ImageFont.truetype(FONT_DIR + path, size * SS)
    ascent, descent = font.getmetrics()
    cells = []
    renders = []
    max_w = 0
    max_h = 0
    for ch in CHARS:
        # Target-size metrics drive the layout, exactly as before: the
        # advance and the ink box (relative to the left-baseline pen
        # point, "ls" anchor) are taken from the target-size font so no
        # line breaks or positions move.
        bb = font.getbbox(ch, anchor="ls")
        adv = int(round(font.getlength(ch)))
        iw = bb[2] - bb[0]
        ih = bb[3] - bb[1]
        ink = None
        if iw > 0 and ih > 0:
            bb4 = font_big.getbbox(ch, anchor="ls")
            iw4 = bb4[2] - bb4[0]
            ih4 = bb4[3] - bb4[1]
            if iw4 > 0 and ih4 > 0:
                tmp = Image.new("L", (iw4 + 8, ih4 + 8), 0)
                td = ImageDraw.Draw(tmp)
                # pen at (4-bx, 4-by) puts the ink box top-left at (4, 4).
                td.text((4 - bb4[0], 4 - bb4[1]), ch, font=font_big,
                        fill=255, anchor="ls")
                ink = tmp.crop((4, 4, 4 + iw4, 4 + ih4))
                ink = ink.resize((iw, ih), Image.BOX)
        if ink is None:
            cells.append((0, 0, adv, 0, 0))
            renders.append(None)
            continue
        max_w = max(max_w, iw)
        max_h = max(max_h, ih)
        cells.append((iw, ih, adv, bb[0], bb[1]))
        renders.append(ink)
    # Lay glyphs out in a grid: columns sized to the widest glyph.
    cols = 16
    cell_w = max_w + 2 * PAD
    cell_h = max_h + 2 * PAD
    rows = (len(CHARS) + cols - 1) // cols
    atlas = Image.new("L", (cols * cell_w, rows * cell_h), 0)
    glyphs = []
    for i, ch in enumerate(CHARS):
        w, h, adv, bx, by = cells[i]
        cx = (i % cols) * cell_w
        cy = (i // cols) * cell_h
        if renders[i] is not None:
            atlas.paste(renders[i], (cx + PAD, cy + PAD))
        # (atlas x, atlas y, w, h, advance, bearing-x, bearing-y rel. baseline)
        glyphs.append([cx + PAD, cy + PAD, w, h, adv, bx, by])
    raw = atlas.tobytes()
    blob = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
    return {
        "w": atlas.width,
        "h": atlas.height,
        "ascent": ascent,
        "descent": descent,
        "size": size,
        "cell_w": cell_w,
        "cell_h": cell_h,
        "pad": PAD,
        "blob": blob,
        "glyphs": glyphs,
    }


def main():
    fonts = {}
    for name, path, size in SPECS:
        fonts[name] = build_atlas(name, path, size)
        print(f"{name}: {fonts[name]['w']}x{fonts[name]['h']} "
              f"blob {len(fonts[name]['blob'])} chars")
    payload = {"chars": CHARS, "fonts": fonts}
    text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    comp = base64.b64encode(zlib.compress(text.encode("utf-8"), 9)).decode("ascii")
    out = (
        "# Generated by gen_assets.py (build time, PIL + system Liberation fonts).\n"
        "# Atlases are 8-bit grayscale coverage maps (supersampled, anti-aliased).\n"
        "# Runtime entry (main.py) is pure Python stdlib and decodes this blob.\n"
        "BLOB = (\n"
    )
    for i in range(0, len(comp), 76):
        out += f"    {comp[i:i + 76]!r}\n"
    out += ")\n"
    with open("assets_blob.py", "w") as fh:
        fh.write(out)
    print(f"assets_blob.py written: {len(out)} bytes, blob {len(comp)} chars")


if __name__ == "__main__":
    main()
