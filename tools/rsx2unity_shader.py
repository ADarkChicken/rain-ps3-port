"""Emit Unity 2017.4 .shader files from Rain's Unity 3.5 PS3 ShaderLab scripts (M2).
Usage: rsx2unity_shader.py <Media dir> <out dir>
- ShaderLab structure (Properties, SubShader/Pass state, Tags, Blend/ZWrite/Cull/...) is kept verbatim.
- Each `Program "vp"/"fp"` pair of a Pass is replaced by one CGPROGRAM holding every original PS3 variant, selected by
  Unity 2017's own built-in keywords where the meaning is the same (see KW_*), so the engine picks the variant per pass,
  renderer and light exactly as 3.5 did. Combinations 3.5 never compiled fall back to the most specific listed variant.
- Microcode is translated by rsx2hlsl (exact RSX register model). Unity 2017 built-ins are used where the meaning is
  identical (matrices, camera, time, screen/projection params); all other uniforms keep their PS3 names.
- Shader names are prefixed "RainPS3/" so they never collide with Unity's own built-in shaders.
Writes <out>/<sanitized name>.shader and <out>/variants.json (per shader/pass: PS3 keyword set and 2017 keyword set per variant)."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsx2hlsl as R
import rsx2hlsl_harness as H

NL = "\n"
CGINC = os.environ.get("RAIN_CGINC", "G:/Decomp/Rain/_tools/Unity-2017.4.40f1/Editor/Data/CGIncludes")
INCLUDES = ["UnityCG.cginc", "UnityLightingCommon.cginc"]

TEXCAT = set()

def unity_catalog():
    """{name: (base type, components, array size or 0)} for uniforms declared by the includes we use (and their includes)."""
    cat, todo, done = {}, list(INCLUDES), set()
    pat = re.compile(r"^\s*(?:uniform\s+)?(?:UNITY_DECLARE_\w+\()?(float|half|fixed|int)(\d(?:x\d)?)?\s+(\w+)\s*(?:\[(\d+)\])?\s*;", re.M)
    while todo:
        f = todo.pop()
        if f in done or not os.path.exists(os.path.join(CGINC, f)): continue
        done.add(f); txt = open(os.path.join(CGINC, f), encoding="utf-8", errors="replace").read()
        todo += re.findall(r'#include\s+"([^"]+)"', txt)
        for m in pat.finditer(txt):
            if m.group(3) not in cat: cat[m.group(3)] = (m.group(1), m.group(2) or "1", int(m.group(4) or 0))
        for m in re.finditer(r"UNITY_DECLARE_TEX\w*\(\s*(\w+)", txt): TEXCAT.add(m.group(1))
        for m in re.finditer(r"^\s*#\s*define\s+(\w+)\b(?!\()", txt, re.M):   # object-like macros (legacy aliases etc.)
            if m.group(1) not in cat: cat[m.group(1)] = ("macro", "4", 0)
        for m in re.finditer(r"^\s*(?:uniform\s+)?sampler\w*\s+(\w+)\s*;", txt, re.M): TEXCAT.add(m.group(1))
    for macro in ("UNITY_MATRIX_MVP", "UNITY_MATRIX_MV", "UNITY_MATRIX_IT_MV", "UNITY_MATRIX_P", "UNITY_LIGHTMODEL_AMBIENT"):
        cat[macro] = ("float", "4x4" if macro.startswith("UNITY_MATRIX") else "4", 0)
    return cat

CAT = unity_catalog()
# Unity 3.5 PS3 name -> Unity 2017.4 expression with identical meaning (verified against CAT at use time)
RENAME = {"glstate_matrix_mvp": "UNITY_MATRIX_MVP", "glstate_matrix_modelview0": "UNITY_MATRIX_MV",
          "glstate_matrix_invtrans_modelview0": "UNITY_MATRIX_IT_MV", "glstate_matrix_projection": "UNITY_MATRIX_P",
          "_Object2World": "unity_ObjectToWorld", "_World2Object": "unity_WorldToObject",
          "glstate_lightmodel_ambient": "UNITY_LIGHTMODEL_AMBIENT", "unity_World2Shadow": "unity_WorldToShadow",
          "_CameraToWorld": "unity_CameraToWorld", "_WorldToCamera": "unity_WorldToCamera"}
# 3.5 SH = ambient + light probes (+ non-important lights), evaluated by the engine per renderer; 2017 fills its own SH
# from its own probes/ambient, so these are owned by the bridge (RainLightProbes sets them per renderer, E85)
BRIDGED = {n: "rain_" + n[len("unity_"):] for n in ("unity_SHAr", "unity_SHAg", "unity_SHAb", "unity_SHBr", "unity_SHBg", "unity_SHBb", "unity_SHC")}
COMPUTED = {"unity_Scale": "float4(1, 1, 1, 1.0 / length(unity_ObjectToWorld[0].xyz))"}
ATTR = {"Vertex": "in_pos", "Normal": "in_normal", "Color": "in_diff_color", "SecondaryColor": "in_spec_color",
        "BlendWeight": "in_weight", "FogCoord": "in_fog", **{f"TexCoord{k}": f"in_tc{k}" for k in range(8)}}
CHANNEL_SEM = {"vertex": "POSITION", "normal": "NORMAL", "color": "COLOR", "tangent": "TANGENT",
               "texcoord": "TEXCOORD0", "texcoord0": "TEXCOORD0", "texcoord1": "TEXCOORD1", "texcoord2": "TEXCOORD2",
               "texcoord3": "TEXCOORD3"}

def resolve(name, want):
    """PS3 uniform `name` of shape `want` ('float4', 'float4x4', 'float') -> (expression, declaration or None)."""
    if name in COMPUTED: return COMPUTED[name], None
    if name in BRIDGED: return BRIDGED[name], f"float4 {BRIDGED[name]};"
    m = re.match(r"unity_LightColor(\d)$", name)
    if m and "unity_LightColor" in CAT: return f"unity_LightColor[{m.group(1)}]", None
    tgt = RENAME.get(name, name)
    if tgt in CAT:
        base, comp, arr = CAT[tgt]
        if want == "float4" and comp == "3": return f"float4({tgt}, 1)", None
        if want == "float" and comp != "1": return f"({tgt}).x", None
        return tgt, None
    if tgt != name: raise R.Unsupported(f"renamed builtin {tgt} missing from catalog")
    # custom uniforms: scalars are declared float4 and read via .x, so a name used as float in the VP and float4 in the
    # FP of the same variant gets one declaration (the runtime bridge sets them with SetVector)
    if want == "float": return f"{name}.x", f"float4 {name};"
    return name, f"{want} {name};"

def vp_constant_init(sp):
    """Lines filling vc[] from uniforms, plus the declarations we must add."""
    lines, decls = [], set()
    for kind, idx, name in sp["consts"]:
        if kind == "Matrix":
            expr, d = resolve(name, "float4x4")
            for r in range(4): lines.append(f"vc[{idx + r}] = {expr}[{r}];")
        elif kind == "Vector":
            expr, d = resolve(name, "float4"); lines.append(f"vc[{idx}] = {expr};")
        else:
            expr, d = resolve(name, "float"); lines.append(f"vc[{idx}] = float4({expr}, {expr}, {expr}, {expr});")
        if d: decls.add(d)
    covered = set()
    for kind, idx, name in sp["consts"]: covered |= set(range(idx, idx + (4 if kind == "Matrix" else 1)))
    for idx, comps in sp["defaults"].items():
        if idx in covered or idx >= 468: continue
        lines.append(f"vc[{idx}] = 0;")
        for c, v in sorted(comps.items()): lines.append(f"vc[{idx}].{'xyzw'[c]} = {repr(float(v))};")
    return lines, decls

def fp_uniforms(t):
    """Map FP uniform names (incl. name[i] and name_rows[i*4+r]) to expressions + declarations."""
    repl, decls, arrays = {}, set(), {}
    for n in t["uniforms"]:
        m = re.match(r"(\w+)_rows\[(\d+)\]$", n)
        if m:
            base = RENAME.get(m.group(1), m.group(1)); i, r = divmod(int(m.group(2)), 4)
            if base in CAT: repl[n] = f"{base}[{i}][{r}]"
            else: arrays[m.group(1) + "_rows"] = max(arrays.get(m.group(1) + "_rows", 0), int(m.group(2)) + 1)
            continue
        m = re.match(r"(\w+)\[(\d+)\]$", n)
        if m:
            base = RENAME.get(m.group(1), m.group(1))
            if base in CAT and CAT[base][1] == "4x4" and CAT[base][2] == 0 and int(m.group(2)) < 4:
                repl[n] = f"{base}[{m.group(2)}]"          # PS3 patched row i of a single matrix
            elif base == "unity_WorldToShadow" and int(m.group(2)) < 4:
                repl[n] = f"{base}[0][{m.group(2)}]"       # 3.5 single shadow matrix (row i) -> cascade 0 of 2017's array
            elif base in CAT and CAT[base][2] > int(m.group(2)):
                repl[n] = f"{base}[{m.group(2)}]" if CAT[base][1] != "4x4" else f"{base}[{m.group(2)}]"
            else: arrays[m.group(1)] = max(arrays.get(m.group(1), 0), int(m.group(2)) + 1)
            continue
        expr, d = resolve(n, "float4"); repl[n] = expr
        if d: decls.add(d)
    decls |= {f"float4 {b}[{sz}];" for b, sz in arrays.items()}
    return repl, decls

def subst(lines, repl):
    if not repl: return lines
    keys = sorted(repl, key=len, reverse=True)
    pat = re.compile("|".join(re.escape(k) + (r"(?![\w\[])" if not k.endswith("]") else "") for k in keys))
    return [pat.sub(lambda m: repl[m.group(0)], l) for l in lines]

def variant_code(vsp, fsp, vi):
    vt = R.vp_to_hlsl(vsp); ft = R.fp_to_hlsl(fsp)
    init, vdecl = vp_constant_init(vsp)
    frepl, fdecl = fp_uniforms(ft)
    samplers = {u: name for u, name, ty in fsp["textures"]}; stypes = {u: ty for u, name, ty in fsp["textures"]}
    body_f = subst(ft["lines"], frepl)
    # unity_Lightmap: same texture in 2017 (engine-bound per renderer, Texture2D+SamplerState) -> sample Unity's own (E84)
    for u, n in list(samplers.items()):
        if n == "unity_Lightmap":
            body_f = [re.sub(rf"\btex2D\(_tex{u},", "UNITY_SAMPLE_TEX2D(unity_Lightmap,", l) for l in body_f]
            if any(re.search(rf"\b_tex{u}\b", l) for l in body_f): raise R.Unsupported("unity_Lightmap sampled with non-tex2D op")
            del samplers[u]
    # other samplers whose names Unity declares itself get a rain_ prefix; the runtime bridge binds them under that name
    samplers = {u: ("rain_" + n if (n in TEXCAT or n in CAT) else n) for u, n in samplers.items()}
    for u, name in samplers.items(): body_f = [re.sub(rf"\b_tex{u}\b", name, l) for l in body_f]
    decl = set(vdecl) | fdecl
    for u, name in samplers.items():
        decl.add({"Cube": "samplerCUBE", "3D": "sampler3D"}.get(stypes[u], "sampler2D") + f" {name};")
    for k in vt["vtex"]: decl.add(f"sampler2D _vtex{k};")
    bind = {ATTR.get(attr): CHANNEL_SEM.get(ch.lower()) for ch, attr in vsp["binds"]}
    ins = sorted(vt["inputs"]); bound = [n for n in ins if bind.get(n)]
    outs = sorted(o for o in vt["outputs"] if o in H.OUT_SEM)
    L = [f"struct rain_vin{vi} {{"] + [f"  float4 {n} : {bind[n]};" for n in bound]
    if not bound: L += ["  float4 rain_unused : POSITION;"]
    L += ["};", f"struct rain_v2f{vi} {{"] + [f"  float4 {R.VP_OUT[o][0]} : {H.OUT_SEM[o]};" for o in outs]
    if 0 not in outs: L += ["  float4 o_pos : SV_POSITION;"]
    L += ["};", f"rain_v2f{vi} rain_vert(rain_vin{vi} v) {{", f"  rain_v2f{vi} o = (rain_v2f{vi})0; float4 vc[468]; float4 cc0 = 0, cc1 = 0;"]
    L += ["  " + l for l in init]
    L += [f"  float4 {n} = v.{n};" if n in bound else f"  float4 {n} = 0;  // no Bind for this attribute" for n in ins]
    L += [f"  float4 {r} = 0;" for r in sorted(vt["temps"])]
    L += [f"  float4 {R.VP_OUT[o][0]} = float4(0,0,0,1);" for o in sorted(vt["outputs"]) if o in R.VP_OUT]
    L += ["  " + l for l in vt["lines"]] + [f"  o.{R.VP_OUT[o][0]} = {R.VP_OUT[o][0]};" for o in outs] + ["  return o;", "}"]
    fins = sorted(n for n in ft["inputs"] if n != "ssa")
    avail = {R.VP_OUT[o][0].replace("o_", ""): o for o in outs}
    L += [f"float4 rain_frag(rain_v2f{vi} i{', bool rain_face : SV_IsFrontFace' if 'ssa' in ft['inputs'] else ''}) : SV_Target {{"]
    for n in fins:
        src = {"diff_color": "col0", "spec_color": "col1", "fogc": "fog"}.get(n, n)
        if n == "wpos": L.append("  float4 in_wpos = i.o_pos;")
        elif src in avail: L.append(f"  float4 in_{n} = i.o_{src};")
        else: L.append(f"  float4 in_{n} = 0;  // not written by the VP")
    if "ssa" in ft["inputs"]: L.append("  float4 in_ssa = rain_face ? 1.0 : -1.0;")
    L += [f"  uint4 _r{k} = 0;" for k in sorted(ft["regs"])] + ["  float4 _v = 0, _t = 0, cc0 = 0, cc1 = 0;"]
    L += ["  " + l for l in body_f] + [f"  return {ft['out']};", "}"]
    return L, decl

def pair_variants(vps, fps):
    """Unity 3.5 keys VP and FP subprograms by possibly different keyword subsets. Variant set = union of both lists;
    for each variant pick the VP and the FP whose keyword set is the most specific subset of the variant's keywords."""
    variants = []
    for kw in [tuple(v["keywords"]) for v in vps] + [tuple(f["keywords"]) for f in fps]:
        if set(kw) not in [set(x) for x in variants]: variants.append(kw)
    def best(lst, kw):
        cands = [p for p in lst if set(p["keywords"]) <= set(kw)]
        return max(cands, key=lambda p: len(p["keywords"])) if cands else None
    pairs = []
    for kw in variants:
        v, f = best(vps, kw), best(fps, kw)
        if v is None or f is None: continue          # keyword combination only meaningful for the other stage
        pairs.append((dict(v, keywords=list(kw)), f))
    if not pairs: raise R.Unsupported("no VP/FP combination")
    return pairs

