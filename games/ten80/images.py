"""Catalog of every image in the ROM file system: where it is, its size and pixel format.

Sources of the layout facts:
  * material tag lists in USO Data (tag 0xCB: flags, pointer, width, height, wrap, ...),
  * `flowimgs.bin` records (name[8], 1, width, height, 2, flags, 4, byte size, pixels),
  * palette descriptors {0x110, 0x100, ->indices, ->palette} (backgrounds, select screens),
  * MANUAL: blobs the code draws directly (sizes found by looking at them once, dev only).

flags: 0x110 = RGBA16, 0x120 = RGBA32, 0x408 = 8-bit intensity.

Record: dict(key, file, sec ("data"|"binary"), off, w, h, fmt, [pal], [name]).
    python -m games.ten80.images <rom>      one-screen summary
"""
import struct
import sys

from . import usofile

FLAGS = {0x110: "rgba16", 0x120: "rgba32", 0x408: "i8"}
BPP = {"rgba16": 2, "rgba32": 4, "i8": 1, "ci8": 1, "i4": 0.5, "ia8": 1}

# file -> [(offset, w, h, fmt)]  (code-drawn images: no descriptor in the data)
MANUAL = {
    "effects.uso": [(0x8, 64, 64, "i8"), (0x1010, 64, 64, "i8"), (0x2018, 64, 64, "i8"), (0x3028, 64, 64, "i8"),
                    (0x4078, 64, 64, "i8"), (0x5080, 32, 32, "i8"), (0x5488, 64, 64, "i8"), (0x6490, 64, 64, "i8"),
                    (0x7498, 64, 64, "i8")],
}
CI_WIDTH = {0x9000: 384, 0x10000: 256}


def size(r):
    return int(r["w"] * r["h"] * BPP[r["fmt"]])


def materials(u):
    d, out = u.data, {}
    for o in range(0, len(d) - 0x20, 4):
        w = struct.unpack_from(">7I", d, o)
        if w[0] != 0xCB or o + 8 not in u.rel or not (0 < w[3] <= 0x200 and 0 < w[4] <= 0x200) or w[1] not in FLAGS:
            continue
        t = u.target(o + 8)
        if t is None:
            continue
        r = dict(file=u.name, sec="data", off=t, w=w[3], h=w[4], fmt=FLAGS[w[1]])
        if t + size(r) <= len(d):
            out[t] = r
    return list(out.values())


def palettes(u):
    """{0x110, 0x100, ->pixels, ->palette}: CI8 picture + 256 RGBA16 colours."""
    d, out = u.data, []
    for o in range(0, len(d) - 15, 4):
        if d[o:o + 8] == b"\0\0\x01\x10\0\0\x01\0" and o + 8 in u.rel and o + 12 in u.rel:
            t, p = u.target(o + 8), u.target(o + 12)
            n = u.blob_end(t) - t
            if t is None or p is None or n not in CI_WIDTH:
                continue
            w = CI_WIDTH[n]
            out.append(dict(file=u.name, sec="data", off=t, w=w, h=n // w, fmt="ci8", pal=p))
    return out


def flowimgs(u):
    b, out, o, seen = u.binary, [], 0, {}
    while o < len(b) - 28:
        n, w, h, f, flg, four, ds = struct.unpack_from(">7I", b, o)
        if four == 4 and n == 1 and f == 2 and flg in FLAGS and 0 < w <= 640 and 0 < h <= 480 and \
                ds == w * h * BPP[FLAGS[flg]]:
            name = b[o - 8:o].split(b"\0")[0].decode("ascii", "replace")
            k = seen[name] = seen.get(name, -1) + 1
            out.append(dict(file=u.name, sec="binary", off=o + 28, w=w, h=h, fmt=FLAGS[flg],
                            name=name + (".%d" % k if k else "")))
            o += 28 + ds
        else:
            o += 1
    return out


def catalog(rom, files=None):
    files = files or usofile.load(rom)
    out = []
    for name, u in files.items():
        recs = []
        if u.data and u.rel:
            recs += materials(u) + palettes(u)
        if name == "flowimgs.bin":
            recs += flowimgs(u)
        for off, w, h, fmt in MANUAL.get(name, ()):
            recs.append(dict(file=name, sec="data", off=off, w=w, h=h, fmt=fmt))
        recs.sort(key=lambda r: r["off"])
        end = 0
        for r in recs:
            assert r["off"] >= end, (name, hex(r["off"]), "overlaps")
            end = r["off"] + size(r)
            r["key"] = "%s@%X" % (name.split(".")[0], r["off"])
        out += recs
    return out


def main(argv):
    rom = open(argv[1], "rb").read()
    cat = catalog(rom)
    by = {}
    for r in cat:
        e = by.setdefault(r["file"], [0, 0])
        e[0] += 1
        e[1] += size(r) + (0x200 if "pal" in r else 0)
    fm = {}
    for r in cat:
        fm[r["fmt"]] = fm.get(r["fmt"], 0) + 1
    print(f"{len(cat)} images, {sum(e[1] for e in by.values())} bytes; formats {fm}")
    print(" ".join(f"{n.split('.')[0]}:{e[0]}" for n, e in by.items()))


if __name__ == "__main__":
    main(sys.argv)
