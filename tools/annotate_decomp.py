"""Annotate a DecompileNamespace.java dump with field names and GOT entry names (E92).
Usage: annotate_decomp.py <il_dir> <assembly> <TypeName> <decomp.txt> <out.txt>
- `*(T *)(param_1 + 0xNN)` -> `this.<field>` using the Mono AOT instance layout observed in this build (E91):
  per class from the base down (UnityEngine.Object header ends at 0x10), reference fields first in declaration order,
  then value fields in declaration order with natural alignment.
- `(puVarN + 0xNNNN)` GOT accesses -> `[PATCHTYPE:target]` from work/maps/<assembly>.got.csv.
Self-check: `python annotate_decomp.py --selftest <il_dir>` verifies RainMergePostEffect against the offsets read from its
decompiled code (E91)."""
import csv, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile

VALUE = {"bool": (1, 1), "byte": (1, 1), "sbyte": (1, 1), "char": (2, 2), "short": (2, 2), "ushort": (2, 2), "int": (4, 4),
         "uint": (4, 4), "float": (4, 4), "long": (8, 8), "ulong": (8, 8), "double": (8, 8), "IntPtr": (4, 4),
         "Vector2": (8, 4), "Vector3": (12, 4), "Vector4": (16, 4), "Quaternion": (16, 4), "Color": (16, 4), "Color32": (4, 1),
         "Rect": (16, 4), "LayerMask": (4, 4), "Matrix4x4": (64, 4), "Bounds": (24, 4)}
ET = {1: "void", 2: "bool", 3: "char", 4: "sbyte", 5: "byte", 6: "short", 7: "ushort", 8: "int", 9: "uint", 10: "long",
      11: "ulong", 12: "float", 13: "double", 14: "string", 0x18: "IntPtr", 0x1c: "object"}

class Asm:
    def __init__(self, path):
        self.pe = dnfile.dnPE(path); self.t = self.pe.net.mdtables
    def cu(self, b, i):
        x = b[i]
        if x & 0x80 == 0: return x, i + 1
        if x & 0x40 == 0: return ((x & 0x3F) << 8) | b[i + 1], i + 2
        return ((x & 0x1F) << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3], i + 4
    def tdor_name(self, v):
        tag, row = v & 3, v >> 2
        r = [self.t.TypeDef, self.t.TypeRef, self.t.TypeSpec][tag].rows[row - 1]
        n = str(getattr(r, "TypeName", "?"))
        if tag == 0 and row in self.enc(): n = f"{self.t.TypeDef.rows[self.enc()[row] - 1].TypeName}/{n}"   # nested: Outer/Inner (E97)
        return n, (tag == 0 and self.is_enum(r))
    def enc(self):
        if not hasattr(self, "_enc"):
            self._enc = {r.NestedClass.row_index: r.EnclosingClass.row_index for r in (self.t.NestedClass.rows if self.t.NestedClass else [])}
        return self._enc
    def is_enum(self, r):
        e = r.Extends
        return bool(e and e.row and str(getattr(e.row, "TypeName", "")) == "Enum")
    def ref_type(self, b):
        """Declared type name of a reference field signature (class/array/generic), for field-chain naming."""
        e = b[1]
        if e == 0x12: v, _ = self.cu(b, 2); return self.tdor_name(v)[0]
        if e == 0x1D: return "array"
        if e == 0x15: return "generic"
        return "ref"
    def kind(self, b):
        """(name, size, align) of a field signature; size None = reference."""
        e = b[1]
        if e in ET: n = ET[e]; return (n,) + VALUE[n] if n in VALUE else (n, None, 4)
        if e == 0x11:   # valuetype
            v, _ = self.cu(b, 2); n, enum = self.tdor_name(v)
            if n.split("/")[-1] in ENUMS: return (n,) + ENUMS[n.split("/")[-1]]          # enums from any assembly, by underlying type size
            if enum: return n, 4, 4
            if n in VALUE: return (n,) + VALUE[n]
            return (n,) + struct_size(n)
        return self.ref_type(b), None, 4
    def find(self, name):
        """TypeDef row by name; nested types as 'Outer/Inner' (matched through the NestedClass table)."""
        if "/" in name:
            outer, inner = name.rsplit("/", 1)
            self.enc()
            want = outer.rsplit("/", 1)[-1]
            for i, r in enumerate(self.t.TypeDef.rows, 1):
                if str(r.TypeName) == inner and i in self._enc and str(self.t.TypeDef.rows[self._enc[i] - 1].TypeName) == want: return r
            return None
        for i, r in enumerate(self.t.TypeDef.rows, 1):
            if str(r.TypeName) == name: return r
        return None

