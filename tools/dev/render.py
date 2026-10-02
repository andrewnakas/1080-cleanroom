import numpy as np


def render(b, fmt, w):
    a = np.frombuffer(b, np.uint8)
    if fmt == "i4":
        a = np.stack([a >> 4, a & 15], 1).reshape(-1) * 17
    elif fmt == "ia4":
        a = np.stack([a >> 4, a & 15], 1).reshape(-1)
        a = (a >> 1) * 36 * (a & 1)
    elif fmt == "i1":
        a = np.unpackbits(a) * 255
    elif fmt == "rgba32":
        h = len(b) // (4 * w)
        v = np.frombuffer(b[:h * w * 4], np.uint8).reshape(h, w, 4).astype(np.float32)
        return (v[..., :3] * v[..., 3:] / 255 + (255 - v[..., 3:]) * 0.4).astype(np.uint8)
    elif fmt == "rgba16":
        v = np.frombuffer(b[:len(b) // 2 * 2], ">u2")
        h = len(v) // w
        v = v[:h * w].reshape(h, w)
        return np.stack([((v >> s) & 31) * 8 for s in (11, 6, 1)], -1).astype(np.uint8)
    h = len(a) // w
    g = a[:h * w].reshape(h, w).astype(np.uint8)
    return np.stack([g, g, g], -1)
