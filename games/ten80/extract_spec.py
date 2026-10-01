"""DIRTY ROOM: read the retail ROM and write the kept facts of every catalogued image.

    python -m games.ten80.extract_spec <retail rom> [spec dir]

Kept per image (user scope): file/offset/format/size (layout), a 4x4 colour grid (16x16 for
pictures of 128 px or more) and the 2-bit alpha outline. For 8-bit intensity images the
intensity is the coverage, so its 2-bit outline is kept as the alpha.  No texels are written.
"""
import json
import os
import sys

import numpy as np

from cleanroom.decomp import spec as cspec

from . import images, usofile


def decode(rec, buf, pal=None):
    w, h, f = rec["w"], rec["h"], rec["fmt"]
    n = images.size(rec)
    b = buf[rec["off"]:rec["off"] + n]
    if f == "rgba16":
        a = np.frombuffer(b, ">u2").reshape(h, w)
        c = [((a >> s) & 31).astype(np.float32) * (255.0 / 31) for s in (11, 6, 1)]
        return np.stack(c + [(a & 1).astype(np.float32) * 255], -1)
    if f == "rgba32":
        return np.frombuffer(b, np.uint8).reshape(h, w, 4).astype(np.float32)
    if f == "i8":
        a = np.frombuffer(b, np.uint8).reshape(h, w).astype(np.float32)
        return np.stack([a, a, a, a], -1)
    if f == "ci8":
        p = np.frombuffer(pal, ">u2")
        a = p[np.frombuffer(b, np.uint8)].reshape(h, w)
        c = [((a >> s) & 31).astype(np.float32) * (255.0 / 31) for s in (11, 6, 1)]
        return np.stack(c + [(a & 1).astype(np.float32) * 255], -1)
    raise ValueError(f)


def payload(u, rec):
    return u.data if rec["sec"] == "data" else u.binary


def fact(rec, rgba):
    n = 16 if max(rec["w"], rec["h"]) >= 128 else 4
    d = {k: rec[k] for k in ("file", "sec", "off", "w", "h", "fmt") if k in rec}
    for k in ("pal", "name"):
        if k in rec:
            d[k] = rec[k]
    d["grid"] = cspec.grid(rgba, n)
    if (rgba[..., 3] < 250).any():
        d["alpha2"] = cspec.alpha2(rgba[..., 3])
    return d


def main(argv):
    rom = open(argv[1], "rb").read()
    out = argv[2] if len(argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec")
    os.makedirs(out, exist_ok=True)
    files = usofile.load(rom)
    cat = images.catalog(rom, files)
    spec = {}
    for r in cat:
        buf = payload(files[r["file"]], r)
        pal = buf[r["pal"]:r["pal"] + 0x200] if "pal" in r else None
        spec[r["key"]] = fact(r, decode(r, buf, pal))
    with open(os.path.join(out, "textures.json"), "w") as f:
        json.dump(spec, f, separators=(",", ":"))
    alpha = sum(1 for d in spec.values() if "alpha2" in d)
    print(f"spec: {len(spec)} images ({alpha} with alpha outline) -> {out}/textures.json "
          f"({os.path.getsize(os.path.join(out, 'textures.json')) // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv)
