"""DIRTY-ROOM CHECK: clean ROM vs retail ROM.

    python -m games.ten80.taint <retail rom> <clean rom>

1. Every regenerated stream (image pixels, palettes, decoded palette pictures, sample data, ADPCM books, loop
   states) is scanned against the same retail streams: a shared run of >= 32 bytes anywhere fails.
   Decoded palette pictures are 2 bytes per texel, so the rule there is 32 texels (64 bytes), as in the other
   clean rooms: runs of a few neighbouring sky colours recur by chance across megabytes of retail pixels.
2. Everything else must be byte-identical (kept facts: code, geometry, parameters, sequences, text), except the
   header checksum.  Yay0 sections are compared decoded.
Exit code 1 when anything fails.
"""
import sys

import numpy as np

from cleanroom import taint

from . import audio, images, romfs, usofile


def regions(rom):
    """-> (files, {(file, sec): [(off, len, label)]})"""
    files = usofile.load(rom)
    out = {}
    for r in images.catalog(rom, files):
        e = out.setdefault((r["file"], r["sec"]), [])
        e.append((r["off"], images.size(r), r["key"]))
        if "pal" in r:
            e.append((r["pal"], 0x200, r["key"] + ".pal"))
    return files, out


def buf(u, sec):
    return u.data if sec == "data" else u.binary


def streams(rom, files, regs, with_ci=True):
    cat = {r["key"]: r for r in images.catalog(rom, files)} if with_ci else {}
    for (name, sec), lst in regs.items():
        b = buf(files[name], sec)
        for off, n, label in lst:
            yield label, b[off:off + n]
    for key, r in cat.items():
        if r["fmt"] == "ci8":           # decoded colours: the palette order is ours, the picture must be too
            b = buf(files[r["file"]], r["sec"])
            pal = np.frombuffer(b[r["pal"]:r["pal"] + 0x200], ">u2")
            yield key + ".rgb", pal[np.frombuffer(b[r["off"]:r["off"] + images.size(r)], np.uint8)].tobytes()


def audio_streams(rom, P):
    B0, W0 = P["sec"]["bank"][0], P["sec"]["wave"][0]
    yield "audio_wave", rom[W0:W0 + P["sec"]["wave"][1]]
    for (wb, addr), w in P["waves"].items():
        for bo in w["books"]:
            yield "book@%X" % bo, rom[B0 + bo + 8:B0 + bo + 8 + 32 * w["npred"]]
        for lo in w["loops"]:
            yield "loop@%X" % lo, rom[B0 + lo + 16:B0 + lo + 48]


def main(argv):
    retail, clean = open(argv[1], "rb").read(), open(argv[2], "rb").read()
    rf, rr = regions(retail)
    cf = usofile.load(clean)
    P = audio.parse(retail)
    index = taint.build_index([s for _, s in streams(retail, rf, rr)] + [s for _, s in audio_streams(retail, P)])
    hits = taint.scan(index, list(streams(clean, cf, rr, with_ci=False)) + list(audio_streams(clean, P)))
    # decoded palette pictures of the clean ROM (layout is a kept fact, so the retail catalog applies)
    cat = [r for r in images.catalog(retail, rf) if r["fmt"] == "ci8"]
    dec = []
    for r in cat:
        b = buf(cf[r["file"]], r["sec"])
        pal = np.frombuffer(b[r["pal"]:r["pal"] + 0x200], ">u2")
        dec.append((r["key"] + ".rgb", pal[np.frombuffer(b[r["off"]:r["off"] + images.size(r)], np.uint8)].tobytes()))
    hits += taint.scan(index, dec)
    nstreams = sum(len(v) for v in rr.values()) + len(dec)
    failing = [h for h in hits if h[3] >= taint.FAIL_RUN * (2 if h[0].endswith(".rgb") else 1)]
    # 2. everything outside the regenerated regions is identical
    outside = 0
    mask = np.ones(len(retail), bool)                     # True = must be identical in the ROM image
    mask[0x10:0x18] = False
    secs_r = romfs.files(retail)
    for name, u in rf.items():
        for sec, t in (("data", 6), ("binary", 12)):
            ss = [x for x in secs_r[name] if x.type == t]
            if not ss:
                continue
            s = ss[0]
            lst = rr.get((name, sec), [])
            if name in ("audio_wave.uso",):
                mask[s.data_off:s.data_off + s.size] = False
                continue
            if name == "audio_bank.uso":
                for (wb, addr), w in P["waves"].items():
                    for bo in w["books"]:
                        mask[s.data_off + bo + 8:s.data_off + bo + 8 + 32 * w["npred"]] = False
                    for lo in w["loops"]:
                        mask[s.data_off + lo + 16:s.data_off + lo + 48] = False
                continue
            if not lst:
                continue
            if s.yay0:
                mask[s.data_off:s.data_off + s.size] = False
                a = np.frombuffer(buf(u, sec), np.uint8)
                b = np.frombuffer(buf(cf[name], sec), np.uint8)
                if len(a) != len(b):
                    outside += abs(len(a) - len(b)) + 1
                    continue
                m = np.ones(len(a), bool)
                for off, n, _ in lst:
                    m[off:off + n] = False
                outside += int(((a != b) & m).sum())
            else:
                for off, n, _ in lst:
                    mask[s.data_off + off:s.data_off + off + n] = False
    r, c = np.frombuffer(retail, np.uint8), np.frombuffer(clean, np.uint8)
    outside += int(((r != c) & mask).sum())
    print(f"taint: {nstreams} image streams + {len(P['waves'])} samples scanned; streams with shared windows "
          f"{len(hits)}, longest shared run {max([h[3] for h in hits] or [0])} B; failing (>= {taint.FAIL_RUN} B): "
          f"{len(failing)}")
    print(f"       bytes changed outside regenerated regions: {outside}")
    for h in sorted(failing, key=lambda h: -h[3])[:12]:
        print("       FAIL %-22s run %d B (%d windows, first at %d)" % (h[0], h[3], h[2], h[1]))
    ok = not failing and outside == 0
    print("       RESULT", "0 failing" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
