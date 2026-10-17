"""DXT1/DXT5 block decoder (numpy). decode(data, w, h, fmt, swap16) -> RGBA uint8 array (h, w, 4).
swap16=True byte-swaps every 16-bit word first (tests the PS3 big-endian storage hypothesis)."""
import numpy as np

def _rgb565(c):
    r = ((c >> 11) & 31) * 255 // 31; g = ((c >> 5) & 63) * 255 // 63; b = (c & 31) * 255 // 31
    return np.stack([r, g, b], -1).astype(np.int32)

def _color_block(blk, dxt1):
    c0 = blk[:, 0].astype(np.uint32) | (blk[:, 1].astype(np.uint32) << 8)
    c1 = blk[:, 2].astype(np.uint32) | (blk[:, 3].astype(np.uint32) << 8)
    idx = blk[:, 4].astype(np.uint32) | (blk[:, 5].astype(np.uint32) << 8) | (blk[:, 6].astype(np.uint32) << 16) | (blk[:, 7].astype(np.uint32) << 24)
    p0, p1 = _rgb565(c0), _rgb565(c1)
    four = (c0 > c1)[:, None] | (not dxt1)
    p2 = np.where(four, (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four, (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)                       # (n,4,3)
    sel = (idx[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3   # (n,16)
    rgb = np.take_along_axis(pal, sel[..., None].astype(np.int64).repeat(3, -1), 1)
    a = np.where((dxt1 & ~four.ravel())[:, None] & (sel == 3), 0, 255)
    return rgb, a

def _alpha_block(blk):
    a0 = blk[:, 0].astype(np.int32); a1 = blk[:, 1].astype(np.int32)
    bits = np.zeros(len(blk), np.uint64)
    for k in range(6): bits |= blk[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
    sel = ((bits[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))) & np.uint64(7)).astype(np.int64)
    pal = np.zeros((len(blk), 8), np.int32); pal[:, 0] = a0; pal[:, 1] = a1
    big = a0 > a1
    for k in range(2, 8):
        pal[:, k] = np.where(big, ((8 - k) * a0 + (k - 1) * a1) // 7, 0)
    for k in range(2, 6):
        pal[:, k] = np.where(big, pal[:, k], ((6 - k) * a0 + (k - 1) * a1) // 5)
    pal[:, 6] = np.where(big, pal[:, 6], 0); pal[:, 7] = np.where(big, pal[:, 7], 255)
    return np.take_along_axis(pal, sel, 1)

def decode(data, w, h, fmt, swap16=False):
    bs = 8 if fmt == 10 else 16
    bw, bh = max(1, w // 4), max(1, h // 4)
    raw = np.frombuffer(data[:bw * bh * bs], np.uint8).copy()
    if swap16: raw = raw.reshape(-1, 2)[:, ::-1].ravel()
    blk = raw.reshape(-1, bs)
    if fmt == 10: rgb, a = _color_block(blk, True)
    else: rgb, _ = _color_block(blk[:, 8:], False); a = _alpha_block(blk[:, :8])
    img = np.concatenate([rgb, a[..., None]], -1).reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return img.astype(np.uint8)

def flip_v(data, w, h, fmt, mips):
    """Vertically flip a whole mip chain. Unity 3.5 stores rows bottom-up (GL); DDS readers expect top-down (E87).
    DXT: reverse block rows, then the pixel rows inside each block (only the first min(h,4) rows for tiny mips)."""
    out, off = bytearray(), 0
    for lv in range(mips):
        lw, lh = max(1, w >> lv), max(1, h >> lv)
        if fmt in (10, 12):
            bs = 8 if fmt == 10 else 16; bw, bh = (lw + 3) // 4, (lh + 3) // 4; n = bw * bh * bs
            blk = np.frombuffer(bytes(data[off:off + n]), np.uint8).reshape(bh, bw, bs)[::-1].copy()
            rows = min(lh, 4)
            blk[..., bs - 4:bs - 4 + rows] = blk[..., bs - 4:bs - 4 + rows][..., ::-1]   # colour indices: 1 byte per row
            if fmt == 12:   # alpha indices: 48 bits little-endian, 12 bits per row
                a = sum(blk[..., 2 + i].astype(np.uint64) << np.uint64(8 * i) for i in range(6))
                r = [(a >> np.uint64(12 * k)) & np.uint64(0xFFF) for k in range(4)]
                r[:rows] = r[:rows][::-1]
                a = sum(r[k] << np.uint64(12 * k) for k in range(4))
                for i in range(6): blk[..., 2 + i] = ((a >> np.uint64(8 * i)) & np.uint64(0xFF)).astype(np.uint8)
        else:
            bpp = {5: 4, 4: 4, 3: 3}[fmt]; n = lw * lh * bpp
            blk = np.frombuffer(bytes(data[off:off + n]), np.uint8).reshape(lh, lw * bpp)[::-1]
        out += blk.tobytes(); off += n
    return bytes(out) + bytes(data[off:])

def _selftest_flip(data, w, h, fmt, mips):
    """flip_v must equal a row flip of the decoded image on every mip level (assert-based)."""
    f = flip_v(data, w, h, fmt, mips); off = 0
    for lv in range(mips):
        lw, lh = max(1, w >> lv), max(1, h >> lv); bs = 8 if fmt == 10 else 16; n = ((lw + 3) // 4) * ((lh + 3) // 4) * bs
        a = decode(data[off:off + n], ((lw + 3) // 4) * 4, ((lh + 3) // 4) * 4, fmt)[:lh, :lw]
        b = decode(f[off:off + n], ((lw + 3) // 4) * 4, ((lh + 3) // 4) * 4, fmt)[:lh, :lw]
        assert (a[::-1] == b).all(), f"flip mismatch at mip {lv} ({lw}x{lh})"
        off += n
    return True
