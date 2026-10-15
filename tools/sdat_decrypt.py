"""SDAT (NPDRM free) decryptor, ported from RPCS3 rpcs3/Crypto/unedat.cpp + lz.cpp (see tools/ref_rpcs3).
Usage: sdat_decrypt.py <in.sdat> <out_file>
Every block's CMAC/HMAC is verified against the file's metadata; any mismatch aborts (no partial output)."""
import hashlib, hmac, struct, sys
from Crypto.Cipher import AES
from Crypto.Hash import CMAC

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps3keys import key
SDAT_KEY   = key("SDAT_KEY")
EDAT_KEY   = [key("EDAT_KEY_0"), key("EDAT_KEY_1")]
EDAT_HASH  = [key("EDAT_HASH_0"), key("EDAT_HASH_1")]
SDAT_FLAG, F_COMP, F_02, F_ENCKEY, F_10, F_20, F_DEBUG = 0x01000000, 1, 2, 8, 0x10, 0x20, 0x80000000
M32 = 0xFFFFFFFF

# ---- LZ (range coder) decompressor: direct port of RPCS3 lz.cpp ----
class _RC:
    __slots__ = ("rng", "code", "src", "data")
def _range(s):
    if not (s.rng >> 24):
        s.rng = (s.rng << 8) & M32
        s.code = ((s.code << 8) + s.data[s.src + 5]) & M32
        s.src += 1
def _bit(s, tmp, p, idx=None):
    """Returns (bit, new_index). idx None == no index tracking."""
    _range(s)
    c = tmp[p]
    val = ((s.rng >> 8) * c) & M32
    c = (c - (c >> 3)) & 0xFF
    if idx is not None: idx <<= 1
    if s.code < val:
        s.rng = val; tmp[p] = (c + 31) & 0xFF
        if idx is not None: idx += 1
        return 1, idx
    s.code = (s.code - val) & M32; s.rng = (s.rng - val) & M32; tmp[p] = c
    return 0, idx
def _direct_bits(s, i, index):
    _range(s)
    while index >= 5:
        i <<= 1; s.rng >>= 1
        if s.code < s.rng: i += 1
        else: s.code = (s.code - s.rng) & M32
        index -= 1
    return i
def _number(s, tmp, p, index):
    i = 1
    if index >= 3:
        _, i = _bit(s, tmp, p + 0x18, i)
        if index >= 4:
            _, i = _bit(s, tmp, p + 0x18, i)
            if index >= 5: i = _direct_bits(s, i, index)
    flag, i = _bit(s, tmp, p, i)
    if index >= 1:
        _, i = _bit(s, tmp, p + 0x8, i)
        if index >= 2: _, i = _bit(s, tmp, p + 0x10, i)
    return i, flag
def _word(s, tmp, p, index):
    i = 1; index //= 8
    if index >= 3:
        _, i = _bit(s, tmp, p + 4, i)
        if index >= 4:
            _, i = _bit(s, tmp, p + 4, i)
            if index >= 5: i = _direct_bits(s, i, index)
    flag, i = _bit(s, tmp, p, i)
    if index >= 1:
        _, i = _bit(s, tmp, p + 1, i)
        if index >= 2: _, i = _bit(s, tmp, p + 2, i)
    return i, flag

def decompress(data, size):
    head = data[0]
    s = _RC(); s.rng = M32; s.code = struct.unpack(">I", data[1:5])[0]; s.src = 0; s.data = data
    if head > 0x80:  # stored; RPCS3 returns 0 here (apparent bug) - we return the stored bytes
        if s.code > size: raise ValueError("stored length too large")
        return bytes(data[5:5 + s.code])
    tmp = bytearray(0xCC8); tmp[:0xCA8] = b"\x80" * 0xCA8
    out = bytearray(); offset = 0; prev = 0
    while True:
        p1 = offset + 0xB68
        bit, _ = _bit(s, tmp, p1)
        if not bit:  # raw char
            if offset > 0: offset -= 1
            if len(out) == size: return bytes(out)
            sect = (((((len(out) & 7) << 8) + prev) >> head) & 7) * 0xFF - 1
            index = 1
            while True:
                _, index = _bit(s, tmp, sect + index, index)
                if index >> 8: break
            out.append(index & 0xFF)
        else:
            index = -1
            while True:
                p1 += 8
                flag, _ = _bit(s, tmp, p1)
                index += flag
                if not (flag and index < 6): break
            b_size = 0x160; p2 = index + 0x7F1
            if index >= 0 or flag:
                sect = (index << 5) | (((len(out) << index) & 3) << 3) | (offset & 7)
                dlen, flag = _number(s, tmp, 0xBA8 + sect, index)
                if dlen == 0xFF: return bytes(out)
            else:
                dlen = 1
            if dlen <= 2: p2 += 0xF8; b_size = 0x40
            shift = 1
            while True:
                diff = (shift << 4) - b_size
                flag, shift = _bit(s, tmp, p2 + (shift << 3), shift)
                if diff >= 0: break
            if diff > 0 or flag:
                if not flag: diff -= 8
                doff, flag = _word(s, tmp, 0x928 + diff, diff)
            else:
                doff = 1
            start = len(out) - doff; end = len(out) + dlen + 1
            if start < 0 or end > size: raise ValueError("bad back-reference")
            offset = ((end + 1) & 1) + 6
            while len(out) < end:
                out.append(out[start]); start += 1
        prev = out[-1]

