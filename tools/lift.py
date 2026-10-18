"""T5 pre-lifter (E96): turn a DecompileNamespace.java dump of one type into per-method "lift packets" -- the exact C#
signature from the skeleton, the callees' C# signatures, and the pseudocode with mechanical C# rewrites applied
(fields/GOT/vtable names via annotate_decomp + vtable, engine calls as properties/methods with receivers, literals,
array indexing, bounds-check/exception noise removed). Completing a packet into C# is review work; the result is
checked with the compile harness (tools/lift_compile.py).
Usage: lift.py <il_dir> <assembly> <TypeName> <decomp.txt> <out.md>
       lift.py <il_dir> <assembly> @<types.txt> <decomp_dir> <out_dir>   (batch: <Type with / as .>.decomp.txt -> .md)"""
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
    if target is None and "<" in name and name.startswith("plt_"):
        base = re.sub(r"<[^>]*>$", "<inst>", name); t0 = plt.get(base)
        if t0: target = t0.replace("<inst>", "") + "<" + name.rsplit("<", 1)[1]
    if target is None: return None
    owner, meth = (target.split("::", 1) + [""])[:2]
    meth = re.sub(r"<[^>]*>$", "", meth)
    # overloads: pick the one whose register-argument count (receiver + GPR words + FPRs) matches the call site
    cands = sigs.m.get(target.split("[")[0].replace("<inst>", ""), []) or sigs.m.get(re.sub(r"<[^>]*>$", "", target), [])
    words = lambda c: (0 if c["static"] else 1) + sum(STRUCTS.get(p, 1) for p in c["params"]) + (STRUCTS.get(c["ret"], 0) and 1)
    sig = next((c for c in cands if words(c) == len(args)), cands[0] if cands else None)
    if sig is None and meth.startswith("GetComponent") and len(args) == 1 and "<" in target:   # generic instance
        return f"{args[0]}.GetComponent<{target.rsplit('<', 1)[1]}()"
    if target == "wrapper:STELEMREF" and len(args) == 3: return f"{args[0]}[{args[1]}] = {args[2]}"   # typed array store
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
    # Ghidra drops trailing int args that follow floats (PPC64: each float also consumes a GPR slot) -> flag them
    merged += [f"/*?{p} arg missing: check asm*/" for p in sig["params"][len(merged):]]
    who = recv if recv is not None else ("/*recv? check asm*/" if not sig["static"] else "") + owner.split(".")[-1]
    if recv == "param_1" and OWN[0] and "." not in owner and owner != OWN[0]: who = "base"   # direct call into a game base type
    if meth.startswith("get_") and not merged: expr = f"{who}.{meth[4:]}"
    elif meth.startswith("set_") and len(merged) == 1: expr = f"{who}.{meth[4:]} = {merged[0]}"
    elif meth == "op_Implicit": expr = f"(bool){merged[0] if merged else who}"
    elif meth == "op_Equality": expr = f"({merged[0]} == {merged[1]})" if len(merged) == 2 else None
    elif meth == "op_Inequality": expr = f"({merged[0]} != {merged[1]})" if len(merged) == 2 else None
    else:
        targs = re.search(r"(<[^>]*>)$", target)
        expr = f"{who}.{meth}{targs.group(1) if targs and targs.group(1) != '<inst>' else ''}({', '.join(merged)})"
    if expr is None: expr = f"{owner.split('.')[-1]}.{meth}({', '.join(merged)})"
    return f"{out} = {expr}" if out else expr

def rgctx_calls(asm_text, got):
    """Per <inst> PLT call in the disassembly: the METHOD_RGCTX GOT entry loaded into r12 just before it."""
    out, hi, lo = [], None, None
    for line in asm_text.splitlines():
        m = re.search(r"lis r0,(-?0x[0-9a-f]+|-?\d+)", line)
        if m: hi = int(m.group(1), 0) & 0xFFFF; continue
        m = re.search(r"ori r0,r0,(0x[0-9a-f]+|\d+)", line)
        if m and hi is not None: lo = (hi << 16) | int(m.group(1), 0); continue
        m = re.search(r"bl 0x[0-9a-f]+ ; (plt_\S+<inst>)", line)
        if m:
            g = got.get(lo, "") if lo is not None else ""
            out.append(g.split(":", 1)[1] if g.startswith("METHOD_RGCTX:") else None); lo = None
    return out

