"""T5 pre-lifter (E96): turn a DecompileNamespace.java dump of one type into per-method "lift packets" -- the exact C#
signature from the skeleton, the callees' C# signatures, and the pseudocode with mechanical C# rewrites applied
(fields/GOT/vtable names via annotate_decomp + vtable, engine calls as properties/methods with receivers, literals,
array indexing, bounds-check/exception noise removed). Completing a packet into C# is review work; the result is
checked with the compile harness (tools/lift_compile.py).
Usage: lift.py <il_dir> <assembly> <TypeName> <decomp.txt> <out.md>"""
import csv, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
import annotate_decomp as AD
import vtable as VT

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ET = {1: "void", 2: "bool", 3: "char", 4: "sbyte", 5: "byte", 6: "short", 7: "ushort", 8: "int", 9: "uint", 10: "long",
      11: "ulong", 12: "float", 13: "double", 14: "string", 0x18: "IntPtr", 0x1c: "object"}
STRUCTS = {"Vector2": 2, "Vector3": 3, "Vector4": 4, "Quaternion": 4, "Color": 4, "Rect": 4}   # words when passed split

def mangle(target):
    return re.sub(r"[^A-Za-z0-9_<>\[\]]", "_", "plt_" + target.replace("::", "__"))

class Sigs:
    """C#-ish signatures of methods by 'Ns.Type::Method' from all IL assemblies."""
    def __init__(self, il_dir):
        self.m = {}
        for f in sorted(os.listdir(il_dir)):
            if not f.endswith(".dll"): continue
            try: pe = dnfile.dnPE(os.path.join(il_dir, f))
            except Exception: continue
            t = pe.net.mdtables
            def tdor(v):
                tag, row = v & 3, v >> 2
                try: return str([t.TypeDef, t.TypeRef, t.TypeSpec][tag].rows[row - 1].TypeName)
                except Exception: return "?"
            def typ(b, i):
                e = b[i]; i += 1
                if e in ET: return ET[e], i
                if e in (0x11, 0x12): v, i = AD.Asm.cu(None, b, i); return tdor(v), i
                if e == 0x1D: s, i = typ(b, i); return s + "[]", i
                if e == 0x10: s, i = typ(b, i); return "ref " + s, i
                if e == 0x15:
                    g, i = typ(b, i); n, i = AD.Asm.cu(None, b, i); a = []
                    for _ in range(n): x, i = typ(b, i); a.append(x)
                    return f"{g.split(chr(96))[0]}<{','.join(a)}>", i
                if e in (0x13, 0x1E): n, i = AD.Asm.cu(None, b, i); return f"T{n}", i
                return f"et{e:#x}", i
            for r in t.TypeDef.rows:
                ns = str(r.TypeNamespace); tn = (ns + "." if ns else "") + str(r.TypeName)
                for mr in (r.MethodList or []):
                    m = mr.row; b = bytes(m.Signature.value)
                    try:
                        n, i = AD.Asm.cu(None, b, 1); ret, i = typ(b, i); ps = []
                        for _ in range(n): p, i = typ(b, i); ps.append(p)
                    except Exception: continue
                    pn = [str(p.row.Name) for p in (m.ParamList or []) if p.row and p.row.Sequence > 0]
                    self.m.setdefault(f"{tn}::{m.Name}", []).append(
                        {"static": bool(m.Flags.mdStatic), "ret": ret, "params": ps, "names": pn, "type": str(r.TypeName)})
    def get(self, target, nargs=None):
        cands = self.m.get(target.split("[")[0].replace("<inst>", ""), [])
        if nargs is not None:
            fit = [c for c in cands if len(c["params"]) + (0 if c["static"] else 1) == nargs]
            if fit: return fit[0]
        return cands[0] if cands else None

