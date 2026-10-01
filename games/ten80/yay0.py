"""Yay0 encoder (our own; hash chains + one-step lazy matching). Decoder is romfs.yay0_decode."""
import struct

WINDOW, MAXLEN, CHAIN = 0x1000, 0x111, 48


def _longest(data, pos, cands, n):
    best_len, best_pos = 0, 0
    limit = min(MAXLEN, n - pos)
    lo = pos - WINDOW
    for c in reversed(cands):
        if c < lo:
            break
        if best_len and data[c + best_len] != data[pos + best_len]:
            continue
        l = 0
        while l < limit and data[c + l] == data[pos + l]:
            l += 1
        if l > best_len:
            best_len, best_pos = l, c
            if l == limit:
                break
    return best_len, best_pos


def encode(data):
    n = len(data)
    table = {}
    links, chunks = bytearray(), bytearray()
    mask_words, mask, bits = [], 0, 0

    def insert(p):
        if p + 3 <= n:
            lst = table.setdefault(data[p:p + 3], [])
            lst.append(p)
            if len(lst) > CHAIN * 2:
                del lst[:CHAIN]

    def find(p):
        if p + 3 > n:
            return 0, 0
        c = table.get(data[p:p + 3])
        return _longest(data, p, c[-CHAIN:], n) if c else (0, 0)

    pos = 0
    pending = None
    while pos < n:
        l, mp = pending if pending else find(pos)
        pending = None
        if l >= 3:
            insert(pos)
            l2, mp2 = find(pos + 1) if pos + 1 < n else (0, 0)
            if l2 > l + 1:
                l, pending = 0, (l2, mp2)       # literal now, better match next
        if l >= 3:
            dist = pos - mp - 1
            if l >= 18:
                links += struct.pack(">H", dist)
                chunks.append(l - 18)
            else:
                links += struct.pack(">H", ((l - 2) << 12) | dist)
            for p in range(pos + 1, pos + l):
                insert(p)
            pos += l
            mask <<= 1
        else:
            if l < 3 and not pending:
                insert(pos)
            chunks.append(data[pos])
            pos += 1
            mask = (mask << 1) | 1
        bits += 1
        if bits == 32:
            mask_words.append(mask)
            mask, bits = 0, 0
    if bits:
        mask_words.append(mask << (32 - bits))
    lo = 16 + 4 * len(mask_words)
    co = lo + len(links)
    return b"Yay0" + struct.pack(">III", n, lo, co) + b"".join(struct.pack(">I", m) for m in mask_words) + bytes(links) + bytes(chunks)
