"""Direct call graph of a Mono AOT PRX (bl targets that are method starts) + per-level reachable closure.
Usage: aot_callgraph.py <prx> <methods.csv> <Media dir> <il dir> <out.csv> level0 level12 ...
Roots = all methods of script classes (and their game base classes) attached in that level. Virtual/delegate calls are
NOT followed (lower bound). Output: level, script classes, reachable game methods, reachable code bytes, external call sites."""
import csv, os, struct, sys, collections, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unity_inventory as u
import unity_mb_decode as d

def main():
    prx, mcsv, media, il, out = sys.argv[1:6]; levels = sys.argv[6:]
    b = open(prx, "rb").read()
    phoff, = struct.unpack(">Q", b[32:40]); ph = [struct.unpack(">IIQQQQQQ", b[phoff+i*56: phoff+i*56+56]) for i in range(3)]
    t0 = ph[0]
    rows = [r for r in csv.DictReader(open(mcsv)) if r["address"]]
    starts = sorted(int(r["address"], 16) for r in rows)
    info = {int(r["address"], 16): r for r in rows}
    bytype = collections.defaultdict(list)
    for r in rows: bytype[r["type"]].append(int(r["address"], 16))
    edges = collections.defaultdict(set); ext = collections.Counter()
    end_code = max(int(r["address"], 16) + int(r["size"]) for r in rows)
    for a in starts:
        sz = int(info[a]["size"])
        for off in range(a, a + sz, 4):
            w, = struct.unpack(">I", b[t0[2] + off: t0[2] + off + 4])
            if (w >> 26) == 18 and (w & 3) == 1:  # bl
                li = w & 0x03FFFFFC
                if li & 0x02000000: li -= 0x04000000
                tgt = off + li
                if tgt in info: edges[a].add(tgt)
                elif tgt >= end_code: ext[a] += 1    # PLT / outside methods
    ms = u.monoscripts(os.path.join(media, "sharedassets0.assets"))
    w = d.World(il); asm = w.asms["Assembly-CSharp"]
    def chain(cls):
        out = []; a, i = asm, asm.byname.get(("", cls))
        while a is asm and i:
            out.append(w.full(a, i)); a, i = w.base(a, i)
        return out
    with open(out, "x", newline="") as f:
        cw = csv.writer(f); cw.writerow(["level", "script_classes", "reachable_methods", "reachable_bytes", "external_call_sites"])
        for lv in levels:
            path = os.path.join(media, lv); ext_files = u.externals(path); classes = set()
            for _, _, ob in u.objects(path, 114):
                fid, spid = struct.unpack(">ii", ob[12:20])
                if 0 < fid <= len(ext_files) and ext_files[fid-1].endswith("sharedassets0.assets") and spid in ms:
                    classes.add(ms[spid][0])
            roots = set()
            for c in classes:
                for t in chain(c): roots.update(bytype.get(t, []))
            seen, stack = set(), list(roots)
            while stack:
                m = stack.pop()
                if m in seen: continue
                seen.add(m); stack.extend(edges[m] - seen)
            cw.writerow([lv, len(classes), len(seen), sum(int(info[m]["size"]) for m in seen), sum(ext[m] for m in seen)])
            print(lv, "classes", len(classes), "reachable methods", len(seen), "bytes", sum(int(info[m]["size"]) for m in seen))
    print("total methods", len(starts), "direct edges", sum(len(v) for v in edges.values()))

if __name__ == "__main__":
    main()
