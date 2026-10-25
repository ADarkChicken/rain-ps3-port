"""Export a Rain scene (PS3 Unity 3.5) to a neutral intermediate for the Unity 2017.4 importer.
Usage: rain_export.py <Media dir> <out dir> <levelfile> [prefab-levelfile ...]
Output (out dir):
  scene.json      {"objects":[{id,name,layer,tag,active,pos,rot,scale,parent,mesh,materials,lightmapIndex,lightmapST}], "roots":[...],
                   "lightmaps":[{far,near}] (texture ids or null), "lightmapsMode", "render":{RenderSettings fields},
                   "lightProbes":{positions[3n], coefficients[27n], tetrahedra[4m] (-1 = outer cell)} or null}
                  renderers also carry useLightProbes and probeAnchor (GO id, optional)
  materials.json  {"materials":[{id,name,shader,shaderName,textures:[{prop,tex,scale,offset}],floats:[{prop,value}],colors:[{prop,value}]}]}
  textures/<id>.dds, meshes/<id>.bin (see write_mesh), report.json (counts, skipped refs)
IDs are "<file>@<pathID>". All objects are read with the byte-exact readers of unity35_classes.py (E75)."""
import json, os, struct, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unity_inventory as u
import unity35_classes as c
import unity_mb_decode as mbd
import dxt

CH_SIZE = {0: 12, 1: 12, 2: 4, 3: 8, 4: 8, 5: 16}

class Files:
    """Lazy object index over serialized files with external-reference resolution."""
    def __init__(self, media):
        self.media = media; self.cache = {}
    def path(self, name):
        if name.startswith("library/"): return os.path.join(self.media, "Resources", name.split("/", 1)[1])
        return os.path.join(self.media, name)
    def load(self, name):
        if name not in self.cache:
            p = self.path(name); objs = {}
            for pid, cid, b in u.objects(p): objs[pid] = (cid, b)
            self.cache[name] = (objs, u.externals(p))
        return self.cache[name]
    def resolve(self, name, pptr):
        fid, pid = pptr
        if pid == 0: return None
        objs, ext = self.load(name)
        target = name if fid == 0 else (ext[fid - 1] if 0 < fid <= len(ext) else None)
        if target is None: return None
        if target.startswith("library/"): target = "library/" + target.split("/", 1)[1]
        try: tobjs, _ = self.load(target)
        except FileNotFoundError: return None
        return (target, pid) if pid in tobjs else None
    def get(self, ref):
        objs, _ = self.load(ref[0]); return objs[ref[1]]

def rid(ref): return f"{os.path.basename(ref[0])}@{ref[1]}"

