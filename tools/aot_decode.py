"""Decode Mono AOT (file version 67, mono/mono@8219a5b, see tools/ref_mono) GOT slot patch info into names.
Usage: aot_decode.py <aot.prx> <exports.txt> <il_dir> <out_got.csv>
Port of aot-runtime.c: mono_aot_get_offset, decode_value, decode_klass_ref, decode_method_ref, decode_field_info,
decode_patch. Names come from IL metadata (il_dir/<image>.dll). Undecodable entries are reported, never guessed."""
import csv, re, struct, sys, os, dnfile

PATCH = """BB ABS LABEL METHOD METHOD_JUMP METHOD_REL METHODCONST INTERNAL_METHOD SWITCH EXC EXC_NAME CLASS IMAGE FIELD
VTABLE CLASS_INIT SFLDA LDSTR LDTOKEN TYPE_FROM_HANDLE R4 R8 IP IID ADJUSTED_IID BB_OVF EXC_OVF GOT_OFFSET DECLSEC RVA
DELEGATE_TRAMPOLINE ICALL_ADDR JIT_ICALL_ADDR INTERRUPTION_REQUEST_FLAG METHOD_RGCTX RGCTX_FETCH GENERIC_CLASS_INIT
MONITOR_ENTER MONITOR_EXIT MSCORLIB_GOT_ADDR SEQ_POINT_INFO LLVM_IMT_TRAMPOLINE NONE""".split()
P = {n: i for i, n in enumerate(PATCH)}
WRAPPER = """NONE DELEGATE_INVOKE DELEGATE_BEGIN_INVOKE DELEGATE_END_INVOKE RUNTIME_INVOKE NATIVE_TO_MANAGED MANAGED_TO_NATIVE
MANAGED_TO_MANAGED REMOTING_INVOKE REMOTING_INVOKE_WITH_CHECK XDOMAIN_INVOKE XDOMAIN_DISPATCH LDFLD STFLD LDFLD_REMOTE
STFLD_REMOTE SYNCHRONIZED DYNAMIC_METHOD ISINST CASTCLASS PROXY_ISINST STELEMREF UNBOX LDFLDA WRITE_BARRIER UNKNOWN
COMINTEROP_INVOKE COMINTEROP ALLOC""".split()
W = {n: i for i, n in enumerate(WRAPPER)}

class Meta:
    """Token -> name for one assembly."""
    def __init__(self, path):
        self.pe = pe = dnfile.dnPE(path); t = pe.net.mdtables
        self.td = t.TypeDef.rows; self.md = t.MethodDef.rows
        self.fd = t.Field.rows if t.Field else []
        enc = {r.NestedClass.row_index: r.EnclosingClass.row_index for r in (t.NestedClass.rows if t.NestedClass else [])}
        def tn(i):
            r = self.td[i-1]; n = str(r.TypeName)
            return tn(enc[i]) + "/" + n if i in enc else ((str(r.TypeNamespace) + ".") if str(r.TypeNamespace) else "") + n
        self.tname = {i: tn(i) for i in range(1, len(self.td)+1)}
        self.mowner, self.fowner = {}, {}
        for i, r in enumerate(self.td, 1):
            for m in (r.MethodList or []): self.mowner[m.row_index] = i
            for f in (r.FieldList or []): self.fowner[f.row_index] = i
        self.ts = getattr(t, "TypeSpec", None); self.ts = self.ts.rows if self.ts else []
        self.ms = getattr(t, "MethodSpec", None); self.ms = self.ms.rows if self.ms else []
        mr = getattr(t, "MemberRef", None); self.mr = mr.rows if mr else []
        tr = getattr(t, "TypeRef", None); self.tr = tr.rows if tr else []
    def typedef(self, row): return self.tname.get(row, f"TypeDef#{row}")
    def method(self, row):
        if not 0 < row <= len(self.md): return f"MethodDef#{row}"
        return f"{self.typedef(self.mowner.get(row, 0))}::{self.md[row-1].Name}"
    def field(self, row):
        if not 0 < row <= len(self.fd): return f"Field#{row}"
        return f"{self.typedef(self.fowner.get(row, 0))}::{self.fd[row-1].Name}"
    def methodspec(self, row):
        try:
            m = self.ms[row-1].Method
            if m.table.name == "MethodDef": return self.method(m.row_index) + "<inst>"
            r = self.mr[m.row_index-1]; c = r.Class
            cn = (str(c.row.TypeName) if c.table.name in ("TypeRef", "TypeDef") else f"{c.table.name}#{c.row_index}")
            return f"{cn}::{r.Name}<inst>"
        except Exception as e: return f"MethodSpec#{row}"
    def us(self, off):
        try:
            s = self.pe.net.user_strings.get(off)
            return s.value if hasattr(s, "value") else str(s)
        except Exception: return f"#US@{off:#x}"

