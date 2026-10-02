"""DEV (dirty): contact sheet of catalogued images of one file, native size, with key labels.
   python tools/dev/flowsheet.py <rom> <out.png> <file> <filter: text|colour|j|all> [zoom]"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, ".")
from games.ten80 import extract_spec, images, usofile

rom = open(sys.argv[1], "rb").read()
files = usofile.load(rom)
cat = [r for r in images.catalog(rom, files) if r["file"] == sys.argv[3]]
flt = sys.argv[4]
z = int(sys.argv[5]) if len(sys.argv) > 5 else 1
tiles = []
for i, r in enumerate(cat):
    nm = r.get("name", r["key"])
    isj = nm.startswith("j_")
    txt = r["fmt"] == "i8"
    if (flt == "text" and (isj or not txt)) or (flt == "colour" and (isj or txt)) or (flt == "j" and not isj):
        continue
    buf = extract_spec.payload(files[r["file"]], r)
    pal = buf[r["pal"]:r["pal"] + 0x200] if "pal" in r else None
    im = extract_spec.decode(r, buf, pal)
    a = im[..., 3:] / 255.0
    rgb = im[..., :3] * a + np.array([60, 30, 90]) * (1 - a) if not txt else im[..., :3]
    t = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    if z > 1:
        t = t.resize((t.width * z, t.height * z), Image.NEAREST)
    tiles.append(("%d %s" % (i, nm), t))
W, x, y, rh = 1800, 0, 0, 0
pos = []
for l, t in tiles:
    tw = max(t.width, 6 * len(l)) + 6
    if x + tw > W:
        x, y, rh = 0, y + rh + 14, 0
    pos.append((x, y))
    x += tw
    rh = max(rh, t.height)
s = Image.new("RGB", (W, y + rh + 14), (25, 25, 60))
d = ImageDraw.Draw(s)
for (l, t), (x, y) in zip(tiles, pos):
    d.text((x, y), l, fill=(255, 255, 0))
    s.paste(t, (x, y + 11))
s.save(sys.argv[2])
print(len(tiles), s.size)
