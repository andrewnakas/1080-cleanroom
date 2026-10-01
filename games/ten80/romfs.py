"""1080 Snowboarding ROM file system (libgdl "USO" section streams).

The ROM holds two flat streams of sections (main at 0xB7C0, boot at 0xD9FDB0):

    u32 type, u32 size, u16 flags, u16 junk, data[size]      (no data for Bss)

type 0 (Info, size 0x2C) starts a file: magic 0x12345678, id, 1, name[28] (NUL + leaked junk), u32.
Other types: 1 Sym, 2-4 relocs, 5 Text, 6 Data, 7 RoData, 8 Bss, 9 EntrySym, 10 EndOfFile, 11 End,
12 BinaryData.  flags 0x1001 = Yay0-compressed data (size = compressed size).

    python -m games.ten80.romfs <rom>          one-screen summary
"""
import struct
import sys

MAGIC = 0x12345678
STREAMS = (0xB7C0, 0xD9FDB0)
NAMES = {0: "Info", 1: "Sym", 2: "TextReloc", 3: "DataReloc", 4: "RoDataReloc", 5: "Text", 6: "Data",
         7: "RoData", 8: "Bss", 9: "EntrySym", 10: "EndOfFile", 11: "End", 12: "Binary", 13: "DiskInfo"}
NODATA = (8,)


class Section:
    __slots__ = ("off", "type", "size", "flags", "junk", "file")

    def __init__(self, off, type_, size, flags, junk, file):
        self.off, self.type, self.size, self.flags, self.junk, self.file = off, type_, size, flags, junk, file

    @property
    def data_off(self):
        return self.off + 12

    @property
    def yay0(self):
        return self.flags == 0x1001

    def __repr__(self):
        return f"<{self.file}:{NAMES.get(self.type, self.type)} @{self.off:X} +{self.size:X} f{self.flags:04X}>"


def walk(rom, start):
    """Yield sections of one stream until the type is not a known one."""
    o, name = start, None
    while o + 12 <= len(rom):
        t, size, flags, junk = struct.unpack_from(">IIHH", rom, o)
        if t > 13 or flags not in (0x0800, 0x1000, 0x1001):
            break
        if t == 0:
            if size != 0x2C or struct.unpack_from(">I", rom, o + 12)[0] != MAGIC:
                break
            name = rom[o + 24:o + 52].split(b"\0")[0].decode("ascii")
        s = Section(o, t, size, flags, junk, name)
        yield s
        o += 12 + (0 if t in NODATA else size)


def sections(rom):
    out = []
    for st in STREAMS:
        out += list(walk(rom, st))
    return out


def files(rom):
    """name -> list of sections (Info first). <null> entries are dropped."""
    out = {}
    for s in sections(rom):
        if s.file and s.file != "<null>":
            out.setdefault(s.file, []).append(s)
    return out


def yay0_decode(buf):
    assert buf[:4] == b"Yay0"
    n, lo, co = struct.unpack_from(">III", buf, 4)
    out = bytearray(n)
    mo, d, mask, bits = 16, 0, 0, 0
    while d < n:
        if bits == 0:
            mask = struct.unpack_from(">I", buf, mo)[0]
            mo += 4
            bits = 32
        if mask & 0x80000000:
            out[d] = buf[co]
            co += 1
            d += 1
        else:
            v = (buf[lo] << 8) | buf[lo + 1]
            lo += 2
            cnt = v >> 12
            if cnt == 0:
                cnt = buf[co] + 18
                co += 1
            else:
                cnt += 2
            src = d - (v & 0xFFF) - 1
            for _ in range(cnt):
                out[d] = out[src]
                d += 1
                src += 1
        mask = (mask << 1) & 0xFFFFFFFF
        bits -= 1
    return bytes(out)


def payload(rom, s):
    raw = rom[s.data_off:s.data_off + s.size]
    return yay0_decode(raw) if s.yay0 else raw


def main(argv):
    rom = open(argv[1], "rb").read()
    fs = files(rom)
    secs = sections(rom)
    print(f"{len(fs)} files, {len(secs)} sections, streams end at "
          + ", ".join(f"{max(s.off + 12 + (0 if s.type in NODATA else s.size) for s in walk(rom, st)):X}" for st in STREAMS))
    for name, ss in fs.items():
        parts = []
        for s in ss[1:]:
            if s.type in (10, 11):
                continue
            n = NAMES.get(s.type, str(s.type))
            parts.append(f"{n}{'*' if s.yay0 else ''}:{s.size:X}")
        print(f"{ss[0].off:7X} {name:18s} " + " ".join(parts)[:150])


if __name__ == "__main__":
    main(sys.argv)
