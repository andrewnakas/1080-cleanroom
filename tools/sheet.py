"""Contact sheet of shot_*.png in a folder -> sheet.png (3 per row)."""
import glob
import os
import sys

from PIL import Image

d = sys.argv[1]
fs = sorted(glob.glob(os.path.join(d, "shot_*.png")), key=lambda f: float(os.path.basename(f)[5:-4]))
ims = [Image.open(f).convert("RGB").crop((0, 0, 960, 600)) for f in fs]
cols = int(sys.argv[2]) if len(sys.argv) > 2 else 3
w, h = 480, 300
sheet = Image.new("RGB", (w * cols, h * ((len(ims) + cols - 1) // cols)))
for i, im in enumerate(ims):
    sheet.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
sheet.save(os.path.join(d, "sheet.png"))
print(len(ims), "shots ->", os.path.join(d, "sheet.png"))