class Aot:
    def __init__(self, prx, exports, il_dir):
        self.b = open(prx, "rb").read(); b = self.b
        phoff, = struct.unpack(">Q", b[32:40]); n, = struct.unpack(">H", b[56:58])
        self.ph = [struct.unpack(">IIQQQQQQ", b[phoff+i*56: phoff+i*56+56]) for i in range(n)]
        self.sym = {}
        for line in open(exports):
            m = re.search(r"addr=(0x[0-9a-f]+) (\S+)$", line.strip())
            if m: self.sym[m.group(2)] = int(m.group(1), 16)
        self.blob = self.sym["blob"]
        self.images = self.read_image_table()
        self.meta = {}
        self.il_dir = il_dir
    def off(self, va):
        for p in self.ph:
            if p[0] == 1 and p[5] and p[3] <= va < p[3] + p[5]: return p[2] + va - p[3]
        raise KeyError(hex(va))
    def u32(self, va): return struct.unpack(">I", self.b[self.off(va): self.off(va)+4])[0]
    def u8(self, va): return self.b[self.off(va)]
    def cstr(self, va):
        o = self.off(va); e = self.b.index(b"\0", o); return self.b[o:e].decode(errors="replace"), va + (e - o) + 1
    def read_image_table(self):
        va = self.sym["mono_image_table"]; n = self.u32(va); va += 4; out = []
        for _ in range(n):
            name, va = self.cstr(va); guid, va = self.cstr(va); _cult, va = self.cstr(va); _pkt, va = self.cstr(va)
            va = (va + 7) & ~7; va += 20
            out.append((name, guid))
        return out
    def M(self, idx):
        name = self.images[idx][0] if idx < len(self.images) else f"image{idx}"
        if name not in self.meta:
            p = os.path.join(self.il_dir, name + ".dll")
            self.meta[name] = Meta(p) if os.path.exists(p) else None
        return name, self.meta[name]
    # --- decoders (pointer = VA) ---
    def val(self, p):
        b0 = self.u8(p)
        if not b0 & 0x80: return b0, p + 1
        if not b0 & 0x40: return ((b0 & 0x3f) << 8) | self.u8(p+1), p + 2
        if b0 != 0xff: return ((b0 & 0x1f) << 24) | (self.u8(p+1) << 16) | (self.u8(p+2) << 8) | self.u8(p+3), p + 4
        return (self.u8(p+1) << 24) | (self.u8(p+2) << 16) | (self.u8(p+3) << 8) | self.u8(p+4), p + 5
    def get_offset(self, table, index):
        noff, gsize, ngroups, esize = (self.u32(table + 4*i) for i in range(4))
        if index >= noff: raise IndexError(index)
        g = index // gsize
        if esize == 2:
            data = table + 16 + 2*ngroups; p = data + struct.unpack(">H", self.b[self.off(table+16+2*g): self.off(table+16+2*g)+2])[0]
        else:
            data = table + 16 + 4*ngroups; p = data + self.u32(table + 16 + 4*g)
        o, p = self.val(p)
        for _ in range(g * gsize + 1, index + 1):
            d, p = self.val(p); o += d
        return o
    def ginst(self, p):
        n, p = self.val(p); args = []
        for _ in range(n): k, p = self.klass(p); args.append(k)
        return "<" + ",".join(args) + ">", p
    def gctx(self, p):
        s = ""
        h, p = self.val(p)
        if h: ci, p = self.ginst(p); s += ci
        h, p = self.val(p)
        if h: mi, p = self.ginst(p); s += "!!" + mi
        return s, p
    def klass(self, p):
        tok, p = self.val(p)
        if tok == 0: return "null", p
        tbl = tok >> 24
        if tbl == 0:
            img, p = self.val(p); n, m = self.M(img); self.kimg = img
            return (m.typedef(tok) if m else f"{n}!TypeDef#{tok}"), p
        if tbl == 0x1b:
            if tok == 0x1b000000:
                ty, p = self.val(p)
                if ty == 0x15:  # GENERICINST
                    g, p = self.klass(p); gi = self.kimg; a, p = self.ginst(p); self.kimg = gi; return g + a, p
                if ty in (0x13, 0x1e):  # VAR / MVAR
                    num, p = self.val(p); is_m, p = self.val(p)
                    if is_m: own, p = self.method(p)
                    else: own, p = self.klass(p)
                    return f"{'!!' if ty == 0x1e else '!'}{num}({own})", p
                raise ValueError(f"typespec type {ty:#x}")
            img, p = self.val(p); n, _ = self.M(img); return f"{n}!TypeSpec#{tok & 0xffffff}", p
        if tok == 0x02000000:
            img, p = self.val(p); rank, p = self.val(p); e, p = self.klass(p)
            return e + "[" + "," * (rank - 1) + "]", p
        raise ValueError(f"klass token {tok:#x}")
    def method(self, p):
        v, p = self.val(p); ii = v >> 24; pre = ""
        if ii == 252: pre = "[noaottramp]"; v, p = self.val(p); ii = v >> 24
        if ii == 253:
            wt, p = self.val(p); wn = WRAPPER[wt] if wt < len(WRAPPER) else str(wt)
            if wt in (W["REMOTING_INVOKE_WITH_CHECK"], W["SYNCHRONIZED"], W["RUNTIME_INVOKE"]):
                m, p = self.method(p); return f"{pre}wrapper:{wn}({m})", p
            if wt in (W["PROXY_ISINST"], W["LDFLD"], W["LDFLDA"], W["STFLD"], W["ISINST"]):
                k, p = self.klass(p); return f"{pre}wrapper:{wn}({k})", p
            if wt == W["ALLOC"]: a, p = self.val(p); return f"{pre}wrapper:alloc(atype={a})", p
            if wt == W["UNKNOWN"]:
                st, p = self.val(p); return f"{pre}wrapper:unknown({['MonitorEnter','MonitorExit','ElementAddr'][st] if st < 3 else st})", p
            if wt == W["MANAGED_TO_MANAGED"]:
                st, p = self.val(p)
                if st == 2: r, p = self.val(p); es, p = self.val(p); return f"{pre}wrapper:element_addr(rank={r},size={es})", p
                raise ValueError(f"m2m subtype {st}")
            if wt in (W["LDFLD_REMOTE"], W["STFLD_REMOTE"], W["WRITE_BARRIER"], W["STELEMREF"]):
                return f"{pre}wrapper:{wn}", p
            raise ValueError(f"wrapper type {wn}")
        if ii == 250:
            s, p = self.cstr(p); return f"{pre}wrapper_name:{s}", p
        if ii == 255:
            img, p = self.val(p); tok, p = self.val(p); n, m = self.M(img)
            return pre + (m.methodspec(tok & 0xffffff) if m else f"{n}!MethodSpec#{tok & 0xffffff}"), p
        if ii == 254:
            k, p = self.klass(p); img, p = self.val(p); tok, p = self.val(p); ctx, p = self.gctx(p)
            n, m = self.M(img)
            base = m.method(tok & 0xffffff) if m else f"{n}!MethodDef#{tok & 0xffffff}"
            return f"{pre}{base}[on {k}]{ctx}", p
        if ii == 251:
            k, p = self.klass(p); mt, p = self.val(p)
            return f"{pre}{k}::{['.ctor(rank)','.ctor(rank*2)','Get','Address','Set'][mt]}", p
        if ii >= 240: raise ValueError(f"methodref kind {ii}")
        n, m = self.M(ii); row = v & 0xffffff
        return pre + (m.method(row) if m else f"{n}!MethodDef#{row}"), p
    def patch(self, t, p):
        nm = PATCH[t] if t < len(PATCH) else f"type{t}"
        if t in (P["METHOD"], P["METHOD_JUMP"], P["ICALL_ADDR"], P["METHOD_RGCTX"], P["METHODCONST"]):
            m, p = self.method(p); return nm, m, p
        if t in (P["INTERNAL_METHOD"], P["JIT_ICALL_ADDR"]):
            ln, p = self.val(p); s, _ = self.cstr(p); return nm, s, p + ln + 1
        if t in (P["VTABLE"], P["CLASS"], P["IID"], P["ADJUSTED_IID"], P["CLASS_INIT"], P["DELEGATE_TRAMPOLINE"], P["EXC_NAME"]):
            k, p = self.klass(p); return nm, k, p
        if t == P["IMAGE"]:
            i, p = self.val(p); return nm, self.M(i)[0], p
        if t in (P["FIELD"], P["SFLDA"]):
            self.kimg = None; k, p = self.klass(p); f, p = self.val(p)
            m = self.M(self.kimg)[1] if self.kimg is not None else None
            fname = m.field(f).split("::")[-1] if m else f"Field#{f}"
            return nm, f"{k}::{fname}", p
        if t == P["R4"]:
            v, p = self.val(p); return nm, repr(struct.unpack(">f", struct.pack(">I", v & 0xffffffff))[0]), p
        if t == P["R8"]:
            a, p = self.val(p); c, p = self.val(p)
            return nm, repr(struct.unpack(">d", struct.pack(">Q", ((c & 0xffffffff) << 32) | (a & 0xffffffff)))[0]), p
        if t == P["LDSTR"]:
            i, p = self.val(p); tok, p = self.val(p); n, m = self.M(i)
            return nm, (m.us(tok & 0xffffff) if m else f"{n}!#US{tok:#x}"), p
        if t in (P["RVA"], P["DECLSEC"], P["LDTOKEN"], P["TYPE_FROM_HANDLE"]):
            i, p = self.val(p); tok, p = self.val(p); hc, p = self.val(p); ctx = ""
            if hc: ctx, p = self.gctx(p)
            n, _ = self.M(i); return nm, f"{n}!token {tok:#010x}{ctx}", p
        if t == P["SWITCH"]:
            n, p = self.val(p); tgt = []
            for _ in range(n): v, p = self.val(p); tgt.append(v)
            return nm, f"{n} targets " + " ".join(hex(x) for x in tgt[:8]) + (" ..." if n > 8 else ""), p
        if t == P["MSCORLIB_GOT_ADDR"]: return nm, "", p
        if t == P["METHOD_REL"]:
            v, p = self.val(p); return nm, str(v), p
        if t in (P["INTERRUPTION_REQUEST_FLAG"], P["GENERIC_CLASS_INIT"], P["MONITOR_ENTER"], P["MONITOR_EXIT"], P["SEQ_POINT_INFO"]):
            return nm, "", p
        if t == P["RGCTX_FETCH"]:
            m, p = self.method(p); inm, p = self.val(p); it, p = self.val(p); st, p = self.val(p)
            sn, sd, p = self.patch(st, p); return nm, f"{m} in_mrgctx={inm} info={it} -> {sn}:{sd}", p
        if t == P["LLVM_IMT_TRAMPOLINE"]:
            m, p = self.method(p); vo, p = self.val(p); return nm, f"{m} vt_off={vo}", p
        raise ValueError(f"unhandled patch {nm}")
