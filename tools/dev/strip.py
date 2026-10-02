"""DEV (dirty): one blob as a zoomed strip with offset ticks.
   python tools/dev/strip.py <rom> <out.png> <file> <off> <len> <fmt> <w> [rows per column] [zoom]"""
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, ".")
sys.argv_saved = sys.argv
from games.ten80 import usofile
import importlib.util
spec = importlib.util.spec_from_file_location("blobs_r", "tools/dev/render.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

a = sys.argv
rom = open(a[1], "rb").read()
u = usofile.load(rom)[a[3]]
buf = u.data or u.binary
off, n, fmt, w = int(a[4], 16), int(a[5], 16), a[6], int(a[7])
fold = int(a[8]) if len(a) > 8 else 256
z = int(a[9]) if len(a) > 9 else 2
im = m.render(buf[off:off + n], fmt, w)
bpr = {"i8": w, "i4": w // 2, "ia4": w // 2, "i1": w // 8, "rgba16": w * 2}[fmt]
ncol = (len(im) + fold - 1) // fold
cw = w * z + 60
sheet = Image.new("RGB", (cw * ncol, fold * z + 4), (30, 30, 70))
d = ImageDraw.Draw(sheet)
for c in range(ncol):
    part = im[c * fold:(c + 1) * fold]
    sheet.paste(Image.fromarray(part).resize((w * z, len(part) * z), Image.NEAREST), (c * cw + 56, 0))
    for r in range(0, len(part), 16):
        d.text((c * cw, r * z - 1), "%X" % (off + (c * fold + r) * bpr), fill=(255, 255, 0) if r % 32 == 0 else (150, 150, 90))
sheet.save(a[2])
print(sheet.size)
