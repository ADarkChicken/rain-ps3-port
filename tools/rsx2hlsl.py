"""RSX (PS3) vertex/fragment microcode -> HLSL (SM4) translator for Unity 3.5 PS3 shaders. Semantics ported from RPCS3
(rpcs3/Emu/RSX/Program/{Vertex,Fragment}ProgramDecompiler.cpp, GLVertexProgram.cpp; see tools/ref_rpcs3/rsx).
API:
  parse_subprogram(text)            -> dict(kind, binds, consts, textures, defaults, offsets, config, code)
  vp_to_hlsl(sp) / fp_to_hlsl(sp)   -> dict(body, inputs, outputs, uniforms, notes)
CLI: rsx2hlsl.py <Media dir> <out dir>   translates every program of every shader, writes per-program HLSL test units,
     compiles them with d3dcompiler_47 (vs_4_0 / ps_4_0) and reports coverage."""
import re, struct, sys, os

SW = "xyzw"
# ---------------- ShaderLab subprogram parsing ----------------
def parse_subprogram(text):
    sp = {"binds": [], "consts": [], "textures": [], "textypes": {}, "defaults": {}, "offsets": {}, "config": b"", "code": b"", "keywords": []}
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'Keywords\s*\{(.*)\}', line)
        if m: sp["keywords"] = re.findall(r'"([^"]+)"', m.group(1))
        m = re.match(r'Bind\s+"([^"]+)"\s+(\w+)', line)
        if m: sp["binds"].append((m.group(1), m.group(2)))
        m = re.match(r'(Matrix|Vector|Float)\s+(\d+)\s+\[([^\]]+)\]', line)
        if m: sp["consts"].append((m.group(1), int(m.group(2)), m.group(3)))
        m = re.match(r'SetTexture\s+(\d+)\s+\[([^\]]+)\]\s+(\w+)', line)
        if m: sp["textures"].append((int(m.group(1)), m.group(2), m.group(3))); sp["textypes"][int(m.group(1))] = m.group(3)
    q = re.search(r'"(sce_[vf]p_rsx)[^\n]*\n(.*?)"', text, re.S)
    if not q: return None
    sp["kind"] = "vp" if q.group(1) == "sce_vp_rsx" else "fp"
    body = q.group(2)
    sec = dict(re.findall(r'\[(\w+)\]\s*\n(.*?)(?=\n\[|\Z)', body, re.S))
    def hexblock(s):
        parts = s.strip().split("\n"); return bytes.fromhex("".join(parts[1:]).replace(" ", "")) if parts else b""
    sp["code"] = hexblock(sec.get("Microcode", "0\n")); sp["config"] = hexblock(sec.get("Configuration", "0\n"))
    if "Defaults" in sec:
        lines = sec["Defaults"].strip().split("\n")[1:]
        # "<constant index> <float count>" + hex floats: component j goes to c[index + j//4].(xyzw)[j%4]
        k = 0
        while k + 1 < len(lines):
            idx, n = map(int, lines[k].split()); k += 1; h = ""
            while len(h) < 8 * n and k < len(lines): h += lines[k].strip(); k += 1
            vals = struct.unpack(f">{n}f", bytes.fromhex(h[:8 * n]))
            for j, v in enumerate(vals): sp["defaults"].setdefault(idx + j // 4, {})[j % 4] = v
    if "Offsets" in sec:
        # entries: "<name> <count> <ndefaults>" / hex offsets (count x u32) / [hex defaults (ndefaults x f32) if ndefaults > 0]
        # hex fields wrap at 64 chars per line: consume lines until the declared length is reached
        lines = [l.strip() for l in sec["Offsets"].strip().split("\n")[1:]]; k = 0
        def take(nbytes):
            nonlocal k
            h = ""
            while len(h) < 2 * nbytes and k < len(lines): h += lines[k]; k += 1
            return bytes.fromhex(h)
        while k < len(lines):
            parts = lines[k].split(); k += 1
            name, n = parts[0], int(parts[1]); ndef = int(parts[2]) if len(parts) > 2 else 0
            offs = take(4 * n)
            for j in range(n): sp["offsets"][struct.unpack(">I", offs[4*j:4*j+4])[0]] = name
            if ndef > 0: take(4 * ndef)
    return sp

# ---------------- vertex programs ----------------
VP_IN = ["in_pos", "in_weight", "in_normal", "in_diff_color", "in_spec_color", "in_fog", "in_point_size", "in_7",
         "in_tc0", "in_tc1", "in_tc2", "in_tc3", "in_tc4", "in_tc5", "in_tc6", "in_tc7"]
VEC_OPS = {0: None, 1: "{0}", 2: "({0} * {1})", 3: "({0} + {2})", 4: "({0} * {1} + {2})", 5: "dot({0}.xyz, {1}.xyz).xxxx",
           6: "dot(float4({0}.xyz, 1.0), {1}).xxxx", 7: "dot({0}, {1}).xxxx", 8: "float4(1.0, {0}.y * {1}.y, {0}.z, {1}.w)",
           9: "min({0}, {1})", 10: "max({0}, {1})", 11: "float4({0} < {1})", 12: "float4({0} >= {1})", 13: "ARL",
           14: "frac({0})", 15: "floor({0})", 16: "float4({0} == {1})", 17: "float4(0,0,0,0)", 18: "float4({0} > {1})",
           19: "float4({0} <= {1})", 20: "float4({0} != {1})", 21: "float4(1,1,1,1)", 22: "sign({0})", 25: "TXL"}
SCA_OPS = {0: None, 1: "{s}", 2: "(1.0 / {s})", 3: "clamp(1.0 / {s}, 5.42101e-20, 1.884467e19)",
           4: "(1.0 / sqrt(max(abs({s}.x), 1.0e-37))).xxxx", 5: "exp2({s})", 6: "log2({s})", 7: "_lit({s})",
           9: "BRI", 13: "log2(max({s}.x, 1.0e-37)).xxxx", 14: "exp2({s}.x).xxxx", 15: "sin({s}.x).xxxx", 16: "cos({s}.x).xxxx"}
VP_OUT = {0: ("o_pos", "SV_POSITION"), 1: ("o_col0", "COLOR0"), 2: ("o_col1", "COLOR1"), 3: ("o_bfc0", None), 4: ("o_bfc1", None),
          5: ("o_fog", "FOG_T"), 6: ("o_reg6", "TEXCOORD9"), 7: ("o_tc0", "TEXCOORD0"), 8: ("o_tc1", "TEXCOORD1"),
          9: ("o_tc2", "TEXCOORD2"), 10: ("o_tc3", "TEXCOORD3"), 11: ("o_tc4", "TEXCOORD4"), 12: ("o_tc5", "TEXCOORD5"),
          13: ("o_tc6", "TEXCOORD6"), 14: ("o_tc7", "TEXCOORD7"), 15: ("o_tc8", "TEXCOORD8")}

def bits(v, lo, n): return (v >> lo) & ((1 << n) - 1)

class Unsupported(Exception): pass

def vp_to_hlsl(sp):
    code = sp["code"]; n = len(code) // 16; lines = []; inputs, outputs, temps, consts = set(), set(), set(), set(); vtex, uses_cc = set(), set()
    if n == 0: raise Unsupported("empty")
    # branch targets (BRI): absolute instruction addresses (iaddrh2<<9 | iaddrh<<3 | iaddrl), RPCS3 GetAddr
    targets_at = {}
    for i in range(n):
        d0, d1, d2, d3 = struct.unpack(">4I", code[16*i:16*i+16])
        if bits(d1, 27, 5) == 8: raise Unsupported("vp BRA (address-register branch)")
        if bits(d1, 27, 5) == 9: targets_at[(bits(d0, 23, 1) << 9) | (bits(d2, 0, 6) << 3) | bits(d3, 29, 3)] = None
    lvl = {a: k + 1 for k, a in enumerate(sorted(t for t in targets_at if t > 0))}; lvl[0] = 0
    if targets_at: lines += ["int jump_position = 0;", "[loop] while (true) {", "if (jump_position <= 0) {"]
    for i in range(n):
        d0, d1, d2, d3 = struct.unpack(">4I", code[16*i:16*i+16])
        if targets_at and i in lvl and i > 0: lines += ["}", f"if (jump_position <= {lvl[i]}) {{"]
        src = [bits(d2, 23, 9) | (bits(d1, 0, 8) << 9), bits(d2, 6, 17), bits(d3, 21, 11) | (bits(d2, 0, 6) << 11)]
        abs_ = [bits(d0, 21, 1), bits(d0, 22, 1), bits(d0, 23, 1)]
        def S(k):
            s = src[k]; t = bits(s, 0, 2)
            if t == 1: r = f"r{bits(s, 2, 6)}"; temps.add(r)
            elif t == 2: r = VP_IN[bits(d1, 8, 4)]; inputs.add(r)
            elif t == 3:
                if bits(d3, 1, 1): raise Unsupported("indexed constant")
                c = bits(d1, 12, 10); consts.add(c); r = f"vc[{c}]" if c < 468 else "float4(0,0,0,0)"
            else: raise Unsupported(f"src reg type {t}")
            sw = SW[bits(s, 14, 2)] + SW[bits(s, 12, 2)] + SW[bits(s, 10, 2)] + SW[bits(s, 8, 2)]
            if sw != "xyzw": r += "." + sw
            if abs_[k]: r = f"abs({r})"
            if bits(s, 16, 1): r = "-" + r
            return r
        condv = bits(d0, 10, 3)
        if condv == 0: continue                    # cond 0: never writes (RPCS3 SetDST)
        cc_idx = bits(d0, 25, 1); vcond = None
        if bits(d0, 13, 1) and condv != 7:         # conditional write against cc[cond_reg_sel_1]
            csw = SW[bits(d0, 8, 2)] + SW[bits(d0, 6, 2)] + SW[bits(d0, 4, 2)] + SW[bits(d0, 2, 2)]
            cmp = {1: "<", 2: "==", 3: "<=", 4: ">", 5: "!=", 6: ">="}[condv]
            vcond = f"(cc{cc_idx}.{csw} {cmp} 0)"
        vop, sop = bits(d1, 22, 5), bits(d1, 27, 5)
        if vop not in VEC_OPS or sop not in SCA_OPS: raise Unsupported(f"vp op vec{vop} sca{sop}")
        vres = bits(d0, 30, 1); dst = bits(d3, 2, 5); sat = bits(d0, 26, 1)
        vmask = "".join(SW[k] for k, b in enumerate((bits(d3, 16, 1), bits(d3, 15, 1), bits(d3, 14, 1), bits(d3, 13, 1))) if b)
        smask = "".join(SW[k] for k, b in enumerate((bits(d3, 20, 1), bits(d3, 19, 1), bits(d3, 18, 1), bits(d3, 17, 1))) if b)
        for is_sca, op, mask in ((False, vop, vmask), (True, sop, smask)):
            f = (SCA_OPS if is_sca else VEC_OPS)[op]
            if f is None or (not mask and f != "BRI"): continue
            if f == "ARL": raise Unsupported("vp ARL")
            if f == "BRI":
                addr = (bits(d0, 23, 1) << 9) | (bits(d2, 0, 6) << 3) | bits(d3, 29, 3)
                if condv == 7: lines.append(f"{{ jump_position = {lvl[addr]}; continue; }}")
                else:
                    csw = SW[bits(d0, 8, 2)] + SW[bits(d0, 6, 2)] + SW[bits(d0, 4, 2)] + SW[bits(d0, 2, 2)]
                    cmp = {1: "<", 2: "==", 3: "<=", 4: ">", 5: "!=", 6: ">="}[condv]; uses_cc.add(cc_idx)
                    lines.append(f"if (any(cc{cc_idx}.{csw} {cmp} 0)) {{ jump_position = {lvl[addr]}; continue; }}")
                continue
            if f == "TXL":
                unit = bits(d2, 8, 2); vtex.add(unit); val = f"tex2Dlod(_vtex{unit}, float4(({S(0)}).xy, 0, ({S(0)}).w))"
            else:
                val = f.format(S(0), S(1), S(2), s=S(2))
            val = f"({val}).{mask}"
            if sat: val = f"saturate({val})"
            tmp = bits(d3, 7, 6) if is_sca else bits(d0, 15, 6)
            to_result = (not vres) if is_sca else vres
            targets = []
            if to_result and dst != 0x1f:
                if dst not in VP_OUT: raise Unsupported(f"vp out {dst}")
                o = VP_OUT[dst][0]; outputs.add(dst); targets.append(f"{o}.{mask}")
            if tmp != 0x3f: r = f"r{tmp}"; temps.add(r); targets.append(f"{r}.{mask}")
            if not targets:
                if bits(d0, 14, 1) or bits(d0, 29, 1):   # CC-only write (RPCS3 GetDST fallback)
                    uses_cc.add(cc_idx); targets.append(f"cc{cc_idx}.{mask}")
                else: continue
            if vcond:
                uses_cc.add(cc_idx)
                for tgt in targets: lines.append(f"{tgt} = ({vcond}.{mask} ? {val} : {tgt});")
            else:
                lines.append(" = ".join(targets) + f" = {val};")
        if bits(d3, 0, 1) and i != n - 1: raise Unsupported("early END")
    if targets_at: lines += ["}", "break;", "}"]
    return {"lines": lines, "inputs": inputs, "outputs": outputs, "temps": temps, "consts": consts, "vtex": vtex, "uses_cc": uses_cc}

# ---------------- fragment programs ----------------
FP_IN = ["wpos", "diff_color", "spec_color", "fogc", "tc0", "tc1", "tc2", "tc3", "tc4", "tc5", "tc6", "tc7", "tc8", "tc9", "ssa"]
FP_OPS = {0x00: None, 0x01: (1, "{0}"), 0x02: (2, "({0} * {1})"), 0x03: (2, "({0} + {1})"), 0x04: (3, "({0} * {1} + {2})"),
          0x05: (2, "dot({0}.xyz, {1}.xyz).xxxx"), 0x06: (2, "dot({0}, {1}).xxxx"), 0x07: (2, "float4(1.0, {0}.y * {1}.y, {0}.z, {1}.w)"),
          0x08: (2, "min({0}, {1})"), 0x09: (2, "max({0}, {1})"), 0x0A: (2, "float4({0} < {1})"), 0x0B: (2, "float4({0} >= {1})"),
          0x0C: (2, "float4({0} <= {1})"), 0x0D: (2, "float4({0} > {1})"), 0x0E: (2, "float4({0} != {1})"), 0x0F: (2, "float4({0} == {1})"),
          0x10: (1, "frac({0})"), 0x11: (1, "floor({0})"), 0x12: (0, "KIL"), 0x15: (1, "ddx({0})"), 0x16: (1, "ddy({0})"),
          0x17: (1, "TEX"), 0x18: (1, "TXP"), 0x1A: (1, "(1.0 / {0}.x).xxxx"), 0x1B: (1, "(1.0 / sqrt(abs({0}.x))).xxxx"),
          0x1C: (1, "exp2({0}.x).xxxx"), 0x1D: (1, "log2(max({0}.x, 1.0e-37)).xxxx"), 0x1F: (3, "lerp({2}, {1}, {0})"),
          0x20: (2, "float4(1,1,1,1)"), 0x21: (2, "float4(0,0,0,0)"), 0x22: (1, "cos({0}.x).xxxx"), 0x23: (1, "sin({0}.x).xxxx"),
          0x26: (2, "pow(abs({0}.x), {1}.x).xxxx"), 0x2F: (1, "TXL"), 0x31: (1, "TXB"), 0x38: (2, "dot({0}.xy, {1}.xy).xxxx"),
          0x39: (1, "float4(normalize({0}.xyz), 0)"), 0x3A: (2, "({0} / {1}.x)"), 0x3B: (2, "({0} / sqrt({1}.x))"),
          0x3D: (0, "NOP"), 0x3E: (0, "NOP"), 0x2E: (3, "(dot({0}.xy, {1}.xy) + {2}.x).xxxx")}

def sw16(w): return ((w & 0xFFFF) << 16) | (w >> 16)

FP_HELPERS = """float4 _geth(uint2 u) { return float4(f16tof32(u.x), f16tof32(u.x >> 16), f16tof32(u.y), f16tof32(u.y >> 16)); }
uint2 _packh(float4 h) { uint4 q = f32tof16(h); return uint2(q.x | (q.y << 16), q.z | (q.w << 16)); }"""

def fp_to_hlsl(sp):
    """Exact RSX register-file model: storage _rK (uint4 bits); RK = asfloat(_rK); H(2K)/H(2K+1) = halves packed in
    _rK.xy/_rK.zw (component x in the low 16 bits, as RPCS3's packHalf2x16). Condition codes cc0/cc1 (float4)."""
    code = sp["code"]; i = 0; lines = []; inputs, texs, uniforms, regs = set(), set(), set(), set()
    off2name = sp["offsets"]; ctrl = struct.unpack(">I", sp["config"][16:20])[0] if len(sp["config"]) >= 20 else 0
    uses_cc = False
    def rd(h, idx):
        k = idx >> 1 if h else idx; regs.add(k)
        return f"_geth(_r{k}.{'zw' if idx & 1 else 'xy'})" if h else f"asfloat(_r{k})"
    while i + 16 <= len(code):
        d, s0, s1, s2 = [sw16(x) for x in struct.unpack(">4I", code[i:i+16])]
        op = bits(d, 24, 6) | (bits(s1, 31, 1) << 6)
        if op not in FP_OPS: raise Unsupported(f"fp opcode {op:#x}")
        spec = FP_OPS[op]; nsrc = spec[0] if spec else 0
        srcs = (s0, s1, s2)[:nsrc]; const_used = any(bits(s, 0, 2) == 2 for s in srcs)
        cexpr = None
        if const_used:
            if i + 16 in off2name:
                cexpr = off2name[i + 16]
                m2 = re.match(r"(\w+)\[(\d+)\]\[(\d+)\]$", cexpr)     # row r of matrix i in a matrix array
                if m2: cexpr = f"{m2.group(1)}_rows[{int(m2.group(2)) * 4 + int(m2.group(3))}]"
                uniforms.add(cexpr)
            else:
                cv = struct.unpack(">4f", struct.pack(">4I", *[sw16(x) for x in struct.unpack(">4I", code[i+16:i+32])]))
                cexpr = "float4(" + ", ".join(repr(float(x)) if x == x and abs(x) != float("inf") else "0.0" for x in cv) + ")"
        step = 32 if const_used else 16
        lt, eq, gt = bits(s0, 18, 1), bits(s0, 19, 1), bits(s0, 20, 1)
        if not (lt or eq or gt):                       # never executes (RPCS3: commented out)
            i += step
            if bits(d, 0, 1): break
            continue
        cond = None
        if not (lt and eq and gt):
            uses_cc = True
            csw = "".join(SW[bits(s0, 21 + 2*k, 2)] for k in range(4))
            ccr = f"cc{bits(s0, 31, 1)}.{csw}"
            cond = {(0, 1, 1): f"({ccr} >= 0)", (1, 1, 0): f"({ccr} <= 0)", (1, 0, 1): f"({ccr} != 0)",
                    (0, 0, 1): f"({ccr} > 0)", (1, 0, 0): f"({ccr} < 0)", (0, 1, 0): f"({ccr} == 0)"}[(lt, eq, gt)]
        attr = bits(d, 13, 4)
        def S(k, s):
            t = bits(s, 0, 2)
            if t == 0: r = rd(bits(s, 8, 1), bits(s, 2, 6))
            elif t == 1:
                if attr >= len(FP_IN): raise Unsupported("bad input")
                r = "in_" + FP_IN[attr]; inputs.add(FP_IN[attr])
            elif t == 2: r = cexpr
            else: raise Unsupported("src type 3")
            sw = "".join(SW[bits(s, 9 + 2*k2, 2)] for k2 in range(4))
            if sw != "xyzw": r = f"({r}).{sw}"
            if (bits(s, 29, 1) if k == 0 else bits(s, 18, 1)): r = f"abs({r})"
            if bits(s, 17, 1): r = "-" + r
            return r
        args = [S(k, s) for k, s in enumerate(srcs)]
        kind = spec[1] if spec else "NOP"
        if kind in ("TEX", "TXP", "TXL", "TXB"):
            unit = bits(d, 17, 4); texs.add(unit); a = args[0]; ttype = sp["textypes"].get(unit, "2D")
            if ttype == "Cube": val = f"texCUBE(_tex{unit}, ({a}).xyz)"
            elif ttype == "3D": val = f"tex3D(_tex{unit}, ({a}).xyz)"
            elif kind == "TEX": val = f"tex2D(_tex{unit}, ({a}).xy)"
            elif kind == "TXP": val = f"tex2Dproj(_tex{unit}, {a})"
            elif kind == "TXL": val = f"tex2Dlod(_tex{unit}, float4(({a}).xy, 0, ({a}).w))"
            else: val = f"tex2Dbias(_tex{unit}, {a})"
        elif kind == "KIL":
            lines.append("discard;" if cond is None else f"if (any{cond}) discard;"); val = None
        elif kind == "NOP": val = None
        else: val = kind.format(*args)
        if val is not None:
            scale = bits(s1, 28, 3)
            if scale: val = {1: f"({val} * 2.0)", 2: f"({val} * 4.0)", 3: f"({val} * 8.0)", 5: f"({val} / 2.0)",
                             6: f"({val} / 4.0)", 7: f"({val} / 8.0)"}.get(scale, val)
            if bits(d, 31, 1): val = f"saturate({val})"
            mask = "".join(SW[k] for k in range(4) if bits(d, 9 + k, 1)) or "xyzw"
            lines.append(f"_v = {val};")
            sel = (lambda new, old: f"({cond}.{mask} ? {new} : {old})") if cond else (lambda new, old: new)
            if not bits(d, 30, 1):                        # register destination
                fp16, idx = bits(d, 7, 1), bits(d, 1, 6)
                if fp16:
                    k = idx >> 1; regs.add(k); half = "zw" if idx & 1 else "xy"
                    lines.append(f"_t = _geth(_r{k}.{half}); _t.{mask} = {sel(f'_v.{mask}', f'_t.{mask}')}; _r{k}.{half} = _packh(_t);")
                    lines.append(f"_v = _t;")               # value as stored (fp16-quantised) feeds the CC update
                else:
                    regs.add(idx)
                    lines.append(f"_r{idx}.{mask} = {sel(f'asuint(_v.{mask})', f'_r{idx}.{mask}')};")
            if bits(d, 8, 1):                             # set_cond: cc[cond_mod_reg_index] = result
                uses_cc = True; ccw = f"cc{bits(s0, 30, 1)}"
                lines.append(f"{ccw}.{mask} = {sel(f'_v.{mask}', f'{ccw}.{mask}')};")
        i += step
        if bits(d, 0, 1): break
    regs.add(0)
    out = "asfloat(_r0)" if ctrl & 0x40 else "_geth(_r0.xy)"
    return {"lines": lines, "inputs": inputs, "texs": texs, "uniforms": uniforms, "regs": regs, "out": out,
            "ctrl": ctrl, "uses_cc": uses_cc, "alias": [], "temps": set()}
