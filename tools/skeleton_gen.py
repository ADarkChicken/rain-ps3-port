"""Generate a compilable C# skeleton of a .NET assembly from IL metadata (bodies stripped by Mono AOT; E10).
Usage: skeleton_gen.py <assembly.dll> <out.cs> [--exclude TypeA,TypeB] [ref.dll ...]
--exclude: top-level types left out because a reconstructed source file provides them.
Emits every type (classes, structs, enums, interfaces, delegates; nested), fields (+ Serializable/SerializeField/
NonSerialized/const/readonly), properties/indexers, events, operators, constructors (with base-ctor chaining),
generics + constraints, virtual/override/abstract/sealed, interface lists. Method bodies throw NotImplementedException.
Compiler-generated types/members (names containing '<') are skipped and counted; skipped items are listed at the end."""
import os, struct, sys, dnfile

KW = set("""abstract as base bool break byte case catch char checked class const continue decimal default delegate do double
else enum event explicit extern false finally fixed float for foreach goto if implicit in int interface internal is lock long
namespace new null object operator out override params private protected public readonly ref return sbyte sealed short sizeof
stackalloc static string struct switch this throw true try typeof uint ulong unchecked unsafe ushort using virtual void
volatile while""".split())
PRIM = {0x01: "void", 0x02: "bool", 0x03: "char", 0x04: "sbyte", 0x05: "byte", 0x06: "short", 0x07: "ushort", 0x08: "int",
        0x09: "uint", 0x0a: "long", 0x0b: "ulong", 0x0c: "float", 0x0d: "double", 0x0e: "string", 0x18: "global::System.IntPtr",
        0x19: "global::System.UIntPtr", 0x1c: "object", 0x16: "global::System.TypedReference"}
OPS = {"op_Implicit": "implicit", "op_Explicit": "explicit", "op_Addition": "+", "op_Subtraction": "-", "op_Multiply": "*",
       "op_Division": "/", "op_Modulus": "%", "op_Equality": "==", "op_Inequality": "!=", "op_LessThan": "<",
       "op_GreaterThan": ">", "op_LessThanOrEqual": "<=", "op_GreaterThanOrEqual": ">=", "op_UnaryNegation": "-",
       "op_UnaryPlus": "+", "op_LogicalNot": "!", "op_BitwiseAnd": "&", "op_BitwiseOr": "|", "op_ExclusiveOr": "^",
       "op_OnesComplement": "~", "op_Increment": "++", "op_Decrement": "--", "op_True": "true", "op_False": "false",
       "op_LeftShift": "<<", "op_RightShift": ">>"}

def ident(n): return "@" + n if n in KW else n
def cu(b, i):
    x = b[i]
    if x & 0x80 == 0: return x, i + 1
    if x & 0x40 == 0: return ((x & 0x3f) << 8) | b[i+1], i + 2
    return ((x & 0x1f) << 24) | (b[i+1] << 16) | (b[i+2] << 8) | b[i+3], i + 4

