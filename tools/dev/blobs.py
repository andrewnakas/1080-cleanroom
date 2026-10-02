"""DEV (dirty): render raw blobs as images to find uncatalogued pictures.
   python tools/dev/blobs.py <rom> <out.png> file:off:len:fmt:w[:fold] ..."""
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, ".")
sys.path.insert(0, "tools/dev")
from games.ten80 import usofile


from render import render  # noqa


rom = open(sys.argv[1], "rb").read()
files = usofile.load(rom)
tiles = []
for spec in sys.argv[3:]:
    p = spec.split(":")
    u = files[p[0]]
    buf = u.data or u.binary
    off, n = int(p[1], 16), int(p[2], 16)
    im = render(buf[off:off + n], p[3], int(p[4]))
    fold = int(p[5]) if len(p) > 5 else 400
    cols = [im[i:i + fold] for i in range(0, len(im), fold)]
    cols = [np.pad(c, ((0, fold - len(c)), (0, 4), (0, 0))) for c in cols]
    tiles.append((spec, np.concatenate(cols, 1)))
W = 1800
x = y = rowh = 0
pos = []
for s, t in tiles:
    if x + t.shape[1] > W:
        x, y, rowh = 0, y + rowh + 14, 0
    pos.append((x, y))
    x += t.shape[1] + 8
    rowh = max(rowh, t.shape[0])
sheet = Image.new("RGB", (W, y + rowh + 14), (40, 40, 60))
d = ImageDraw.Draw(sheet)
for (s, t), (x, y) in zip(tiles, pos):
    sheet.paste(Image.fromarray(t), (x, y + 12))
    d.text((x, y), s[:t.shape[1] // 6 + 8], fill=(255, 255, 0))
sheet.save(sys.argv[2])
print(sheet.size)