def write_dds(path, d, data):
    w, h, fmt = d["width"], d["height"], d["format"]
    fourcc = {10: b"DXT1", 12: b"DXT5"}.get(fmt)
    mips = 1
    if d["mipMap"]:
        while (w >> mips) or (h >> mips): mips += 1
    data = dxt.flip_v(data, w, h, fmt, mips)   # 3.5 rows are bottom-up, DDS is top-down (E87)
    if fourcc:
        bs = 8 if fmt == 10 else 16; linear = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * bs
        pf = struct.pack("<II4sIIIII", 32, 0x4, fourcc, 0, 0, 0, 0, 0)
        flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000 | (0x20000 if mips > 1 else 0)
    else:   # uncompressed: ARGB32(5) / RGBA32(4) / RGB24(3) -> stored as given; channel masks describe byte order
        bpp = {5: 32, 4: 32, 3: 24}[fmt]; linear = w * (bpp // 8)
        masks = {5: (0x0000FF00, 0x00FF0000, 0xFF000000, 0x000000FF), 4: (0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000),
                 3: (0x000000FF, 0x0000FF00, 0x00FF0000, 0)}[fmt]
        pf = struct.pack("<II4sIIIII", 32, 0x40 | (0x1 if masks[3] else 0), b"\0\0\0\0", bpp, *masks)
        flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x8 | (0x20000 if mips > 1 else 0)
    caps = 0x1000 | ((0x8 | 0x400000) if mips > 1 else 0)
    hdr = b"DDS " + struct.pack("<7I", 124, flags, h, w, linear, 0, mips) + b"\0" * 44 + pf + struct.pack("<5I", caps, 0, 0, 0, 0)
    with open(path, "wb") as f: f.write(hdr + data)

def strip_to_list(idx):
    out = []
    for k in range(len(idx) - 2):
        a, b, c_ = idx[k], idx[k + 1], idx[k + 2]
        if a == b or b == c_ or a == c_: continue           # degenerate (strip restart)
        out += [a, b, c_] if k % 2 == 0 else [b, a, c_]
    return out

def write_mesh(path, d, b):
    """bin layout (LE): u32 vertexCount, u32 channelMask, then per channel present (order pos,nrm,col,uv0,uv1,tan) the
    de-interleaved float data (colors as 4 u8), then u32 submeshCount, per submesh u32 indexCount + u32 indices."""
    n = d["vertexCount"]; vd = b[d["vertex_offset"]: d["vertex_offset"] + d["vertex_size"]]
    chans = {}
    for mask, off, stride, _ in d["streams"]:
        if not mask: continue
        pos = 0
        for ch in range(6):
            if mask >> ch & 1:
                sz = CH_SIZE[ch]; arr = bytearray()
                for v in range(n):
                    s = vd[off + v * stride + pos: off + v * stride + pos + sz]
                    if ch == 2: arr += s                                     # color: 4 bytes as stored
                    else: arr += struct.pack(f"<{sz // 4}f", *struct.unpack(f">{sz // 4}f", s))
                chans[ch] = bytes(arr); pos += sz
    idx_all = struct.unpack(f">{d['index_size'] // 2}H", b[d["index_offset"]: d["index_offset"] + d["index_size"]])
    out = bytearray(struct.pack("<II", n, sum(1 << k for k in chans)))
    for ch in sorted(chans): out += chans[ch]
    out += struct.pack("<I", len(d["submeshes"]))
    for sm in d["submeshes"]:
        first = sm["firstByte"] // 2; seg = list(idx_all[first: first + sm["indexCount"]])
        tris = strip_to_list(seg) if sm["topology"] == 2 else seg
        out += struct.pack(f"<I{len(tris)}I", len(tris), *tris)
    with open(path, "wb") as f: f.write(out)

#: M6 critical-path gameplay classes (work/m6_dependency_map.md) that actually carry MonoBehaviour instances
#: (work/maps/monobehaviour_decode_summary.csv: all decode byte-exact, 0 failures). Decoded generically below and
#: attached to their GameObject as o["scripts"][cls] so a later Unity-side importer can restore real components.
SCRIPT_CLASSES = {
    "ActiveKeepTrigger", "ActiveSwitchTrigger", "BoyParameter", "CameraConstrainForRainEffect", "CameraManager",
    "CharacterGesture", "CharacterGestureManager", "CharacterKillTrigger", "CharacterPlayer", "CharacterProperty",
    "CharacterResetParams", "CharacterShaderConection", "CharacterStatus", "CharacterTaskBase",
    "CharacterTriggerProperty", "CharacterWatchCollision", "CharacterWatchPoint", "CreateRainDrop",
    "CreateRefrectionRTT", "DisplayRange", "FootStep", "FourParameter", "Full_billboard", "FunctionEventFlagOFF",
    "FunctionEventFlagON", "FunctionRestartTriggerSwitch", "FunctionSituation", "GameManager", "GlowAlphaAnimaton",
    "HeadLookController", "IlluminationCameraController", "KillCameraManager", "LatchConstantRotation",
    "MapInstantiation", "MapLoader", "MapLoaderEntry", "MotionDataManager", "MotionEvent",
    "PartialRestartGameObject", "ParticleColorControl", "PathCamera", "PathCameraArea", "PathCameraEventObj",
    "PathCameraGazePoint", "PathCameraGazePosArea", "PathCameraKeyframe", "PathCameraRouteSet", "PathGraph",
    "PathManager", "PositionMarker", "PrefabManager", "PushBody", "PushBodyParameter", "RainAreaCheck",
    "RainEffectManager", "RainFallPaticleController", "RainFallTransformController", "RainManager",
    "RainMergePostEffect", "RainRenderEffect", "ReflectionCameraEffect", "RegionBox", "RegionManager",
    "RegionTrigger", "RegionTriggerCameraArea", "RegionTriggerEmitter", "RegionTriggerObjectActivate",
    "RegionTriggerPuddle", "RegionTriggerText", "RestartManager", "RestartTrigger", "RootMotionComputer",
    "SafetyFallTrigger", "ScriptPositionManager", "SingletonObject", "SituationTrigger", "SpawnPoint",
    "SpawnTriggerPass", "SpawnTriggerPassActive", "SpawnTriggerPassDelete", "StageClearTrigger",
    "TriggerCollisionArea", "TriggerCondition_AlwaysTrue", "TriggerCondition_CharaNameCtrl",
    "TriggerCondition_CharaTypeCtrl", "TriggerCondition_EventFlag", "TriggerCondition_ExtraState",
    "TriggerEventFlagON", "TriggerProcessPlayBGM", "TwoParameter", "UIKillCamera", "WetNewspaper", "myBlurEffect",
}

class Exporter:
    def __init__(self, media, out):
        self.F = Files(media); self.out = out
        for sub in ("textures", "meshes"): os.makedirs(os.path.join(out, sub), exist_ok=True)
        self.objects, self.materials, self.done = [], {}, set()
        self.textures, self.meshes = set(), set(); self.report = collections.Counter(); self.roots = []
        self.shader_names = {}; self.world = None; self._clsidx = {}
    def shader_name(self, ref):
        if ref is None: return None
        if ref in self.shader_names: return self.shader_names[ref]
        cid, b = self.F.get(ref); name = None
        if cid == 48:
            r = c.R(b); r.string(); script = r.string()
            import re
            m = re.match(r'\s*Shader\s+"([^"]+)"', script); name = m.group(1) if m else None
        self.shader_names[ref] = name; return name
    def texture(self, ref):
        if ref is None: return None
        if ref not in self.textures:
            cid, b = self.F.get(ref)
            if cid != 28: self.report["non-texture tex ref"] += 1; return None
            d = c.texture2d(c.R(b))
            if d["format"] not in (10, 12, 5, 4, 3): self.report[f"texfmt {d['format']}"] += 1; return None
            write_dds(os.path.join(self.out, "textures", rid(ref) + ".dds"), d, b[d["data_offset"]: d["data_offset"] + d["data_size"]])
            self.textures.add(ref)
        return rid(ref)
    def material(self, ref):
        if ref is None: return None
        if ref not in self.materials:
            cid, b = self.F.get(ref); d = c.material(c.R(b)); sref = self.F.resolve(ref[0], d["shader"])
            m = {"id": rid(ref), "name": d["name"], "shader": rid(sref) if sref else None, "shaderName": self.shader_name(sref),
                 "textures": [], "floats": [{"prop": k, "value": v} for k, v in d["floats"]],
                 "colors": [{"prop": k, "value": list(v)} for k, v in d["colors"]]}
            for k, te in d["texenvs"]:
                t = self.texture(self.F.resolve(ref[0], te["tex"]))
                m["textures"].append({"prop": k, "tex": t, "scale": list(te["scale"]), "offset": list(te["offset"])})
            self.materials[ref] = m
        return rid(ref)
    def mesh(self, ref):
        if ref is None: return None
        if ref not in self.meshes:
            cid, b = self.F.get(ref); d = c.mesh(c.R(b))
            write_mesh(os.path.join(self.out, "meshes", rid(ref) + ".bin"), d, b); self.meshes.add(ref)
        return rid(ref)
    def gameobject(self, ref, parent):
        """Export GO + its Transform subtree."""
        if ref in self.done: return
        self.done.add(ref)
        cid, b = self.F.get(ref); go = c.gameobject(c.R(b))
        o = {"id": rid(ref), "name": go["name"], "layer": go["layer"], "tag": go["tag"], "active": go["active"], "parent": parent,
             "mesh": None, "materials": [], "lightmapIndex": 255, "lightmapST": [1, 1, 0, 0]}
        children = []
        for ccid, pp in go["components"]:
            cref = self.F.resolve(ref[0], pp)
            if cref is None: continue
            _, cb = self.F.get(cref)
            if ccid == 4:
                t = c.transform(c.R(cb)); o.update(pos=list(t["pos"]), rot=list(t["rot"]), scale=list(t["scale"]))
                for ch in t["children"]:
                    tref = self.F.resolve(cref[0], ch)
                    if tref:
                        tg = c.transform(c.R(self.F.get(tref)[1]))["go"]; gref = self.F.resolve(tref[0], tg)
                        if gref: children.append(gref)
            elif ccid == 33:
                o["mesh"] = self.mesh(self.F.resolve(cref[0], c.meshfilter(c.R(cb))["mesh"]))
            elif ccid == 23:
                rd = c.renderer_base(c.R(cb)); o["rendererEnabled"] = rd["enabled"]
                o["materials"] = [self.material(self.F.resolve(cref[0], m)) for m in rd["materials"]]
                o["lightmapIndex"] = rd["lightmapIndex"]; o["lightmapST"] = list(rd["lightmapTilingOffset"])
                o["useLightProbes"] = rd["useLightProbes"]; aref = self.F.resolve(cref[0], rd["lightProbeAnchor"])
                if aref: o["probeAnchor"] = rid(self.F.resolve(aref[0], c.transform(c.R(self.F.get(aref)[1]))["go"]))
            elif ccid == 20:
                d = c.camera(c.R(cb)); tt = self.F.resolve(cref[0], d["targetTexture"])
                o["camera"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items() if k not in ("go", "targetTexture")}
                o["camera"]["hasTargetTexture"] = tt is not None
            elif ccid == 114 and (pe := self.post_effect(cref, cb)) is not None:
                o[pe[0]] = pe[1]
            elif ccid == 114 and (sc := self.script_component(cref, cb)) is not None:
                o.setdefault("scripts", {})[sc[0]] = sc[1]
            else:
                self.report[f"component {ccid} skipped"] += 1
        self.objects.append(o)
        for ch in children: self.gameobject(ch, o["id"])
    def scene_roots(self, level):
        objs, _ = self.F.load(level); roots = []
        for pid, (cid, b) in objs.items():
            if cid == 4 and c.transform(c.R(b))["father"][1] == 0:
                g = self.F.resolve(level, c.transform(c.R(b))["go"])
                if g: roots.append(g)
        return roots
    POST_EFFECTS = {"RainMergePostEffect": "Assembly-CSharp", "RainCommonPostEffect": "Assembly-UnityScript-firstpass"}
    def post_effect(self, cref, b):
        """(key, settings) of a camera image effect we reproduce (E91, E92); scalars kept, curves flattened to
        (time, value, inSlope, outSlope)*n, colours as lists, textures exported; other MonoBehaviours -> None."""
        if self.world is None: return None
        if not hasattr(self, "_ms"): self._ms = u.monoscripts(os.path.join(self.F.media, "sharedassets0.assets"))
        go, en, (fid, spid), name, p = mbd.header(b); ext = self.F.load(cref[0])[1]
        cls = self._ms.get(spid, ("",))[0]
        if not (0 < fid <= len(ext) and ext[fid - 1] == "sharedassets0.assets" and cls in self.POST_EFFECTS): return None
        a = self.world.asms[self.POST_EFFECTS[cls]]; i = a.byname[("", cls)]; v = {}
        for fn, node in self.world.fields(a, i): v[fn], p = mbd.read(self.world, node, b, p)
        keep = {"enabled": bool(en)}
        for k, x in v.items():
            if isinstance(x, (bool, int, float)): keep[k] = x
            elif isinstance(x, dict) and "keys" in x: keep[k] = [f for key in x["keys"] for f in key]
            elif isinstance(x, tuple) and len(x) == 4 and all(isinstance(f, float) for f in x): keep[k] = list(x)
        for k in ("m_BlendTexture", "maskTexture"):
            if k in v: keep[k] = self.texture(self.F.resolve(cref[0], v[k]))
        return ("rainMerge" if cls == "RainMergePostEffect" else "rainCommon"), keep
    def _decode_value(self, level, node, val):
        """JSON-safe form of a decoded field, resolving PPtr(fileID,pathID) leaves to scene.json object ids (rid)."""
        k = node[0]
        if k == "pptr": return rid(ref) if (ref := self.F.resolve(level, val)) else None
        if k in ("floats", "bytes4"): return list(val)
        if k == "curve": return {"keys": [list(key) for key in val["keys"]], "pre_post": list(val["pre_post"])}
        if k in ("array", "list"): return [self._decode_value(level, node[1], v) for v in val]
        if k == "inline":
            fields = dict(self.world.fields(node[1], node[2]))
            return {fn: self._decode_value(level, fields[fn], v) for fn, v in val.items()}
        return val   # prim / string
    def script_component(self, cref, b):
        """(className, decoded fields) for any SCRIPT_CLASSES MonoBehaviour component, else None (E40 decoder,
        generalised from post_effect to the full M6 critical-path class list, work/m6_dependency_map.md)."""
        if self.world is None: return None
        if not hasattr(self, "_ms"): self._ms = u.monoscripts(os.path.join(self.F.media, "sharedassets0.assets"))
        go, en, (fid, spid), name, p = mbd.header(b); ext = self.F.load(cref[0])[1]
        cls = self._ms.get(spid, ("",))[0]
        if not (0 < fid <= len(ext) and ext[fid - 1] == "sharedassets0.assets" and cls in SCRIPT_CLASSES): return None
        if cls not in self._clsidx:
            a = self.world.asms["Assembly-CSharp"]; self._clsidx[cls] = (a, a.byname.get(("", cls)))
        a, i = self._clsidx[cls]
        if not i: self.report[f"script {cls} no_type"] += 1; return None
        vals = {"enabled": bool(en)}
        try:
            for fn, node in self.world.fields(a, i):
                v, p = mbd.read(self.world, node, b, p)
                vals[fn] = self._decode_value(cref[0], node, v)
        except (mbd.Bad, struct.error, IndexError) as e:
            self.report[f"script {cls} decode error"] += 1; return None
        return cls, vals
    def monobehaviours(self, level, world, cls):
        """Decoded fields of every `cls` MonoBehaviour (Assembly-CSharp) in a level."""
        ms = u.monoscripts(os.path.join(self.F.media, "sharedassets0.assets")); objs, ext = self.F.load(level)
        a = world.asms["Assembly-CSharp"]; i = a.byname[("", cls)]
        for pid, (cid, b) in objs.items():
            if cid != 114: continue
            go, en, (fid, spid), name, p = mbd.header(b)
            if not (0 < fid <= len(ext) and ext[fid - 1] == "sharedassets0.assets" and ms.get(spid, ("",))[0] == cls): continue
            vals = {}
            for fn, node in world.fields(a, i): vals[fn], p = mbd.read(world, node, b, p)
            yield vals
    def prefab_table(self, prefab_levels, world):
        """PrefabManager.GetSharedPrefab(type, index) table (E89): each registry puts its entry j of m_Prefab /
        m_ModelPrefab at global slot idxTbl[1 + j//2] low/high 16 bits (idxTbl[0] = count)."""
        tbl = {1: {}, 2: {}}
        for pl in prefab_levels:
            for v in self.monobehaviours(pl, world, "PrefabManager"):
                for t, lst, idx in ((1, v["m_Prefab"], v["m_PrefabIndexTbl"]), (2, v["m_ModelPrefab"], v["m_ModelPrefabIndexTbl"])):
                    for j, k in enumerate(lst):
                        w = idx[1 + j // 2]; ref = self.F.resolve(pl, k["_prefab"])
                        if ref and self.F.get(ref)[0] == 1: tbl[t][(w & 0xFFFF) if j % 2 == 0 else (w >> 16)] = ref
                        else: self.report["unresolved prefab"] += 1
        return tbl
    def subtree(self, ref):
        """Prefab hierarchy as exported objects, preorder (= MapInstantiation.GetGenerationTransforms order)."""
        saved = (self.objects, self.done); self.objects, self.done = [], set()
        try: self.gameobject(ref, None); return self.objects
        finally: self.objects, self.done = saved
    def map_instances(self, level, world, prefabs):
        """Recreate what MapInstantiation instantiates at runtime (E89): each ObjectKind = one copy of a shared prefab with
        per-node transform/layer overrides (ObjectKind.RestoreTransform) and per-renderer lightmap data (LightMapAdjuster.Param)."""
        cache = {}; n = 0
        def pick(i, vals, idxs):   # RestoreTransform index rule: idxs[i]-1, else i, else keep the prefab's value
            k = idxs[i] - 1 if i < len(idxs) else (i if i < len(vals) else -1)
            return vals[k] if 0 <= k < len(vals) else None
        for v in self.monobehaviours(level, world, "MapInstantiation"):
            for kind in v["m_ObjectTbl"] + v["m_NoPrefabTbl"] + v["m_DynamicTbl"]:
                if kind["_cutSceneOnly"] or kind["_noCreate"]: self.report["map kind skipped (cutscene/noCreate)"] += 1; continue
                if kind["_obj"][1]: self.report["map kind with scene object (not handled)"] += 1; continue
                ref = prefabs.get(kind["_prefabType"], {}).get(kind["_prefabIndex"])
                if ref is None: self.report["map kind unresolved"] += 1; continue
                if ref not in cache: cache[ref] = self.subtree(ref)
                pre = f"mi{n}:"; n += 1; nodes = []
                for o in cache[ref]:
                    c2 = json.loads(json.dumps(o)); c2["id"] = pre + o["id"]; c2["parent"] = pre + o["parent"] if o["parent"] else None
                    c2["active"] = True; nodes.append(c2)   # streamed in = activated with its whole hierarchy (E86)
                for i, o in enumerate(nodes):
                    for key, vals, idxs in (("pos", kind["_pos"], kind["_posIdx"]), ("rot", kind["_rot"], kind["_rotIdx"]), ("scale", kind["_scale"], kind["_scaleIdx"])):
                        if vals and (x := pick(i, vals, idxs)) is not None: o[key] = list(x)
                    if kind["_layer"] and (x := pick(i, kind["_layer"], kind["_layerIdx"])) is not None: o["layer"] = x
                lp = kind["_lightmapParam"]; rends = [o for o in nodes if o["materials"]]; j = 0
                # shortcut: renderer order = preorder like GetComponentsInChildren and LightMapAdjuster index remap = identity
                # (single lightmap set in st01); upgrade if lightmaps land on the wrong objects
                for k, o in enumerate(rends[:len(lp["_index"])]):
                    if not o.get("rendererEnabled", True): continue
                    o["useLightProbes"] = k in lp["_useProbeRendererIndex"]
                    li = lp["_index"][k] - 1; o["lightmapIndex"] = li if li >= 0 else 255
                    if li >= 0:
                        ti = lp["_tillingIndex"][j] - 1 if j < len(lp["_tillingIndex"]) else j
                        oi = lp["_offsetIndex"][j] - 1 if j < len(lp["_offsetIndex"]) else j
                        if ti < len(lp["_tilling"]) and oi < len(lp["_offset"]): o["lightmapST"] = list(lp["_tilling"][ti]) + list(lp["_offset"][oi])
                        j += 1
                self.objects += nodes; self.roots.append(nodes[0]["id"]); self.report["map instances"] += 1
    def settings(self, level):
        """LightmapSettings + RenderSettings of the main level (streamed prefab levels carry none, E83)."""
        objs, _ = self.F.load(level); lm = rs = None
        for pid, (cid, b) in objs.items():
            if cid == 157: lm = c.lightmapsettings(c.R(b))
            elif cid == 104: rs = c.rendersettings(c.R(b))
        pref = self.F.resolve(level, lm["lightProbes"]); lp = c.lightprobes(c.R(self.F.get(pref)[1])) if pref else None
        lm["lightProbes"] = lp and {"positions": [x for p in lp["positions"] for x in p], "coefficients": [x for k in lp["coefficients"] for x in k],
                                    "tetrahedra": [i for t in lp["tetrahedra"] for i in t["indices"]]}
        lm["lightmaps"] = [{"far": self.texture(self.F.resolve(level, f)), "near": self.texture(self.F.resolve(level, n))} for f, n in lm["lightmaps"]]
        rs = {"fog": rs["fog"], "fogColor": list(rs["fogColor"]), "fogMode": rs["fogMode"], "fogDensity": rs["fogDensity"],
              "fogStart": rs["fogStart"], "fogEnd": rs["fogEnd"], "ambient": list(rs["ambient"]), "skybox": self.material(self.F.resolve(level, rs["skybox"])),
              "haloStrength": rs["haloStrength"], "flareStrength": rs["flareStrength"]}
        return lm, rs
    def run(self, level, prefab_levels):
        world = self.world = mbd.World(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", "managed_il"))
        for r in self.scene_roots(level): self.roots.append(rid(r)); self.gameobject(r, None)
        self.map_instances(level, world, self.prefab_table(prefab_levels, world))   # prefab templates themselves never render
        lm, rs = self.settings(level)
        json.dump({"objects": self.objects, "roots": self.roots, "lightmaps": lm["lightmaps"], "lightmapsMode": lm["mode"], "lightProbes": lm["lightProbes"], "render": rs},
                  open(os.path.join(self.out, "scene.json"), "w"))
        json.dump({"materials": list(self.materials.values())}, open(os.path.join(self.out, "materials.json"), "w"))
        rep = {"gameobjects": len(self.objects), "roots": len(self.roots), "meshes": len(self.meshes), "textures": len(self.textures),
               "materials": len(self.materials), "renderers": sum(1 for o in self.objects if o["materials"]), **self.report}
        json.dump(rep, open(os.path.join(self.out, "report.json"), "w"), indent=1); print(rep)

if __name__ == "__main__":
    Exporter(sys.argv[1], sys.argv[2]).run(sys.argv[3], sys.argv[4:])
