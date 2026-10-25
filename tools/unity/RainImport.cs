// Rain intermediate -> Unity 2017.4 assets + scene (M1). Run headless:
//   Unity.exe -batchmode -quit -projectPath <proj> -executeMethod RainImport.Run -rainExport <dir> -rainScene <name>
// Reads scene.json / materials.json / textures/*.dds / meshes/*.bin written by tools/rain_export.py.
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class RainImport
{
    [Serializable] public class TexRef { public string prop; public string tex; public float[] scale; public float[] offset; }
    [Serializable] public class FloatProp { public string prop; public float value; }
    [Serializable] public class ColorProp { public string prop; public float[] value; }
    [Serializable] public class Mat { public string id; public string name; public string shader; public string shaderName; public TexRef[] textures; public FloatProp[] floats; public ColorProp[] colors; }
    [Serializable] public class MatFile { public Mat[] materials; }
    [Serializable] public class Obj
    {
        public string id; public string name; public int layer; public int tag; public bool active; public string parent;
        public float[] pos; public float[] rot; public float[] scale; public string mesh; public string[] materials;
        public int lightmapIndex; public float[] lightmapST; public bool rendererEnabled = true;
        public bool useLightProbes; public string probeAnchor;
        public Cam camera; public Merge rainMerge; public Common rainCommon;
    }
    [Serializable] public class Cam
    {
        public bool enabled; public int clearFlags; public float[] background; public float[] rect; public float near, far, fov, orthoSize, depth;
        public bool ortho; public long cullingMask; public int renderingPath; public bool hdr; public bool hasTargetTexture;
    }
    [Serializable] public class Merge
    {
        public bool enabled; public float[] m_RGBCurve; public string m_BlendTexture;
        public float m_GaussIntensity, m_SoftFocusBlendIntensity, m_ColorVignetteIntensity, m_BlurVignetteIntensity, m_TextureBlendIntensity, m_SaturationIntensity;
        public bool m_UpdateRGBCurve, m_ColorVignette, m_BlurVignette, m_UseMergeShader;
        public int m_SoftFocusBlendMode, m_TextureBlendMode, m_DownSizeDiv;
    }
    [Serializable] public class Common
    {
        public bool enabled, useDepthCorrection, m_SunShaftEnable; public int m_FXAASampleCount;
        public float[] redChannel, greenChannel, blueChannel, zCurve, depthRedChannel, depthGreenChannel, depthBlueChannel;
        public string maskTexture; public float[] maskColor, globalFogColor, globalFogHeightColor;
        public float maskIntensity, globalFogStartDistance, globalFogDensity, globalFogHeightScale, globalFogHeight, globalFogHeightDensity, globalFogFarClip;
    }
    [Serializable] public class LmRef { public string far; public string near; }
    [Serializable] public class Render
    {
        public bool fog; public float[] fogColor; public int fogMode; public float fogDensity, fogStart, fogEnd;
        public float[] ambient; public string skybox; public float haloStrength, flareStrength;
    }
    [Serializable] public class Probes { public float[] positions; public float[] coefficients; public int[] tetrahedra; }
    [Serializable] public class SceneFile { public Obj[] objects; public string[] roots; public LmRef[] lightmaps; public int lightmapsMode; public Render render; public Probes lightProbes; }

    static string Arg(string name)
    {
        var a = Environment.GetCommandLineArgs();
        for (int i = 0; i < a.Length - 1; i++) if (a[i] == name) return a[i + 1];
        throw new ArgumentException("missing " + name);
    }
    static string Safe(string id) { return id.Replace("@", "_").Replace(" ", "_"); }

    public static void Run()
    {
        string src = Arg("-rainExport"), sceneName = Arg("-rainScene");
        string root = "Assets/Rain/" + sceneName;
        foreach (var d in new[] { root, root + "/Textures", root + "/Meshes", root + "/Materials" })
            Directory.CreateDirectory(d);

        // textures: copy DDS files, let Unity import them
        foreach (var f in Directory.GetFiles(Path.Combine(src, "textures"), "*.dds"))
        {
            string dst = root + "/Textures/" + Safe(Path.GetFileName(f));
            if (!File.Exists(dst)) File.Copy(f, dst);
        }
        AssetDatabase.Refresh();

        // materials: converted shaders (RainPS3/<3.5 name>, M2); legacy placeholders only if a conversion is missing
        var mats = new Dictionary<string, Material>(); int bound = 0;
        var mf = JsonUtility.FromJson<MatFile>(File.ReadAllText(Path.Combine(src, "materials.json")));
        Shader fallback = Shader.Find("Legacy Shaders/Diffuse"), cutout = Shader.Find("Legacy Shaders/Transparent/Cutout/Diffuse");
        foreach (var m in mf.materials)
        {
            bool alpha = m.shaderName != null && (m.shaderName.Contains("Transparent") || m.shaderName.Contains("Cutout") || m.shaderName.Contains("Alpha"));
            var sh = m.shaderName != null ? Shader.Find("RainPS3/" + m.shaderName) : null;
            if (sh != null) bound++; else Debug.LogWarning("RAIN IMPORT: no converted shader for " + m.name + " (" + m.shaderName + ")");
            var mat = new Material(sh ?? (alpha ? cutout : fallback)) { name = m.name };
            foreach (var t in m.textures)
            {
                if (t.tex == null) continue;
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(root + "/Textures/" + Safe(t.tex) + ".dds");
                if (tex == null || !mat.HasProperty(t.prop)) continue;
                mat.SetTexture(t.prop, tex);
                mat.SetTextureScale(t.prop, new Vector2(t.scale[0], t.scale[1]));
                mat.SetTextureOffset(t.prop, new Vector2(t.offset[0], t.offset[1]));
            }
            foreach (var f in m.floats) if (mat.HasProperty(f.prop)) mat.SetFloat(f.prop, f.value);
            foreach (var c in m.colors) if (mat.HasProperty(c.prop)) mat.SetColor(c.prop, new Color(c.value[0], c.value[1], c.value[2], c.value[3]));
            AssetDatabase.CreateAsset(mat, root + "/Materials/" + Safe(m.id) + ".mat");
            mats[m.id] = mat;
        }

        // meshes
        var meshes = new Dictionary<string, Mesh>();
        foreach (var f in Directory.GetFiles(Path.Combine(src, "meshes"), "*.bin"))
        {
            string id = Path.GetFileNameWithoutExtension(f);
            var mesh = ReadMesh(f); mesh.name = id;
            AssetDatabase.CreateAsset(mesh, root + "/Meshes/" + Safe(id) + ".asset");
            meshes[id] = mesh;
        }
        AssetDatabase.SaveAssets();

        // scene
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        var sf = JsonUtility.FromJson<SceneFile>(File.ReadAllText(Path.Combine(src, "scene.json")));
        var gos = new Dictionary<string, GameObject>();
        var lpR = new List<Renderer>(); var lpA = new List<string>();
        var lmR = new List<Renderer>(); var lmI = new List<int>(); var lmST = new List<Vector4>();
        int lmCount = sf.lightmaps == null ? 0 : sf.lightmaps.Length;
        foreach (var o in sf.objects) gos[o.id] = new GameObject(o.name);
        int renderers = 0;
        foreach (var o in sf.objects)
        {
            var go = gos[o.id];
            go.layer = Mathf.Clamp(o.layer, 0, 31);
            if (o.parent != null && gos.ContainsKey(o.parent)) go.transform.SetParent(gos[o.parent].transform, false);
            if (o.pos != null && o.pos.Length == 3)
            {
                go.transform.localPosition = new Vector3(o.pos[0], o.pos[1], o.pos[2]);
                go.transform.localRotation = new Quaternion(o.rot[0], o.rot[1], o.rot[2], o.rot[3]);
                go.transform.localScale = new Vector3(o.scale[0], o.scale[1], o.scale[2]);
            }
            if (!string.IsNullOrEmpty(o.mesh) && meshes.ContainsKey(o.mesh))
                go.AddComponent<MeshFilter>().sharedMesh = meshes[o.mesh];
            if (o.materials != null && o.materials.Length > 0)
            {
                var r = go.AddComponent<MeshRenderer>(); renderers++;
                var list = new List<Material>();
                foreach (var id in o.materials) list.Add(id != null && mats.ContainsKey(id) ? mats[id] : null);
                r.sharedMaterials = list.ToArray(); r.enabled = o.rendererEnabled;
                if (o.useLightProbes && o.lightmapIndex >= lmCount) { lpR.Add(r); lpA.Add(o.probeAnchor); }
                if (o.lightmapIndex < lmCount) { lmR.Add(r); lmI.Add(o.lightmapIndex); lmST.Add(new Vector4(o.lightmapST[0], o.lightmapST[1], o.lightmapST[2], o.lightmapST[3])); }
            }
        }
        // cameras: data kept for all; only on-screen cameras (no render target, cleared to sky/colour) are enabled
        foreach (var o in sf.objects)
        {
            var c = o.camera; if (c == null || c.background == null || c.background.Length != 4) continue;
            var cam = gos[o.id].AddComponent<Camera>();
            cam.clearFlags = (CameraClearFlags)c.clearFlags; cam.backgroundColor = Col(c.background);
            cam.rect = new Rect(c.rect[0], c.rect[1], c.rect[2], c.rect[3]); cam.nearClipPlane = c.near; cam.farClipPlane = c.far;
            cam.fieldOfView = c.fov; cam.orthographic = c.ortho; cam.orthographicSize = c.orthoSize; cam.depth = c.depth;
            cam.cullingMask = (int)c.cullingMask; cam.allowHDR = c.hdr;
            cam.enabled = c.enabled && !c.hasTargetTexture && (c.clearFlags == 1 || c.clearFlags == 2);
            // image effects in the original component order: RainCommonPostEffect, (DepthOfFieldSimple: masked), RainMergePostEffect
            var rc = o.rainCommon;
            if (rc != null && rc.redChannel != null && rc.redChannel.Length > 0)
            {
                var ce = gos[o.id].AddComponent<RainCommonPostEffect>();
                ce.ccDepthShader = Shader.Find("RainPS3/Hidden/RainCommonAdvancedShader"); ce.fxaaShader = Shader.Find("RainPS3/Hidden/FXAA2Shader");
                ce.redChannel = Curve(rc.redChannel); ce.greenChannel = Curve(rc.greenChannel); ce.blueChannel = Curve(rc.blueChannel);
                ce.useDepthCorrection = rc.useDepthCorrection; ce.zCurve = Curve(rc.zCurve);
                ce.depthRedChannel = Curve(rc.depthRedChannel); ce.depthGreenChannel = Curve(rc.depthGreenChannel); ce.depthBlueChannel = Curve(rc.depthBlueChannel);
                ce.maskTexture = LoadTex(root, rc.maskTexture); ce.maskColor = Col(rc.maskColor); ce.maskIntensity = rc.maskIntensity;
                ce.globalFogStartDistance = rc.globalFogStartDistance; ce.globalFogDensity = rc.globalFogDensity; ce.globalFogColor = Col(rc.globalFogColor);
                ce.globalFogHeightScale = rc.globalFogHeightScale; ce.globalFogHeight = rc.globalFogHeight; ce.globalFogHeightDensity = rc.globalFogHeightDensity;
                ce.globalFogHeightColor = Col(rc.globalFogHeightColor); ce.globalFogFarClip = rc.globalFogFarClip;
                ce.m_FXAASampleCount = rc.m_FXAASampleCount; ce.m_SunShaftEnable = rc.m_SunShaftEnable; ce.enabled = rc.enabled;
            }
            var m = o.rainMerge; if (m == null || m.m_RGBCurve == null || m.m_RGBCurve.Length == 0) continue;
            var pe = gos[o.id].AddComponent<RainMergePostEffect>();
            pe.m_MergeShader = Shader.Find("RainPS3/Hidden/RainMergePostEffectShader");
            pe.m_RGBCurve = Curve(m.m_RGBCurve); pe.m_BlendTexture = LoadTex(root, m.m_BlendTexture);
            pe.m_GaussIntensity = m.m_GaussIntensity; pe.m_SoftFocusBlendIntensity = m.m_SoftFocusBlendIntensity;
            pe.m_ColorVignette = m.m_ColorVignette; pe.m_ColorVignetteIntensity = m.m_ColorVignetteIntensity;
            pe.m_BlurVignette = m.m_BlurVignette; pe.m_BlurVignetteIntensity = m.m_BlurVignetteIntensity;
            pe.m_TextureBlendIntensity = m.m_TextureBlendIntensity; pe.m_TextureBlendMode = m.m_TextureBlendMode;
            pe.m_SaturationIntensity = m.m_SaturationIntensity; pe.m_UseMergeShader = m.m_UseMergeShader; pe.m_DownSizeDiv = m.m_DownSizeDiv;
            pe.m_SoftFocusBlendMode = m.m_SoftFocusBlendMode; pe.m_UpdateRGBCurve = m.m_UpdateRGBCurve; pe.enabled = m.enabled;
        }
        foreach (var o in sf.objects) gos[o.id].SetActive(o.active);

        // gameplay scripts (M6): reflection-based attach from the raw scene.json scripts{} dicts (JsonUtility can't
        // deserialize the arbitrary per-class field shape, so we re-parse with MiniJson for this part only).
        int scriptsOk = 0, scriptsErr = 0;
        AttachScripts(gos, mats, File.ReadAllText(Path.Combine(src, "scene.json")), ref scriptsOk, ref scriptsErr);
        Debug.Log("RAIN IMPORT: scripts attached fields=" + scriptsOk + " errors=" + scriptsErr);


        // lightmaps: applied at runtime by RainLightmaps (index 255 = none; out-of-range indices dropped)
        Lightmapping.giWorkflowMode = Lightmapping.GIWorkflowMode.OnDemand;   // keep the editor from baking over them
        var lm = new GameObject("RainLightmaps").AddComponent<RainLightmaps>();
        lm.far = new Texture2D[lmCount]; lm.near = new Texture2D[lmCount];
        for (int i = 0; i < lmCount; i++) { lm.far[i] = LoadTex(root, sf.lightmaps[i].far); lm.near[i] = LoadTex(root, sf.lightmaps[i].near); }
        lm.renderers = lmR.ToArray(); lm.indices = lmI.ToArray(); lm.scaleOffsets = lmST.ToArray();
        lm.Apply();

        // light probes: SH per renderer from the original probe set (RainLightProbes); everything else gets ambient-only SH
        var lp = new GameObject("RainLightProbes").AddComponent<RainLightProbes>();
        if (sf.lightProbes != null && sf.lightProbes.positions != null && sf.lightProbes.positions.Length > 0)
        { lp.positions = sf.lightProbes.positions; lp.coefficients = sf.lightProbes.coefficients; lp.tetrahedra = sf.lightProbes.tetrahedra; }
        else { lp.positions = new float[0]; lp.coefficients = new float[0]; lp.tetrahedra = new int[0]; lpR.Clear(); lpA.Clear(); }
        lp.renderers = lpR.ToArray(); lp.ambient = Col(sf.render.ambient);
        lp.anchors = lpA.ConvertAll(id => id != null && gos.ContainsKey(id) ? gos[id].transform : null).ToArray();
        lp.Apply();
        Debug.Log("RAIN IMPORT: light probes " + lp.SelfTest() + " probe renderers=" + lpR.Count);

        // render settings (3.5 FogMode values equal UnityEngine.FogMode)
        var rs = sf.render;
        RenderSettings.fog = rs.fog; RenderSettings.fogColor = Col(rs.fogColor); RenderSettings.fogMode = (FogMode)rs.fogMode;
        RenderSettings.fogDensity = rs.fogDensity; RenderSettings.fogStartDistance = rs.fogStart; RenderSettings.fogEndDistance = rs.fogEnd;
        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat; RenderSettings.ambientLight = Col(rs.ambient);
        RenderSettings.skybox = rs.skybox != null && mats.ContainsKey(rs.skybox) ? mats[rs.skybox] : null;
        RenderSettings.haloStrength = rs.haloStrength; RenderSettings.flareStrength = rs.flareStrength;

        string scenePath = root + "/" + sceneName + ".unity";
        EditorSceneManager.SaveScene(scene, scenePath);
        Debug.Log(string.Format("RAIN IMPORT: gameobjects={0} renderers={1} meshes={2} materials={3} (converted shader {4}) textures={5} lightmaps={6} lightmapped={7} scene={8}",
            gos.Count, renderers, meshes.Count, mats.Count, bound, Directory.GetFiles(root + "/Textures", "*.dds").Length, lmCount, lmR.Count, scenePath));
    }

    static Texture2D LoadTex(string root, string id) { return id == null ? null : AssetDatabase.LoadAssetAtPath<Texture2D>(root + "/Textures/" + Safe(id) + ".dds"); }
    static Color Col(float[] v) { return new Color(v[0], v[1], v[2], v[3]); }
    static AnimationCurve Curve(float[] f)   // flat (time, value, inSlope, outSlope)*n from rain_export.py
    {
        var keys = new Keyframe[f == null ? 0 : f.Length / 4];
        for (int k = 0; k < keys.Length; k++) keys[k] = new Keyframe(f[4 * k], f[4 * k + 1], f[4 * k + 2], f[4 * k + 3]);
        return new AnimationCurve(keys);
    }

    static Mesh ReadMesh(string path)
    {
        using (var br = new BinaryReader(File.OpenRead(path)))
        {
            int n = br.ReadInt32(); int mask = br.ReadInt32();
            var mesh = new Mesh();
            if (n > 65535) mesh.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            if ((mask & 1) != 0) mesh.vertices = ReadV3(br, n);
            if ((mask & 2) != 0) mesh.normals = ReadV3(br, n);
            if ((mask & 4) != 0) { var cs = new Color32[n]; for (int i = 0; i < n; i++) cs[i] = new Color32(br.ReadByte(), br.ReadByte(), br.ReadByte(), br.ReadByte()); mesh.colors32 = cs; }
            if ((mask & 8) != 0) mesh.uv = ReadV2(br, n);
            if ((mask & 16) != 0) mesh.uv2 = ReadV2(br, n);
            if ((mask & 32) != 0) { var t = new Vector4[n]; for (int i = 0; i < n; i++) t[i] = new Vector4(br.ReadSingle(), br.ReadSingle(), br.ReadSingle(), br.ReadSingle()); mesh.tangents = t; }
            int subs = br.ReadInt32(); mesh.subMeshCount = subs;
            for (int s = 0; s < subs; s++)
            {
                int c = br.ReadInt32(); var idx = new int[c];
                for (int i = 0; i < c; i++) idx[i] = br.ReadInt32();
                mesh.SetTriangles(idx, s);
            }
            mesh.RecalculateBounds();
            return mesh;
        }
    }
    static Vector3[] ReadV3(BinaryReader br, int n) { var v = new Vector3[n]; for (int i = 0; i < n; i++) v[i] = new Vector3(br.ReadSingle(), br.ReadSingle(), br.ReadSingle()); return v; }
    static Vector2[] ReadV2(BinaryReader br, int n) { var v = new Vector2[n]; for (int i = 0; i < n; i++) v[i] = new Vector2(br.ReadSingle(), br.ReadSingle()); return v; }

    // --- M6: generic gameplay-script component attach (reconstructed types in Assets/RainRuntime/Recon) ---------

    static Dictionary<string, Type> _typeCache;
    static Type FindType(string cls)
    {
        if (_typeCache == null)
        {
            _typeCache = new Dictionary<string, Type>();
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                try { foreach (var t in asm.GetTypes()) if (!_typeCache.ContainsKey(t.Name)) _typeCache[t.Name] = t; }
                catch (ReflectionTypeLoadException) { }
        }
        Type r; return _typeCache.TryGetValue(cls, out r) ? r : null;
    }
    static FieldInfo FindField(Type t, string name)
    {
        for (var bt = t; bt != null; bt = bt.BaseType)
        {
            var fi = bt.GetField(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly);
            if (fi != null) return fi;
        }
        return null;
    }
    static object ConvertKeyframes(object val)   // decoded {"keys":[[t,v,in,out],...], "pre_post":[a,b]} -> AnimationCurve
    {
        var d = (Dictionary<string, object>)val; var keysRaw = (List<object>)d["keys"];
        var keys = new Keyframe[keysRaw.Count];
        for (int i = 0; i < keys.Length; i++)
        {
            var k = (List<object>)keysRaw[i];
            keys[i] = new Keyframe(Convert.ToSingle(k[0]), Convert.ToSingle(k[1]), Convert.ToSingle(k[2]), Convert.ToSingle(k[3]));
        }
        var curve = new AnimationCurve(keys); var pp = (List<object>)d["pre_post"];
        curve.preWrapMode = (WrapMode)Convert.ToInt32(pp[0]); curve.postWrapMode = (WrapMode)Convert.ToInt32(pp[1]);
        return curve;
    }
    // resolve a scene-object-id string (file@pathID, as written by rid() in rain_export.py) against whichever table
    // actually holds it: scene GameObjects first (by far the common case for gameplay fields), else materials.
    static object ResolveRef(string id, Type fieldType, Dictionary<string, GameObject> gos, Dictionary<string, Material> mats)
    {
        if (id == null) return null;
        GameObject go;
        if (gos.TryGetValue(id, out go))
        {
            if (fieldType == typeof(GameObject)) return go;
            if (fieldType == typeof(Transform)) return go.transform;
            if (typeof(Component).IsAssignableFrom(fieldType)) return go.GetComponent(fieldType);
            return go;
        }
        Material mat;
        if (typeof(Material).IsAssignableFrom(fieldType) && mats.TryGetValue(id, out mat)) return mat;
        return null;   // texture/other asset refs, or an object outside this level set: not wired yet
    }
    static object ConvertValue(object val, Type ft, Dictionary<string, GameObject> gos, Dictionary<string, Material> mats)
    {
        if (ft == typeof(string)) return val as string;
        if (val is string) return ResolveRef((string)val, ft, gos, mats);   // pptr leaf
        if (val == null) return ft.IsValueType ? Activator.CreateInstance(ft) : null;
        if (ft.IsEnum) return Enum.ToObject(ft, Convert.ToInt64((double)val));
        if (ft == typeof(bool)) return Convert.ToBoolean(val);
        if (ft == typeof(int)) return Convert.ToInt32((double)val);
        if (ft == typeof(uint)) return Convert.ToUInt32((double)val);
        if (ft == typeof(long)) return Convert.ToInt64((double)val);
        if (ft == typeof(float)) return Convert.ToSingle((double)val);
        if (ft == typeof(double)) return (double)val;
        if (ft == typeof(byte) || ft == typeof(sbyte) || ft == typeof(short) || ft == typeof(ushort)) return Convert.ChangeType(val, ft);
        if (ft == typeof(AnimationCurve)) return ConvertKeyframes(val);
        if (ft == typeof(LayerMask)) { var lm = default(LayerMask); lm.value = Convert.ToInt32((double)val); return lm; }
        if (val is Dictionary<string, object>)   // [Serializable] inline struct/class: recurse per declared field
        {
            var inl = (Dictionary<string, object>)val;
            object inst = Activator.CreateInstance(ft);
            foreach (var kv in inl) { var fi = FindField(ft, kv.Key); if (fi != null) fi.SetValue(inst, ConvertValue(kv.Value, fi.FieldType, gos, mats)); }
            return inst;
        }
        var list = val as List<object>;
        if (list != null)
        {
            if (ft == typeof(Color32) && list.Count == 4) return new Color32((byte)Convert.ToInt32(list[0]), (byte)Convert.ToInt32(list[1]), (byte)Convert.ToInt32(list[2]), (byte)Convert.ToInt32(list[3]));
            if (ft == typeof(Vector2) && list.Count >= 2) return new Vector2(Convert.ToSingle(list[0]), Convert.ToSingle(list[1]));
            if (ft == typeof(Vector3) && list.Count >= 3) return new Vector3(Convert.ToSingle(list[0]), Convert.ToSingle(list[1]), Convert.ToSingle(list[2]));
            if (ft == typeof(Vector4) && list.Count >= 4) return new Vector4(Convert.ToSingle(list[0]), Convert.ToSingle(list[1]), Convert.ToSingle(list[2]), Convert.ToSingle(list[3]));
            if (ft == typeof(Quaternion) && list.Count >= 4) return new Quaternion(Convert.ToSingle(list[0]), Convert.ToSingle(list[1]), Convert.ToSingle(list[2]), Convert.ToSingle(list[3]));
            if (ft == typeof(Color) && list.Count >= 4) return new Color(Convert.ToSingle(list[0]), Convert.ToSingle(list[1]), Convert.ToSingle(list[2]), Convert.ToSingle(list[3]));
            if (ft == typeof(Rect) && list.Count >= 4) return new Rect(Convert.ToSingle(list[0]), Convert.ToSingle(list[1]), Convert.ToSingle(list[2]), Convert.ToSingle(list[3]));
            if (ft == typeof(Bounds) && list.Count >= 6) return new Bounds(new Vector3(Convert.ToSingle(list[0]), Convert.ToSingle(list[1]), Convert.ToSingle(list[2])), 2 * new Vector3(Convert.ToSingle(list[3]), Convert.ToSingle(list[4]), Convert.ToSingle(list[5])));
            if (ft.IsArray)
            {
                var el = ft.GetElementType(); var arr = Array.CreateInstance(el, list.Count);
                for (int i = 0; i < list.Count; i++) arr.SetValue(ConvertValue(list[i], el, gos, mats), i);
                return arr;
            }
            if (ft.IsGenericType && ft.GetGenericTypeDefinition() == typeof(List<>))
            {
                var el = ft.GetGenericArguments()[0]; var lst = (System.Collections.IList)Activator.CreateInstance(ft);
                foreach (var v in list) lst.Add(ConvertValue(v, el, gos, mats));
                return lst;
            }
            return null;   // unmodelled generic/collection field type
        }
        return Convert.ChangeType(val, ft);   // leftover numeric prim (double -> int/float handled above; fallback)
    }
    static void AttachScripts(Dictionary<string, GameObject> gos, Dictionary<string, Material> mats, string rawJson, ref int ok, ref int err)
    {
        var root = (Dictionary<string, object>)MiniJson.Parse(rawJson);
        var objs = (List<object>)root["objects"];
        var compMap = new Dictionary<string, Dictionary<string, object>>();
        foreach (var ox in objs)
        {
            var od = (Dictionary<string, object>)ox; object scriptsObj;
            if (!od.TryGetValue("scripts", out scriptsObj)) continue;
            string id = (string)od["id"]; GameObject go;
            if (!gos.TryGetValue(id, out go)) continue;
            var scripts = (Dictionary<string, object>)scriptsObj; compMap[id] = scripts;
            foreach (var cls in scripts.Keys)
            {
                var t = FindType(cls);
                if (t == null) { Debug.LogWarning("RAIN IMPORT: unknown script class " + cls); err++; continue; }
                if (go.GetComponent(t) == null) go.AddComponent(t);
            }
        }
        foreach (var kv in compMap)
        {
            var go = gos[kv.Key];
            foreach (var ce in kv.Value)
            {
                var t = FindType(ce.Key); if (t == null) continue;
                var comp = go.GetComponent(t); if (comp == null) continue;
                var fields = (Dictionary<string, object>)ce.Value;
                foreach (var fe in fields)
                {
                    if (fe.Key == "enabled") { var b = comp as Behaviour; if (b != null) b.enabled = Convert.ToBoolean(fe.Value); continue; }
                    var fi = FindField(t, fe.Key);
                    if (fi == null) continue;   // field dropped/renamed vs the decompile (rare); leave default
                    try { fi.SetValue(comp, ConvertValue(fe.Value, fi.FieldType, gos, mats)); ok++; }
                    catch (Exception e) { Debug.LogWarning("RAIN IMPORT: " + ce.Key + "." + fe.Key + ": " + e.Message); err++; }
                }
            }
        }
    }

    // Minimal JSON parser (object graph: Dictionary<string,object> / List<object> / string / double / bool / null).
    // scene.json has no large numeric precision needs here (ids/flags/floats only), so double is enough.
    static class MiniJson
    {
        public static object Parse(string s) { int i = 0; SkipWs(s, ref i); return ParseValue(s, ref i); }
        static void SkipWs(string s, ref int i) { while (i < s.Length && char.IsWhiteSpace(s[i])) i++; }
        static object ParseValue(string s, ref int i)
        {
            SkipWs(s, ref i);
            switch (s[i])
            {
                case '{': return ParseObject(s, ref i);
                case '[': return ParseArray(s, ref i);
                case '"': return ParseString(s, ref i);
                case 't': i += 4; return true;
                case 'f': i += 5; return false;
                case 'n': i += 4; return null;
                default: return ParseNumber(s, ref i);
            }
        }
        static Dictionary<string, object> ParseObject(string s, ref int i)
        {
            var d = new Dictionary<string, object>(); i++; SkipWs(s, ref i);
            if (s[i] == '}') { i++; return d; }
            while (true)
            {
                SkipWs(s, ref i); string k = ParseString(s, ref i); SkipWs(s, ref i); i++;   // ':'
                d[k] = ParseValue(s, ref i); SkipWs(s, ref i);
                if (s[i] == ',') { i++; continue; }
                i++; break;   // '}'
            }
            return d;
        }
        static List<object> ParseArray(string s, ref int i)
        {
            var l = new List<object>(); i++; SkipWs(s, ref i);
            if (s[i] == ']') { i++; return l; }
            while (true)
            {
                l.Add(ParseValue(s, ref i)); SkipWs(s, ref i);
                if (s[i] == ',') { i++; continue; }
                i++; break;   // ']'
            }
            return l;
        }
        static string ParseString(string s, ref int i)
        {
            i++; var sb = new System.Text.StringBuilder();
            while (s[i] != '"')
            {
                if (s[i] == '\\')
                {
                    i++;
                    switch (s[i])
                    {
                        case 'n': sb.Append('\n'); break; case 't': sb.Append('\t'); break; case 'r': sb.Append('\r'); break;
                        case 'b': sb.Append('\b'); break; case 'f': sb.Append('\f'); break;
                        case 'u': sb.Append((char)Convert.ToInt32(s.Substring(i + 1, 4), 16)); i += 4; break;
                        default: sb.Append(s[i]); break;
                    }
                    i++;
                }
                else sb.Append(s[i++]);
            }
            i++; return sb.ToString();
        }
        static double ParseNumber(string s, ref int i)
        {
            int st = i;
            while (i < s.Length && (char.IsDigit(s[i]) || s[i] == '-' || s[i] == '+' || s[i] == '.' || s[i] == 'e' || s[i] == 'E')) i++;
            return double.Parse(s.Substring(st, i - st), System.Globalization.CultureInfo.InvariantCulture);
        }
    }
}
