"""Decode MonoBehaviour serialized data (Unity 3.5 v9 BE, no type trees) from IL metadata alone.
Layout rules (observed, E33): header PPtr GameObject, bool m_Enabled (aligned 4), PPtr m_Script, string m_Name;
then serializable instance fields in declaration order (base classes first). Serializable = not static/const/
initonly/NonSerialized and (public or [SerializeField]). bool/byte/sbyte/char/short/ushort aligned to 4; strings and
arrays: int32 count + data, aligned to 4; UnityEngine.Object refs = PPtr(fileID i32, pathID i32); [Serializable]
classes/structs inline; List<T> as array; enums as underlying int. Unity built-in structs use known float layouts.
Usage: unity_mb_decode.py <Media dir> <il dir> <out_summary.csv> [--dump ClassName N]"""
import csv, glob, os, struct, sys, collections, dnfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unity_inventory as u

PRIM = {2: ("bool", 1), 3: ("char", 2), 4: ("sbyte", 1), 5: ("byte", 1), 6: ("short", 2), 7: ("ushort", 2), 8: ("int", 4),
        9: ("uint", 4), 10: ("long", 8), 11: ("ulong", 8), 12: ("float", 4), 13: ("double", 8)}
BUILTIN = {"Vector2": 2, "Vector3": 3, "Vector4": 4, "Quaternion": 4, "Color": 4, "Rect": 4, "Matrix4x4": 16, "Bounds": 6}
UNSUPPORTED = {"AnimationCurve", "Gradient", "GUIStyle", "RectOffset", "Color32", "LayerMask"}

class Asm:
    def __init__(self, path):
        pe = dnfile.dnPE(path); t = pe.net.mdtables; self.t = t; self.name = os.path.basename(path)[:-4]
        self.td = t.TypeDef.rows
        self.byname = {}
        enc = {r.NestedClass.row_index: r.EnclosingClass.row_index for r in (t.NestedClass.rows if t.NestedClass else [])}
        for i, r in enumerate(self.td, 1):
            if i not in enc: self.byname[(str(r.TypeNamespace), str(r.TypeName))] = i
        self.nested = {}
        for n, o in enc.items(): self.nested[(o, str(self.td[n-1].TypeName))] = n
        self.serfield = set()  # Field rows with [SerializeField]
        for ca in (t.CustomAttribute.rows if t.CustomAttribute else []):
            try:
                if ca.Parent.table.name != "Field": continue
                ty = ca.Type.row
                cls = ty.Class.row if hasattr(ty, "Class") else None
                if cls is not None and str(getattr(cls, "TypeName", "")) == "SerializeField": self.serfield.add(ca.Parent.row_index)
            except Exception: pass

