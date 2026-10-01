"""Stage the shared touch pad into a published N64Wasm clean-room site.

    python tools/roll_pad.py sf64 [--work D:/n64work/padroll]

Clones the game's gh-pages branch, writes touch.js (settings from ports/web/pad/games/<id>.json plus the shared
library) and, for sites published before the pad existed, adds the script tag and the module-ready hook. Only
our own JavaScript changes: no ROM or generated asset is touched. The result is committed locally and NOT pushed;
review it, then `git -C <work>/<id> push origin gh-pages`.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = "        if (window.cleanroomTouchWanted) window.cleanroomTouchInstall(myClass);\n"
ANCHOR = "        if (rom) { myClass.rom_name = myClass.extractRomName(rom); myClass.load_url(rom); }"
TAG = '<script src="touch.js"></script>\n</head>'
# (old, new) text swaps in index.html per game.
RETIRE = {
    "dkr": (('<script src="touchpad.js"></script>', ''),),
    "mm": (('if("1"===t||"0"!==t&&matchMedia("(pointer: coarse)").matches){document.body.classList.add("touch")',
            'if(false){document.body.classList.add("touch")'),),
}


def run(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("--work", default="D:/n64work/padroll")
    a = ap.parse_args()
    site = os.path.join(a.work, a.game)
    if os.path.exists(site):
        raise SystemExit("exists: %s (remove it to stage again)" % site)
    os.makedirs(a.work, exist_ok=True)
    run("git", "clone", "-q", "--depth", "1", "-b", "gh-pages",
        "https://github.com/andrewnakas/%s-cleanroom.git" % a.game, site)
    run(sys.executable, os.path.join(HERE, "make_pad.py"),
        os.path.join(HERE, "..", "ports", "web", "pad", "games", a.game + ".json"), os.path.join(site, "touch.js"))
    # Shells that shipped their own touch code: retire it so the shared pad is the only one.
    index = os.path.join(site, "index.html")
    html = open(index, encoding="utf-8", newline="").read()
    for old, new in RETIRE.get(a.game, ()):
        if old in html:
            html = html.replace(old, new, 1)
            print("retired the old touch code")
    open(index, "w", encoding="utf-8", newline="").write(html)
    for name, anchor, new in (("script.js", ANCHOR, HOOK + ANCHOR), ("index.html", "</head>", TAG)):
        path = os.path.join(site, name)
        if not os.path.exists(path):   # script.js is N64Wasm's; other runtimes only need the tag
            continue
        src = open(path, encoding="utf-8", newline="").read()   # keep the file's own line endings
        marker = "cleanroomTouchInstall" if name == "script.js" else 'src="touch.js"'
        if marker in src:
            continue
        if anchor not in src:
            raise SystemExit("%s: hook point not found" % name)
        eol = "\r\n" if "\r\n" in src else "\n"
        open(path, "w", encoding="utf-8", newline="").write(src.replace(anchor, new.replace("\n", eol), 1))
        print("patched", name)
    run("git", "add", "-A", cwd=site)
    run("git", "-c", "user.name=andre", "-c", "user.email=treesixtyweather@gmail.com", "commit", "-qm",
        "Shared touch pad: D-pad, L button, controller hot-plug\n\n"
        "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>", cwd=site)
    run("git", "--no-pager", "show", "--stat", "--format=%h %s", "HEAD", cwd=site)


if __name__ == "__main__":
    main()