# 3.5 -> 2017 keyword bridge (E84). *_OFF keywords mean "absent" in 2017.
KW_DROP = {"SHADOWS_NATIVE", "SHADOWS_SPLIT_SPHERES"}     # D3D11 shadow maps are always native; split spheres is engine-side in 2017
KW_NEVER = {"SHADOWS_NONATIVE", "DIRLIGHTMAP_ON"}         # no 2017 equivalent (Rain uses dual, not directional, lightmaps: E83)
KW_RENAME = {"HDR_LIGHT_PREPASS_ON": "UNITY_HDR_ON"}
KW_GROUPS = [["POINT", "DIRECTIONAL", "SPOT", "POINT_COOKIE", "DIRECTIONAL_COOKIE"], ["SHADOWS_SCREEN", "SHADOWS_DEPTH", "SHADOWS_CUBE"]]

def scalarize(decls, lines):
    """Custom `float4 X;` uniforms only ever read through .x are scalars: declare them `float` so Material.SetFloat and
    Float properties bind (Unity does not route SetFloat into a float4 uniform -- every such value read 0, E91)."""
    code = "\n".join(lines); out = set()
    for d in decls:
        m = re.match(r"float4 (\w+);$", d)
        if m and all(re.match(r"\)?\.x+\b", code[u.end():]) for u in re.finditer(r"\b" + m.group(1) + r"\b", code)):
            out.add(f"float {m.group(1)};")
        else: out.add(d)
    return out

