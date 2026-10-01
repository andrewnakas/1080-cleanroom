"""One USO/bin file of the ROM file system: sections, symbols, data relocations.

Sym entries are 12 bytes: u16 type ('b' local data, 'd'/'t'/'R'/'T' section, 1 = import), u16 junk,
u32 value, u32 junk/import id.  DataReloc entries are 12 bytes: u32 (symbol index << 4 | 4),
u32 offset in Data, u32 1 (a 32-bit pointer).
"""
import bisect
import struct

from . import romfs


class Uso:
    def __init__(self, rom, name, secs):
        self.name, self.secs = name, secs
        self.by = {}
        for s in secs:
            self.by.setdefault(s.type, s)
        self.data = romfs.payload(rom, self.by[6]) if 6 in self.by else b""
        self.binary = romfs.payload(rom, self.by[12]) if 12 in self.by else b""
        sy = romfs.payload(rom, self.by[1]) if 1 in self.by else b""
        self.syms = [struct.unpack_from(">HHII", sy, i) for i in range(0, len(sy), 12)]
        r = romfs.payload(rom, self.by[3]) if 3 in self.by else b""
        self.rel = {}
        for i in range(0, len(r), 12):
            a, o, _ = struct.unpack_from(">III", r, i)
            self.rel[o] = self.syms[a >> 4]
        self.vals = sorted(set(v for t, _, v, _ in self.syms if t == 0x62 and v <= len(self.data)) | {0, len(self.data)})

    def target(self, off):
        """Data offset a relocated pointer at `off` points to (None: no reloc or import)."""
        s = self.rel.get(off)
        if s is None or s[0] != 0x62:
            return None
        return s[2] + struct.unpack_from(">I", self.data, off)[0]

    def blob_end(self, v):
        i = bisect.bisect_right(self.vals, v)
        return self.vals[i] if i < len(self.vals) else len(self.data)


def load(rom):
    return {n: Uso(rom, n, ss) for n, ss in romfs.files(rom).items()}