# ---- EDAT/SDAT container ----
def dec_section(m):
    d = bytes([m[0xC+k] ^ m[0x8+k] ^ m[0x10+k] for k in range(4)] + [m[0x4+k] ^ m[0x8+k] ^ m[0x14+k] for k in range(4)] +
              [m[0xC+k] ^ m[0x0+k] ^ m[0x18+k] for k in range(4)] + [m[0x4+k] ^ m[0x0+k] ^ m[0x1C+k] for k in range(4)])
    return struct.unpack(">Qii", d)

def decrypt_sdat(buf):
    magic, ver, lic, typ = struct.unpack(">4siii", buf[:16])
    assert magic == b"NPD\0", "not NPD"
    digest, dev_hash = buf[0x40:0x50], buf[0x60:0x70]
    flags, bsize, fsize = struct.unpack(">IIQ", buf[0x80:0x90])
    assert flags & SDAT_FLAG, "not SDAT (EDAT needs a klicensee/RAP)"
    assert not flags & F_DEBUG, "debug data flag not handled"
    crypt_key = bytes(a ^ b for a, b in zip(dev_hash, SDAT_KEY))
    ksel = 1 if ver == 4 else 0
    msize = 0x20 if flags & (F_COMP | F_20) else 0x10
    nblocks = -(-fsize // bsize)
    crypto_raw = bool(flags & F_02)
    hash_mode = 0x02 if not flags & F_10 else (0x04 if not flags & F_20 else 0x01)
    ecb = AES.new(crypt_key, AES.MODE_ECB)
    out = bytearray()
    for i in range(nblocks):
        comp_end = 0
        if flags & F_COMP:
            m = buf[0x100 + i*msize: 0x100 + i*msize + 0x20]
            off, length, comp_end = (struct.unpack(">Qii", m[0x10:0x20]) if ver <= 1 else dec_section(m))
            hres = m[:0x10]
        elif flags & F_20:
            mo = 0x100 + i*(msize + bsize); m = buf[mo:mo+0x20]
            hres = bytes(m[j] ^ m[j+0x10] for j in range(0x10)) + m[0x10:0x14]
            off, length = mo + 0x20, bsize
            if i == nblocks-1 and fsize % bsize: length = fsize % bsize
        else:
            hres = buf[0x100 + i*msize: 0x100 + i*msize + 0x10]
            off, length = 0x100 + i*bsize + nblocks*msize, bsize
            if i == nblocks-1 and fsize % bsize: length = fsize % bsize
        pad_len = length; length = (length + 15) & ~15
        enc = buf[off:off+length]
        bkey = (bytes(12) if ver <= 1 else dev_hash[:12]) + struct.pack(">i", i)
        kres = ecb.encrypt(bkey)
        hkey = ecb.encrypt(kres) if flags & F_10 else kres
        if flags & F_ENCKEY:  # 0x10000000 mode: keys are encrypted with EDAT_KEY
            kfin = AES.new(EDAT_KEY[ksel], AES.MODE_CBC, bytes(16)).decrypt(kres)
            hfin = AES.new(EDAT_KEY[ksel], AES.MODE_CBC, bytes(16)).decrypt(hkey)
        else:
            kfin, hfin = kres, hkey
        iv = bytes(16) if ver <= 1 else digest
        dec = enc if crypto_raw else AES.new(kfin, AES.MODE_CBC, iv).decrypt(enc)
        if (hash_mode & 0xFF) == 0x02:
            ok = CMAC.new(hfin, msg=enc, ciphermod=AES).digest() == hres[:0x10]
        else:  # SHA1-HMAC, 0x14 (mode 1) or truncated 0x10 (mode 4)
            n = 0x14 if hash_mode == 0x01 else 0x10
            ok = hmac.new(hfin, enc, hashlib.sha1).digest()[:n] == hres[:n]
        if not ok: raise ValueError(f"block {i}: hash mismatch")
        if flags & F_COMP and comp_end:
            out += decompress(dec, bsize)
        else:
            out += dec[:pad_len]
    if len(out) != fsize: raise ValueError(f"size mismatch {len(out)} != {fsize}")
    return bytes(out)

if __name__ == "__main__":
    data = decrypt_sdat(open(sys.argv[1], "rb").read())
    with open(sys.argv[2], "xb") as f: f.write(data)
    print(f"{sys.argv[1]} -> {sys.argv[2]} ({len(data)} bytes, sha1 {hashlib.sha1(data).hexdigest()})")
