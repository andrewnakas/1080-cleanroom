"""1080 Snowboarding audio: sound fonts (audio_bank.uso), sample banks (audio_wave.uso), sequences (audio_seq.uso).

The engine is Nintendo EAD's (SM64 lineage, tables in the later "AudioTable" form).  Three tables sit in
bootup.uso's Data section (ROM offsets below); each is  s16 count, pad[14]  then count 16-byte entries
    u32 offset, u32 size, u8 medium, u8 cachePolicy, u8 d0, u8 d1, u8 d2, u8 d3, u16 d4
(offset is relative to the matching .uso Data payload; size 0 = alias of entry `offset`).
  FONT_TBL  30 fonts : d0 = sample bank, d1 = 2nd bank (0xFF), d2 = numInstruments, d3 = numDrums, d4 = numSfx
  SEQ_TBL   90 seqs
  WAVE_TBL  13 sample banks (they tile audio_wave.uso exactly)
Font (all pointers relative to the font start):
  u32 drums (-> u32[numDrums] -> Drum), u32 sfx (-> Sound[numSfx]), u32 instruments[numInstruments], pad to 16
  Instrument 32 B: u8 loaded, lo, hi, release; u32 envelope; Sound low, normal, high
  Drum       16 B: u8 release, pan, loaded, pad; Sound; u32 envelope
  Sound       8 B: u32 sample, f32 tuning (= rate / 32000 at the root key)
  Sample     16 B: u8 flags (codec << 4 | ...), u24 size; u32 addr (in the sample bank); u32 loop; u32 book
  Book           : s32 order (2), s32 npred, s16 [16 * npred]            (padded to 16)
  Loop           : u32 start, end, count, 0;  s16 state[16] only when count != 0 (= decoded frame holding start)
  Envelope       : s16 (delay, arg) pairs until delay <= 0

Dirty room :  extract_spec(rom) -> spec    kept facts per unique wave: length, frames, loop, nominal rate,
                                           coarse outline (cleanroom.audio.descriptor), median f0 (YIN)
Clean room :  regenerate(rom_bytearray, spec) -> summary    our waveform, our books, our loop states, in place

    python -m games.ten80.audio <retail rom> <out rom>     extract (if spec missing) + regenerate + checks
    python -m games.ten80.audio parse <retail rom>         bank summary + coverage
"""
import json
import os
import pickle
import struct
import sys
import zlib

import numpy as np

from . import romfs

FONT_TBL, SEQ_TBL, WAVE_TBL = 0xDBFA10, 0xDBFE30, 0xDC03E0
HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec", "audio.json")
CACHE = "D:/n64work/1080/work/audio_cache.pkl"
PROCS = 3
FRAME = {0: 9, 3: 5}            # sample codec -> bytes per 16-sample frame (0 = 4-bit VADPCM, 3 = 2-bit VADPCM)


# ------------------------------------------------------------------ VADPCM, 4-bit and 2-bit residuals
# frame = header (scale << 4 | predictor) + 16 residuals of 4 or 2 bits; r = signed residual << scale;
# y[i] = (r[i] * 2048 + b0[i] * y[-2] + b1[i] * y[-1] + sum_{k<i} b1[i-1-k] * r[k]) >> 11   per group of 8.

def _mats(coefs, npred):
    """per predictor an 8 x 10 integer matrix M:  y[0..7] = (M @ [y-2, y-1, r0..r7]) >> 11."""
    ent = np.asarray(coefs, np.int64).reshape(npred, 2, 8)
    M = np.zeros((npred, 8, 10), np.int64)
    for p in range(npred):
        M[p, :, 0], M[p, :, 1] = ent[p, 0], ent[p, 1]
        for i in range(8):
            M[p, i, 2 + i] = 2048
            for k in range(i):
                M[p, i, 2 + k] = ent[p, 1, i - 1 - k]
    return ent, M