def apply_rgctx(body, names):
    """Replace the k-th `plt_X<inst>(` in the pseudocode by the k-th resolved instantiation."""
    it = iter(names)
    def sub(m):
        n = next(it, None)
        return ("" if m.group(1) else "") + ("plt_" + re.sub(r"[^A-Za-z0-9_<>\[\],]", "_", n.replace("::", "__")) + "(" if n else m.group(0))
    return re.sub(r"(::)?plt_[A-Za-z0-9_]+<inst>\(", sub, body)

def local_types(body, plt, sigs):
    """{local: type} for `local = plt_call(...)` whose return type is a class (or the generic argument of GetComponent<T>)."""
    types = {}
    for m in re.finditer(r"(\w+) = (plt_[A-Za-z0-9_<>\[\],]+)\(", body):
        tgt = plt.get(m.group(2)) or m.group(2)[4:].replace("__", "::")
        g = re.search(r"<(\w+)>$", tgt)
        sig = sigs.get(re.sub(r"<[^>]*>$", "", tgt))
        t = g.group(1) if g and "GetComponent" in tgt else (sig["ret"] if sig else None)
        if t and t not in ("void", "bool", "int", "float", "object", "string") and not t.endswith("[]"): types[m.group(1)] = t
    # `local = Type.staticField` (e.g. an inlined singleton GetInstance) -> the static field's declared type
    for m in re.finditer(r"(\w+) = \*+\([^)]*\)\[SFLDA:([\w/]+)::(\w+)\]", body):
        t = static_type(m.group(2), m.group(3))
        if t: types[m.group(1)] = t
    return types

def static_type(tn, field):
    """Declared type of a static reference field, read from the skeleton (top-level game types only)."""
    skel = _CACHE.get("skel", "")
    c = re.search(rf"(?m)^(?:\[[^\n]*\][ \t]*)*(?:(?:public|internal|sealed|abstract|static|partial) )*class {re.escape(tn.split('/')[-1])}\b.*?^\}}", skel, re.S)
    f = c and re.search(rf"static global::([\w.]+) {re.escape(field)};", c.group(0))
    return f.group(1).split(".")[-1] if f and not f.group(1).startswith("UnityEngine.") else None

def getter_index(il, asm, got):
    """{field-or-static: 'Type.Method()'} for trivial AOT getters: body (after the r30 GOT prologue) is one load from
    `this` (`lwz r3,0x30(r1); l* rX,off(r3)`) or from a static slot (`lis/ori r0; lwzx r3,r30,r0; l* rX,0(r3)`)."""
    import capstone, struct
    f = open(os.path.join(ROOT, "work", "retail_elf", asm + ".dll.prx"), "rb").read()
    ph, n = struct.unpack(">Q", f[0x20:0x28])[0], struct.unpack(">H", f[0x38:0x3a])[0]
    segs = [struct.unpack(">IIQQQQQQ", f[ph + i * 56:ph + i * 56 + 56]) for i in range(n)]
    seg = [(s[2], s[3], s[4]) for s in segs if s[0] == 1]   # (file off, vaddr, filesz)
    md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    out, layouts = {}, {}
    for r in csv.DictReader(open(os.path.join(ROOT, "work", "maps", asm + ".methods.csv"))):
        a, sz = int(r["address"] or "0", 16), int(r["size"] or "0")
        if not r["address"] or sz > 96 or "," in r.get("params", ""): continue
        so = next((o + a - v for o, v, fs in seg if v <= a < v + fs), None)
        if so is None: continue
        ins = [f"{i.mnemonic} {i.op_str}" for i in md.disasm(f[so:so + sz], a)]
        try: core = ins[ins.index("lwz r30, 0(r30)") + 1:ins.index("ld r0, 0x60(r1)")]
        except ValueError: continue
        tn, mn = r["type"], r["method"]
        def fld_at(off):
            if tn not in layouts:
                try: layouts[tn] = AD.layout(il, asm, tn)
                except Exception: layouts[tn] = {}
            return layouts[tn].get(off)
        # store-only method (setter, SetX(v){a=v; b=1;}, Cancel(){a=0;}): only this/param loads, li, stores to this
        # -> key "=field" for every written field, value "Type.M(v): a=v, b=1"
        c = [x for x in core if x not in ("frsp f1, f1", "fmr f1, f1")]
        regs, eff = {}, []
        for x in c:
            if x == "lwz r3, 0x30(r1)": regs["r3"] = "this"; continue
            m = re.fullmatch(r"l[bhwf]\w* (\w+), 0x34\(r1\)", x) or re.fullmatch(r"li (\w+), (-?\w+)", x)
            if m: regs[m.group(1)] = "v" if "0x34" in x else str(int(m.group(2), 0)); continue
            m = re.fullmatch(r"st[bhwf]\w* (\w+), (0x[0-9a-f]+|\d+)\(r3\)", x)
            if m and regs.get("r3") == "this" and m.group(1) in regs and fld_at(int(m.group(2), 0)):
                eff.append((fld_at(int(m.group(2), 0)), regs[m.group(1)])); continue
            eff = None; break
        if eff:
            d = f"{tn}.{mn}({'v' if r.get('params') else ''}): " + ", ".join(f"{fl}={v}" for fl, v in eff)
            for fl, _ in eff: out.setdefault("=" + fl, []).append(d)
            continue
        if r.get("params"): continue
        m = re.fullmatch(r"l[bhwf]\w* \w+, (0x[0-9a-f]+|\d+)\(r3\)", c[1]) if len(c) == 2 and c[0] == "lwz r3, 0x30(r1)" else None
        if m:
            fld = fld_at(int(m.group(1), 0))
            if fld: out.setdefault(fld, []).append(f"{tn}.{mn}()")
            continue
        if len(c) == 4 and c[2] == "lwzx r3, r30, r0" and re.fullmatch(r"l[bhwf]\w* \w+, 0\(r3\)", c[3]):
            hi = re.fullmatch(r"lis r0, (-?\w+)", c[0]); lo = re.fullmatch(r"ori r0, r0, (\w+)", c[1])
            if hi and lo:
                g = got.get(((int(hi.group(1), 0) & 0xFFFF) << 16) | int(lo.group(1), 0), "")
                if g.startswith("SFLDA:"): out.setdefault(g[6:].replace("::", "."), []).append(f"{tn}.{mn}()")
    return out