class World:
    def __init__(self, il_dir):
        self.asms = {}
        for p in glob.glob(os.path.join(il_dir, "*.dll")):
            try: a = Asm(p); self.asms[a.name] = a
            except Exception: pass
        self.cache = {}
    def find(self, ns, name):
        for a in self.asms.values():
            i = a.byname.get((ns, name))
            if i: return a, i
        return None, None
    def resolve_tdor(self, a, coded):
        """TypeDefOrRef coded index -> (asm, typedef row) or (None, 'TypeSpec')"""
        tag, row = coded & 3, coded >> 2
        if tag == 0: return a, row
        if tag == 1:
            r = a.t.TypeRef.rows[row-1]; scope = r.ResolutionScope
            if scope and scope.table.name == "TypeRef":
                oa, oi = self.resolve_tdor(a, (scope.row_index << 2) | 1)
                if oa: return oa, oa.nested.get((oi, str(r.TypeName)))
                return None, None
            return self.find(str(r.TypeNamespace), str(r.TypeName))
        return None, "TypeSpec"
    def full(self, a, i): r = a.td[i-1]; return (str(r.TypeNamespace) + "." if str(r.TypeNamespace) else "") + str(r.TypeName)
    def base(self, a, i):
        e = a.td[i-1].Extends
        if not e or not e.row: return None, None
        tag = {"TypeDef": 0, "TypeRef": 1, "TypeSpec": 2}[e.table.name]
        return self.resolve_tdor(a, (e.row_index << 2) | tag)
    def is_uobject(self, a, i):
        while a and i:
            if self.full(a, i) == "UnityEngine.Object": return True
            a, i = self.base(a, i)
        return False
    def kind(self, a, i):
        """Classify a resolved type."""
        if a is None: return ("unknown",)
        nm = self.full(a, i); r = a.td[i-1]
        if nm.startswith("UnityEngine.") and nm.split(".")[-1] in BUILTIN: return ("floats", BUILTIN[nm.split(".")[-1]])
        if nm.startswith("UnityEngine.") and nm.split(".")[-1] in UNSUPPORTED: return ("unsupported", nm)
        if self.is_uobject(a, i): return ("pptr",)
        ba, bi = self.base(a, i); bn = self.full(ba, bi) if ba else ""
        if bn == "System.Enum":
            for f in (r.FieldList or []):
                if not f.row.Flags.fdStatic: return ("prim",) + PRIM[bytes(f.row.Signature.value)[1]]
        if r.Flags.tdSerializable or bn == "System.ValueType" and nm.startswith("UnityEngine.") is False and r.Flags.tdSerializable:
            return ("inline", a, i)
        return ("skip", nm)
    def sig_type(self, a, b, p):
        """Parse a field type signature -> layout node."""
        e = b[p]; p += 1
        if e in PRIM: return ("prim",) + PRIM[e], p
        if e == 0x0e: return ("string",), p
        if e in (0x11, 0x12):
            v, p = cu(b, p); ra, ri = self.resolve_tdor(a, v)
            if ri == "TypeSpec": return ("unknown", "typespec"), p
            return self.kind(ra, ri), p
        if e == 0x1d:
            el, p = self.sig_type(a, b, p); return ("array", el), p
        if e == 0x15:
            g, p = self.sig_type(a, b, p); n, p = cu(b, p); args = []
            for _ in range(n): x, p = self.sig_type(a, b, p); args.append(x)
            return ("list", args[0]) if n == 1 else ("unknown", "generic"), p
        if e == 0x1c: return ("skip", "object"), p
        return ("unknown", f"et{e:#x}"), p
    def fields(self, a, i):
        key = (a.name, i)
        if key in self.cache: return self.cache[key]
        out = []
        ba, bi = self.base(a, i)
        if ba and bi and self.full(ba, bi) not in ("UnityEngine.MonoBehaviour", "UnityEngine.Behaviour", "System.Object", "System.ValueType"):
            out += self.fields(ba, bi)
        for f in (a.td[i-1].FieldList or []):
            fr = f.row; fl = fr.Flags
            if fl.fdStatic or fl.fdLiteral or fl.fdInitOnly or fl.fdNotSerialized: continue
            if not (fl.fdPublic or f.row_index in a.serfield): continue
            node, _ = self.sig_type(a, bytes(fr.Signature.value), 1)
            if node[0] == "skip": continue
            out.append((str(fr.Name), node))
        self.cache[key] = out
        return out

def cu(b, i):
    x = b[i]
    if x & 0x80 == 0: return x, i+1
    if x & 0x40 == 0: return ((x & 0x3f) << 8) | b[i+1], i+2
    return ((x & 0x1f) << 24) | (b[i+1] << 16) | (b[i+2] << 8) | b[i+3], i+4

class Bad(Exception): pass

