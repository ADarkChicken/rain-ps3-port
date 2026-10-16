"""Compile harness for rsx2hlsl: wraps translated programs in standalone HLSL units, compiles them with d3dcompiler_47
and reports coverage. Usage: rsx2hlsl_harness.py <Media dir>"""
import collections, ctypes, glob, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rsx2hlsl import parse_subprogram, vp_to_hlsl, fp_to_hlsl, Unsupported, VP_OUT
import unity_inventory as u, unity35_classes as c

NL = "\n"
VIN_SEM = {"in_pos": "POSITION", "in_weight": "BLENDWEIGHT", "in_normal": "NORMAL", "in_diff_color": "COLOR0",
           "in_spec_color": "COLOR1", "in_fog": "TEXCOORD15", "in_point_size": "PSIZE", "in_7": "TEXCOORD14",
           **{f"in_tc{k}": f"TEXCOORD{k}" for k in range(8)}}
FIN_SEM = {"wpos": "SV_POSITION", "diff_color": "COLOR0", "spec_color": "COLOR1", "fogc": "FOG",
           **{f"tc{k}": f"TEXCOORD{k}" for k in range(9)}, "tc9": "TEXCOORD9"}
OUT_SEM = {0: "SV_POSITION", 1: "COLOR0", 2: "COLOR1", 5: "FOG", 6: "TEXCOORD9", **{7 + k: f"TEXCOORD{k}" for k in range(9)}}

def vp_unit(t):
    ins = sorted(t["inputs"]); outs = sorted(o for o in t["outputs"] if o in OUT_SEM)
    L = ["float4 vc[468];", "struct VIn {"]
    L += [f"  float4 {n} : {VIN_SEM[n]};" for n in ins] or ["  float4 _dummy : TEXCOORD13;"]
    L += ["};", "struct VOut {"] + [f"  float4 {VP_OUT[o][0]} : {OUT_SEM[o]};" for o in outs]
    if 0 not in outs: L += ["  float4 o_pos : SV_POSITION;"]
    L = [f"sampler2D _vtex{k};" for k in sorted(t["vtex"])] + L
    L += ["};", "VOut main(VIn v) {", "  VOut o = (VOut)0;", "  float4 cc0 = 0, cc1 = 0;"]
    L += [f"  float4 {n} = v.{n};" for n in ins]
    L += [f"  float4 {r} = 0;" for r in sorted(t["temps"])]
    L += [f"  float4 {VP_OUT[o][0]} = float4(0,0,0,1);" for o in sorted(t["outputs"]) if o in VP_OUT]
    L += ["  " + l for l in t["lines"]]
    L += [f"  o.{VP_OUT[o][0]} = {VP_OUT[o][0]};" for o in outs]
    L += ["  return o;", "}"]
    return NL.join(L)

def fp_unit(t, sp):
    from rsx2hlsl import FP_HELPERS
    L = [FP_HELPERS]
    for unit in sorted(t["texs"]):
        ty = sp["textypes"].get(unit, "2D")
        L.append({"Cube": "samplerCUBE", "3D": "sampler3D"}.get(ty, "sampler2D") + f" _tex{unit};")
    arrays = {}
    for n in sorted(t["uniforms"]):
        m = re.match(r"(\w+)\[(\d+)\]$", n)
        if m: arrays[m.group(1)] = max(arrays.get(m.group(1), 0), int(m.group(2)) + 1)
        else: L.append(f"float4 {n};")
    L += [f"float4 {b}[{sz}];" for b, sz in sorted(arrays.items())]
    ins = sorted(n for n in t["inputs"] if n != "ssa")
    L += ["struct PIn {"] + [f"  float4 in_{n} : {FIN_SEM[n]};" for n in ins]
    if "wpos" not in ins: L += ["  float4 _p : SV_POSITION;"]
    if "ssa" in t["inputs"]: L += ["  bool in_ssa_b : SV_IsFrontFace;"]
    L += ["};", "float4 main(PIn i) : SV_Target {"]
    L += [f"  float4 in_{n} = i.in_{n};" for n in ins]
    if "ssa" in t["inputs"]: L += ["  float4 in_ssa = i.in_ssa_b ? 1.0 : -1.0;"]
    L += [f"  uint4 _r{k} = 0;" for k in sorted(t["regs"])]
    L += ["  float4 _v = 0, _t = 0, cc0 = 0, cc1 = 0;"]
    L += ["  " + l for l in t["lines"]]
    L += [f"  return {t['out']};", "}"]
    return NL.join(L)

