"""Build the clean ROM: kept facts (code, geometry, parameters, sequences) + regenerated images
(and, with audio.py, regenerated samples).

    python -m games.ten80.generate <retail rom> <out.z64> [--no-audio] [--spec dir]

The retail ROM supplies only the kept parts; every catalogued image is written from
spec/textures.json (+ our own drawings in drawn.py).  Sections keep their ROM slots: Yay0
sections are re-compressed with our encoder and must fit (detail noise is reduced until they do).
"""
import hashlib
import json
import os
import struct
import sys

import numpy as np

from cleanroom.decomp import gen

from . import images, romfs, usofile, yay0

HERE = os.path.dirname(os.path.abspath(__file__))
RETAIL_SHA1 = "79cd1166c365e5809dec9b62e6d40d6032d5db3a"


def blur(a, k=1):
    """Small box blur (edge-replicated) on a 2-D float array."""
    for _ in range(k):
        p = np.pad(a, 1, mode="edge")
        a = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] + 4 * p[1:-1, 1:-1]) / 8.0
    return a


def base_image(key, d, scale=1.0):
    """RGBA float image from the kept grid + outline, with our own noise detail."""
    w, h = d["w"], d["h"]
    n = int(round(len(d["grid"]) ** 0.5))
    rgba = gen.upsample_grid(d["grid"], n, w, h)
    if scale > 0:
        amount = (0.03 if n > 4 else 0.07) * scale
        rgba[..., :3] *= gen.detail(gen.h32("detail", key), w, h, amount, 4.0 if n == 4 else 8.0)[..., None]
    if "alpha2" in d:
        rgba[..., 3] = gen.unpack_alpha2(d["alpha2"], w, h)
    else:
        rgba[..., 3] = 255
    return np.clip(rgba, 0, 255)


def enc_rgba16(img):
    r, g, b = [(np.clip(img[..., i], 0, 255) * (31 / 255.0) + 0.5).astype(np.uint16) for i in range(3)]
    a = (img[..., 3] >= 128).astype(np.uint16)
    return ((r << 11) | (g << 6) | (b << 1) | a).astype(">u2").tobytes()


def enc_ci8(img):
    """Our own palette (median cut) + indices; palette entries are opaque RGBA16."""
    from PIL import Image
    rgb = (np.clip(img[..., :3], 0, 255).astype(np.uint8) & 0xF8)
    q = Image.fromarray(rgb, "RGB").quantize(256, method=Image.MEDIANCUT, dither=Image.NONE)
    flat = (q.getpalette() or [])[:768]
    pal = np.array(flat + [0] * (768 - len(flat)), np.uint8).reshape(256, 3).astype(np.uint16) >> 3
    pal16 = ((pal[:, 0] << 11) | (pal[:, 1] << 6) | (pal[:, 2] << 1) | 1).astype(">u2").tobytes()
    return np.asarray(q, np.uint8).tobytes(), pal16


def encode(key, d, img):
    f = d["fmt"]
    if f == "rgba16":
        return enc_rgba16(img), None
    if f == "rgba32":
        return np.clip(img + 0.5, 0, 255).astype(np.uint8).tobytes(), None
    if f == "i8":
        return np.clip(img[..., 0] + 0.5, 0, 255).astype(np.uint8).tobytes(), None
    if f == "ci8":
        return enc_ci8(img)
    raise ValueError(f)


def render(key, d, scale, hooks):
    if key in hooks:
        img = hooks[key](key, d)
        if img is not None:
            return np.asarray(img, np.float32)
    img = base_image(key, d, scale)
    if d["fmt"] == "i8":
        # intensity pictures are their own coverage: the kept outline carries the shape
        if "alpha2" in d:
            lum = float(np.max(np.asarray(d["grid"], np.float32)[:, :3]))
            a = blur(img[..., 3]) * (max(lum, 160.0) / 255.0)
        else:
            a = img[..., :3].mean(-1)
        img = np.stack([a, a, a, a], -1)
    return img


