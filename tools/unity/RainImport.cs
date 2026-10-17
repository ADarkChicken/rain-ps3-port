// Rain intermediate -> Unity 2017.4 assets + scene (M1). Run headless:
//   Unity.exe -batchmode -quit -projectPath <proj> -executeMethod RainImport.Run -rainExport <dir> -rainScene <name>
// Reads scene.json / materials.json / textures/*.dds / meshes/*.bin written by tools/rain_export.py.
using System;
using System.Collections.Generic;
using System.IO;
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
        public Cam camera; public Merge rainMerge;
    }
    [Serializable] public class Cam
    {
        public bool enabled; public int clearFlags; public float[] background; public float[] rect; public float near, far, fov, orthoSize, depth;
        public bool ortho; public long cullingMask; public int renderingPath; public bool hdr; public bool hasTargetTexture;
    }
    [Serializable] public class Merge
    {
        public bool enabled; public float[] curve; public string blendTexture;
        public float m_GaussIntensity, m_SoftFocusBlendIntensity, m_ColorVignetteIntensity, m_BlurVignetteIntensity, m_TextureBlendIntensity, m_SaturationIntensity;
        public bool m_UpdateRGBCurve, m_ColorVignette, m_BlurVignette, m_UseMergeShader;
        public int m_SoftFocusBlendMode, m_TextureBlendMode, m_DownSizeDiv;
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
            var m = o.rainMerge; if (m == null || m.curve == null || m.curve.Length == 0) continue;
            var pe = gos[o.id].AddComponent<RainMergePostEffect>();
            var keys = new Keyframe[m.curve.Length / 4];
            for (int k = 0; k < keys.Length; k++) keys[k] = new Keyframe(m.curve[4 * k], m.curve[4 * k + 1], m.curve[4 * k + 2], m.curve[4 * k + 3]);
            pe.m_RGBCurve = new AnimationCurve(keys); pe.m_BlendTexture = LoadTex(root, m.blendTexture);
            pe.m_GaussIntensity = m.m_GaussIntensity; pe.m_SoftFocusBlendIntensity = m.m_SoftFocusBlendIntensity;
            pe.m_ColorVignette = m.m_ColorVignette; pe.m_ColorVignetteIntensity = m.m_ColorVignetteIntensity;
            pe.m_BlurVignette = m.m_BlurVignette; pe.m_BlurVignetteIntensity = m.m_BlurVignetteIntensity;
            pe.m_TextureBlendIntensity = m.m_TextureBlendIntensity; pe.m_TextureBlendMode = m.m_TextureBlendMode;
            pe.m_SaturationIntensity = m.m_SaturationIntensity; pe.m_UseMergeShader = m.m_UseMergeShader; pe.m_DownSizeDiv = m.m_DownSizeDiv;
            pe.m_SoftFocusBlendMode = m.m_SoftFocusBlendMode; pe.m_UpdateRGBCurve = m.m_UpdateRGBCurve; pe.enabled = m.enabled;
        }
        foreach (var o in sf.objects) gos[o.id].SetActive(o.active);

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
}
