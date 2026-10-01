"""Give our ROM the emulator's 1080 Snowboarding settings (SRAM save type, rumble).

mupen64plus looks ROMs up by MD5 in a database compiled into the core; an unknown
ROM gets no EEPROM and the game may stall. The database has a hack entry whose
RefMD5 is the US game's, so it inherits every US setting: we point that entry at
our ROM's MD5 (same length, so a plain byte replacement in the wasm).

    python ports/ejs/patch_core.py <rom.z64> <cores dir in, e.g. data/cores> <cores dir out>
"""
import hashlib
import io
import os
import sys

import py7zr

SLOT = b"[E428181D573E25DCC0DC7F9F3BF4D1E1]"      # "1080 Snowboarding (JU) (M2) [b1]", RefMD5 = JU (SRAM)
CORES = ["mupen64plus_next-wasm.data", "mupen64plus_next-legacy-wasm.data"]


def patch(src, dst, md5):
    import tempfile
    tmp = tempfile.mkdtemp(prefix="core_")
    with py7zr.SevenZipFile(src) as z:
        names = [n for n in z.getnames()]
        z.extractall(tmp)
    files = {n: open(os.path.join(tmp, n), "rb").read() for n in names if os.path.isfile(os.path.join(tmp, n))}
    n = 0
    for name, data in files.items():
        if name.endswith(".wasm"):
            assert data.count(SLOT) == 1, f"{name}: slot not found"
            files[name] = data.replace(SLOT, b"[" + md5.upper().encode() + b"]")
            n += 1
    with py7zr.SevenZipFile(dst, "w") as z:
        for name, data in files.items():
            z.writef(io.BytesIO(data), name)
    return n


def main(argv):
    rom, cin, cout = argv[1:4]
    md5 = hashlib.md5(open(rom, "rb").read()).hexdigest()
    os.makedirs(cout, exist_ok=True)
    for c in CORES:
        if os.path.exists(os.path.join(cin, c)):
            patch(os.path.join(cin, c), os.path.join(cout, c), md5)
    print(f"patch_core: 1080 settings entry -> md5 {md5}")


if __name__ == "__main__":
    main(sys.argv)