TYPES = {}   # (declaring type, field) -> declared type name of reference fields
STRUCT_AT = {}   # (type, field offset) -> (struct type name, size) for value-type fields wider than one word
HASREF = set()   # value types that contain object references (Mono lays them out in the reference pass, E97)
ENUMS = {}   # enum type name -> (size, align) of its underlying type, collected from all assemblies

def collect_enums(asms):
    for a in asms.values():
        for r in a.t.TypeDef.rows:
            if not a.is_enum(r): continue
            for f in (r.FieldList or []):
                fr = f.row
                if fr.Flags.fdStatic: continue
                et = bytes(fr.Signature.value)[1]
                n = ET.get(et)
                if n in VALUE: ENUMS.setdefault(str(r.TypeName), VALUE[n])
                break

def struct_size(name):
    """(size, align) of a value type from its instance fields in any loaded assembly (sequential layout); cached in VALUE."""
    for a in (x for asms in _ASMS.values() for x in asms.values()):
        r = a.find(name)
        if r is None: continue
        off, al = 0, 1
        for f in (r.FieldList or []):
            if f.row.Flags.fdStatic: continue
            fn, sz, fa = a.kind(bytes(f.row.Signature.value))
            if sz is None or fn in HASREF: HASREF.add(name)
            sz = sz if sz is not None else 4
            off = (off + fa - 1) // fa * fa + sz; al = max(al, fa)
        VALUE[name] = ((off + al - 1) // al * al or 1, al)
        return VALUE[name]
    raise ValueError(f"unknown value type {name}")

class Layout(dict):
    """{offset: field} that remembers its type (for struct-interior names)."""
    def __init__(self, typename): super().__init__(); self.typename = typename

def struct_fields(name):
    """{offset: 'a.b'} of a struct's instance fields (sequential), nested structs flattened."""
    for a in (x for asms in _ASMS.values() for x in asms.values()):
        r = a.find(name)
        if r is None: continue
        out, off = {}, 0
        for f in (r.FieldList or []):
            if f.row.Flags.fdStatic: continue
            fn, sz, fa = a.kind(bytes(f.row.Signature.value)); sz = sz or 4
            off = (off + fa - 1) // fa * fa
            sub = struct_fields(fn) if sz > fa and fn not in VALUE_PRIMS else {}
            out.update({off + k: f"{f.row.Name}.{v}" for k, v in sub.items()} or {off: str(f.row.Name)})
            off += sz
        return out
    return {}

VALUE_PRIMS = {"long", "ulong", "double"}

def field_name(typename, fields, off):
    """Name of the field at off, or 'struct.sub' when off falls inside a struct-typed field."""
    if off in fields: return fields[off]
    for (t, o), (n, size) in STRUCT_AT.items():
        if t == typename and o < off < o + size:
            sub = struct_fields(n).get(off - o)
            if sub: return f"{fields[o]}.{sub}"
    return None

def typename_of(src, r): return str(r.TypeName)

_ASMS = {}

def layout(il_dir, asm, typename):
    """{offset: field} for typename incl. base classes found in il_dir assemblies."""
    asms = _ASMS.get(il_dir)
    if asms is None:
        asms = _ASMS[il_dir] = {f[:-4]: Asm(os.path.join(il_dir, f)) for f in os.listdir(il_dir) if f.endswith(".dll")}
        collect_enums(asms)
    chain, a, name, ns = [], asms[asm], typename, ""
    while name not in ("MonoBehaviour", "Behaviour", "Component", "Object", "ValueType", None):
        src = next((x for x in [a] + list(asms.values()) if x.find(name)), None)
        if src is None: break
        r = src.find(name); chain.append((src, r))
        name, ns = (str(r.Extends.row.TypeName), str(getattr(r.Extends.row, "TypeNamespace", ""))) if r.Extends and r.Extends.row else (None, "")
    # object header: UnityEngine.Object-derived 0x10, plain class (System.Object) 0x8 (vtable + sync), struct `this` 0
    off, out = (0 if name == "ValueType" else 8 if (name, ns) == ("Object", "System") else 0x10), Layout(typename)
    for src, r in reversed(chain):
        fs = [f.row for f in (r.FieldList or []) if not f.row.Flags.fdStatic]
        kinds = [(f, src.kind(bytes(f.Signature.value))) for f in fs]
        off = (off + 3) // 4 * 4
        for f, (n, size, al) in kinds:   # pass 0: references and structs containing references, declaration order
            if size is None: out[off] = str(f.Name); TYPES[(typename_of(src, r), str(f.Name))] = n; off += 4
            elif n in HASREF: off = (off + al - 1) // al * al; out[off] = str(f.Name); STRUCT_AT[(typename, off)] = (n, size); off += size
        for f, (n, size, al) in kinds:
            if size is not None and n not in HASREF:
                off = (off + al - 1) // al * al; out[off] = str(f.Name)
                if size > al: STRUCT_AT[(typename, off)] = (n, size)
                off += size
    return out

def annotate(text, fields, got, static=()):
    """Per function: `this` may be typed int* by Ghidra (param_1[i] / param_1 + i scale by 4) or as a byte offset."""
    def fname(off): return field_name(getattr(fields, "typename", None), fields, off)
    def name(off): return "this." + (fname(off) or hex(off))
    def gotref(blk):   # (GOTBASE + off) -> [slot name]; GOTBASE = PTR_got_IMAGE_* or a puVarN assigned from it here
        base = "|".join(["PTR_got_IMAGE_\\w+"] + re.findall(r"\b(puVar\d+) = PTR_got_IMAGE_\w+;", blk))
        return re.sub(rf"\((?:{base}) \+ (0x[0-9a-f]+|\d+)\)", lambda m: f"[{got.get(int(m.group(1), 0), m.group(1))}]", blk)
    out = []
    for blk in re.split(r"(?m)^(?===== )", text):
        h = re.match(r"==== (\w+) ", blk)
        if h and h.group(1) in static: out.append(gotref(blk)); continue   # static method: param_1 is not `this`
        sig = re.search(r"\w[\w:<>]*\(([^)]*)\)\s*\{", blk)
        scale = 4 if sig and re.search(r"(int|undefined4|uint) \*param_1", sig.group(1)) else 1
        blk = re.sub(r"\*\([a-z0-9 ]+\*\)\(\(int\)param_1 \+ (0x[0-9a-f]+|\d+)\)", lambda m: name(int(m.group(1), 0)), blk)
        blk = re.sub(r"\*\([a-z0-9 ]+\*\)\(param_1 \+ (0x[0-9a-f]+|\d+)\)", lambda m: name(int(m.group(1), 0) * scale), blk)
        blk = re.sub(r"param_1\[(0x[0-9a-f]+|\d+)\]", lambda m: name(int(m.group(1), 0) * 4), blk)
        # remaining `param_1 + off` (not dereferenced) = address of a field, e.g. a struct passed by ref
        blk = re.sub(r"(?<![*\w])(\(int\))?param_1 \+ (0x[0-9a-f]+)(?![\w\[])",
                     lambda m: "ref " + name(int(m.group(2), 16) * (1 if m.group(1) else scale)) if fname(int(m.group(2), 16) * (1 if m.group(1) else scale)) else m.group(0), blk)
        out.append(gotref(blk))
    return "".join(out)

def chain_fields(text, il_dir, asm, owner):
    """*(T *)(this.f + 0xNN) -> this.f.name, using the layout of f's declared type (one level, E96)."""
    cache = {}
    def sub(m):
        f, off = m.group(1), int(m.group(2), 0)
        t = next((v for (o, n), v in TYPES.items() if n == f and o == owner), None) or next((v for (o, n), v in TYPES.items() if n == f), None)
        if t in (None, "array", "generic", "ref"): return m.group(0)
        if t not in cache:
            try: cache[t] = layout(il_dir, asm, t)
            except Exception: cache[t] = {}
        n = cache[t].get(off)
        return f"this.{f}.{n}" if n else m.group(0)
    return re.sub(r"\*\([a-z0-9 ]+\*\)\(this\.(\w+) \+ (0x[0-9a-f]+|\d+)\)", sub, text)

if __name__ == "__main__":
    if sys.argv[1] == "--selftest":
        L = layout(sys.argv[2], "Assembly-CSharp", "RainMergePostEffect")
        want = {0x10: "m_RGBCurve", 0x14: "m_RGBCurveTex", 0x18: "m_ColorTbl", 0x1c: "m_SoftFocusMaterial", 0x30: "m_aGaussWeight",
                0x34: "m_aGaussOffset", 0x38: "m_GaussIntensity", 0x48: "m_UpdateRGBCurve", 0x68: "m_UpdateTexturesOnStartup", 0x78: "m_UseMergeShader", 0x7c: "m_DownSizeDiv"}
        bad = {k: (v, L.get(k)) for k, v in want.items() if L.get(k) != v}
        assert not bad, bad; print("layout selftest ok:", len(want), "offsets")
        sys.exit()
    il, asm, tn, src, dst = sys.argv[1:6]
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", "maps")
    got = {int(r["got_byte_offset"], 16): (r["patch_type"] + ":" + r["target"])[:70] for r in csv.DictReader(open(os.path.join(root, asm + ".got.csv")))}
    open(dst, "w", encoding="utf-8").write(annotate(open(src, encoding="utf-8").read(), layout(il, asm, tn), got))