class Asm:
    def __init__(self, path):
        self.pe = dnfile.dnPE(path); t = self.pe.net.mdtables; self.t = t
        g = lambda n: (getattr(t, n).rows if getattr(t, n, None) else [])
        self.td, self.md, self.fd, self.tr, self.ts = g("TypeDef"), g("MethodDef"), g("Field"), g("TypeRef"), g("TypeSpec")
        self.enc = {r.NestedClass.row_index: r.EnclosingClass.row_index for r in g("NestedClass")}
        self.mowner, self.fowner = {}, {}
        for i, r in enumerate(self.td, 1):
            for m in (r.MethodList or []): self.mowner[m.row_index] = i
            for f in (r.FieldList or []): self.fowner[f.row_index] = i
        self.gparams = {}
        for r in g("GenericParam"):
            self.gparams.setdefault((r.Owner.table.name, r.Owner.row_index), []).append(r)
        for k in self.gparams: self.gparams[k].sort(key=lambda r: r.Number)
        self.gconstr = {}
        rows = g("GenericParam")
        for c in g("GenericParamConstraint"):
            self.gconstr.setdefault(c.Owner.row_index, []).append(c.Constraint)
        self.gp_index = {id(r): i for i, r in enumerate(rows, 1)}
        self.consts = {}
        for c in g("Constant"):
            self.consts[(c.Parent.table.name, c.Parent.row_index)] = (c.Type, bytes(c.Value.value if hasattr(c.Value, "value") else c.Value))
        self.attrs = {}
        for ca in g("CustomAttribute"):
            try:
                ty = ca.Type.row; cls = ty.Class.row if hasattr(ty, "Class") else None
                nm = str(getattr(cls, "TypeName", "")) if cls is not None else ""
                self.attrs.setdefault((ca.Parent.table.name, ca.Parent.row_index), set()).add(nm)
            except Exception: pass
        self.ifaces = {}
        for ii in g("InterfaceImpl"): self.ifaces.setdefault(ii.Class.row_index, []).append(ii.Interface)
        self.props, self.events, self.sem = {}, {}, {}
        for pm in g("PropertyMap"):
            pass
        for s in g("MethodSemantics"):
            self.sem[s.Method.row_index] = (s.Association.table.name, s.Association.row_index, s.struct.Semantics)
        self.prop_rows, self.event_rows = g("Property"), g("Event")
        self.prop_owner, self.event_owner = {}, {}
        pmr = g("PropertyMap")
        for k, pm in enumerate(pmr):
            for p in (pm.PropertyList or []): self.prop_owner[p.row_index] = pm.Parent.row_index
        for k, em in enumerate(g("EventMap")):
            for e in (em.EventList or []): self.event_owner[e.row_index] = em.Parent.row_index
        self.params = {i: [p.row for p in (r.ParamList or []) if p.row] for i, r in enumerate(self.md, 1)}