def keyword_select(variants):
    """3.5 keyword lists -> (pragma lines, [(variant index, 2017 keyword set)] most specific first). Variants without a 2017
    equivalent are dropped; if two map to the same set the first wins."""
    mapped, seen = [], []
    for vi, kws in enumerate(variants):
        if any(k in KW_NEVER for k in kws): continue
        ks = frozenset(KW_RENAME.get(k, k) for k in kws if k and not k.endswith("_OFF") and k not in KW_DROP)
        if ks not in seen: seen.append(ks); mapped.append((vi, ks))
    if not mapped: mapped = [(0, frozenset())]
    always = frozenset.intersection(*[ks for _, ks in mapped]); switches = set().union(*[ks for _, ks in mapped]) - always
    pragmas = []
    for g in KW_GROUPS:
        mem = [k for k in g if k in switches]
        if mem:
            none = any(not (ks & set(mem)) for _, ks in mapped)
            pragmas.append("#pragma multi_compile " + ("__ " if none else "") + " ".join(mem)); switches -= set(mem)
    pragmas += [f"#pragma multi_compile __ {k}" for k in sorted(switches)]
    order = sorted(mapped, key=lambda m: -len(m[1] - always))
    return pragmas, [(vi, ks - always) for vi, ks in order], always

def block_end(text, open_idx):
    """Index just past the '}' matching the '{' at open_idx (braces inside "..." strings are ignored)."""
    depth, i, inq = 0, open_idx, False
    while i < len(text):
        ch = text[i]
        if ch == '"': inq = not inq
        elif not inq:
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0: return i + 1
        i += 1
    raise ValueError("unbalanced braces")