def d3dcompile(src, profile):
    from ctypes import c_void_p, c_size_t, c_uint, byref, POINTER
    d = ctypes.WinDLL("d3dcompiler_47.dll")
    code, err = c_void_p(), c_void_p(); b = src.encode()
    hr = d.D3DCompile(b, c_size_t(len(b)), None, None, None, b"main", profile.encode(), c_uint(0x1000), c_uint(0), byref(code), byref(err))  # 0x1000 = D3DCOMPILE_ENABLE_BACKWARDS_COMPATIBILITY (tex2D etc.)
    msg = ""
    if err.value:
        vt = ctypes.cast(ctypes.cast(err.value, POINTER(c_void_p))[0], POINTER(c_void_p))
        gp = ctypes.WINFUNCTYPE(c_void_p, c_void_p)(vt[3]); gs = ctypes.WINFUNCTYPE(c_size_t, c_void_p)(vt[4])
        msg = ctypes.string_at(gp(err.value), gs(err.value)).decode(errors="replace")
    return hr == 0, msg

SUBPROG = re.compile(r'SubProgram "ps3 " \{(.*?' + NL + r'")' + NL + r'\}', re.S)

def iter_subprograms(media):
    seen = set()
    for f in glob.glob(media + "/*.assets") + [media + "/Resources/unity default resources"]:
        for pid, cid, b in u.objects(f, 48):
            d = c.shader(c.R(b)); s = d["script"]
            m = re.match(r'\s*Shader\s+"([^"]+)"', s); name = m.group(1) if m else d["name"]
            if name in seen: continue
            seen.add(name)
            for m in SUBPROG.finditer(s): yield name, m.group(1)

if __name__ == "__main__":
    media = sys.argv[1]
    st = collections.Counter(); why = collections.Counter(); alias = amb = 0; uniq = set(); fails = []
    for name, text in iter_subprograms(media):
        sp = parse_subprogram(text)
        if sp is None: st["unparsed"] += 1; continue
        key = (sp["kind"], sp["code"], tuple(sorted(sp["offsets"].items())), tuple(sorted(sp["textypes"].items())))
        if key in uniq: continue
        uniq.add(key)
        try:
            if sp["kind"] == "vp": t = vp_to_hlsl(sp); src = vp_unit(t); prof = "vs_4_0"
            else:
                t = fp_to_hlsl(sp); src = fp_unit(t, sp); prof = "ps_4_0"
                alias += bool(t["alias"]); amb += t["out"] == "AMBIGUOUS"
        except Unsupported as e:
            st[sp["kind"] + " unsupported"] += 1; why[str(e)] += 1; continue
        ok, msg = d3dcompile(src, prof)
        st[sp["kind"] + (" compiled" if ok else " compile-error")] += 1
        if not ok:
            why["compile: " + (re.findall(r"error X\d+: [^" + NL + r"]{0,70}", msg) or [msg[:70]])[0]] += 1
            if len(fails) < 2: fails.append((name, src, msg[:400]))
    print(dict(st)); print("unique programs:", len(uniq), " FP with cross H/R aliasing:", alias, " FP with ambiguous output:", amb)
    print("reasons:", why.most_common(14))
    for n, s_, m_ in fails: print("----", n, NL, m_, NL, s_[:1500])
