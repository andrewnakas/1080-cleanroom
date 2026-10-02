"""DEV (dirty): symbol-bounded blobs of a file with a row-stride estimate (bytes per row).
   python tools/dev/stride.py <rom> <file> [min]"""
import struct
import sys

import numpy as np

sys.path.insert(0, ".")
from games.ten80 import images, usofile


def stride(b, nib=False):
    a = np.frombuffer(b, np.uint8).astype(np.int32)
    if nib:
        a = np.stack([a >> 4, a & 15], 1).reshape(-1)
    if len(a) < 64:
        return ""
    base = np.abs(a[1:] - a[:-1]).mean() + 1e-6
    out = []
    for s in range(4, min(len(a) // 3, 400)):
        out.append((np.abs(a[s:] - a[:-s]).mean() / base, s))
    out.sort()
    return " ".join("%d:%.2f" % (s, v) for v, s in out[:4])


def main():
    rom = open(sys.argv[1], "rb").read()
    u = usofile.load(rom)[sys.argv[2]]
    mn = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x80
    buf = u.data or u.binary
    vals = u.vals if u.data else [0, len(buf)]
    rel = sorted(u.rel)
    for a, b in zip(vals, vals[1:]):
        if b - a < mn:
            continue
        blob = buf[a:b]
        nrel = sum(1 for o in rel if a <= o < b)
        z = 100 * blob.count(0) // len(blob)
        print("%6X +%5X rel%3d z%2d%% head %s | i8 %s | i4 %s" % (a, b - a, nrel, z, blob[:12].hex(), stride(blob), stride(blob, True)))


main()
