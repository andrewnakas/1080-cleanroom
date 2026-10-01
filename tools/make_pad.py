"""Write a game's touch-pad script: its settings followed by the shared pad library.

    python tools/make_pad.py games/sf64/pad.json D:/n64work/sf64/site/touch.js

The library is ports/web/pad/cleanroom-pad.js (one copy for every N64 build). The settings file is optional
JSON with any of: labels, hide, hint, adapter, map, canvas, takeover (see the library header).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "ports", "web", "pad", "cleanroom-pad.js")


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    cfg_path, out = sys.argv[1], sys.argv[2]
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    lib = open(LIB, encoding="utf-8").read()
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("window.CLEANROOM_PAD = " + json.dumps(cfg, ensure_ascii=False) + ";\n" + lib)
    print("pad ->", out, "(%d settings)" % len(cfg))


if __name__ == "__main__":
    main()