def decode(data, coefs, npred, codec):
    fb = FRAME[codec]
    nfr = len(data) // fb
    a = np.frombuffer(data, np.uint8)[:nfr * fb].reshape(nfr, fb)
    if codec == 0:
        r = np.stack([a[:, 1:] >> 4, a[:, 1:] & 15], 2).reshape(nfr, 16).astype(np.int64)
        r = np.where(r >= 8, r - 16, r)
    else:
        r = np.stack([a[:, 1:] >> 6, (a[:, 1:] >> 4) & 3, (a[:, 1:] >> 2) & 3, a[:, 1:] & 3], 2).reshape(nfr, 16).astype(np.int64)
        r = np.where(r >= 2, r - 4, r)
    r = (r << (a[:, :1] >> 4).astype(np.int64)).tolist()
    pred = np.minimum(a[:, 0] & 15, npred - 1).tolist()
    M = [m.tolist() for m in _mats(coefs, npred)[1]]
    out = [0] * (nfr * 16)
    y2 = y1 = 0
    o = 0
    for f in range(nfr):
        m, rf = M[pred[f]], r[f]
        for g in (0, 8):
            rg = rf[g:g + 8]
            for i in range(8):
                row = m[i]
                acc = row[0] * y2 + row[1] * y1
                for k in range(i + 1):
                    acc += row[2 + k] * rg[k]
                v = acc >> 11
                out[o + i] = 32767 if v > 32767 else (-32768 if v < -32768 else v)
            y2, y1 = out[o + 6], out[o + 7]
            o += 8
    return np.asarray(out, np.int16)


def _enc_group(b0, b1, shift, lo, hi, target, y2, y1):
    """greedy closed-loop quantisation of 8 samples for C candidates (predictor, scale) at once."""
    C = b0.shape[0]
    r = np.zeros((C, 8), np.int64)
    nib = np.zeros((C, 8), np.int64)
    out = np.zeros((C, 8), np.int64)
    err = np.zeros(C, np.int64)
    step = (np.int64(1) << shift).astype(np.float64)
    for i in range(8):
        acc = b0[:, i] * y2 + b1[:, i] * y1
        for k in range(i):
            acc = acc + b1[:, i - 1 - k] * r[:, k]
        n = np.clip(np.round((target[i] - acc / 2048.0) / step), lo, hi).astype(np.int64)
        for _ in range(8):      # never let the 16-bit output wrap
            val = (acc + ((n << shift) << 11)) >> 11
            bad = ((val < -32768) | (val > 32767)) & (n != 0)
            if not bad.any():
                break
            n = np.where(bad, n - np.sign(n), n)
        nib[:, i] = n
        r[:, i] = n << shift
        o = np.clip((acc + (r[:, i] << 11)) >> 11, -32768, 32767)
        out[:, i] = o
        err += (o - int(target[i])) ** 2
    return nib, out, err