def fix_switches(body, start):
    """Ghidra prints jump-table overrides (DecompileNamespace + got.csv) as switch(*(GOT[SWITCH] + idx*4)) with case
    labels = target addresses; rewrite to switch(idx) with case labels = table indices (targets are method-relative)."""
    where = {}
    def sw(m):
        for k, off in enumerate(int(x, 16) for x in m.group(1).split()): where.setdefault(start + off, []).append(k)
        return f"switch({m.group(2)})"
    body = re.sub(r"switch\(\*\([^)]*\)\s*\(\*\([^)]*\)\[SWITCH:\d+ targets ([0-9a-fx ]+)\] \+\s*(.+?) \* 4\)\)", sw, body, flags=re.S)
    return re.sub(r"case 0x([0-9a-f]+):", lambda m: " ".join(f"case {k}:" for k in where[int(m.group(1), 16)]) if int(m.group(1), 16) in where else m.group(0), body)

IL_DIR, ASM, OWN = [None], [None], [None]
def typedef_name(asm, row):
    a = AD._ASMS.get(IL_DIR[0], {}).get(asm)
    return a.tdor_name(row << 2)[0].replace("/", ".") if a else f"{asm}!0x02{row:06x}"

PRIMS = {"bool", "byte", "sbyte", "char", "short", "ushort", "int", "uint", "string", "object"}
UNSAFE = {"float", "double", "long", "ulong", "Vector2", "Vector3", "Vector4", "Quaternion", "Color", "Color32", "Rect", "Bounds",
          "Matrix4x4", "RaycastHit", "Ray"}
def skel_params(cs_line):
    """[(type, name)] from a skeleton declaration, or None when Ghidra's param numbering is unreliable (float/struct/long)."""
    m = re.search(r"\(([^)]*)\)\s*(?::[^{]*)?\{", cs_line)
    if not m or not m.group(1).strip(): return []
    out = []
    for p in m.group(1).split(","):
        if " " not in p.strip() or "<" in p or "params " in p: return None
        t, n = p.strip().rsplit(" ", 1); t = t.replace("ref ", "").replace("out ", "").replace("global::", "")
        if t.split(".")[-1] in UNSAFE: return None
        out.append((t, n))
    return out