def main(prx, exports, il_dir, out):
    a = Aot(prx, exports, il_dir)
    goi = a.sym["got_info_offsets"]; nslots = a.u32(goi)
    ok = bad = 0; types = {}
    with open(out, "x", newline="") as f:
        w = csv.writer(f); w.writerow(["slot", "got_byte_offset", "patch_type", "target"])
        for s in range(nslots):
            try:
                p = a.blob + a.get_offset(goi, s)
                t, p = a.val(p); nm, desc, _ = a.patch(t, p); ok += 1
            except Exception as e:
                nm, desc = "ERROR", str(e); bad += 1
            types[nm] = types.get(nm, 0) + 1
            w.writerow([s, f"0x{4*s:x}", nm, desc])
    print(f"images={[i[0] for i in a.images]}")
    print(f"slots={nslots} decoded={ok} errors={bad} types={dict(sorted(types.items(), key=lambda kv: -kv[1]))}")

if __name__ == "__main__" and len(sys.argv) == 5:
    main(*sys.argv[1:5])

def decode_plt(a, out):
    """PPC PLT (function-descriptor variant, aot-compiler.c arch_emit_plt_entry): 8 insns + plt_info word.
    Validates that each entry's lis/ori GOT offset == (plt_got_offset_base + index) * 4."""
    fi = a.sym["mono_aot_file_info"]; base, pltsz = a.u32(fi), a.u32(fi + 8)
    esz = 36; start = a.sym["plt_end"] - esz * pltsz
    ok = bad = mism = 0; types = {}
    with open(out, "x", newline="") as f:
        w = csv.writer(f); w.writerow(["plt_index", "address", "got_slot", "patch_type", "target"])
        for i in range(pltsz):
            e = start + esz * i
            hi, lo = a.u32(e) & 0xffff, a.u32(e + 4) & 0xffff
            slot = ((hi << 16) | lo) // 4
            if slot != base + i: mism += 1
            info = a.u32(e + 32)
            try:
                if i == 0: raise ValueError("entry 0 reserved (plt_got_info_offsets[0]=0)")
                t, p = a.val(a.blob + info); nm, desc, _ = a.patch(t, p); ok += 1
            except Exception as ex:
                nm, desc = "ERROR", str(ex); bad += 1
            types[nm] = types.get(nm, 0) + 1
            w.writerow([i, f"0x{e:x}", slot, nm, desc])
    print(f"plt start={start:#x} entries={pltsz} decoded={ok} errors={bad} slot_mismatches={mism} types={types}")

if __name__ == "__main__" and len(sys.argv) > 5 and sys.argv[5] == "--plt":
    decode_plt(Aot(*sys.argv[1:4]), sys.argv[4].replace(".got.csv", ".plt.csv"))