def split_args(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "," and depth == 0: out.append(cur.strip()); cur = ""; continue
        depth += ch in "(["; depth -= ch in ")]"; cur += ch
    if cur.strip(): out.append(cur.strip())
    return out

def call_sites(text):
    """(start, end, name, args) for each `plt_...(...)` call, balanced parentheses."""
    for m in re.finditer(r"(?:::)?(plt_[A-Za-z0-9_<>\[\]]+)\(", text):
        i, depth = m.end(), 1
        while i < len(text) and depth:
            depth += text[i] == "("; depth -= text[i] == ")"; i += 1
        yield m.start(), i, m.group(1), split_args(text[m.end():i - 1])

def join_struct(words):
    """uStack_a4, uStack_a0, uStack_9c -> uStack_a4 (consecutive 4-byte stack words of one struct)."""
    offs = [re.fullmatch(r"(?:\(\w+\))?u?[A-Za-z]*Stack_([0-9a-f]+)(?:\._\d+_\d+_)?", w) for w in words]
    if all(offs):
        v = [int(o.group(1), 16) for o in offs]
        if all(v[k] - v[k + 1] == 4 for k in range(len(v) - 1)) or all(v[k + 1] - v[k] == 4 for k in range(len(v) - 1)):
            return words[0] if v[0] > v[-1] else words[0]
    return "new(" + ", ".join(words) + ")"

def rewrite_call(name, args, plt, sigs):
    target = plt.get(name)
    if target is None: return None
    sig = sigs.get(target)
    owner, meth = (target.split("::", 1) + [""])[:2]
    meth = meth.replace("<inst>", "")
    if sig is None: return f"/*?{target}*/{meth}({', '.join(args)})"
    # value-type return through a hidden first pointer argument: plt(&tmp, ...) -> tmp = ...
    out = None
    if sig["ret"] in STRUCTS and args and args[0].startswith("&"):
        out, args = args[0][1:], args[1:]
    nf = sum(p in ("float", "double") for p in sig["params"])
    fargs, gargs = (args[:nf], args[nf:]) if nf and len(args) >= nf else ([], args)
    recv = None
    if not sig["static"] and gargs: recv, gargs = gargs[0], gargs[1:]
    # rebuild IL order: floats from the FPR list, everything else from the GPR list (structs split into words)
    merged, k, fi = [], 0, 0
    for p in sig["params"]:
        if p in ("float", "double") and nf:
            merged.append(re.sub(r"^\(double\)\(float\)|^\(double\)", "", fargs[fi]) if fi < len(fargs) else "?"); fi += 1; continue
        n = STRUCTS.get(p, 1)
        if k + n <= len(gargs): merged.append(join_struct(gargs[k:k + n]) if n > 1 else gargs[k])
        k += n
    merged += gargs[k:]
    who = recv if recv is not None else owner.split(".")[-1]
    if meth.startswith("get_") and not merged: expr = f"{who}.{meth[4:]}"
    elif meth.startswith("set_") and len(merged) == 1: expr = f"{who}.{meth[4:]} = {merged[0]}"
    elif meth == "op_Implicit": expr = f"(bool){merged[0] if merged else who}"
    elif meth == "op_Equality": expr = f"({merged[0]} == {merged[1]})" if len(merged) == 2 else None
    elif meth == "op_Inequality": expr = f"({merged[0]} != {merged[1]})" if len(merged) == 2 else None
    else: expr = f"{who}.{meth}({', '.join(merged)})"
    if expr is None: expr = f"{owner.split('.')[-1]}.{meth}({', '.join(merged)})"
    return f"{out} = {expr}" if out else expr

def prelift(body, plt, sigs, vt, own=""):
    b = body
    b = re.sub(r"\*\*\(float \*\*\)\[R4:([-0-9.e]+)\]", lambda m: m.group(1) + "f", b)
    b = re.sub(r"\*\*\(double \*\*\)\[R8:([-0-9.e]+)\]", lambda m: m.group(1), b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\[LDSTR:([^\]]*)\]", lambda m: '"' + m.group(1).replace('"', '\\"') + '"', b)
    b = re.sub(r"\*\*\([a-z0-9 ]+\*\*\)\[SFLDA:([^\]]*)\]", lambda m: m.group(1).replace("::", "."), b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\[SFLDA:([^\]]*)\]", lambda m: m.group(1).replace("::", "."), b)
    # virtual calls on this
    b = re.sub(r"\(\*\*\(code \*\*\)\(\*param_1 \+ (0x[0-9a-f]+)\)\)\(param_1,?\s*", lambda m: "this." + vt.get(int(m.group(1), 16), "vcall_" + m.group(1)).split("::")[-1] + "(", b)
    # array length / element / bounds-check noise
    b = re.sub(r"\*\(u?int \*\)\((\w+(?:\.\w+)?) \+ 0xc\)", r"\1.Length", b)
    b = re.sub(r"\n\s*if \(\(?(?:ulonglong|uint)\)?\(?(?:longlong)?\)?[^\n]*<= [^\n]*\) \{\n\s*[^\n]*func_0x[0-9a-f]+\([^\n]*\);\n(?:\s*[^\n]*= \(\w+\)\w+;\n)?\s*\}", "", b)
    b = re.sub(r"\n\s*\w+ = func_0x[0-9a-f]+\([^\n]*\);", "", b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\((\w+(?:\.\w+)?) \+ \(?(?:int)?\)?\(?(\w+) << 2\)? \+ 0x10\)", r"\1[\2]", b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\((\w+(?:\.\w+)?) \+ (\w+) \* 4 \+ 0x10\)", r"\1[\2]", b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\((\w+(?:\.\w+)?) \+ 0x10\)", r"\1[0]", b)
    # engine / game calls through the PLT, innermost first
    for _ in range(2000):
        changed = False
        for st, en, name, args in sorted(call_sites(b), key=lambda c: c[1] - c[0]):
            inner = b[st:en]
            if "plt_" in inner[len(name) + 1:]: continue
            r = rewrite_call(name, args, plt, sigs)
            if r is not None: b = b[:st] + r + b[en:]; changed = True; break
        if not changed: break
    def direct(m):
        tname, meth, args = m.group(1), m.group(2), split_args(m.group(3))
        sig = sigs.get(f"{tname or own}::{meth}", len(args))
        if sig and not sig["static"] and args: return f"{args[0]}.{meth}({', '.join(args[1:])})"
        return f"{tname + '.' if tname else ''}{meth}({', '.join(args)})"
    b = re.sub(r"(?<![\w.])(?:([A-Za-z_]\w*)::)?([A-Za-z_]\w*)\(((?:[^()]|\([^()]*\))*)\)(?=;|\s*\)|,)",
               lambda m: direct(m) if (m.group(1) or sigs.get(f"{own}::{m.group(2)}")) and not m.group(2).startswith(("plt_", "func_")) else m.group(0), b)
    b = b.replace("param_1", "this")
    return b

def main(il, asm, tn, src, dst):
    maps = os.path.join(ROOT, "work", "maps")
    plt = {mangle(r["target"]): r["target"] for r in csv.DictReader(open(os.path.join(maps, asm + ".plt.csv"))) if r["patch_type"] == "METHOD"}
    got = {int(r["got_byte_offset"], 16): (r["patch_type"] + ":" + r["target"])[:90] for r in csv.DictReader(open(os.path.join(maps, asm + ".got.csv")))}
    text = AD.annotate(open(src, encoding="utf-8").read(), AD.layout(il, asm, tn), got)
    sigs = Sigs(il); vt = VT.offsets(VT.Types(il), tn)
    skel = open(os.path.join(ROOT, "work", "skeleton", asm + ".cs"), encoding="utf-8").read()
    m = re.search(rf"(?m)^public partial class {re.escape(tn)}\b.*?^\}}", skel, re.S)
    skel_t = m.group(0) if m else ""
    out = [f"# Lift packets: {asm} {tn}\n"]
    for blk in re.split(r"(?m)^(?===== )", text):
        h = re.match(r"==== (\w+) @ ([0-9a-f]+)\s+// C# ([^\n]*)", blk)
        if not h: continue
        body = blk.split("---- asm")[0]
        body = body[body.index("{", body.index("(")):] if "{" in body else body
        lifted = prelift(body, plt, sigs, vt, tn)
        name = h.group(1).replace("_ctor", ".ctor").replace("_cctor", ".cctor")
        cs = [l.strip() for l in skel_t.splitlines() if re.search(rf"\b{re.escape(name.split('.')[-1] if name.startswith('.') else name)}\(", l)]
        callees = sorted({rewrite_call(n, a, plt, sigs) and plt.get(n) for _, _, n, a in call_sites(body)} - {None})
        out.append(f"## {h.group(3)}  @0x{h.group(2)}\n\nSkeleton: `{' | '.join(cs) or '?'}`\n\nCallees: {', '.join('`' + c + '`' for c in callees) or '-'}\n\n```c\n{lifted.strip()}\n```\n")
    open(dst, "w", encoding="utf-8").write("\n".join(out))

if __name__ == "__main__":
    main(*sys.argv[1:6])