def program_blocks(text):
    """[(kind, start, end)] for every `Program "vp"|"fp" { ... }` block, brace-matched."""
    out = []
    for m in re.finditer(r'Program "(vp|fp)" \{', text):
        end = block_end(text, m.end() - 1); out.append((m.group(1), m.start(), end))
    return out

KNOWN = set()   # names of all shaders being converted (filled by __main__)

PROGRAM = re.compile(r'Program "(vp|fp)" \{\s*(.*?)\n\}\s*\n', re.S)

def convert_shader(script, prefix="RainPS3/"):
    name = re.match(r'\s*Shader\s+"([^"]+)"', script).group(1)
    out = re.sub(r'(\s*Shader\s+")([^"]+)(")', lambda m: m.group(1) + prefix + m.group(2) + m.group(3), script, count=1)
    # Fallbacks point at the converted copy when we have one (e.g. "Diffuse Fast" is only Properties + Fallback "VertexLit")
    out = re.sub(r'(\n\s*Fallback\s+)(Off|"([^"]*)")',
                 lambda m: m.group(1) + '"' + prefix + m.group(3) + '"' if m.group(3) in KNOWN else "", out)
    out = re.sub(r'\n\s*Dependency\s+"[^"]*"\s*=\s*"[^"]*"', "", out)
    variants_info = []; approximated = []
    pieces, pos, pass_no = [], 0, 0
    blocks = program_blocks(out); k = 0
    while k < len(blocks):
        kind, st, en = blocks[k]
        group = [blocks[k]]
        if kind == "vp" and k + 1 < len(blocks) and blocks[k + 1][0] == "fp" and not out[en:blocks[k + 1][1]].strip():
            group.append(blocks[k + 1]); k += 1
        k += 1
        pieces.append(out[pos:group[0][1]]); pos = group[-1][2]
        progs = {g[0]: [p for p in (R.parse_subprogram(sm.group(1)) for sm in H.SUBPROG.finditer(out[g[1]:g[2]])) if p] for g in group}
        if "vp" not in progs or "fp" not in progs or not progs["vp"] or not progs["fp"]:
            # fixed-function + one program stage, or blocks without any ps3 subprogram: keep fixed-function only
            approximated.append(f"pass {pass_no}: lone {list(progs)[0]} program dropped (fixed-function kept)"); pass_no += 1
            continue
        pairs = pair_variants(progs["vp"], progs["fp"])
        pragmas, order, always = keyword_select([v["keywords"] for v, f in pairs])
        cg = ["CGPROGRAM", "// UNITY_SHADER_NO_UPGRADE  (names are mapped explicitly by rsx2unity_shader.py)",
              "#pragma target 4.0", "#pragma vertex rain_vert", "#pragma fragment rain_frag"]
        cg += pragmas
        cg += ["#include \"UnityCG.cginc\"", "#include \"UnityLightingCommon.cginc\"", R.FP_HELPERS]
        for n, (vi, ks) in enumerate(order):
            v, f = pairs[vi]; L, dcl = variant_code(v, f, vi)
            cond = " && ".join(f"defined({k})" for k in sorted(ks))
            if len(order) > 1: cg.append(("#if " if n == 0 else "#elif " if cond else "#else") + cond + f"   // 3.5: {' '.join(v['keywords'])}")
            cg += sorted(scalarize(dcl, L)) + L
        if len(order) > 1: cg.append("#endif")
        cg.append("ENDCG")
        pieces.append(NL.join(cg) + NL)
        variants_info.append({"pass": pass_no, "variants": [v["keywords"] for v, f in pairs],
                              "unity": {str(vi): sorted(ks | always) for vi, ks in order}}); pass_no += 1
    pieces.append(out[pos:])
    return name, "".join(pieces), {"passes": variants_info, "approximated": approximated}

