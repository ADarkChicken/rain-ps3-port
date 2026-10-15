"""List PS3 PRX module info + exports/imports, resolving NIDs against candidate names.
Usage: prx_exports.py <prx> [names_file]
Module info at seg0 + (p_paddr - p_offset) (RPCS3 ppu_load_prx). NID = LE u32 of SHA1(name + suffix)[:4]."""
import hashlib, re, struct, sys

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps3keys import key
SUFFIX = key("NID_SUFFIX")
def nid(name): return struct.unpack("<I", hashlib.sha1(name.encode() + SUFFIX).digest()[:4])[0]

def load(path):
    b = open(path, "rb").read()
    phoff, = struct.unpack(">Q", b[32:40]); n, = struct.unpack(">H", b[56:58])
    ph = [struct.unpack(">IIQQQQQQ", b[phoff+i*56: phoff+i*56+56]) for i in range(n)]
    segs = [(p[3], p[2], p[5]) for p in ph if p[0] == 1 and p[5]]  # vaddr, offset, filesz
    def rd(va, sz):
        for v, o, s in segs:
            if v <= va < v + s: return b[o + va - v: o + va - v + sz]
        raise KeyError(hex(va))
    return b, ph, rd

def cstr(rd, va):
    out = b""
    while True:
        c = rd(va + len(out), 1)
        if c == b"\0": return out.decode(errors="replace")
        out += c

def main():
    b, ph, rd = load(sys.argv[1])
    names = {}
    if len(sys.argv) > 2:
        for line in open(sys.argv[2]):
            s = line.strip()
            if s: names[nid(s)] = s
    p0 = ph[0]; mi_va = p0[3] + (p0[4] - p0[2])
    attr, v0, v1 = struct.unpack(">HBB", rd(mi_va, 4)); mname = rd(mi_va + 4, 28).split(b"\0")[0].decode()
    toc, es, ee, is_, ie = struct.unpack(">IIIII", rd(mi_va + 32, 20))
    print(f"module '{mname}' attr={attr:#x} toc={toc:#x} exports={es:#x}-{ee:#x} imports={is_:#x}-{ie:#x}")
    va = es
    while va < ee:
        sz, _, ver, at, nf, nv, ntls, _, _, _, _, nm, nids, addrs = struct.unpack(">BBHHHHHBBBBIII", rd(va, 0x1c))
        lib = cstr(rd, nm) if nm else "(module)"
        print(f" EXPORT lib={lib} funcs={nf} vars={nv} attr={at:#x}")
        for i in range(nf + nv + ntls):
            n_, = struct.unpack(">I", rd(nids + 4*i, 4)); a_, = struct.unpack(">I", rd(addrs + 4*i, 4))
            kind = "func" if i < nf else "var"
            print(f"   {kind} nid={n_:08x} addr={a_:#x} {names.get(n_, '')}")
        va += sz
    va = is_
    while va < ie:
        sz, = struct.unpack(">B", rd(va, 1))
        f = rd(va, sz)
        nf, nv = struct.unpack(">HH", f[6:10]); nm, = struct.unpack(">I", f[0x10:0x14])
        print(f" IMPORT lib={cstr(rd, nm) if nm else '?'} funcs={nf} vars={nv}")
        va += sz

if __name__ == "__main__":
    main()
