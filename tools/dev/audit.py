"""DEV (dirty): list Data/Binary blobs that the image catalog does not cover and that do not look like
geometry / display lists / pointer tables.   python tools/dev/audit.py <retail rom> [min bytes]"""
import struct
import sys

import numpy as np

sys.path.insert(0, ".")
from games.ten80 import images, usofile

GFX = set(range(0xB0, 0xC0)) | set(range(0xE4, 0x100)) | {1, 3, 4, 6, 0xAF, 0xB1}


def guess(b, nrel):
    n = len(b)
    a = np.frombuffer(b, np.uint8)
    if not a.any():
        return "zero"
    if nrel * 16 > n:
        return "ptrs"
    if n % 16 == 0 and n >= 32:
        v = a.reshape(-1, 16)
        if (v[:, 6] == 0).mean() > 0.9 and (v[:, 7] == 0).mean() > 0.9:
            return "vtx"
    if n % 8 == 0:
        ops = a.reshape(-1, 8)[:, 0]
        if np.isin(ops, list(GFX)).mean() > 0.8:
            return "gfx"
    if n % 4 == 0:
        w = np.frombuffer(b, ">u4")
        ex = (w >> 23) & 0xFF
        if (((ex > 100) & (ex < 150)) | (w == 0)).mean() > 0.85:
            return "float"
    h = np.bincount(a, minlength=256) / n
    ent = -(h[h > 0] * np.log2(h[h > 0])).sum()
    return "?%.1f z%d%%" % (ent, 100 * (a == 0).mean())


def main():
    rom = open(sys.argv[1], "rb").read()
    mn = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x100
    files = usofile.load(rom)
    cat = images.catalog(rom, files)
    tot = 0
    for name, u in files.items():
        if name.startswith("audio_"):
            continue
        for sec, buf in (("data", u.data), ("binary", u.binary)):
            if not buf:
                continue
            cov = np.zeros(len(buf), bool)
            for r in cat:
                if r["file"] == name and r["sec"] == sec:
                    cov[r["off"]:r["off"] + images.size(r)] = True
                    if "pal" in r:
                        cov[r["pal"]:r["pal"] + 0x200] = True
            vals = u.vals if sec == "data" else [0, len(buf)]
            rel = sorted(u.rel) if sec == "data" else []
            out = []
            for a, b in zip(vals, vals[1:]):
                # split blob at covered runs
                un = np.nonzero(~cov[a:b])[0]
                if len(un) < mn:
                    continue
                runs = np.split(un, np.nonzero(np.diff(un) > 1)[0] + 1)
                for r in runs:
                    s, e = a + int(r[0]), a + int(r[-1]) + 1
                    if e - s < mn:
                        continue
                    g = guess(buf[s:e], sum(1 for o in rel if s <= o < e))
                    if g[0] == "?":
                        out.append("%X+%X %s" % (s, e - s, g))
                        tot += e - s
            if out:
                print("%-16s %s %6X/%6X uncovered | %s" % (name, sec[0], int((~cov).sum()), len(buf), "; ".join(out)[:400]))
    print("unknown bytes", tot)


main()