class Gen:
    def __init__(self, main, refs, exclude=()):
        self.a = Asm(main); self.refs = [Asm(r) for r in refs]; self.exclude = set(exclude)
        self.skipped = []
        self.by_full = {}
        for asm in [self.a] + self.refs:
            for i, r in enumerate(asm.td, 1):
                if i not in asm.enc: self.by_full.setdefault((str(r.TypeNamespace), str(r.TypeName)), (asm, i))

    # ---------- type names ----------
    def tdef_name(self, asm, i, with_args=True):
        r = asm.td[i-1]; n = str(r.TypeName)
        base = n.split("`")[0]
        if i in asm.enc: outer = self.tdef_name(asm, asm.enc[i], with_args=False)
        else: outer = "global::" + (str(r.TypeNamespace) + "." if str(r.TypeNamespace) else "")
        full = (outer + "." if i in asm.enc else outer) + ident(base)
        return full
    def tref_name(self, asm, row):
        r = asm.tr[row-1]; n = str(r.TypeName).split("`")[0]; scope = r.ResolutionScope
        if scope is not None and scope.table.name == "TypeRef":
            return self.tref_name(asm, scope.row_index) + "." + ident(n)
        ns = str(r.TypeNamespace)
        return "global::" + (ns + "." if ns else "") + ident(n)
    def coded(self, asm, v, ctx):
        tag, row = v & 3, v >> 2
        if tag == 0: return self.tdef_name(asm, row)
        if tag == 1: return self.tref_name(asm, row)
        b = bytes(asm.ts[row-1].Signature.value); s, _ = self.sig_type(asm, b, 0, ctx); return s
    def sig_type(self, asm, b, i, ctx):
        e = b[i]; i += 1
        if e in PRIM: return PRIM[e], i
        if e in (0x11, 0x12): v, i = cu(b, i); return self.coded(asm, v, ctx), i
        if e == 0x1d: s, i = self.sig_type(asm, b, i, ctx); return s + "[]", i
        if e == 0x14:
            s, i = self.sig_type(asm, b, i, ctx); rank, i = cu(b, i)
            n, i = cu(b, i); i2 = i
            for _ in range(n): _, i2 = cu(b, i2)
            m, i2 = cu(b, i2)
            for _ in range(m): _, i2 = cu(b, i2)
            return s + "[" + "," * (rank - 1) + "]", i2
        if e == 0x15:
            gt, i = self.sig_type(asm, b, i, ctx); n, i = cu(b, i); args = []
            for _ in range(n): a_, i = self.sig_type(asm, b, i, ctx); args.append(a_)
            return f"{gt}<{', '.join(args)}>", i
        if e == 0x13: n, i = cu(b, i); return ctx["type_gp"][n] if n < len(ctx["type_gp"]) else f"T{n}", i
        if e == 0x1e: n, i = cu(b, i); return ctx["meth_gp"][n] if n < len(ctx["meth_gp"]) else f"M{n}", i
        if e == 0x10: s, i = self.sig_type(asm, b, i, ctx); return "ref " + s, i
        if e == 0x0f: s, i = self.sig_type(asm, b, i, ctx); return s + "*", i
        if e in (0x1f, 0x20): _, i = cu(b, i); return self.sig_type(asm, b, i, ctx)   # modreq/modopt
        if e == 0x45: return self.sig_type(asm, b, i, ctx)                             # pinned
        raise ValueError(f"sig element {e:#x}")
    def method_sig(self, asm, mi, ctx):
        b = bytes(asm.md[mi-1].Signature.value); i = 0; conv = b[i]; i += 1
        if conv & 0x10: _, i = cu(b, i)
        n, i = cu(b, i); ret, i = self.sig_type(asm, b, i, ctx); ps = []
        for _ in range(n): p, i = self.sig_type(asm, b, i, ctx); ps.append(p)
        return ret, ps

    # ---------- helpers ----------
    def access(self, flags_val, member="method"):
        m = flags_val & 7
        return {1: "private", 2: "internal", 3: "internal", 4: "protected", 5: "protected internal", 6: "public"}.get(m, "private")
    def type_access(self, r, nested):
        f = r.struct.Flags
        v = f & 7
        if not nested: return "public" if v == 1 else "internal"
        return {2: "public", 3: "private", 4: "protected", 5: "internal", 6: "internal", 7: "protected internal"}.get(v, "private")
    def gp_names(self, asm, table, row):
        return [str(r.Name) for r in asm.gparams.get((table, row), [])]
    def gp_clause(self, asm, table, row, ctx):
        out = []
        for r in asm.gparams.get((table, row), []):
            cs = []; f = r.struct.Flags
            if f & 0x8: cs.append("struct")
            elif f & 0x4: cs.append("class")
            for c in asm.gconstr.get(asm.gp_index[id(r)], []):
                tag = {"TypeDef": 0, "TypeRef": 1, "TypeSpec": 2}[c.table.name]
                n = self.coded(asm, (c.row_index << 2) | tag, ctx)
                if n not in ("global::System.ValueType",): cs.append(n)
            if f & 0x10 and not f & 0x8: cs.append("new()")
            if cs: out.append(f" where {r.Name} : {', '.join(cs)}")
        return "".join(out)
    def const_literal(self, asm, key, ty):
        c = asm.consts.get(key)
        if not c: return "default(" + ty + ")"
        et, v = c
        fmt = {0x02: "?", 0x03: "H", 0x04: "b", 0x05: "B", 0x06: "h", 0x07: "H", 0x08: "i", 0x09: "I", 0x0a: "q", 0x0b: "Q",
               0x0c: "f", 0x0d: "d"}
        if et == 0x0e: return '"' + v.decode("utf-16-le").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'
        if et == 0x12: return "null"
        x = struct.unpack("<" + fmt[et], v)[0]
        if et == 0x02: return "true" if x else "false"
        if et == 0x03: return f"(char){x}"
        if et == 0x0c: return "float.NaN" if x != x else ("float.PositiveInfinity" if x == float("inf") else ("float.NegativeInfinity" if x == float("-inf") else repr(x) + "f"))
        if et == 0x0d: return "double.NaN" if x != x else ("double.PositiveInfinity" if x == float("inf") else ("double.NegativeInfinity" if x == float("-inf") else repr(x)))
        suffix = {0x09: "u", 0x0a: "L", 0x0b: "UL"}.get(et, "")
        return f"unchecked(({ty}){x}{suffix})" if x < 0 or et in (0x09, 0x0b) else f"{x}{suffix}"

    def base_info(self, asm, i):
        e = asm.td[i-1].Extends
        if not e or not e.row: return None, None, None
        tag = {"TypeDef": 0, "TypeRef": 1, "TypeSpec": 2}[e.table.name]
        name = self.coded(asm, (e.row_index << 2) | tag, {"type_gp": self.gp_names(asm, "TypeDef", i), "meth_gp": []})
        ra, ri = None, None
        if e.table.name == "TypeDef": ra, ri = asm, e.row_index
        elif e.table.name == "TypeRef":
            r = asm.tr[e.row_index-1]; ra, ri = self.by_full.get((str(r.TypeNamespace), str(r.TypeName)), (None, None))
        elif e.table.name == "TypeSpec":
            b = bytes(asm.ts[e.row_index-1].Signature.value)
            if b[0] == 0x15 and b[1] in (0x11, 0x12):
                v, _ = cu(b, 2); t2, row = v & 3, v >> 2
                if t2 == 0: ra, ri = asm, row
                elif t2 == 1:
                    r = asm.tr[row-1]; ra, ri = self.by_full.get((str(r.TypeNamespace), str(r.TypeName)), (None, None))
        return name, ra, ri
    def ctor_chain(self, asm, i):
        """': base(...)' if the base type has no accessible parameterless instance ctor."""
        _, ba, bi = self.base_info(asm, i)
        if not ba: return ""
        ctors = []
        for m in (ba.td[bi-1].MethodList or []):
            r = m.row
            if str(r.Name) == ".ctor" and (r.struct.Flags & 7) != 1:
                b = bytes(r.Signature.value); n, _ = cu(b, 1); ctors.append((n, m.row_index))
        if not ctors or any(n == 0 for n, _ in ctors): return ""
        n, mi = min(ctors)
        try:
            _, ps = self.method_sig(ba, mi, {"type_gp": self.gp_names(ba, "TypeDef", bi), "meth_gp": []})
            return " : base(" + ", ".join(f"default({p.replace('ref ', '')})" for p in ps) + ")"
        except Exception: return ""

    # ---------- emit ----------
    def emit_type(self, asm, i, ind, out):
        r = asm.td[i-1]; name = str(r.TypeName)
        if "<" in name or name == "<Module>": self.skipped.append(("type", self.tdef_name(asm, i))); return
        f = r.Flags; nested = i in asm.enc
        gps = self.gp_names(asm, "TypeDef", i); ctx = {"type_gp": gps, "meth_gp": []}
        bname, ba, bi = self.base_info(asm, i)
        is_iface = bool(f.tdInterface)
        kind = "interface" if is_iface else "class"
        if bname == "global::System.Enum": kind = "enum"
        elif bname == "global::System.ValueType": kind = "struct"
        elif bname in ("global::System.MulticastDelegate",): kind = "delegate"
        mods = [self.type_access(r, nested)]
        if kind == "class":
            if f.tdAbstract and f.tdSealed: mods.append("static")
            elif f.tdAbstract: mods.append("abstract")
            elif f.tdSealed: mods.append("sealed")
        attrs = asm.attrs.get(("TypeDef", i), set())
        pre = ind + ("[global::System.Serializable] " if f.tdSerializable and kind in ("class", "struct") else "")
        own = gps[self.outer_gp_count(asm, i):] if nested else gps
        simple = ident(name.split("`")[0]) + (f"<{', '.join(own)}>" if own else "")
        if kind == "delegate":
            inv = [m.row_index for m in (r.MethodList or []) if str(m.row.Name) == "Invoke"]
            ret, ps = self.method_sig(asm, inv[0], ctx); pn = self.param_names(asm, inv[0], len(ps))
            out.append(f"{pre}{' '.join(mods)} delegate {ret} {simple}({', '.join(self.param_decl(asm, inv[0], ps, pn))}){self.gp_clause(asm, 'TypeDef', i, ctx)};")
            return
        if kind == "enum":
            ut = "int"; lines = []
            for fl in (r.FieldList or []):
                fr = fl.row
                if str(fr.Name) == "value__": ut, _ = self.sig_type(asm, bytes(fr.Signature.value), 1, ctx); continue
                lines.append(f"{ind}    {ident(str(fr.Name))} = {self.const_literal(asm, ('Field', fl.row_index), ut)},")
            flags = "[global::System.Flags] " if "FlagsAttribute" in attrs else ""
            out.append(f"{ind}{flags}{' '.join(mods)} enum {simple} : {ut}"); out.append(ind + "{"); out += lines; out.append(ind + "}")
            return
        bases = []
        if kind == "class" and bname and bname != "object" and bname != "global::System.Object": bases.append(bname)
        for itf in asm.ifaces.get(i, []):
            tag = {"TypeDef": 0, "TypeRef": 1, "TypeSpec": 2}[itf.table.name]
            bases.append(self.coded(asm, (itf.row_index << 2) | tag, ctx))
        out.append(f"{pre}{' '.join(mods)} {'partial ' if kind != 'interface' else ''}{kind} {simple}" + (" : " + ", ".join(bases) if bases else "") + self.gp_clause(asm, "TypeDef", i, ctx))
        out.append(ind + "{")
        self.emit_members(asm, i, kind, ind + "    ", out, ctx)
        for n, o in sorted(asm.enc.items()):
            if o == i: self.emit_type(asm, n, ind + "    ", out)
        out.append(ind + "}")
    def outer_gp_count(self, asm, i):
        return len(self.gp_names(asm, "TypeDef", asm.enc[i])) if i in asm.enc else 0
    def own_gps(self, asm, i):
        return len(self.gp_names(asm, "TypeDef", i)) > self.outer_gp_count(asm, i)
    def param_names(self, asm, mi, n):
        names = {p.Sequence: str(p.Name) for p in asm.params.get(mi, [])}
        return [ident(names.get(k + 1) or f"p{k}") for k in range(n)]
    def param_decl(self, asm, mi, ps, pn):
        outs = {p.Sequence for p in asm.params.get(mi, []) if p.Flags.pdOut and not p.Flags.pdIn}
        res = []
        for k, (t, n) in enumerate(zip(ps, pn)):
            if t.startswith("ref ") and (k + 1) in outs: t = "out " + t[4:]
            res.append(f"{t} {n}")
        return res
    def emit_members(self, asm, i, kind, ind, out, ctx):
        r = asm.td[i-1]; is_iface = kind == "interface"
        for fl in (r.FieldList or []):
            fr = fl.row; fn = str(fr.Name)
            if "<" in fn or "$" in fn: self.skipped.append(("field", f"{self.tdef_name(asm, i)}::{fn}")); continue
            ty, _ = self.sig_type(asm, bytes(fr.Signature.value), 1, ctx); fv = fr.Flags
            mods = [self.access(fr.struct.Flags)]
            a = asm.attrs.get(("Field", fl.row_index), set())
            pre = ""
            if "SerializeField" in a: pre += "[global::UnityEngine.SerializeField] "
            if fv.fdNotSerialized: pre += "[global::System.NonSerialized] "
            if "HideInInspector" in a: pre += "[global::UnityEngine.HideInInspector] "
            if fv.fdLiteral:
                lit = self.const_literal(asm, ('Field', fl.row_index), ty)
                if ty not in PRIM.values() and lit != "null": lit = f"({ty})({lit})"   # enum-typed constants
                out.append(f"{ind}{pre}{' '.join(mods)} const {ty} {ident(fn)} = {lit};"); continue
            if fv.fdStatic: mods.append("static")
            if fv.fdInitOnly: mods.append("readonly")
            out.append(f"{ind}{pre}{' '.join(mods)} {ty} {ident(fn)};")
        accessor = {}
        for m in (r.MethodList or []):
            s = asm.sem.get(m.row_index)
            if s: accessor[m.row_index] = s
        # properties
        for pi, prow in enumerate(asm.prop_rows, 1):
            if asm.prop_owner.get(pi) != i: continue
            self.emit_property(asm, i, pi, prow, accessor, kind, ind, out, ctx)
        for ei, erow in enumerate(asm.event_rows, 1):
            if asm.event_owner.get(ei) != i: continue
            self.emit_event(asm, i, ei, erow, accessor, kind, ind, out, ctx)
        for m in (r.MethodList or []):
            mi = m.row_index
            if mi in accessor and accessor[mi][0] in ("Property", "Event"): continue
            self.emit_method(asm, i, mi, kind, ind, out, ctx)
    def base_has_virtual(self, asm, mi):
        """True if some base class declares a virtual method with the same name and parameter count."""
        i = asm.mowner.get(mi); name = str(asm.md[mi-1].Name)
        n, _ = cu(bytes(asm.md[mi-1].Signature.value), 1 + (1 if asm.md[mi-1].Signature.value[0] & 0x10 else 0))
        _, ba, bi = self.base_info(asm, i)
        seen = 0
        while ba and bi and seen < 32:
            for m in (ba.td[bi-1].MethodList or []):
                r = m.row
                if str(r.Name) == name and r.Flags.mdVirtual:
                    b = bytes(r.Signature.value); k, _ = cu(b, 1 + (1 if b[0] & 0x10 else 0))
                    if k == n: return True
            _, ba, bi = self.base_info(ba, bi); seen += 1
        return False
    def mods_for(self, asm, mi, kind):
        mr = asm.md[mi-1]; f = mr.Flags; fv = mr.struct.Flags
        if kind == "interface": return []
        mods = [self.access(fv)]
        if f.mdStatic: mods.append("static")
        if f.mdVirtual:
            reuse = not f.mdNewSlot and self.base_has_virtual(asm, mi)
            if f.mdAbstract: mods.append("abstract")
            elif not f.mdNewSlot and not reuse: mods.append("virtual")   # UnityScript: virtual w/o newslot, nothing to override
            elif not f.mdNewSlot: mods.append("sealed override" if f.mdFinal else "override")
            elif f.mdFinal: pass                     # implicit interface implementation
            else: mods.append("virtual")
            if f.mdAbstract and not f.mdNewSlot and reuse: mods[-1] = "abstract override"
        return mods
    def body(self, kind, mi=None, asm=None):
        if kind == "interface": return ";"
        if asm is not None and asm.md[mi-1].Flags.mdAbstract: return ";"
        return " { throw new global::System.NotImplementedException(); }"
    def emit_method(self, asm, i, mi, kind, ind, out, ctx):
        mr = asm.md[mi-1]; name = str(mr.Name); f = mr.Flags
        if "<" in name or name == ".cctor":
            if name != ".cctor": self.skipped.append(("method", f"{self.tdef_name(asm, i)}::{name}"))
            return
        mctx = {"type_gp": ctx["type_gp"], "meth_gp": self.gp_names(asm, "MethodDef", mi)}
        try: ret, ps = self.method_sig(asm, mi, mctx)
        except Exception as e: self.skipped.append(("method", f"{name}: {e}")); return
        pn = self.param_names(asm, mi, len(ps)); pd = ", ".join(self.param_decl(asm, mi, ps, pn))
        if "." in name and name not in (".ctor",):   # explicit interface implementation
            itf, meth = name.rsplit(".", 1)
            out.append(f"{ind}{ret} global::{itf.split('<')[0]}.{ident(meth)}({pd}){self.body(kind)}"); return
        if name == ".ctor":
            if kind == "struct" and not ps: return
            if f.mdStatic: return
            simple = ident(str(asm.td[i-1].TypeName).split("`")[0])
            out.append(f"{ind}{self.access(mr.struct.Flags)} {simple}({pd}){self.ctor_chain(asm, i) if kind == 'class' else ''} {{ throw new global::System.NotImplementedException(); }}"); return
        if name == "Finalize" and not ps and kind == "class" and f.mdVirtual and not f.mdNewSlot:
            out.append(f"{ind}~{ident(str(asm.td[i-1].TypeName).split('`')[0])}() {{ }}"); return   # C# destructor syntax
        mods = self.mods_for(asm, mi, kind)
        gps = mctx["meth_gp"]; gtxt = f"<{', '.join(gps)}>" if gps else ""
        where = "" if "override" in " ".join(mods) else self.gp_clause(asm, "MethodDef", mi, mctx)
        if name in OPS:
            op = OPS[name]
            if op in ("implicit", "explicit"):
                out.append(f"{ind}public static {op} operator {ret}({pd}){self.body(kind)}"); return
            out.append(f"{ind}public static {ret} operator {op}({pd}){self.body(kind)}"); return
        out.append(f"{ind}{' '.join(mods)}{' ' if mods else ''}{ret} {ident(name)}{gtxt}({pd}){where}{self.body(kind, mi, asm)}")
    def emit_property(self, asm, i, pi, prow, accessor, kind, ind, out, ctx):
        getter = setter = None
        for mi, (tbl, row, sem) in accessor.items():
            if tbl == "Property" and row == pi:
                if sem & 2: getter = mi
                elif sem & 1: setter = mi
        acc = getter or setter
        if not acc: return
        pname = str(prow.Name)
        mctx = {"type_gp": ctx["type_gp"], "meth_gp": []}
        ret, ps = self.method_sig(asm, getter, mctx) if getter else (None, None)
        if not getter:
            _, sps = self.method_sig(asm, setter, mctx); ret, ps = sps[-1], sps[:-1]
        mods = self.mods_for(asm, acc, kind)
        def part(mi, word):
            if not mi: return ""
            if kind == "interface" or asm.md[mi-1].Flags.mdAbstract: return f" {word};"
            a1 = self.access(asm.md[mi-1].struct.Flags); a0 = self.access(asm.md[acc-1].struct.Flags)
            return f" {a1 + ' ' if a1 != a0 else ''}{word} {{ throw new global::System.NotImplementedException(); }}"
        if "." in pname:
            itf, p = pname.rsplit(".", 1)
            head = f"{ret} global::{itf}." + ("this[" + ", ".join(self.param_decl(asm, acc, ps, self.param_names(asm, acc, len(ps)))) + "]" if ps else ident(p))
            out.append(f"{ind}{head} {{{part(getter, 'get')}{part(setter, 'set')} }}"); return
        if ps:
            pd = ", ".join(self.param_decl(asm, acc, ps, self.param_names(asm, acc, len(ps))))
            head = f"{' '.join(mods)}{' ' if mods else ''}{ret} this[{pd}]"
        else:
            head = f"{' '.join(mods)}{' ' if mods else ''}{ret} {ident(pname)}"
        out.append(f"{ind}{head} {{{part(getter, 'get')}{part(setter, 'set')} }}")
    def emit_event(self, asm, i, ei, erow, accessor, kind, ind, out, ctx):
        add = [mi for mi, (t, r_, s) in accessor.items() if t == "Event" and r_ == ei]
        if not add: return
        et = erow.EventType; tag = {"TypeDef": 0, "TypeRef": 1, "TypeSpec": 2}[et.table.name]
        ty = self.coded(asm, (et.row_index << 2) | tag, ctx)
        mods = self.mods_for(asm, add[0], kind)
        body = ";" if kind == "interface" else " { add { throw new global::System.NotImplementedException(); } remove { throw new global::System.NotImplementedException(); } }"
        out.append(f"{ind}{' '.join(mods)}{' ' if mods else ''}event {ty} {ident(str(erow.Name))}{body}")

    def run(self, out_path):
        out = ["// AUTO-GENERATED skeleton from IL metadata (tools/skeleton_gen.py). Bodies are stubs.",
               "#pragma warning disable 0108, 0114, 0414, 0169, 0649, 0067, 0659, 0661, 0660, 0628, 0109"]
        byns = {}
        for i, r in enumerate(self.a.td, 1):
            if i in self.a.enc or str(r.TypeName) == "<Module>": continue
            byns.setdefault(str(r.TypeNamespace), []).append(i)
        for ns, items in sorted(byns.items()):
            ind = ""
            if ns: out.append(f"namespace {ns}"); out.append("{"); ind = "    "
            for i in items:
                if str(self.a.td[i-1].TypeName) in self.exclude: continue
                self.emit_type(self.a, i, ind, out)
            if ns: out.append("}")
        open(out_path, "w", encoding="utf-8").write("\n".join(out) + "\n")
        print(f"{out_path}: {len(out)} lines; skipped {len(self.skipped)} compiler-generated/unsupported items")

if __name__ == "__main__":
    args = sys.argv[3:]; excl = []
    if args and args[0] == "--exclude": excl = args[1].split(","); args = args[2:]
    Gen(sys.argv[1], args, excl).run(sys.argv[2])