def write_file(payload, recs, spec, scale, hooks):
    for key in recs:
        d = spec[key]
        img = render(key, d, scale, hooks)
        pix, pal = encode(key, d, img)
        assert len(pix) == images.size(d), key
        payload[d["off"]:d["off"] + len(pix)] = pix
        if pal is not None:
            payload[d["pal"]:d["pal"] + 0x200] = pal


def build(retail, spec, hooks=None, log=print):
    hooks = hooks or {}
    rom = bytearray(retail)
    secs = romfs.files(retail)
    by_file = {}
    for key, d in spec.items():
        by_file.setdefault((d["file"], d["sec"]), []).append(key)
    stats = dict(images=0, files=0, squeezed=[])
    for (name, sec), keys in by_file.items():
        s = [x for x in secs[name] if x.type == (6 if sec == "data" else 12)][0]
        orig = romfs.payload(retail, s)
        for scale in (1.0, 0.5, 0.25, 0.0):
            payload = bytearray(orig)
            write_file(payload, keys, spec, scale, hooks)
            if not s.yay0:
                out = bytes(payload)
                break
            out = yay0.encode(bytes(payload))
            if len(out) <= s.size:
                break
        else:
            raise SystemExit(f"{name}: regenerated data does not fit its slot ({len(out)} > {s.size})")
        if scale != 1.0:
            stats["squeezed"].append(f"{name}:{scale}")
        rom[s.data_off:s.data_off + s.size] = out + bytes(s.size - len(out))
        stats["images"] += len(keys)
        stats["files"] += 1
    return rom, stats


def fix_crc(rom):
    """N64 header checksum (CIC-6103, the chip this cartridge uses)."""
    seed = 0xA3886759
    t1 = t2 = t3 = t4 = t5 = t6 = seed
    data = np.frombuffer(bytes(rom[0x1000:0x101000]), ">u4").astype(np.uint64)
    M = 0xFFFFFFFF
    for d in data.tolist():
        if (t6 + d) & M < t6:
            t4 = (t4 + 1) & M
        t6 = (t6 + d) & M
        t3 ^= d
        r = ((d << (d & 31)) | (d >> (32 - (d & 31)))) & M
        t5 = (t5 + r) & M
        if t2 > d:
            t2 ^= r
        else:
            t2 ^= t6 ^ d
        t1 = (t1 + (t5 ^ d)) & M
    struct.pack_into(">II", rom, 0x10, ((t6 ^ t4) + t3) & M, ((t5 ^ t2) + t1) & M)


def hooks_all():
    try:
        from . import drawn
    except ImportError:
        return {}
    return drawn.hooks()


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    retail = open(args[0], "rb").read()
    assert hashlib.sha1(retail).hexdigest() == RETAIL_SHA1, "base ROM is not the decomp's target"
    sdir = argv[argv.index("--spec") + 1] if "--spec" in argv else os.path.join(HERE, "spec")
    spec = json.load(open(os.path.join(sdir, "textures.json")))
    rom, st = build(retail, spec, hooks_all())
    crc0 = bytes(rom[0x10:0x18])
    fix_crc(rom)
    line = f"images {st['images']} in {st['files']} files; squeezed {st['squeezed'] or 'none'}"
    if "--no-audio" not in argv:
        from . import audio
        res = audio.regenerate(rom, audio.load_spec())
        fix_crc(rom)
        line += f"; audio {res}"
    open(args[1], "wb").write(rom)
    diff = int((np.frombuffer(bytes(rom), np.uint8) != np.frombuffer(retail, np.uint8)).sum())
    print(line)
    print(f"clean ROM {args[1]}: sha1 {hashlib.sha1(rom).hexdigest()[:12]}, {diff} bytes differ from the base, "
          f"crc {'kept' if crc0 == bytes(rom[0x10:0x18]) else 'recomputed'}")


if __name__ == "__main__":
    main(sys.argv)
