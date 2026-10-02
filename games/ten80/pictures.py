"""Our own colour pictures for the menu images (flowimgs): logo, cards, rider name plates with flags,
portraits, course banners, button and stick icons.  Nothing here reads retail pixels: sizes and the kept
grid / outline come from the spec, the drawings are ours.

    hooks(spec) -> {spec key: fn(key, d) -> float RGBA (h, w, 4)}
"""
import math

import numpy as np
from PIL import Image, ImageDraw

from cleanroom.gfx import facepaint

from . import drawn

SS = 4


# ------------------------------------------------------------------ helpers

def canvas(d, rgba=(0, 0, 0, 0)):
    im = Image.new("RGBA", (d["w"] * SS, d["h"] * SS), rgba)
    return im, ImageDraw.Draw(im)


def done(im, d):
    return np.asarray(im.resize((d["w"], d["h"]), Image.LANCZOS), np.float32)


def grow(mask, r):
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r + 1:
                out = np.maximum(out, np.roll(np.roll(mask, dy, 0), dx, 1))
    return out


def ink(img, mask, top, bottom=None, outline=None, r=1):
    """Composite text coverage onto a float RGBA image: vertical gradient fill, optional dark outline."""
    h, w = mask.shape
    if outline is not None:
        o = grow(mask, r)
        img[..., :3] = img[..., :3] * (1 - o[..., None]) + np.asarray(outline, np.float32) * o[..., None]
        img[..., 3] = np.maximum(img[..., 3], o * 255)
    ys = np.nonzero(mask.max(1) > 0.1)[0]
    t = np.zeros(h, np.float32)
    if len(ys) > 1:
        t = np.clip((np.arange(h) - ys[0]) / (ys[-1] - ys[0]), 0, 1).astype(np.float32)
    col = np.asarray(top, np.float32)[None, :] * (1 - t[:, None]) + np.asarray(bottom or top, np.float32)[None, :] * t[:, None]
    img[..., :3] = img[..., :3] * (1 - mask[..., None]) + col[:, None, :] * mask[..., None]
    img[..., 3] = np.maximum(img[..., 3], mask * 255)
    return img


def text_on(img, text, style, box, align="c", **kw):
    m = np.zeros(img.shape[:2], np.float32)
    drawn.fit(m, text, style, box, align)
    return ink(img, m, **kw)


def base(key, d):
    from . import generate
    return generate.base_image(key, d, 1.0)


# ------------------------------------------------------------------ logo and cards