def encode(pcm, coefs, npred, codec):
    """-> (bytes, decoded int16).  Our own encoder; works for both residual widths."""
    bits, nsc = (4, 13) if codec == 0 else (2, 15)
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    ent, _ = _mats(coefs, npred)
    preds = np.repeat(np.arange(npred), nsc)
    scales = np.tile(np.arange(nsc), npred).astype(np.int64)
    b0, b1 = ent[preds, 0, :], ent[preds, 1, :]
    x = np.asarray(pcm, np.int64)
    x = np.concatenate([x, np.zeros((-len(x)) % 16, np.int64)])
    nfr = len(x) // 16
    hdr = np.zeros(nfr, np.uint8)
    res = np.zeros((nfr, 16), np.int64)
    dec = np.zeros(len(x), np.int64)
    y2 = y1 = 0
    for f in range(nfr):
        t = x[f * 16:f * 16 + 16]
        if not t.any() and y1 == 0 and y2 == 0:
            continue            # digital silence: all-zero frame
        n0, o0, e0 = _enc_group(b0, b1, scales, lo, hi, t[:8], y2, y1)
        n1, o1, e1 = _enc_group(b0, b1, scales, lo, hi, t[8:], o0[:, 6], o0[:, 7])
        c = int(np.argmin(e0 + e1))
        hdr[f] = (int(scales[c]) << 4) | int(preds[c])
        res[f, :8], res[f, 8:] = n0[c], n1[c]
        dec[f * 16:f * 16 + 8], dec[f * 16 + 8:f * 16 + 16] = o0[c], o1[c]
        y2, y1 = int(o1[c][6]), int(o1[c][7])
    m = (1 << bits) - 1
    res &= m
    per = 8 // bits
    body = np.zeros((nfr, 16 // per), np.int64)
    for j in range(per):
        body = (body << bits) | res[:, j::per]
    out = np.concatenate([hdr[:, None], body.astype(np.uint8)], 1).astype(np.uint8)
    return out.tobytes(), dec.astype(np.int16)


# ------------------------------------------------------------------ parser (structure only)

def table(rom, off):
    n = struct.unpack_from(">h", rom, off)[0]
    out = []
    for i in range(n):
        o, size, med, cache, d0, d1, d2, d3, d4 = struct.unpack_from(">IIBBBBBBH", rom, off + 16 + 16 * i)
        out.append({"off": o, "size": size, "medium": med, "cache": cache, "d": (d0, d1, d2, d3, d4)})
    for e in out:
        if e["size"] == 0 and e["off"] < n:
            e["alias"] = e["off"]
    return out


def sections(rom):
    f = romfs.files(rom)
    out = {}
    for k in ("bank", "seq", "wave"):
        s = [x for x in f[f"audio_{k}.uso"] if x.type == 6][0]
        assert not s.yay0
        out[k] = (s.data_off, s.size)
    return out


def parse(rom):
    """-> dict(sec, fonts, waves, bank_cover, seqs).  waves: (bank, addr) -> facts; all offsets in `books`/`loops`
    are absolute inside the audio_bank payload."""
    sec = sections(rom)
    B0, BN = sec["bank"]
    b = rom[B0:B0 + BN]
    fonts, wbanks = table(rom, FONT_TBL), table(rom, WAVE_TBL)
    assert sum(e["size"] for e in wbanks) == sec["wave"][1], "sample banks must tile audio_wave"
    u = lambda o: struct.unpack_from(">I", b, o)[0]
    cover = np.zeros(BN, np.uint8)
    waves = {}

    def mark(o, n, kind):
        cover[o:o + n] = kind

    def envelope(F, p):
        o = F + p
        while True:
            d = struct.unpack_from(">h", b, o)[0]
            mark(o, 4, 5)
            o += 4
            if d <= 0:
                break

    def sound(F, o, wb, who, tunings):
        p, tun = u(o), struct.unpack_from(">f", b, o + 4)[0]
        if not p:
            return
        sample(F, F + p, wb, who, tun)

    def sample(F, so, wb, who, tun):
        w0, addr, lp, bk = u(so), u(so + 4), u(so + 8), u(so + 12)
        flags, size = w0 >> 24, w0 & 0xFFFFFF
        mark(so, 16, 2)
        bo, lo = F + bk, F + lp
        order, npred = struct.unpack_from(">ii", b, bo)
        assert order == 2 and 1 <= npred <= 8, (hex(bo), order, npred)
        mark(bo, 8 + 32 * npred, 3)
        st, en, cnt, z = struct.unpack_from(">IIII", b, lo)
        mark(lo, 48 if cnt else 16, 4)
        w = waves.setdefault((wb, addr), {"bank": wb, "addr": addr, "len": size, "flags": flags, "npred": npred,
                                          "loop": [st, en, cnt], "books": [], "loops": [], "tun": [], "use": set()})
        assert flags >> 4 in FRAME, f"codec {flags >> 4} at {so:X}"
        # the low flag bits may differ between fonts; codec, size, book size and loop may not
        assert (w["len"], w["npred"], w["loop"], w["flags"] >> 4) == (size, npred, [st, en, cnt], flags >> 4), hex(so)
        w["flags"] |= flags
        if bo not in w["books"]:
            w["books"].append(bo)
        if cnt and lo not in w["loops"]:
            w["loops"].append(lo)
        if tun:
            w["tun"].append(round(tun, 5))
        w["use"].add(who)

    for fi, e in enumerate(fonts):
        if "alias" in e:
            continue
        F = e["off"]
        wb, _, ninst, ndrum, nsfx = e["d"]
        hdr = (8 + 4 * ninst + 15) & ~15
        mark(F, hdr, 1)
        dp, sp = u(F), u(F + 4)
        if dp:
            mark(F + dp, 4 * ndrum, 1)
            for i in range(ndrum):
                p = u(F + dp + 4 * i)
                if p:
                    mark(F + p, 16, 6)
                    sound(F, F + p + 4, wb, f"f{fi}d{i}", None)
                    envelope(F, u(F + p + 12))
        if sp:
            mark(F + sp, 8 * nsfx, 6)
            for i in range(nsfx):
                sound(F, F + sp + 8 * i, wb, f"f{fi}s{i}", None)
        for i in range(ninst):
            p = u(F + 8 + 4 * i)
            if p:
                mark(F + p, 32, 6)
                envelope(F, u(F + p + 4))
                for k in (8, 16, 24):
                    sound(F, F + p + k, wb, f"f{fi}i{i}", None)
    # orphans: sample structs no instrument points at (their wave data is still in the ROM)
    for fi, e in enumerate(fonts):
        if "alias" in e:
            continue
        F, S, wb = e["off"], e["size"], e["d"][0]
        for so in range(F, F + S - 15, 16):
            if cover[so:so + 16].any():
                continue
            w0, addr, lp, bk = struct.unpack_from(">IIII", b, so)
            if not ((w0 >> 28) in FRAME and 0 < (w0 & 0xFFFFFF) and addr + (w0 & 0xFFFFFF) <= wbanks[wb]["size"]
                    and 0 < bk < S and 0 < lp < S and bk % 16 == 0 and lp % 16 == 0 and (w0 >> 24) & 0xC == 0):
                continue
            if struct.unpack_from(">i", b, F + bk)[0] != 2 or not 1 <= u(F + bk + 4) <= 8:
                continue
            sample(F, so, wb, f"f{fi}orphan", 0)
    for w in waves.values():
        w["base"] = wbanks[w["bank"]]["off"] + w["addr"]
        w["use"] = sorted(w["use"])
    return {"sec": sec, "fonts": fonts, "wbanks": wbanks, "waves": waves, "cover": cover, "seqs": table(rom, SEQ_TBL)}


def wave_cover(P):
    n = P["sec"]["wave"][1]
    c = np.zeros(n, bool)
    for w in P["waves"].values():
        c[w["base"]:w["base"] + w["len"]] = True
    return c


def rate_of(w):
    """Nominal rate: tuning * 32000 (the engine's convention).  Not stored in the ROM as such; drums and sfx are
    played at their root so the smallest tuning is the best guess."""
    t = [x for x in w["tun"] if x > 0]
    r = 32000 * (min(t) if t else 0.6890625)
    while r > 44100:
        r /= 2
    while r < 5000:
        r *= 2
    return int(round(r))


def _runs(mask):
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]


def parse_summary(rom):
    P = parse(rom)
    W, wc, bc = P["waves"], wave_cover(P), P["cover"]
    wv = rom[P["sec"]["wave"][0]:P["sec"]["wave"][0] + len(wc)]
    wvn = np.frombuffer(wv, np.uint8)
    s, e = _runs(~wc)
    gapnz = int((wvn[~wc] != 0).sum())
    print(f"fonts {len(P['fonts'])} ({sum('alias' in f for f in P['fonts'])} aliases)  sample banks {len(P['wbanks'])}"
          f"  sequences {len(P['seqs'])}  unique waves {len(W)} "
          f"(orphans {sum(all('orphan' in x for x in w['use']) for w in W.values())})")
    print(f"audio_wave: {wc.sum()}/{len(wc)} B covered ({100 * wc.mean():.3f} %), {len(s)} gaps, longest "
          f"{(e - s).max() if len(s) else 0} B, non-zero gap bytes {gapnz}")
    kinds = ["unparsed", "header/ptr", "sample", "book", "loop", "envelope", "inst/drum/sfx"]
    print("audio_bank: " + ", ".join(f"{kinds[k]} {int((bc == k).sum())}" for k in range(7)))
    nb = np.frombuffer(rom[P["sec"]["bank"][0]:P["sec"]["bank"][0] + len(bc)], np.uint8)
    print(f"audio_bank unparsed non-zero bytes: {int((nb[bc == 0] != 0).sum())}")
    fl = {}
    for w in W.values():
        fl[(w["flags"], w["npred"], bool(w["loop"][2]))] = fl.get((w["flags"], w["npred"], bool(w["loop"][2])), 0) + 1
    print("flags/npred/looped:", {f"{k[0]:02X}/{k[1]}/{int(k[2])}": v for k, v in sorted(fl.items())})
    print("len%9:", np.bincount([w["len"] % 9 for w in W.values()], minlength=9).tolist())
    return P


# ------------------------------------------------------------------ dirty room

def _describe(job):
    from cleanroom.audio import descriptor
    from cleanroom.audio.pitch import median_f0
    key, raw, coefs, nf, rate, lstate, lstart, codec = job
    pcm = decode(raw, coefs, len(coefs) // 16, codec)[:nf].astype(np.float64)
    d = {"desc": descriptor.describe(pcm, rate)}
    f0 = median_f0((pcm[:rate * 2] / 32768).astype(np.float32), rate)
    if f0:
        d["f0"] = round(float(f0), 1)
    if lstate is not None:      # dev check of the loop-state convention only (not stored)
        a = (lstart >> 4) * 16
        d["_st"] = bool(np.abs(pcm[a:a + 16] - np.asarray(lstate)).max() == 0)
    return key, d


def extract_spec(rom, out=SPEC, procs=PROCS):
    from multiprocessing import Pool
    P = parse(rom)
    B0, W0 = P["sec"]["bank"][0], P["sec"]["wave"][0]
    facts, jobs = {}, []
    for (wb, addr), w in sorted(P["waves"].items()):
        key = f"{wb}:{addr:X}"
        codec = w["flags"] >> 4
        nfr = w["len"] // FRAME[codec]
        rate = rate_of(w)
        facts[key] = {"bank": wb, "addr": addr, "base": w["base"], "len": w["len"], "codec": codec, "nframes": nfr * 16,
                      "npred": w["npred"], "rate": rate, "loop": w["loop"], "books": w["books"],
                      "loops": w["loops"], "use": w["use"][:4]}
        bo = B0 + w["books"][0]
        coefs = list(struct.unpack_from(">%dh" % (16 * w["npred"]), rom, bo + 8))
        ls = list(struct.unpack_from(">16h", rom, B0 + w["loops"][0] + 16)) if w["loops"] else None
        jobs.append((key, bytes(rom[W0 + w["base"]:W0 + w["base"] + nfr * FRAME[codec]]), coefs, nfr * 16, rate, ls,
                     w["loop"][0], codec))
    jobs.sort(key=lambda j: -j[3])
    okst = nst = 0
    with Pool(procs) as p:
        for key, d in p.imap_unordered(_describe, jobs, chunksize=4):
            if "_st" in d:
                nst += 1
                okst += d.pop("_st")
            facts[key].update(d)
    S = {"wave_len": P["sec"]["wave"][1], "bank_len": P["sec"]["bank"][1], "waves": facts}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(S, open(out, "w"), separators=(",", ":"))
    tot = sum(d["nframes"] / d["rate"] for d in facts.values())
    print(f"spec: {len(facts)} waves, {tot:.0f} s, loop-state convention ok {okst}/{nst} -> {out} "
          f"({os.path.getsize(out) // 1024} KB)")
    return S


# ------------------------------------------------------------------ clean room

def h32(*a):
    return zlib.crc32(repr(a).encode())


def k_predictors(x, k=2):
    """Our own predictor set: k-means over per-16-sample 2nd-order LPC fits of our own waveform."""
    fits = []
    for s in range(2, len(x) - 16, 16):
        y, p1, p2 = x[s:s + 16], x[s - 1:s + 15], x[s - 2:s + 14]
        if (y ** 2).sum() < 1e3:
            continue
        a, *_ = np.linalg.lstsq(np.stack([p1, p2], 1), y, rcond=None)
        fits.append(a)
        if len(fits) >= 400:
            break
    base = [(1.0, 0.0), (1.8, -0.82), (0.5, 0.0), (1.4, -0.5), (0.0, 0.0), (1.95, -0.96), (-0.5, 0.0), (1.2, -0.3)]
    if len(fits) < k:
        return base[:k]
    f = np.clip(np.asarray(fits), [-1.95, -0.98], [1.95, 0.98])
    pick = np.linspace(0, len(f) - 1, k).astype(int)
    c = f[pick][np.argsort(f[pick, 0])].copy()
    for _ in range(12):
        lab = np.argmin(((f[:, None, :] - c[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (lab == j).any():
                c[j] = f[lab == j].mean(0)
    out = []
    for a1, a2 in c:
        a2 = float(np.clip(a2, -0.98, 0.98))
        out.append((float(np.clip(a1, -(1 - a2) + 0.02, (1 - a2) - 0.02)), a2))
    return out


def _make(job):
    from cleanroom.audio import descriptor, vadpcm
    key, d = job
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    nf = d["nframes"]
    if nf == 0:
        return key, b"", None, None
    desc = d["desc"]
    if d.get("f0"):             # playbook: the YIN median is the pitch target (frame f0 has octave errors)
        fr = []
        for f in desc["frames"]:
            f = dict(f)
            if f["f0"] > 20 and f["h"] > 0.3:
                f["f0"] = d["f0"] * 2 ** float(np.clip(np.log2(f["f0"] / d["f0"]) - round(np.log2(f["f0"] / d["f0"])), -0.5, 0.5))
            fr.append(f)
        desc = {"frames": fr}
    x = descriptor.synthesize(desc, nf, d["rate"], seed=h32("1080", key))
    x = np.pad(np.asarray(x, np.float32)[:nf], (0, max(0, nf - len(x))))
    st, en, cnt = d["loop"]
    if cnt and en > st + 16:
        x = descriptor.make_loop_seamless(x, st, min(en, nf))
    dither = np.random.default_rng(h32("dither", key)).integers(-1, 2, nf)
    pcm = np.clip(np.round(np.clip(x, -1, 1) * 30000) + dither, -32768, 32767).astype(np.int16)
    book = vadpcm.make_book(k_predictors(pcm.astype(np.float64), d["npred"]))
    data, dec = encode(pcm, book["book"], d["npred"], d["codec"])
    data = bytes(data[:d["len"]]) + bytes(max(0, d["len"] - len(data)))
    vals = struct.pack(">%dh" % len(book["book"]), *book["book"])
    state = None
    if cnt:                     # loop state = the decoded frame that holds `start` (verified on every retail loop)
        a = (st >> 4) * 16
        state = struct.pack(">16h", *[int(v) for v in dec[a:a + 16]])
    return key, data, vals, state


def synth_all(spec, cache=CACHE, procs=PROCS):
    key = zlib.crc32(json.dumps(spec["waves"], sort_keys=True).encode())
    if cache and os.path.exists(cache):
        k, res = pickle.load(open(cache, "rb"))
        if k == key:
            return res, True
    from multiprocessing import Pool
    jobs = sorted(spec["waves"].items(), key=lambda j: -j[1]["nframes"])
    with Pool(procs) as p:
        res = p.map(_make, jobs, chunksize=2)
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        pickle.dump((key, res), open(cache, "wb"))
    return res, False


def regenerate(rom, spec, cache=CACHE, procs=PROCS):
    """Patch `rom` (bytearray, a copy of the retail image) in place.  Only the spec is used for the content."""
    assert isinstance(rom, bytearray)
    sec = sections(rom)
    B0, W0 = sec["bank"][0], sec["wave"][0]
    assert sec["wave"][1] == spec["wave_len"] and sec["bank"][1] == spec["bank_len"]
    res, cached = synth_all(spec, cache, procs)
    regions = []                # (rom offset, length, kind)
    secs = 0.0
    for key, data, vals, state in res:
        d = spec["waves"][key]
        o = W0 + d["base"]
        rom[o:o + d["len"]] = data
        regions.append((o, d["len"], "wave"))
        nb = 32 * d["npred"]
        for bo in d["books"]:
            rom[B0 + bo + 8:B0 + bo + 8 + nb] = vals if vals else bytes(nb)
            regions.append((B0 + bo + 8, nb, "book"))
        for lo in d["loops"]:
            rom[B0 + lo + 16:B0 + lo + 48] = state if state else bytes(32)
            regions.append((B0 + lo + 16, 32, "loop"))
        secs += d["nframes"] / d["rate"]
    cov = np.zeros(sec["wave"][1], bool)
    for d in spec["waves"].values():
        cov[d["base"]:d["base"] + d["len"]] = True
    s, e = _runs(~cov)          # padding between samples and the file tail: silence
    for a, c in zip(s.tolist(), e.tolist()):
        rom[W0 + a:W0 + c] = bytes(c - a)
        regions.append((W0 + a, c - a, "gap"))
    return {"samples": len(res), "seconds": round(secs, 1), "cached": cached, "regions": regions,
            "wave": (W0, sec["wave"][1]), "bank": (B0, sec["bank"][1]),
            "bytes": {k: sum(n for _, n, kk in regions if kk == k) for k in ("wave", "book", "loop")}}


# ------------------------------------------------------------------ checks

def _const_windows(a, n):
    """bool per window start: all n bytes equal."""
    same = np.concatenate([[0], np.cumsum(a[1:] == a[:-1])])
    return same[n - 1:] - same[:len(a) - n + 1] == n - 1


def _roll(a, n):
    """64-bit hash of every n-byte window (sum of position-independent mixes of n/8 strided u64 words)."""
    k = n // 8
    w = np.zeros(len(a) - 7, np.uint64)
    for i in range(8):
        w |= a[i:len(a) - 7 + i].astype(np.uint64) << np.uint64(8 * (7 - i))
    m = len(a) - n + 1
    h = np.zeros(m, np.uint64)
    with np.errstate(over="ignore"):
        for j in range(k):
            h = (h * np.uint64(0x9E3779B97F4A7C15)) ^ (w[8 * j:8 * j + m] * np.uint64(0xC2B2AE3D27D4EB4F) + np.uint64(j))
    return h


def check(retail, clean, summary, n=32):
    """-> dict: same-position identical runs >= n and position-free shared n-byte windows, trivial ones excluded."""
    W0, WN = summary["wave"]
    r, c = np.frombuffer(retail, np.uint8), np.frombuffer(clean, np.uint8)
    mask = np.zeros(len(r), bool)
    for o, ln, _ in summary["regions"]:
        mask[o:o + ln] = True
    same = mask & (r == c)
    s, e = _runs(same)
    runs = [(a, b) for a, b in zip(s, e) if b - a >= n]
    nontriv = [(a, b) for a, b in runs if len(set(clean[a:b])) > 1]
    # position-free: any n-byte window of the new wave data that also occurs anywhere in retail wave data
    hr = _roll(r[W0:W0 + WN], n)
    hc = _roll(c[W0:W0 + WN], n)
    shared = np.isin(hc, hr) & ~_const_windows(c[W0:W0 + WN], n)
    regm = mask[W0:W0 + WN]
    ident_wave = int((same[W0:W0 + WN]).sum())
    nz = int((same[W0:W0 + WN] & (c[W0:W0 + WN] != 0)).sum())
    return {"runs": len(runs), "nontrivial_runs": len(nontriv), "shared_windows": int(shared.sum()),
            "identical_wave_bytes": ident_wave, "identical_nonzero_wave_bytes": nz,
            "uncovered_wave_bytes": int((~regm).sum()),
            "uncovered_nonzero": int((c[W0:W0 + WN][~regm] != 0).sum()),
            "changed": int((r != c).sum()), "changed_outside": int(((r != c) & ~mask).sum())}


def speech_candidates(spec, min_s=0.6):
    out = []
    for i, (k, d) in enumerate(spec["waves"].items()):
        dur = d["nframes"] / d["rate"]
        if dur >= min_s and not d["loop"][2]:
            out.append((i, k, round(dur, 2), d["rate"], d.get("f0"), d["use"][0]))
    return out


def main(argv):
    if argv[1] == "parse":
        parse_summary(open(argv[2], "rb").read())
        return
    retail = open(argv[1], "rb").read()
    if argv[1].replace("\\", "/").lower() == argv[2].replace("\\", "/").lower():
        raise SystemExit("refusing to overwrite the retail ROM")
    spec = json.load(open(SPEC)) if os.path.exists(SPEC) else extract_spec(retail)
    rom = bytearray(retail)
    s = regenerate(rom, spec)
    open(argv[2], "wb").write(rom)
    c = check(retail, bytes(rom), s)
    print(f"audio: {s['samples']} samples, {s['seconds']} s ({'cached' if s['cached'] else 'synthesised'})")
    print(f"  rewritten: wave {s['bytes']['wave']} B, books {s['bytes']['book']} B, loop states {s['bytes']['loop']} B")
    print(f"  bytes changed {c['changed']} (outside audio regions: {c['changed_outside']})")
    print(f"  audio_wave {s['wave'][1]} B: identical to retail {c['identical_wave_bytes']} "
          f"(non-zero {c['identical_nonzero_wave_bytes']} = chance matches); outside any sample "
          f"{c['uncovered_wave_bytes']} B (non-zero {c['uncovered_nonzero']})")
    print(f"  same-position identical runs >=32: {c['runs']} (non-trivial {c['nontrivial_runs']}); "
          f"32-byte windows shared with retail wave data anywhere: {c['shared_windows']}")
    sp = speech_candidates(spec)
    print(f"  long non-looping clips (>=0.6 s): {len(sp)} -> {argv[2]}")
    ok = c["nontrivial_runs"] == 0 and c["shared_windows"] == 0 and c["changed_outside"] == 0
    print("  CHECK", "OK" if ok else "FAILED")


if __name__ == "__main__":
    main(sys.argv)
