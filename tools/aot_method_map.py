"""Map Mono AOT native code to IL MethodDefs (verified layout: addr = methods + code_offsets[row-1]).
Usage: aot_method_map.py <il.dll> <aot.prx> <exports.txt from prx_exports.py> <out.csv>
CSV columns: token,address,size,type,method,params,flags  (size = distance to next mapped method, upper bound)"""
import csv, re, struct, sys, dnfile

def main(il, prx, exports, out):
    sym = {}
    for line in open(exports):
        m = re.search(r"addr=(0x[0-9a-f]+) (\S+)$", line.strip())
        if m: sym[m.group(2)] = int(m.group(1), 16)
    b = open(prx, "rb").read()
    phoff, = struct.unpack(">Q", b[32:40]); n, = struct.unpack(">H", b[56:58])
    ph = [struct.unpack(">IIQQQQQQ", b[phoff+i*56: phoff+i*56+56]) for i in range(n)]
    def off(va):
        for p in ph:
            if p[0] == 1 and p[5] and p[3] <= va < p[3] + p[5]: return p[2] + va - p[3]
        raise KeyError(hex(va))
    pe = dnfile.dnPE(il); t = pe.net.mdtables
    md, td = t.MethodDef.rows, t.TypeDef.rows
    co = [struct.unpack(">i", b[off(sym["code_offsets"]) + 4*i: off(sym["code_offsets"]) + 4*i + 4])[0] for i in range(len(md))]
    enclosing = {}
    if t.NestedClass:
        for r in t.NestedClass.rows: enclosing[r.NestedClass.row_index] = r.EnclosingClass.row_index
    def tname(ti):
        r = td[ti-1]; nm = str(r.TypeName)
        if ti in enclosing: return tname(enclosing[ti]) + "/" + nm
        return (str(r.TypeNamespace) + "." if str(r.TypeNamespace) else "") + nm
    owner = {}
    for ti, r in enumerate(td, 1):
        for m in (r.MethodList or []): owner[m.row_index] = tname(ti)
    pnames = {}
    for i, r in enumerate(md, 1):
        pnames[i] = [str(p.row.Name) for p in (r.ParamList or []) if p.row and p.row.Sequence > 0]
    addrs = sorted(sym["methods"] + c for c in co if c != -1)
    nxt = {a: (addrs[k+1] if k+1 < len(addrs) else sym["methods_end"]) for k, a in enumerate(addrs)}
    with open(out, "x", newline="") as f:
        w = csv.writer(f); w.writerow(["token", "address", "size", "type", "method", "params", "flags"])
        for i, r in enumerate(md, 1):
            a = None if co[i-1] == -1 else sym["methods"] + co[i-1]
            w.writerow([f"0x06{i:06x}", f"0x{a:x}" if a is not None else "", (nxt[a] - a) if a is not None else "",
                        owner.get(i, "?"), str(r.Name), " ".join(pnames[i]), "nocode" if a is None else ""])
    print(f"{out}: {len(md)} methods, {sum(1 for c in co if c != -1)} with code")

if __name__ == "__main__":
    main(*sys.argv[1:5])
