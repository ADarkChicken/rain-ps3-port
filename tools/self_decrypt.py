"""NPDRM SELF/SPRX -> ELF decryptor (logic per RPCS3 unself.cpp; keys via klic_check.py).
Usage: self_decrypt.py <in.self> <out.elf> [--klic HEX | --free]   (default klic: all-zero)
Output = original ELF header + program headers + decrypted/decompressed segments placed at p_offset,
plus section headers if present. Metadata info is validated (32 zero pad bytes) before anything is written."""
import os, struct, sys, zlib, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Crypto.Cipher import AES
from Crypto.Util import Counter
from klic_check import NPDRM_KEYS, NP_KLIC_KEY, NP_KLIC_FREE

def ctr(key, iv, data):
    return AES.new(key, AES.MODE_CTR, counter=Counter.new(128, initial_value=int.from_bytes(iv, "big"))).decrypt(data)

def decrypt_self(b, klic):
    assert b[:4] == b"SCE\0"
    rev, htype, meta_off = struct.unpack(">HHI", b[8:16])
    hlen, dlen = struct.unpack(">QQ", b[16:32])
    ext = struct.unpack(">10Q", b[0x20:0x70])
    ehdr_off, phdr_off, shdr_off = ext[2], ext[3], ext[4]
    erk, riv = (bytes.fromhex(x) for x in NPDRM_KEYS[rev])
    debug = rev & 0x8000
    mi = b[0x20 + meta_off: 0x60 + meta_off]
    if not debug:
        k = AES.new(NP_KLIC_KEY, AES.MODE_ECB).decrypt(klic)
        mi = AES.new(k, AES.MODE_CBC, bytes(16)).decrypt(mi)
        mi = AES.new(erk, AES.MODE_CBC, riv).decrypt(mi)
    if mi[16:32] != bytes(16) or mi[48:64] != bytes(16): raise ValueError("metadata info not decrypted (wrong klic/key)")
    mh = ctr(mi[0:16], mi[32:48], b[0x60 + meta_off: hlen])
    _siglen, _algo, nsec, nkeys, _opt, _u1, _u2 = struct.unpack(">QIIIIII", mh[:0x20])
    secs = [struct.unpack(">QQIIIIIIII", mh[0x20 + i*0x30: 0x50 + i*0x30]) for i in range(nsec)]
    kbase = 0x20 + nsec*0x30; keys = [mh[kbase + i*16: kbase + (i+1)*16] for i in range(nkeys)]
    # ELF64 header + program headers from the (plaintext) SELF header area
    eh = bytearray(b[ehdr_off: ehdr_off + 0x40])
    assert eh[:4] == b"\x7fELF" and eh[4] == 2, "only ELF64 handled"
    e_phoff, e_shoff = struct.unpack(">QQ", eh[0x20:0x30])
    e_phentsize, e_phnum, e_shentsize, e_shnum = struct.unpack(">HHHH", eh[0x36:0x3E])
    ph = [struct.unpack(">IIQQQQQQ", b[phdr_off + i*56: phdr_off + (i+1)*56]) for i in range(e_phnum)]
    size = max([e_phoff + e_phnum*e_phentsize] + [p[2] + p[5] for p in ph])
    if shdr_off and e_shnum: size = max(size, e_shoff + e_shnum*e_shentsize)
    out = bytearray(size)
    out[0:0x40] = eh
    out[e_phoff: e_phoff + e_phnum*56] = b[phdr_off: phdr_off + e_phnum*56]
    report = []
    for (doff, dsz, typ, pidx, hashed, sha1i, enc, ki, ivi, comp) in secs:
        if typ != 2: continue  # only program segments
        data = b[doff: doff + dsz]
        if enc == 3: data = ctr(keys[ki], keys[ivi], data)
        if comp == 2: data = zlib.decompress(data)
        p = ph[pidx]
        if len(data) != p[5]: raise ValueError(f"segment {pidx}: size {len(data)} != p_filesz {p[5]}")
        out[p[2]: p[2] + len(data)] = data
        report.append((pidx, hex(p[3]), len(data), comp == 2))
    if shdr_off and e_shnum:
        out[e_shoff: e_shoff + e_shnum*e_shentsize] = b[shdr_off: shdr_off + e_shnum*e_shentsize]
    return bytes(out), report

if __name__ == "__main__":
    klic = bytes(16)
    if "--free" in sys.argv: klic = NP_KLIC_FREE
    if "--klic" in sys.argv: klic = bytes.fromhex(sys.argv[sys.argv.index("--klic") + 1])
    elf, rep = decrypt_self(open(sys.argv[1], "rb").read(), klic)
    with open(sys.argv[2], "xb") as f: f.write(elf)
    print(f"{sys.argv[2]}: {len(elf)} bytes sha1 {hashlib.sha1(elf).hexdigest()} segs={rep}")
