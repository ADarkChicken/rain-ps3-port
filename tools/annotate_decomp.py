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
        return str(getattr(r, "TypeName", "?")), (tag == 0 and self.is_enum(r))
    def is_enum(self, r):
        e = r.Extends
        return bool(e and e.row and str(getattr(e.row, "TypeName", "")) == "Enum")
    def kind(self, b):
        """(name, size, align) of a field signature; size None = reference."""
        e = b[1]
        if e in ET: n = ET[e]; return (n,) + VALUE[n] if n in VALUE else (n, None, 4)
        if e == 0x11:   # valuetype
            v, _ = self.cu(b, 2); n, enum = self.tdor_name(v)
            if enum: return n, 4, 4
            if n in VALUE: return (n,) + VALUE[n]
            raise ValueError(f"unknown value type {n}")
        return "ref", None, 4
    def find(self, name):
        for i, r in enumerate(self.t.TypeDef.rows, 1):
            if str(r.TypeName) == name: return r
        return None

def layout(il_dir, asm, typename):
    """{offset: field} for typename incl. base classes found in il_dir assemblies."""
    asms = {f[:-4]: Asm(os.path.join(il_dir, f)) for f in os.listdir(il_dir) if f.endswith(".dll")}
    chain, a, name = [], asms[asm], typename
    while name not in ("MonoBehaviour", "Behaviour", "Component", "Object", None):
        src = next((x for x in [a] + list(asms.values()) if x.find(name)), None)
        if src is None: break
        r = src.find(name); chain.append((src, r))
        name = str(r.Extends.row.TypeName) if r.Extends and r.Extends.row else None
    off, out = 0x10, {}
    for src, r in reversed(chain):
        fs = [f.row for f in (r.FieldList or []) if not f.row.Flags.fdStatic]
        kinds = [(f, src.kind(bytes(f.Signature.value))) for f in fs]
        for f, (n, size, al) in kinds:
            if size is None: out[off] = str(f.Name); off += 4
        for f, (n, size, al) in kinds:
            if size is not None: off = (off + al - 1) // al * al; out[off] = str(f.Name); off += size
    return out

def annotate(text, fields, got):
    """Per function: `this` may be typed int* by Ghidra (param_1[i] / param_1 + i scale by 4) or as a byte offset."""
    def name(off): return "this." + fields.get(off, hex(off))
    out = []
    for blk in re.split(r"(?m)^(?===== )", text):
        sig = re.search(r"\w[\w:<>]*\(([^)]*)\)\s*\{", blk)
        scale = 4 if sig and re.search(r"(int|undefined4|uint) \*param_1", sig.group(1)) else 1
        blk = re.sub(r"\*\([a-z0-9 ]+\*\)\(\(int\)param_1 \+ (0x[0-9a-f]+|\d+)\)", lambda m: name(int(m.group(1), 0)), blk)
        blk = re.sub(r"\*\([a-z0-9 ]+\*\)\(param_1 \+ (0x[0-9a-f]+|\d+)\)", lambda m: name(int(m.group(1), 0) * scale), blk)
        blk = re.sub(r"param_1\[(0x[0-9a-f]+|\d+)\]", lambda m: name(int(m.group(1), 0) * 4), blk)
        out.append(blk)
    text = "".join(out)
    return re.sub(r"\(puVar[0-9]+ \+ (0x[0-9a-f]+)\)", lambda m: f"[{got.get(int(m.group(1), 16), m.group(1))}]", text)

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