if __name__ == "__main__":
    import collections
    media, outdir = sys.argv[1], sys.argv[2]; os.makedirs(outdir, exist_ok=True)
    import glob, unity_inventory as u, unity35_classes as c
    st = collections.Counter(); why = collections.Counter(); seen = set(); info = {}
    for f in glob.glob(media + "/*.assets") + [media + "/Resources/unity default resources"]:
        for pid, cid, b in u.objects(f, 48):
            m = re.match(r'\s*Shader\s+"([^"]+)"', c.shader(c.R(b))["script"])
            if m: KNOWN.add(m.group(1))
    for f in glob.glob(media + "/*.assets") + [media + "/Resources/unity default resources"]:
        for pid, cid, b in u.objects(f, 48):
            d = c.shader(c.R(b)); s = d["script"]
            m = re.match(r'\s*Shader\s+"([^"]+)"', s)
            if not m or m.group(1) in seen: continue
            seen.add(m.group(1))
            try:
                name, text, vinfo = convert_shader(s)
                fn = re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".shader"
                open(os.path.join(outdir, fn), "w", encoding="utf-8").write(text); info[name] = {"file": fn, **vinfo}
                if vinfo["approximated"]: st["approximated passes"] += len(vinfo["approximated"])
                st["converted"] += 1
            except Exception as e:
                st["failed"] += 1; why[f"{type(e).__name__}: {str(e)[:60]}"] += 1
    json.dump(info, open(os.path.join(outdir, "variants.json"), "w"), indent=1)
    print(dict(st), why.most_common(8))