def logo(key, d):
    w, h = d["w"], d["h"]
    img = np.zeros((h, w, 4), np.float32)
    m = np.zeros((h, w), np.float32)
    drawn.fit(m, "1080°", "b", (2, 2, w - 3, int(h * 0.72)), "c", stretch=1.6)
    ink(img, m, (235, 245, 255), (40, 90, 230), outline=(10, 20, 90), r=max(1, h // 60))
    text_on(img, "SNOWBOARDING", "c", (int(w * 0.12), int(h * 0.78), int(w * 0.88), h - 2), top=(255, 255, 255),
            outline=(10, 20, 90))
    return img


def card(lines, bg=(0, 0, 0, 255), fg=(235, 235, 235), style="c"):
    def fn(key, d):
        w, h = d["w"], d["h"]
        img = np.zeros((h, w, 4), np.float32)
        img[:] = bg
        n = len(lines)
        lh = min(h / (n + 1.0), w / 9.0)
        y = (h - lh * n) / 2
        for i, t in enumerate(lines):
            text_on(img, t, style, (6, int(y + i * lh + lh * 0.15), w - 6, int(y + (i + 1) * lh - lh * 0.15)), top=fg)
        if bg[3] == 0:
            img[..., 3] = (img[..., 3] > 0) * img[..., 3]
        return img
    return fn


def over_grid(text, style="m", top=(255, 255, 255), bottom=None, outline=(20, 20, 40), box=None, align="c"):
    def fn(key, d):
        img = base(key, d)
        w, h = d["w"], d["h"]
        b = box or (0.12, 0.2, 0.88, 0.8)
        return text_on(img, text, style, (int(b[0] * w), int(b[1] * h), int(b[2] * w), int(b[3] * h)), align, top=top,
                       bottom=bottom, outline=outline)
    return fn


# ------------------------------------------------------------------ rider name plates

def flag(kind, w, h):
    im = Image.new("RGB", (w * SS, h * SS), (250, 250, 250))
    dr = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    if kind == "jp":
        r = H * 0.3
        dr.ellipse((W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r), fill=(200, 20, 40))
    elif kind == "ca":
        dr.rectangle((0, 0, W * 0.25, H), fill=(215, 30, 40))
        dr.rectangle((W * 0.75, 0, W, H), fill=(215, 30, 40))
        cx, cy, r = W / 2, H / 2, H * 0.3
        dr.polygon([(cx, cy - r), (cx + r * 0.9, cy), (cx + r * 0.3, cy + r * 0.2), (cx, cy + r), (cx - r * 0.3, cy + r * 0.2),
                    (cx - r * 0.9, cy)], fill=(215, 30, 40))
    elif kind == "uk":
        dr.rectangle((0, 0, W, H), fill=(20, 40, 130))
        for wd, c in ((H * 0.3, (250, 250, 250)), (H * 0.12, (200, 20, 40))):
            dr.line((0, 0, W, H), fill=c, width=int(wd))
            dr.line((0, H, W, 0), fill=c, width=int(wd))
        for wd, c in ((H * 0.36, (250, 250, 250)), (H * 0.2, (200, 20, 40))):
            dr.line((W / 2, 0, W / 2, H), fill=c, width=int(wd))
            dr.line((0, H / 2, W, H / 2), fill=c, width=int(wd))
    elif kind == "us":
        for i in range(7):
            if i % 2 == 0:
                dr.rectangle((0, H * i / 7, W, H * (i + 1) / 7), fill=(200, 20, 40))
        dr.rectangle((0, 0, W * 0.42, H * 4 / 7), fill=(20, 40, 130))
    return np.asarray(im.resize((w, h), Image.LANCZOS), np.float32)


RIDERS = {"akar": ("Akari Hayami", "jp"), "ak": ("Akari Hayami", "jp"), "kima": ("Kensuke Kimachi", "jp"),
          "ki": ("Kensuke Kimachi", "jp"), "dion": ("Dion Blaster", "uk"), "di": ("Dion Blaster", "uk"),
          "rick": ("Ricky Winterborn", "ca"), "ri": ("Ricky Winterborn", "ca"), "rob": ("Rob Haywood", "us"),
          "ro": ("Rob Haywood", "us")}


def plate(name, kind):
    def fn(key, d):
        w, h = d["w"], d["h"]
        img = np.zeros((h, w, 4), np.float32)
        fw, fh = 22, 14
        fx, fy = w - fw - 6, (h - fh) // 2 + 2
        text_on(img, name, "s", (3, int(h * 0.14), fx - 5, int(h * 0.86)), "l", top=(200, 255, 190), bottom=(20, 170, 90),
                outline=(0, 40, 30))
        img[fy - 1:fy + fh + 1, fx - 1:fx + fw + 1] = (30, 30, 40, 255)
        img[fy:fy + fh, fx:fx + fw, :3] = flag(kind, fw, fh)
        return img
    return fn


# ------------------------------------------------------------------ portraits (facepaint briefs, ours)

def _eyes(y, dx, r, iris, look=(0.25, 0.1)):
    return [{"eye": {"c": [0.5 - dx + 0.03, y], "r": [r, r * 0.62], "iris": iris, "look": list(look), "border": 0.25}},
            {"eye": {"c": [0.5 + dx + 0.03, y], "r": [r, r * 0.62], "iris": iris, "look": list(look), "border": 0.25}}]


def _person(skin, shade, jacket, hair=None, hat=None, shades=False, iris=(70, 45, 25), lips=(150, 70, 70), long_hair=False,
            brow=(40, 25, 15)):
    ops = [{"e": [0.5, 1.08, 0.5, 0.3], "c": list(jacket)},                    # shoulders
           {"rect": [0.42, 0.7, 0.6, 0.9], "c": list(shade)}]                  # neck
    if long_hair:
        ops.append({"e": [0.52, 0.44, 0.35, 0.36], "c": list(hair)})
    ops += [{"sphere": [0.52, 0.48, 0.27, 0.33], "c": list(skin)},
            {"e": [0.26, 0.5, 0.04, 0.07], "c": list(shade)}]                  # ear
    if hair and not long_hair:
        ops.append({"poly": [[0.24, 0.42], [0.27, 0.2], [0.5, 0.1], [0.76, 0.2], [0.8, 0.42], [0.7, 0.28], [0.4, 0.26]],
                    "c": list(hair)})
    if long_hair:
        ops.append({"poly": [[0.2, 0.5], [0.26, 0.18], [0.52, 0.08], [0.8, 0.18], [0.86, 0.5], [0.74, 0.3], [0.5, 0.22],
                             [0.34, 0.3]], "c": list(hair)})
    if hat:
        ops += [{"poly": [[0.22, 0.4], [0.26, 0.16], [0.5, 0.05], [0.76, 0.14], [0.82, 0.4], [0.52, 0.32]], "c": list(hat)},
                {"line": [[0.22, 0.4], [0.52, 0.33], [0.82, 0.4]], "w": 0.07, "c": [int(c * 0.65) for c in hat]}]
    if shades:
        ops += [{"e": [0.42, 0.47, 0.11, 0.065], "c": [15, 15, 25]}, {"e": [0.66, 0.47, 0.11, 0.065], "c": [15, 15, 25]},
                {"line": [[0.3, 0.46], [0.78, 0.46]], "w": 0.03, "c": [15, 15, 25]},
                {"hl": [0.39, 0.45, 0.02]}, {"hl": [0.63, 0.45, 0.02]}]
    else:
        ops += _eyes(0.47, 0.115, 0.07, list(iris))
        ops += [{"line": [[0.33, 0.39], [0.47, 0.385]], "w": 0.03, "c": list(brow)},
                {"line": [[0.59, 0.385], [0.73, 0.39]], "w": 0.03, "c": list(brow)}]
    ops += [{"line": [[0.55, 0.5], [0.57, 0.59], [0.52, 0.6]], "w": 0.025, "c": list(shade)},
            {"arc": [0.54, 0.66, 0.1, 0.04, 20, 160], "w": 0.035, "c": list(lips)}]
    return ops


def _frame():
    return [{"line": [[0.02, 0.02], [0.98, 0.02], [0.98, 0.98], [0.02, 0.98], [0.02, 0.02]], "w": 0.06, "c": [200, 220, 255]}]


BG = {"grad": [[60, 110, 230], [15, 30, 120]]}
FACES = {
    "rob": _person((120, 78, 50), (85, 52, 32), (225, 110, 40), hair=(25, 20, 18), iris=(50, 30, 15), lips=(110, 55, 50)),
    "kensuke": _person((235, 190, 150), (190, 140, 105), (60, 60, 70), hat=(200, 30, 35), iris=(60, 40, 25)),
    "akari": _person((245, 205, 170), (205, 150, 120), (240, 200, 60), hair=(110, 60, 30), long_hair=True,
                     lips=(215, 80, 90), iris=(90, 55, 30)),
    "ricky": _person((245, 205, 165), (205, 155, 115), (210, 40, 40), hair=(235, 200, 90), hat=(40, 90, 200),
                     iris=(60, 110, 190)),
    "dion": _person((240, 200, 160), (200, 150, 115), (50, 110, 70), hair=(240, 215, 120), shades=True),
    "crystal": [{"e": [0.5, 1.08, 0.5, 0.3], "c": [120, 190, 255]}, {"sphere": [0.52, 0.48, 0.27, 0.33], "c": [150, 210, 255]},
                {"poly": [[0.3, 0.3], [0.5, 0.14], [0.72, 0.3], [0.52, 0.4]], "c": [225, 245, 255]},
                {"poly": [[0.3, 0.55], [0.44, 0.44], [0.48, 0.7]], "c": [95, 160, 240]},
                {"poly": [[0.74, 0.55], [0.6, 0.44], [0.58, 0.7]], "c": [200, 235, 255]},
                {"e": [0.42, 0.47, 0.06, 0.03], "c": [40, 90, 190]}, {"e": [0.64, 0.47, 0.06, 0.03], "c": [40, 90, 190]},
                {"line": [[0.45, 0.67], [0.63, 0.67]], "w": 0.03, "c": [40, 90, 190]}, {"hl": [0.4, 0.3, 0.035]}],
    "metal": [{"e": [0.5, 1.08, 0.5, 0.3], "c": [150, 150, 165]}, {"sphere": [0.52, 0.48, 0.27, 0.33], "c": [225, 195, 95]},
              {"arc": [0.52, 0.48, 0.2, 0.26, 200, 320], "w": 0.05, "c": [255, 245, 190]},
              {"e": [0.42, 0.47, 0.07, 0.035], "c": [60, 45, 15]}, {"e": [0.64, 0.47, 0.07, 0.035], "c": [60, 45, 15]},
              {"line": [[0.44, 0.67], [0.64, 0.67]], "w": 0.03, "c": [110, 85, 30]},
              {"arc": [0.52, 0.5, 0.3, 0.36, 20, 160], "w": 0.04, "c": [150, 120, 50]}, {"hl": [0.4, 0.3, 0.04]}],
    "panda": [{"e": [0.5, 1.1, 0.5, 0.3], "c": [25, 25, 30]}, {"e": [0.26, 0.2, 0.13, 0.13], "c": [20, 20, 25]},
              {"e": [0.78, 0.2, 0.13, 0.13], "c": [20, 20, 25]}, {"sphere": [0.52, 0.5, 0.33, 0.35], "c": [245, 245, 240]},
              {"e": [0.38, 0.46, 0.09, 0.11], "c": [20, 20, 25], "rot": 25}, {"e": [0.66, 0.46, 0.09, 0.11], "c": [20, 20, 25], "rot": -25},
              {"hl": [0.39, 0.45, 0.03]}, {"hl": [0.65, 0.45, 0.03]}, {"e": [0.52, 0.6, 0.05, 0.035], "c": [20, 20, 25]},
              {"arc": [0.52, 0.66, 0.08, 0.05, 20, 160], "w": 0.03, "c": [20, 20, 25]}],
}
PORTRAIT = {"rodman": "rob", "kimati": "kensuke", "akari": "akari", "winterb": "ricky", "haywood": "dion",
            "crystal": "crystal", "metal": "metal", "panda": "panda",
            "rank_ro": "rob", "rank_ki": "kensuke", "rank_ak": "akari", "rank_ri": "ricky", "rank_ro.1": "dion",
            "rank_cr": "crystal", "rank_me": "metal", "rank_pa": "panda",
            "rank_ro.2": "rob", "rank_ki.1": "kensuke", "rank_ak.1": "akari", "rank_wi": "ricky", "rank_ha": "dion",
            "rank_cr.1": "crystal", "rank_me.1": "metal", "rank_pa.1": "panda"}


def portrait(who):
    def fn(key, d):
        brief = {"base": BG, "ops": FACES[who] + _frame()}
        return facepaint.render(brief, d["w"], d["h"])
    return fn


# ------------------------------------------------------------------ icons

def level_mark(shape):
    def fn(key, d):
        im, dr = canvas(d, (245, 245, 245, 255))
        W, H = im.size
        dr.rectangle((0, 0, W - 1, H - 1), outline=(120, 120, 130, 255), width=SS)
        cx, cy, r = W / 2, H / 2, W * 0.3
        if shape == "circle":
            dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(20, 150, 60, 255))
        elif shape == "square":
            dr.rectangle((cx - r, cy - r, cx + r, cy + r), fill=(30, 110, 200, 255))
        else:
            dr.polygon([(cx, cy - r * 1.35), (cx + r, cy), (cx, cy + r * 1.35), (cx - r, cy)], fill=(15, 15, 20, 255))
        return done(im, d)
    return fn


def button(letter, colour, round_=True):
    def fn(key, d):
        im, dr = canvas(d)
        W, H = im.size
        dark = tuple(int(c * 0.55) for c in colour) + (255,)
        if round_:
            r = min(W, H) / 2 - SS
            dr.ellipse((W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r), fill=tuple(colour) + (255,), outline=dark, width=SS)
        else:
            dr.rounded_rectangle((SS, SS, W - SS, H - SS), SS * 3, fill=tuple(colour) + (255,), outline=dark, width=SS)
        img = done(im, d)
        w, h = d["w"], d["h"]
        s = min(w, h)
        return text_on(img, letter, "c", ((w - s) // 2 + s // 4, (h - s) // 2 + s // 4, (w + s) // 2 - s // 4, (h + s) // 2 - s // 4),
                       top=(255, 255, 255))
    return fn


def stick(angle):
    """Control stick pushed towards `angle` (degrees, 0 = up, clockwise)."""
    def fn(key, d):
        im, dr = canvas(d)
        W, H = im.size
        cx, cy, r = W / 2, H / 2, min(W, H) * 0.3
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(150, 150, 160, 255), outline=(70, 70, 80, 255), width=SS)
        a = math.radians(angle)
        dx, dy = math.sin(a), -math.cos(a)
        tip = (cx + dx * r * 1.55, cy + dy * r * 1.55)
        dr.line((cx, cy, cx + dx * r * 1.1, cy + dy * r * 1.1), fill=(220, 30, 40, 255), width=int(SS * 2.5))
        px, py = -dy, dx
        dr.polygon([tip, (cx + dx * r * 0.8 + px * r * 0.55, cy + dy * r * 0.8 + py * r * 0.55),
                    (cx + dx * r * 0.8 - px * r * 0.55, cy + dy * r * 0.8 - py * r * 0.55)], fill=(220, 30, 40, 255))
        dr.ellipse((cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3), fill=(235, 235, 240, 255))
        return done(im, d)
    return fn


def spin(direction):
    def fn(key, d):
        im, dr = canvas(d)
        W, H = im.size
        cx, cy, r = W / 2, H / 2 + SS, min(W, H) * 0.24
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(150, 150, 160, 255), outline=(70, 70, 80, 255), width=SS)
        R = r * 1.6
        dr.arc((cx - R, cy - R, cx + R, cy + R), 200, 340, fill=(220, 30, 40, 255), width=int(SS * 2.5))
        a = math.radians(340 if direction > 0 else 200)
        ex, ey = cx + R * math.cos(a), cy + R * math.sin(a)
        s = r * 0.7 * direction
        dr.polygon([(ex + s * 0.3, ey + abs(s) * 1.0), (ex - s * 0.9, ey - abs(s) * 0.2), (ex + s * 0.9, ey - abs(s) * 0.5)],
                   fill=(220, 30, 40, 255))
        return done(im, d)
    return fn