def prelift(body, plt, sigs, vt, own="", types=None, static=False, params=()):
    b = body
    # IL parameter names (only when Ghidra's numbering is reliable: no float/struct params): param_2.. (param_1 = this)
    for k, (pt, pn) in enumerate(params):
        b = re.sub(rf"\bparam_{k + (1 if static else 2)}\b", pn, b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\[TYPE_FROM_HANDLE:([\w.-]+)!token 0x02([0-9a-f]{6})\]", lambda m: f"typeof({typedef_name(m.group(1), int(m.group(2), 16))})", b)
    b = re.sub(r"\*\*\([a-z0-9 ]+ \*\*\)\[R4:([-0-9.e]+)\]", lambda m: m.group(1) + "f", b)
    b = re.sub(r"\*\*\(double \*\*\)\[R8:([-0-9.e]+)\]", lambda m: m.group(1), b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\[LDSTR:([^\]]*)\]", lambda m: '"' + m.group(1).replace('"', '\\"') + '"', b)
    b = re.sub(r"\*\*\([a-z0-9 ]+\*\*\)\[SFLDA:([^\]]*)\]", lambda m: m.group(1).replace("::", "."), b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\[SFLDA:([^\]]*)\]", lambda m: m.group(1).replace("::", "."), b)
    # virtual calls on this
    b = re.sub(r"\(\*\*\(code \*\*\)\(\*param_1 \+ (0x[0-9a-f]+|\d+)\)\)\(param_1,?\s*", lambda m: "this." + vt.get(int(m.group(1), 0), "vcall_" + m.group(1)).split("::")[-1] + "(", b)
    for m in re.finditer(r"(\w+) = \(\w+ \*\)(?:Object\.|plt_UnityEngine_Object__)FindObjectOfType\(typeof\(([\w.]+)\)\)", b):   # `as T` result
        types = dict(types or {}); types.setdefault(m.group(1), m.group(2).replace(".", "/"))
    for var, t in (types or {}).items():
        try: L = AD.layout(IL_DIR[0], ASM[0], t)
        except Exception: continue
        sc = 4 if re.search(rf"\b(?:int|uint|undefined4) \*{var};", b) else 1   # Ghidra scales pointer arithmetic
        b = re.sub(rf"\*\([a-z0-9 ]+\*\)\({var} \+ (0x[0-9a-f]+|\d+)\)", lambda m: f"{var}.{L[int(m.group(1), 0) * sc]}" if int(m.group(1), 0) * sc in L else m.group(0), b)
        try: vtt = VT.offsets(cached("vt", lambda: VT.Types(IL_DIR[0])), t)
        except Exception: vtt = {}
        b = re.sub(rf"\(\*\*\(code \*\*\)\(\*\(?(?:int \*)?\)?{var} \+ (0x[0-9a-f]+|\d+)\)\)\(\(?(?:int \*)?\)?{var},?\s*",
                   lambda m: f"{var}.{vtt[int(m.group(1), 0)].split('::')[-1]}(" if int(m.group(1), 0) in vtt else m.group(0), b)
        b = re.sub(rf"\b{var}\[(0x[0-9a-f]+|\d+)\]", lambda m: f"{var}.{L[int(m.group(1), 0) * 4]}" if int(m.group(1), 0) * 4 in L else m.group(0), b)   # Ghidra int* view
    # array length / element / bounds-check noise
    b = re.sub(r"\*\(u?int \*\)\((\w+(?:\.\w+)?) \+ 0xc\)", r"\1.Length", b)
    b = re.sub(r"\n\s*if \(\(?(?:ulonglong|uint)\)?\(?(?:longlong)?\)?[^\n]*<= [^\n]*\) \{\n\s*[^\n]*func_0x[0-9a-f]+\([^\n]*\);\n(?:\s*[^\n]*= \(\w+\)\w+;\n)?\s*\}", "", b)
    b = re.sub(r"\n\s*\w+ = func_0x[0-9a-f]+\([^\n]*\);", "", b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\((\w+(?:\.\w+)?) \+ \(?(?:int)?\)?\(?(\w+) << 2\)? \+ 0x10\)", r"\1[\2]", b)
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\((\w+(?:\.\w+)?) \+ (\w+) \* 4 \+ 0x10\)", r"\1[\2]", b)
    # element 0 sits at +0x10 like the first field of a UnityEngine.Object: only for variables also used as arrays
    b = re.sub(r"\*\([a-z0-9 ]+\*\)\((\w+(?:\.\w+)?) \+ 0x10\)", lambda m: m.group(1) + "[0]" if m.group(1) + ".Length" in b else m.group(0), b)
    b = re.sub(r"(plt_[A-Za-z0-9_<>\[\],]+)\s+\(", r"\1(", b)   # Ghidra wraps long calls before the parenthesis
    # object / array allocation through the Mono runtime (the .ctor call, if not inlined, follows)
    b = re.sub(r"plt_mono_array_new_specific\(\*\([^)]*\)\[VTABLE:([\w/.]+)\[\]\],\s*([^)]+)\)", lambda m: f"new {m.group(1)}[{m.group(2)}]", b)
    b = re.sub(r"plt_mono_object_new_specific\(\*\([^)]*\)\[VTABLE:([\w/.]+)\]\)", lambda m: f"new {m.group(1)}() /*alloc; ctor below or inlined*/", b)
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
        if sig and not sig["static"] and args:
            if tname and tname != own and args[0] == "param_1": return f"base.{meth}({', '.join(args[1:])})"   # non-virtual call into a base type
            return f"{args[0]}.{meth}({', '.join(args[1:])})"
        return f"{tname + '.' if tname else ''}{meth}({', '.join(args)})"
    b = re.sub(r"(?<![\w.])(?:([A-Za-z_]\w*)::)?([A-Za-z_]\w*)\(((?:[^()]|\([^()]*\))*)\)(?=;|\s*\)|,)",
               lambda m: direct(m) if (m.group(1) or sigs.get(f"{own}::{m.group(2)}")) and not m.group(2).startswith(("plt_", "func_")) else m.group(0), b)
    if not static: b = b.replace("param_1", "this")   # static methods keep param_N (no receiver)
    return b

_CACHE = {}
LOCAL_DECL = re.compile(r"  [a-z][a-z0-9 ]* \*?(?:[a-zA-Z]*Var\d+|[a-z]*Stack_[0-9a-f_]+|local_[0-9a-f]+);")
def compact(lifted):
    """Token-lean packet body: drop Ghidra local declarations, the GOT-base load, blank lines and the final `return;`."""
    ls = [l for l in lifted.strip().splitlines() if l.strip() and not LOCAL_DECL.fullmatch(l)
          and not re.fullmatch(r"\s*\w+ = PTR_got_IMAGE_\w+;", l)]
    if len(ls) > 2 and ls[-2].strip() == "return;" and ls[-1] == "}": del ls[-2]
    return "\n".join(ls)

def cached(key, fn):
    if key not in _CACHE: _CACHE[key] = fn()
    return _CACHE[key]

def main(il, asm, tn, src, dst):
    maps = os.path.join(ROOT, "work", "maps")
    plt = cached("plt", lambda: {mangle(r["target"]): r["target"] for r in csv.DictReader(open(os.path.join(maps, asm + ".plt.csv"))) if r["patch_type"] == "METHOD"})
    got = cached("got", lambda: {int(r["got_byte_offset"], 16): (r["patch_type"] + ":" + r["target"])[:90 if r["patch_type"] != "SWITCH" else None] for r in csv.DictReader(open(os.path.join(maps, asm + ".got.csv")))})
    sigs = cached("sigs", lambda: Sigs(il)); vt = VT.offsets(cached("vt", lambda: VT.Types(il)), tn); IL_DIR[0], ASM[0], OWN[0] = il, asm, tn
    getters = cached("getters", lambda: getter_index(il, asm, got))
    skel = cached("skel", lambda: open(os.path.join(ROOT, "work", "skeleton", asm + ".cs"), encoding="utf-8").read())
    m = re.search(rf"(?m)^([ \t]*)(?:\[[^\n]*\][ \t]*)*(?:(?:public|internal|private|protected|sealed|abstract|static|partial) )*(?:class|struct) {re.escape(tn.split('/')[-1])}\b.*?^\1\}}", skel, re.S)
    skel_t = m.group(0) if m else ""
    static = set(re.findall(r"(?m)^[ \t]*(?:\[[^\n]*\][ \t]*)*(?:(?:public|private|protected|internal) )*static [^(=;]*?(\w+)\(", skel_t))
    text = AD.annotate(open(src, encoding="utf-8").read(), AD.layout(il, asm, tn), got, static)
    text = AD.chain_fields(text, il, asm, tn)
    out = [f"# Lift packets: {asm} {tn}\n"]
    for blk in re.split(r"(?m)^(?===== )", text):
        h = re.match(r"==== (\w+) @ ([0-9a-f]+)\s+// C# ([^\n]*)", blk)
        if not h: continue
        body = blk.split("---- asm")[0]
        body = body[body.index("{", body.index("(")):] if "{" in body else body
        asm_part = blk.split("---- asm")[1] if "---- asm" in blk else ""
        body = apply_rgctx(body, rgctx_calls(asm_part, got))
        body = fix_switches(body, int(h.group(2), 16))
        name = h.group(1).replace("_ctor", ".ctor").replace("_cctor", ".cctor")
        cs = [l.strip() for l in skel_t.splitlines() if re.search(rf"\b{re.escape(tn.split('/')[-1] if name.startswith('.') else name)}\(", l)]
        isstatic = any(" static " in l for l in cs)
        hn = re.search(r"\(([^)]*)\)", h.group(3)).group(1).split()   # IL parameter names from the packet header
        pick = [l for l in cs if (skel_params(l) or [(None, None)] * 99) and [n for _, n in (skel_params(l) or [])] == hn]
        ps = skel_params(pick[0]) if len(pick) == 1 else (skel_params(cs[0]) if len(cs) == 1 else None)
        lts0 = local_types(body, plt, sigs)
        for pt, pn in ps or []:
            if pt not in PRIMS and not pt.startswith(("UnityEngine.", "System.")) and not pt.endswith("[]"):
                lts0[pn] = pt.replace(".", "/") if "." in pt and not pt.startswith("UTILITY.") else pt
        lifted = prelift(body, plt, sigs, vt, tn, lts0, isstatic, ps or ())
        callees = sorted({rewrite_call(n, a, plt, sigs) and plt.get(n) for _, _, n, a in call_sites(body)} - {None})
        def recv_types(fld):   # declared types of the receivers in `X.fld` (this = own type)
            ts = set()
            for x in re.findall(rf"(\w+)\.{re.escape(fld)}\b", lifted):
                ts |= {tn} if x == "this" else {v for (o, n), v in AD.TYPES.items() if n == x} | ({lts[x]} if x in lts else set())
            return ts
        lts = local_types(body, plt, sigs)
        gs = sorted(f"`{k}` = {' / '.join(v)}" for k, v in getters.items() if "." in k and re.search(rf"(?<!\w){re.escape(k)}\b", lifted))
        gs += sorted(f"`{k}` = {' / '.join(g for g in v if g.split('.')[0] in rt)}" for k, v in getters.items()
                     if "." not in k and not k.startswith("=") and (rt := recv_types(k)) and any(g.split(".")[0] in rt for g in v))
        ss = sorted(f"`{k[1:]}`: {' / '.join(g for g in v if g.split('.')[0] in rt)}" for k, v in getters.items()
                    if k.startswith("=") and re.search(rf"\.{re.escape(k[1:])} =[^=]", lifted) and (rt := recv_types(k[1:])) and any(g.split(".")[0] in rt for g in v))
        meta = [f"Callees: {', '.join('`' + c + '`' for c in callees)}" if callees else "",
                f"Inlined getters (field read = this getter): {'; '.join(gs)}" if gs else "",
                f"Inlined store-only methods (field write may be one of): {'; '.join(ss)}" if ss else ""]
        out.append(f"## {h.group(3)}  @0x{h.group(2)}\n" + "".join(m + "\n" for m in meta if m) + f"```c\n{compact(lifted)}\n```\n")
    open(dst, "w", encoding="utf-8").write("\n".join(out))

if __name__ == "__main__":
    il, asm, tn, src, dst = sys.argv[1:6]
    if not tn.startswith("@"): main(il, asm, tn, src, dst)
    else:
        for t in open(tn[1:]).read().split():
            f = os.path.join(src, t.replace("/", ".").replace("<", "_").replace(">", "_") + ".decomp.txt")
            if not os.path.exists(f): continue
            try: main(il, asm, t, f, os.path.join(dst, t.replace("/", ".").replace("<", "_").replace(">", "_") + ".md"))
            except Exception as e: print(f"{t}: {type(e).__name__}: {e}")
