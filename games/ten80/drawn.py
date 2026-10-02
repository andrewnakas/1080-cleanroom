"""Our own drawings for images where the kept colour grid is not enough: every piece of text is
re-typeset, fonts and digit strips are drawn glyph by glyph.

Text comes from open-licensed fonts (games/ten80/fonts: Rubik, Lilita One, Luckiest Guy, Press Start 2P).
The only facts used from the spec are the image size and the kept 2-bit outline (where the ink sits).

    hooks() -> {spec key: fn(key, d) -> float RGBA (h, w, 4)}
    python -m games.ten80.drawn <out.png> [filter]      clean contact sheet of every drawn image
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cleanroom.decomp import gen

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
_cache = {}

# style -> (font file, weight, shear, tracking)
STYLES = {
    "m": ("Rubik.ttf", 500, 0.0),            # menu entries
    "c": ("Rubik.ttf", 700, 0.0),            # caps headings
    "h": ("Rubik.ttf", 800, 0.22),           # HUD italics
    "s": ("LilitaOne-Regular.ttf", None, 0.25),      # script-like course names
    "b": ("LuckiestGuy-Regular.ttf", None, 0.2),     # big brush messages
    "p": ("PressStart2P-Regular.ttf", None, 0.0),
}


def font(style, size):
    k = (style, size)
    if k not in _cache:
        name, wght, _ = STYLES[style]
        f = ImageFont.truetype(os.path.join(FONTS, name), size)
        if wght:
            f.set_variation_by_axes([wght])
        _cache[k] = f
    return _cache[k]


def text_mask(text, style, size=64, crop=True):
    """Tight coverage mask (float 0..1) of one line of text."""
    f = font(style, size)
    w = int(f.getlength(text)) + size * 2
    im = Image.new("L", (w, size * 2), 0)
    ImageDraw.Draw(im).text((size // 2, size // 4), text, fill=255, font=f)
    sh = STYLES[style][2]
    if sh:
        im = im.transform(im.size, Image.AFFINE, (1, sh, -sh * size, 0, 1, 0), Image.BILINEAR)
    a = np.asarray(im, np.float32) / 255.0
    if not crop:
        return a
    ys, xs = np.nonzero(a > 0.05)
    if not len(ys):
        return np.zeros((1, 1), np.float32)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def resize(mask, w, h):
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    im = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8))
    return np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255.0


def paste(dst, mask, x, y):
    h, w = dst.shape
    x, y = int(round(x)), int(round(y))
    mh, mw = mask.shape
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + mw, w), min(y + mh, h)
    if x1 > x0 and y1 > y0:
        dst[y0:y1, x0:x1] = np.maximum(dst[y0:y1, x0:x1], mask[y0 - y:y1 - y, x0 - x:x1 - x])


def fit(dst, text, style, box, align="l", stretch=1.3):
    """Draw `text` into box (x0, y0, x1, y1) of dst: as large as fits, aspect kept within `stretch`."""
    x0, y0, x1, y1 = box
    bw, bh = max(2, x1 - x0), max(2, y1 - y0)
    m = text_mask(text, style)
    sy = bh / m.shape[0]
    sx = bw / m.shape[1]
    if sx > sy * stretch:
        sx = sy * stretch
    elif sy > sx * stretch:
        sy = sx * stretch
    g = resize(m, m.shape[1] * sx, m.shape[0] * sy)
    ox = x0 if align == "l" else (x0 + (bw - g.shape[1]) / 2 if align == "c" else x1 - g.shape[1])
    paste(dst, g, ox, y0 + (bh - g.shape[0]) / 2)


def ink_box(d, pad=0):
    """Bounding box of the kept 2-bit outline (None when the image is empty or has no outline)."""
    w, h = d["w"], d["h"]
    if "alpha2" not in d:
        return (1, 1, w - 1, h - 1)
    a = gen.unpack_alpha2(d["alpha2"], w, h) >= 85
    ys, xs = np.nonzero(a)
    if not len(ys):
        return (1, 1, w - 1, h - 1)
    return (max(0, xs.min() - pad), max(0, ys.min() - pad), min(w, xs.max() + 1 + pad), min(h, ys.max() + 1 + pad))


def bands(d, n):
    """Split the ink box into n line boxes, at the emptiest rows of the kept outline."""
    x0, y0, x1, y1 = ink_box(d)
    if n == 1:
        return [(x0, y0, x1, y1)]
    w, h = d["w"], d["h"]
    rows = (gen.unpack_alpha2(d["alpha2"], w, h) >= 85).sum(1).astype(np.float32) if "alpha2" in d else np.ones(h)
    cuts = [y0]
    for i in range(1, n):
        c = y0 + (y1 - y0) * i / n
        lo, hi = int(max(y0 + 2, c - (y1 - y0) / (2.5 * n))), int(min(y1 - 2, c + (y1 - y0) / (2.5 * n)))
        cuts.append(lo + int(np.argmin(rows[lo:hi + 1])) if hi > lo else int(c))
    cuts.append(y1)
    out = []
    for a, b in zip(cuts, cuts[1:]):
        r = np.nonzero(rows[a:b] > 0)[0]
        out.append((x0, a + (int(r[0]) if len(r) else 0), x1, a + (int(r[-1]) + 1 if len(r) else b - a)))
    return out


def grey(mask, level=255.0):
    v = np.clip(mask, 0, 1) * level
    return np.stack([v, v, v, v], -1)


def label(text, style, align="l", level=255.0):
    lines = text.split("|")

    def fn(key, d):
        m = np.zeros((d["h"], d["w"]), np.float32)
        for t, box in zip(lines, bands(d, len(lines))):
            fit(m, t, style, box, align)
        return grey(m, level)
    return fn


def strip(chars, style, cw, ch=None, bg=0.0, fg=255.0, fill=0.8, cols=None):
    """Glyph cells side by side (or stacked when cols is given), one shared size."""
    def fn(key, d):
        w, h = d["w"], d["h"]
        hh = ch or h
        nc = cols or (w // cw)
        size = 64
        ref = text_mask("0", style, size)
        sc = hh * fill / ref.shape[0]
        m = np.zeros((h, w), np.float32)
        full = text_mask("0", style, size, crop=False)
        ys = np.nonzero(full.max(1) > 0.05)[0]
        top, bot = ys.min(), ys.max() + 1                       # digit band of the uncropped line
        for i, c in enumerate(chars):
            if c == " ":
                continue
            g = text_mask(c, style, size, crop=False)
            xs = np.nonzero(g.max(0) > 0.05)[0]
            if not len(xs):
                continue
            g = g[max(0, top - size // 4):bot + size // 4, xs.min():xs.max() + 1]
            g = resize(g, min(g.shape[1] * sc, cw - 1), g.shape[0] * sc)
            cx, cy = (i % nc) * cw, (i // nc) * hh
            paste(m, g, cx + (cw - g.shape[1]) / 2, cy + (hh - (bot - top) * sc) / 2 - (size // 4) * sc)
        v = bg + (fg - bg) * m
        return np.stack([v, v, v, v], -1)
    return fn


def boxed(text, icon):
    """Sound-mode card: frame, caption, a simple speaker / headphone symbol."""
    def fn(key, d):
        w, h = d["w"], d["h"]
        im = Image.new("L", (w * 4, h * 4), 0)
        dr = ImageDraw.Draw(im)
        dr.rounded_rectangle((6, 6, w * 4 - 7, h * 4 - 7), 24, outline=255, width=7)
        cx, cy = w * 2, int(h * 2.6)
        if icon == "headset":
            dr.arc((cx - 60, cy - 55, cx + 60, cy + 65), 180, 360, fill=255, width=12)
            dr.rounded_rectangle((cx - 72, cy, cx - 44, cy + 50), 8, fill=255)
            dr.rounded_rectangle((cx + 44, cy, cx + 72, cy + 50), 8, fill=255)
        else:
            dr.polygon([(cx - 40, cy - 16), (cx - 16, cy - 16), (cx + 14, cy - 44), (cx + 14, cy + 44), (cx - 16, cy + 16),
                        (cx - 40, cy + 16)], fill=255)
            dr.arc((cx - 4, cy - 30, cx + 46, cy + 30), -55, 55, fill=255, width=9)
            if icon == "stereo":
                dr.arc((cx - 20, cy - 50, cx + 76, cy + 50), -55, 55, fill=255, width=9)
                dr.arc((cx - 76, cy - 50, cx + 20, cy + 50), 125, 235, fill=255, width=9)
        m = np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255.0
        fit(m, text, "m", (10, 6, w - 10, int(h * 0.36)), "c")
        return grey(m)
    return fn


COURSES = ["Air Make", "Half Pipe", "Crystal Lake", "Crystal Peak", "Golden Forest", "Mountain Village", "Dragon Cave",
           "Deadly Fall"]
BOARDS = ["Tahoe 151", "Merlot 147", "B-Line 149", "Scout 156", "Tahoe 155", "Scout Ltd 162", "Merlot 143", "B-Line 154"]
RIDER_STATS = ["MAX SPEED", "TECHNIQUE", "BALANCE", "JUMP", "POWER"]
BOARD_STATS = ["ACCELERATION", "RESPONSE", "EDGE CONTROL", "FLEX", "STABILITY"]

# flowimgs record name -> (text, style[, align]).  "|" separates lines.  The Japanese-language set (j_*) is
# typeset in English too.
TEXT = {
    "press_s": ("Press START", "m"), "no_cont": ("NO CONTROLLER", "c"), "ending_": ("CLEAN ROOM", "c", "c"),
    "pressst": ("PRESS START BUTTON", "c"),
    "racemod": ("Match Race", "m"), "timeatt": ("Time Attack", "m"), "trickat": ("Trick Attack", "m"),
    "2player": ("2P VS", "m"), "options": ("Options", "m"), "contest": ("Contest", "m"), "trainin": ("Training", "m"),
    "j_match": ("Match Race", "m"), "j_time_": ("Time Attack", "m"), "j_trick": ("Trick Attack", "m"),
    "j_2Pvs": ("2P VS", "m"), "j_optio": ("Options", "m"), "j_conte": ("Contest", "m"), "j_train": ("Training", "m"),
    "continu": ("Continue", "m"), "retry": ("Retry", "m"), "change_": ("Change Rider", "m"),
    "change_.1": ("Change Board", "m"), "change_.2": ("Change Course", "m"), "quit": ("Quit", "m"),
    "view_re": ("View Replay", "m"), "update_": ("Update Ghost", "m"), "retire": ("Retire", "m"),
    "restart": ("Restart", "m"),
    "j_conti": ("Continue", "m"), "j_retry": ("Retry", "m"), "j_rider": ("Change Rider", "m"),
    "j_boad_": ("Change Board", "m"), "j_cours": ("Change Course", "m"), "j_quit_": ("Quit", "m"),
    "j_repla": ("View Replay", "m"), "j_ghost": ("Update Ghost", "m"), "j_retir": ("Retire", "m"),
    "j_resta": ("Restart", "m"),
    "game_ti": ("TIME", "h"), "score": ("SCORE", "h"), "game_km": ("km/h", "h"), "con_sec": ("+|SECS", "c"),
    "contest.1": ("TRICK", "c"), "contest.2": ("CHECK", "c"), "contest.3": ("TIME BONUS", "c"),
    "game_da": ("DAMAGE", "h"), "1st": ("1st", "h"), "2nd": ("2nd", "h"), "best_ti": ("BEST TIME", "h"),
    "best_sc": ("BEST SCORE", "h"), "copntes": ("COMBO", "c"),
    "new_go": ("GO!", "b", "c"), "n_ready": ("Ready", "b", "c"), "goal2": ("Goal!", "b", "c"),
    "start_2": ("1", "b", "c"), "start_3": ("2", "b", "c"), "start_1": ("3", "b", "c"),
    "n_win": ("You Win!", "b", "c"), "n_lose": ("You Lose", "b", "c"), "n_retir": ("Retire", "b", "c"),
    "n_timeo": ("Time Out", "b", "c"), "n_gameo": ("Game Over", "b", "c"), "n_draw": ("Draw", "b", "c"),
    "regular": ("Regular", "m"), "goofy": ("Goofy", "m"), "j_regui": ("Regular", "m"), "j_goofy": ("Goofy", "m"),
    "select_.2": ("SELECT LEVEL", "c"), "select_.3": ("SELECT RIDER", "c"), "select_.4": ("SELECT BOARD", "c"),
    "select_.5": ("SELECT COURSE", "c"), "2p_sele.4": ("SELECT RIDER", "c"), "2p_sel_": ("SELECT BOARD", "c"),
    "2p_sele.5": ("SELECT COURSE", "c"),
    "j_level": ("SELECT LEVEL", "c"), "j_selec": ("SELECT RIDER", "c"), "j_selec.1": ("SELECT BOARD", "c"),
    "j_selec.2": ("SELECT COURSE", "c"), "j_selec.3": ("SELECT RIDER", "c"), "j_selec.4": ("SELECT BOARD", "c"),
    "j_selec.5": ("SELECT COURSE", "c"),
    "handica": ("HANDICAP", "c"), "on": ("ON", "c"), "off": ("OFF", "c"),
    "j_handi": ("HANDICAP", "c"), "j_on": ("ON", "c"), "j_off": ("OFF", "c"),
    "1p_spee": ("SPEED", "c"), "j_1p_te": ("TECHNIQUE", "c"), "j_1p_ba": ("BALANCE", "c"), "j_1p_ju": ("JUMP", "c"),
    "j_1p_po": ("POWER", "c"),
    "rank_1s": ("1st", "h", "c"), "rank_2n": ("2nd", "h", "c"), "rank_3r": ("3rd", "h", "c"),
    "round": ("Round", "m"), "last": ("Last", "m"), "round_1": ("1", "m"), "round_2": ("2", "m"), "round_3": ("3", "m"),
    "round_4": ("4", "m"), "round_5": ("5", "m"),
    "advance": ("ADVANCE TO NEXT ROUND", "c"), "level_c": ("Level Cleared", "m"), "goal_ne": ("New Record", "m"),
    "result_": ("TIME", "c"), "result_.1": ("SCORE", "c"), "result_.2": ("TOTAL", "c"),
    "normal": ("Normal|4COURSES", "m", "c"), "hard": ("Hard|5COURSES", "m", "c"), "expert": ("Expert|6COURSES", "m", "c"),
    "j_norma": ("Normal|4COURSES", "m", "c"), "j_hard": ("Hard|5COURSES", "m", "c"),
    "j_exper": ("Expert|6COURSES", "m", "c"),
    "new_rec": ("New Record", "m"), "new_rec.1": ("New Records", "m"),
    "1st_pla": ("1st place", "m"), "2nd_pla": ("2nd place", "m"), "3rd_pla": ("3rd place", "m"),
    "j_1st_r": ("1st place", "m"), "j_2nd_r": ("2nd place", "m"), "j_3rd_r": ("3rd place", "m"),
    "name_en": ("NAME ENTRY", "c"), "j_name_.8": ("NAME ENTRY", "c"),
    "tit_opt": ("Options", "m"), "records": ("Records", "m"), "replay": ("Replay", "m"), "sound": ("Sound", "m"),
    "languag": ("Language", "m"), "erase_s": ("Erase Saved Data", "m"),
    "j_tit_o": ("Options", "m"), "j_recor": ("Records", "m"), "j_repla.1": ("Replay", "m"), "j_sound": ("Sound", "m"),
    "j_langu": ("Language", "m"), "j_erase": ("Erase Saved Data", "m"),
    "ok": ("OK", "m"), "go_back": ("Go Back", "m"), "are_you": ("Are you sure?", "m"), "yes": ("Yes", "m"),
    "no": ("No", "m"),
    "j_ok": ("OK", "m"), "j_go_ba": ("Go Back", "m"), "j_are_y": ("Are you sure?", "m"), "j_yes": ("Yes", "m"),
    "j_no": ("No", "m"),
    "select_.14": ("Time", "m"), "select_.15": ("Score", "m"), "select_.16": ("Contest", "m"),
    "select_.17": ("Ghost", "m"), "select_.18": ("All Data", "m"),
    "j_optio.1": ("Time", "m"), "j_optio.2": ("Score", "m"), "j_optio.3": ("Contest", "m"), "j_optio.4": ("Ghost", "m"),
    "j_all_d": ("All Data", "m"),
    "tit_rec": ("Records", "m"), "tit_bes": ("Best Times", "m"), "tit_bes.1": ("Best Scores", "m"),
    "tit_bes.2": ("Best Contest Scores", "m"), "tit_rep": ("Replay", "m"), "tit_era": ("Erase Saved Data", "m"),
    "tit_lan": ("Language", "m"), "tit_sou": ("Sound", "m"),
    "j_tit_r": ("Records", "m"), "j_tit_b": ("Best Times", "m"), "j_tit_b.1": ("Best Scores", "m"),
    "j_tit_b.2": ("Best Contest Scores", "m"), "j_tit_r.1": ("Replay", "m"), "j_tit_e": ("Erase Saved Data", "m"),
    "j_tit_l": ("Language", "m"), "j_tit_s": ("Sound", "m"),
    "bgm": ("BGM", "c"), "se": ("SE", "c"), "voice": ("VOICE", "c"), "english": ("English", "m"),
    "japanes": ("Japanese", "m"),
    "j_bgm": ("BGM", "c"), "j_se": ("SE", "c"), "j_voice": ("VOICE", "c"), "j_engli": ("English", "m"),
    "j_japan": ("Japanese", "m"),
    "tit_upg": ("Update Ghost", "m"), "time_gh": ("Time Ghost", "m"), "score_g": ("Score Ghost", "m"),
    "save_gh": ("Save ghost data?", "m"), "current": ("Current saved data|will be erased.", "m", "c"),
    "j_tit_u": ("Update Ghost", "m"), "j_time_.1": ("Time Ghost", "m"), "j_score": ("Score Ghost", "m"),
    "j_save_": ("Save ghost data?", "m"), "j_curre": ("Current saved data will be erased.", "m"),
    "trick_l": ("Trick List", "m"), "j_trick.1": ("Trick List", "m"),
}


def _series(names, texts, style, align="l"):
    for n, t in zip(names, texts):
        TEXT[n] = (t, style, align)


_series(["air_mak", "half_pi", "lake", "peak", "golden", "mountai", "dragon", "deadly"], COURSES, "s")
_series(["option_"] + ["option_.%d" % i for i in range(1, 8)], COURSES, "s")
_series(["j_name_"] + ["j_name_.%d" % i for i in range(1, 8)], COURSES, "c")
_B1 = ["tahoe15", "merlot1", "bline14", "scout15", "tahoe15.1", "1p_scou", "merlot1.1", "b_line1"]
_B2 = ["2p_taho", "2p_merl", "2p_b_li", "2p_scou", "2p_taho.1", "2p_scou.1", "2p_merl.1", "2p_b_li.1"]
_B3 = ["j_tahoe", "j_merlo", "j_b_lin", "j_scout", "j_tahoe.1", "j_scout.1", "j_merlo.1", "j_b_lin.1"]
_B4 = ["j_2p_ta", "j_2p_me", "j_2p_b_", "j_2p_sc", "j_2p_ta.1", "j_2p_sc.1", "j_2p_me.1", "j_2p_b_.1"]
for _b in (_B1, _B2):
    _series(_b, BOARDS, "s")
for _b in (_B3, _B4):
    _series(_b, BOARDS, "c")
_series(["speed", "techniq", "balance", "jump", "power"], RIDER_STATS, "c")
_series(["2p_max_", "2p_tech", "2p_bala", "2p_jump", "2p_powe"], RIDER_STATS, "c")
_series(["j_2p_sp", "j_2p_te", "j_2p_ba", "j_2p_ju", "j_2p_po"], ["SPEED"] + RIDER_STATS[1:], "c")
_series(["acceler", "respons", "edge", "frex", "stabili"], BOARD_STATS, "c")
_series(["2p_acce", "2p_resp", "2p_edge", "2p_frex", "2p_stab"], BOARD_STATS, "c")
_series(["j_1p_ac", "j_1p_re", "j_1p_ed", "j_1p_fl", "j_1p_su"], BOARD_STATS, "c")
_series(["j_2p_ac", "j_2p_re", "j_2p_ed", "j_2p_fl", "j_2p_su"], BOARD_STATS, "c")

NAME_ENTRY = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890.?!") + ["SPC", "DEL", "END", "_"]


def name_entry(key, d):
    """Name-entry strip: 43 cells of 22 px, bright glyphs on a light ground."""
    w, h = d["w"], d["h"]
    m = np.zeros((h, w), np.float32)
    for i, c in enumerate(NAME_ENTRY):
        x = i * 22
        if c == "_":
            m[h - 5:h - 3, x + 3:x + 19] = 1
        elif len(c) > 1:
            fit(m, c, "c", (x + 1, 7, x + 21, h - 7), "c", stretch=2.0)
        else:
            fit(m, c, "h", (x + 2, 3, x + 20, h - 3), "c", stretch=1.0)
    return grey(m * (15 / 255.0) + 240 / 255.0)


FLOW_SPECIAL = {
    "result_.3": strip("0123456789'\"", "h", 16),
    "record_.1": strip("0123456789'\"", "h", 16),
    "record_": name_entry,
    "stereo_": boxed("Stereo", "stereo"), "mono_mo": boxed("Mono", "mono"), "headset": boxed("Headset", "headset"),
    "j_stere": boxed("Stereo", "stereo"), "j_mono_": boxed("Mono", "mono"), "j_heads": boxed("Headset", "headset"),
}

N64PROC = list("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ&-'\"/.") + [" ", "<", ">", "+"]
TITPROC = list("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-.") + ["°", "!", ",", "/"]


def arrows(fn, cw, ch, cols):
    """Replace the '<' / '>' cells of a font sheet by solid triangles."""
    def out(key, d):
        img = fn(key, d)
        for i, c in enumerate(N64PROC):
            if c in "<>":
                x, y = (i % cols) * cw, (i // cols) * ch
                im = Image.new("L", (cw * 4, ch * 4), 0)
                pts = [(12, ch * 2), (cw * 4 - 14, 8), (cw * 4 - 14, ch * 4 - 8)]
                if c == ">":
                    pts = [(cw * 4 - p[0], p[1]) for p in pts]
                ImageDraw.Draw(im).polygon(pts, fill=255)
                img[y:y + ch, x:x + cw] = np.asarray(im.resize((cw, ch), Image.LANCZOS), np.float32)[..., None]
        return img
    return out


def debug_font(key, d):
    """8x8 cells, 16 per row, ASCII order; control codes stay blank."""
    m = np.zeros((d["h"], d["w"]), np.float32)
    f = font("p", 8)
    im = Image.new("L", (d["w"], d["h"]), 0)
    dr = ImageDraw.Draw(im)
    for c in range(0x20, 0x7F):
        dr.text(((c % 16) * 8, (c // 16) * 8), chr(c), fill=255, font=f)
    m = (np.asarray(im, np.float32) >= 128) * 255.0
    return np.stack([m, m, m, m], -1)


FIXED = {
    "gamegfx@8": strip("0123456789\"'", "h", 16, fill=0.85),
    "gamegfx@850": strip("0123456789", "h", 32, 32, fill=0.72, cols=1),
    "gamegfx@1C58": strip("0123456789'", "h", 32, fill=0.85),
    "gamegfx@33C0": strip("0123456789", "h", 24, fill=0.85),
    "gamegfx@3E18": strip("0123456789", "c", 16, bg=32.0, fill=0.72),
    "n64proc@D8": arrows(strip(N64PROC, "c", 16, 12, fill=0.8, cols=2), 16, 12, 2),
    "titproc@548": strip(TITPROC, "m", 24, 17, fill=0.62, cols=3),
    "bootup@2B3D8": debug_font,
}


def hooks(spec=None):
    spec = spec or json.load(open(os.path.join(HERE, "spec", "textures.json")))
    out = {}
    for key, d in spec.items():
        n = d.get("name")
        if key in FIXED:
            out[key] = FIXED[key]
        elif n in FLOW_SPECIAL:
            out[key] = FLOW_SPECIAL[n]
        elif n in TEXT and d["fmt"] == "i8":
            t = TEXT[n]
            out[key] = label(t[0], t[1], t[2] if len(t) > 2 else "l")
    try:
        from . import pictures
        out.update(pictures.hooks(spec))
    except ImportError:
        pass
    return out


def sheet(path, flt="", zoom=1):
    spec = json.load(open(os.path.join(HERE, "spec", "textures.json")))
    hk = hooks(spec)
    tiles = []
    for key, fn in hk.items():
        d = spec[key]
        nm = d.get("name", key)
        if flt and flt not in key and flt not in nm:
            continue
        img = np.asarray(fn(key, d), np.float32)
        if d["fmt"] in ("i8", "i4"):
            rgb = img[..., :3]
        else:
            a = img[..., 3:] / 255.0
            rgb = img[..., :3] * a + np.array([60, 30, 90]) * (1 - a)
        t = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
        if zoom > 1:
            t = t.resize((t.width * zoom, t.height * zoom), Image.NEAREST)
        if t.width > 1000:
            a = np.asarray(t)
            t = Image.fromarray(np.concatenate([a[:, :a.shape[1] // 2], a[:, a.shape[1] // 2:a.shape[1] // 2 * 2]], 0))
        tiles.append((nm[:max(4, t.width // 6)], t))
    W, x, y, rh, pos = 1800, 0, 0, 0, []
    for l, t in tiles:
        tw = max(t.width, 6 * len(l)) + 6
        if x + tw > W:
            x, y, rh = 0, y + rh + 14, 0
        pos.append((x, y))
        x += tw
        rh = max(rh, t.height)
    s = Image.new("RGB", (W, y + rh + 14), (25, 25, 60))
    dr = ImageDraw.Draw(s)
    for (l, t), (x, y) in zip(tiles, pos):
        dr.text((x, y), l, fill=(255, 255, 0))
        s.paste(t, (x, y + 11))
    s.save(path)
    print(len(tiles), "drawn images ->", path, s.size)


if __name__ == "__main__":
    sheet(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "", int(sys.argv[3]) if len(sys.argv) > 3 else 1)
