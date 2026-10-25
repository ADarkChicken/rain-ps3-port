"""Closure v2 (E103): the direct-call closure of aot_callgraph.py plus the edges it missed, read from each method's GOT
loads (r30 = GOT base; `lwz rD,d(r30)` or `lis/ori r0` + `lwzx rD,r30,r0`):
  bl to a PLT stub of T::M  -> edge to every T::M overload (calls that need a class-init check go through the PLT even
                               inside the assembly; aot_callgraph.py counted them as external)
  METHODCONST T::M          -> edge to T::M (delegate / coroutine targets)
  SFLDA T::f                -> edge to T::.cctor (static field read/write runs the type initializer)
  VTABLE T, AddComponent<T> -> T is instantiated: every virtual method of T and its Assembly-CSharp bases is reachable
                               (virtual dispatch cannot be resolved without IL bodies, so this is an upper bound per type)
Roots: the root=1 rows of the old closure (scene/prefab script classes and their base chains); those are instantiated too.
Usage: closure_v2.py <prx> <methods.csv> <got.csv> <plt.csv> <il dir> <old closure.methods.csv> <recon dir> <out.csv>
Writes <out.csv> (one row per reachable method: type, method, address, size, reason, in_old, recon_type) and prints
the types not reconstructed yet, biggest first."""
import csv, os, re, struct, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unity_mb_decode as d

def main():
    prx, mcsv, gcsv, pcsv, il, old, recon, out = sys.argv[1:9]
    b = open(prx, "rb").read()
    phoff, = struct.unpack(">Q", b[32:40]); t0 = struct.unpack(">IIQQQQQQ", b[phoff: phoff + 56])
    rows = [r for r in csv.DictReader(open(mcsv)) if r["address"]]
    info = {int(r["address"], 16): r for r in rows}
    end_code = max(a + int(r["size"]) for a, r in info.items())
    byname = collections.defaultdict(list); bytype = collections.defaultdict(list)
    for a, r in info.items():
        byname[(r["type"], r["method"])].append(a); bytype[r["type"]].append(a)
    got = {int(r["got_byte_offset"], 16): (r["patch_type"], r["target"]) for r in csv.DictReader(open(gcsv))}
    plt = {}
    for r in csv.DictReader(open(pcsv)):
        if r["patch_type"] == "METHOD" and "::" in r["target"]:
            t, m = r["target"].rsplit("::", 1)
            if (t, m) in byname: plt[int(r["address"], 16)] = byname[(t, m)]

    # virtual flag per method token (MethodDef.Flags & 0x40)
    asm = d.World(il).asms["Assembly-CSharp"]
    virt = {0x06000000 | i for i, m in enumerate(asm.t.MethodDef.rows, 1) if m.Flags.mdVirtual}
    # type -> base type name (Assembly-CSharp only), names as in methods.csv ("Outer/Inner")
    names = {}
    enc = {r.NestedClass.row_index: r.EnclosingClass.row_index for r in (asm.t.NestedClass.rows if asm.t.NestedClass else [])}
    def tname(i):
        if i in names: return names[i]
        r = asm.td[i - 1]; n = str(r.TypeName)
        n = (tname(enc[i]) + "/" + n) if i in enc else ((str(r.TypeNamespace) + "." if str(r.TypeNamespace) else "") + n)
        names[i] = n; return n
    w = d.World.__new__(d.World); w.asms = {"Assembly-CSharp": asm}; w.cache = {}
    base = {}
    for i in range(1, len(asm.td) + 1):
        try: ba, bi = w.base(asm, i)
        except Exception: ba, bi = None, None
        if ba is asm and isinstance(bi, int): base[tname(i)] = tname(bi)
    def chain(t):
        while t: yield t; t = base.get(t)

    # per-method edges
    edges = collections.defaultdict(set); inst_of = collections.defaultdict(set); why = {}
    for a, r in info.items():
        hi = None
        for off in range(a, a + int(r["size"]), 4):
            wd, = struct.unpack(">I", b[t0[2] + off: t0[2] + off + 4]); op = wd >> 26
            ra, rd = (wd >> 16) & 31, (wd >> 21) & 31
            g = None
            if op == 18 and (wd & 3) == 1:   # bl
                li = wd & 0x03FFFFFC
                if li & 0x02000000: li -= 0x04000000
                if off + li in info: edges[a].add(off + li)
                elif off + li in plt: edges[a].update(plt[off + li])
                continue
            if op == 15 and ra == 0 and rd == 0: hi = (wd & 0xFFFF) << 16; continue          # lis r0,HI
            if op == 24 and rd == 0 and ra == 0 and hi is not None: hi |= wd & 0xFFFF; continue  # ori r0,r0,LO
            if op == 32 and ra == 30: g = wd & 0xFFFF                                            # lwz rD,d(r30)
            elif op == 31 and ((wd >> 1) & 0x3FF) == 23 and ra == 30 and ((wd >> 11) & 31) == 0 and hi is not None: g = hi
            if g is None or g not in got: continue
            k, tg = got[g]
            if k == "METHODCONST" and "::" in tg:
                t, m = tg.rsplit("::", 1)
                for x in byname.get((t, m), []): edges[a].add(x)
            elif k == "SFLDA" and "::" in tg:
                for x in byname.get((tg.rsplit("::", 1)[0], ".cctor"), []): edges[a].add(x)
            elif k == "VTABLE" and tg in bytype or k == "METHOD_RGCTX" and "AddComponent<" in tg:
                t = tg if k == "VTABLE" else tg[tg.index("AddComponent<") + 13:-1]
                if t in bytype: inst_of[a].add(t)

    olds = [r for r in csv.DictReader(open(old))]
    old_set = {int(r["address"], 16) for r in olds}
    roots = {int(r["address"], 16) for r in olds if r["root"] == "1"}
    seen, insts = set(), set(); stack = [(m, "root") for m in roots]
    for m in roots: insts.add(info[m]["type"])
    def instantiate(t, src):
        if t in insts: return
        insts.add(t)
        for c in chain(t):
            for x in bytype.get(c, []):
                if int(info[x]["token"], 16) in virt: stack.append((x, "virtual:" + t))
    for t in list(insts):
        insts.discard(t); instantiate(t, "root")
    while stack:
        m, rs = stack.pop()
        if m in seen: continue
        seen.add(m); why[m] = rs
        for x in edges[m]:
            if x not in seen: stack.append((x, "call"))
        for t in inst_of[m]: instantiate(t, info[m]["type"])

    have = {f[:-3] for f in os.listdir(recon) if f.endswith(".cs")}
    def top(t): return t.split("/")[0]
    with open(out, "w", newline="") as f:
        cw = csv.writer(f); cw.writerow(["type", "method", "address", "size", "reason", "in_old", "recon_type"])
        for m in sorted(seen, key=lambda m: (info[m]["type"], m)):
            r = info[m]; cw.writerow([r["type"], r["method"], hex(m), r["size"], why[m], int(m in old_set), int(top(r["type"]) in have)])
    new = collections.Counter(); allm = collections.Counter(r["type"].split("/")[0] for r in rows)
    for m in seen:
        t = top(info[m]["type"])
        if t not in have: new[t] += 1
    print(f"reachable methods {len(seen)} (old {len(old_set)}), instantiated types {len(insts)}")
    print(f"not reconstructed: {len(new)} top-level types, {sum(new.values())} reachable methods "
          f"({sum(allm[t] for t in new)} methods in those types)")
    for t, n in new.most_common(): print(f"  {t:32} reachable {n:4} / {allm[t]:4}")

if __name__ == "__main__":
    main()
