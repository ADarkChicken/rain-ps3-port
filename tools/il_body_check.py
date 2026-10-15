"""Classify MethodDef IL bodies (RVA 0 / tiny stub / real). Usage: il_body_check.py <dll>..."""
import sys, collections, dnfile
for p in sys.argv[1:]:
    pe = dnfile.dnPE(p); md = pe.net.mdtables.MethodDef
    stats = collections.Counter(); sizes = collections.Counter()
    for r in md.rows:
        if not r.Rva: stats["rva0(abstract/extern)"] += 1; continue
        off = pe.get_offset_from_rva(r.Rva); h = pe.__data__[off]
        if h & 3 == 2: sz = h >> 2; code = pe.__data__[off+1:off+1+sz]
        else: sz = int.from_bytes(pe.__data__[off+4:off+8], "little"); code = pe.__data__[off+12:off+12+sz]
        sizes[bytes(code)] += 1; stats["has_body"] += 1
    common = sizes.most_common(3)
    print(f"{p.split('/')[-1]}: methods={len(md.rows)} {dict(stats)} distinct_bodies={len(sizes)} top={[ (c.hex()[:24], n) for c, n in common]}")