def ghost(key, d):
    img = np.zeros((d["h"], d["w"], 4), np.float32)
    return text_on(img, "GHOST", "b", (2, 6, d["w"] - 2, d["h"] - 6), top=(255, 120, 230), bottom=(190, 30, 170),
                   outline=(60, 0, 60))


# ------------------------------------------------------------------ table

NAMED = {
    "1080tit": logo, "1080tit.1": logo,
    "1998nin": card(["clean-room rebuild"], bg=(0, 0, 0, 0), fg=(255, 255, 255), style="m"),
    "lamarhi": card(["1080 CLEAN ROOM", "every texture and sound", "regenerated from", "coarse facts"]),
    "n64": card(["1080", "CLEAN", "ROOM"]),
    "green": level_mark("circle"), "blue": level_mark("square"), "black": level_mark("diamond"),
    "a_key_s": button("A", (40, 90, 220)), "b_key_s": button("B", (30, 160, 70)),
    "a_key": button("A", (40, 90, 220)), "b_key": button("B", (30, 160, 70)),
    "z_key": button("Z", (120, 120, 130), False), "r_key": button("R", (120, 120, 130), False),
    "yellow_": button("C", (225, 190, 30)),
    "up": stick(0), "right_u": stick(45), "right": stick(90), "right_d": stick(135), "down": stick(180),
    "left_do": stick(225), "left": stick(270), "left_up": stick(315),
    "spin_le": spin(-1), "spin_ri": spin(1),
    "ghost_m": ghost,
    "tit_all": over_grid("All Data"), "j_tit_a": over_grid("All Data"),
    "bestcon": over_grid("Best Contest Scores"), "j_bestc": over_grid("Best Contest Scores"),
}
for _i, _c in enumerate(drawn.COURSES):
    _kw = dict(style="s", top=(255, 240, 120), bottom=(250, 150, 30), outline=(40, 20, 0), box=(0.14, 0.16, 0.86, 0.84))
    NAMED["ranking" + (".%d" % _i if _i else "")] = over_grid(_c, **_kw)
    NAMED[["j_ranki", "j_rank_", "j_rank_.1", "j_rank_.2", "j_rank_.3", "j_rank_.4", "j_rank_.5", "j_rank_.6"][_i]] = \
        over_grid(_c, **_kw)
    NAMED["select_.%d" % (6 + _i)] = over_grid(_c, **_kw)
for _p in ("1p_", "2p_", "j_1p_", "j_2p_"):
    for _s in (("akar", "kima", "dion", "rick", "rob") if not _p.startswith("j_") else ("ak", "ki", "di", "ri", "ro")):
        NAMED[_p + _s] = plate(*RIDERS[_s])
for _n, _who in PORTRAIT.items():
    NAMED[_n] = portrait(_who)


def hooks(spec):
    out = {}
    for key, d in spec.items():
        n = d.get("name")
        if n in NAMED and d["fmt"] != "i8":
            out[key] = NAMED[n]
    return out