def read(w, node, b, p, depth=0):
    al = lambda q: (q + 3) & ~3
    k = node[0]
    if k == "prim":
        _, nm, sz = node
        fmt = {"bool": "?", "char": "H", "sbyte": "b", "byte": "B", "short": "h", "ushort": "H", "int": "i", "uint": "I",
               "long": "q", "ulong": "Q", "float": "f", "double": "d"}[nm]
        if p + sz > len(b): raise Bad("eof")
        v = struct.unpack(">" + fmt, b[p:p+sz])[0]; p += sz
        if sz < 4: p = al(p)
        return v, p
    if k == "string":
        n = struct.unpack(">i", b[p:p+4])[0]
        if n < 0 or p + 4 + n > len(b): raise Bad("bad string len")
        return b[p+4:p+4+n].decode(errors="replace"), al(p + 4 + n)
    if k == "pptr":
        if p + 8 > len(b): raise Bad("eof")
        return struct.unpack(">ii", b[p:p+8]), p + 8
    if k == "floats":
        n = node[1]
        if p + 4*n > len(b): raise Bad("eof")
        return struct.unpack(f">{n}f", b[p:p+4*n]), p + 4*n
    if k in ("array", "list"):
        n = struct.unpack(">i", b[p:p+4])[0]; p += 4
        if n < 0 or n > 100000: raise Bad("bad array len")
        out = []
        for _ in range(n): v, p = read(w, node[1], b, p, depth+1); out.append(v)
        return out, al(p)
    if k == "inline":
        if depth > 8: raise Bad("depth")
        d = {}
        for fn, fnode in w.fields(node[1], node[2]): d[fn], p = read(w, fnode, b, p, depth+1)
        return d, p
    raise Bad(f"unsupported node {node}")

def header(b):
    go = struct.unpack(">ii", b[0:8]); en = b[8]; scr = struct.unpack(">ii", b[12:20])
    n = struct.unpack(">i", b[20:24])[0]; name = b[24:24+n].decode(errors="replace")
    return go, en, scr, name, (24 + n + 3) & ~3

def main():
    media, il_dir, out = sys.argv[1:4]
    dump = sys.argv[sys.argv.index("--dump")+1:sys.argv.index("--dump")+3] if "--dump" in sys.argv else None
    w = World(il_dir)
    ms = u.monoscripts(os.path.join(media, "sharedassets0.assets"))
    stats = collections.defaultdict(lambda: collections.Counter()); reasons = collections.defaultdict(collections.Counter)
    shown = 0
    files = sorted(glob.glob(os.path.join(media, "level*"))) + sorted(glob.glob(os.path.join(media, "sharedassets*.assets")))
    for f in files:
        ext = u.externals(f)
        for pid, _, b in u.objects(f, 114):
            go, en, (fid, spid), name, p = header(b)
            src = os.path.basename(f) if fid == 0 else (ext[fid-1] if 0 < fid <= len(ext) else "?")
            if not src.endswith("sharedassets0.assets"): stats["(other script file)"]["skipped"] += 1; continue
            cls, ns, asmname = ms.get(spid, ("?", "", ""))
            a = w.asms.get(asmname[:-4] if asmname.endswith(".dll") else asmname)
            ra, ri = (w.find(ns, cls) if a is None else (a, a.byname.get((ns, cls))))
            st = stats[cls]; st["instances"] += 1
            if not ri: st["no_type"] += 1; continue
            try:
                d = {}
                for fn, node in w.fields(ra, ri): d[fn], p = read(w, node, b, p)
                if p == len(b): st["exact"] += 1
                else: st["size_mismatch"] += 1; reasons[cls][f"end {p} != {len(b)}"] += 1
                if dump and cls == dump[0] and shown < int(dump[1]):
                    shown += 1; print(f"{os.path.basename(f)} pathID={pid} go={go} enabled={en} -> {d}")
            except (Bad, struct.error, IndexError) as e:
                st["error"] += 1; reasons[cls][str(e)[:60]] += 1
    with open(out, "w", newline="") as fo:
        cw = csv.writer(fo); cw.writerow(["class", "instances", "exact", "size_mismatch", "error", "no_type", "top_reason"])
        for cls, st in sorted(stats.items(), key=lambda kv: -kv[1]["instances"]):
            cw.writerow([cls, st["instances"], st["exact"], st["size_mismatch"], st["error"], st["no_type"],
                         reasons[cls].most_common(1)[0][0] if reasons[cls] else ""])
    tot = sum(s["instances"] for s in stats.values()); ex = sum(s["exact"] for s in stats.values())
    full = sum(1 for c, s in stats.items() if s["instances"] and s["exact"] == s["instances"])
    print(f"instances={tot} exact={ex} ({100*ex/max(tot,1):.1f}%) classes={len(stats)} classes_fully_exact={full}")

if __name__ == "__main__":
    main()
