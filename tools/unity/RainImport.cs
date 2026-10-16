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
    }
    [Serializable] public class SceneFile { public Obj[] objects; public string[] roots; }

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

        // materials (placeholder shaders until M2 provides translated ones)
        var mats = new Dictionary<string, Material>();
        var mf = JsonUtility.FromJson<MatFile>(File.ReadAllText(Path.Combine(src, "materials.json")));
        Shader fallback = Shader.Find("Legacy Shaders/Diffuse"), cutout = Shader.Find("Legacy Shaders/Transparent/Cutout/Diffuse");
        foreach (var m in mf.materials)
        {
            bool alpha = m.shaderName != null && (m.shaderName.Contains("Transparent") || m.shaderName.Contains("Cutout") || m.shaderName.Contains("Alpha"));
            var mat = new Material(alpha ? cutout : fallback) { name = m.name };
            foreach (var t in m.textures)
            {
                if (t.tex == null) continue;
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(root + "/Textures/" + Safe(t.tex) + ".dds");
                if (tex == null || !mat.HasProperty(t.prop)) continue;
                mat.SetTexture(t.prop, tex);
                mat.SetTextureScale(t.prop, new Vector2(t.scale[0], t.scale[1]));
                mat.SetTextureOffset(t.prop, new Vector2(t.offset[0], t.offset[1]));
            }
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
            }
        }
        foreach (var o in sf.objects) gos[o.id].SetActive(o.active);
        string scenePath = root + "/" + sceneName + ".unity";
        EditorSceneManager.SaveScene(scene, scenePath);
        Debug.Log(string.Format("RAIN IMPORT: gameobjects={0} renderers={1} meshes={2} materials={3} textures={4} scene={5}",
            gos.Count, renderers, meshes.Count, mats.Count, Directory.GetFiles(root + "/Textures", "*.dds").Length, scenePath));
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
}
