// Render preview images of an imported Rain scene headless (M1/M3 visual checks).
//   Unity.exe -batchmode -quit -projectPath <proj> -executeMethod RainShot.Run -rainScenePath <Assets/...unity> -rainOut <dir>
//     [-rainPoses <poses.jsonl from tools/probe_campose.py>]  -> also <label>_port.png per captured RPCS3 camera pose
// Uses the scene's own RenderSettings, lightmaps (RainLightmaps) and light probes (RainLightProbes); no preview lights.
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

public static class RainShot
{
    static string Arg(string n) { var a = Environment.GetCommandLineArgs(); for (int i = 0; i < a.Length - 1; i++) if (a[i] == n) return a[i + 1]; return null; }

    public static void Run()
    {
        var sc = EditorSceneManager.OpenScene(Arg("-rainScenePath"));
        // Preview only: simulate all streamed map chunks being loaded (scene asset is not saved). Chunks are stored inactive at
        // every level (3.5 active flags are per object, E86), so activate each inactive root with its whole subtree.
        int activated = 0;
        foreach (var r in sc.GetRootGameObjects())
            if (!r.activeSelf) { foreach (var t in r.GetComponentsInChildren<Transform>(true)) t.gameObject.SetActive(true); activated++; }
        Debug.Log("RAIN SHOT: activated roots=" + activated);
        string outDir = Arg("-rainOut"); Directory.CreateDirectory(outDir);
        var lm = UnityEngine.Object.FindObjectOfType<RainLightmaps>(); if (lm != null) lm.Apply();
        var lp = UnityEngine.Object.FindObjectOfType<RainLightProbes>(); if (lp != null) lp.Apply();

        Bounds b = new Bounds(); bool first = true; int n = 0;
        foreach (var r in UnityEngine.Object.FindObjectsOfType<Renderer>())
        {
            if (!r.enabled || !r.gameObject.activeInHierarchy) continue;
            if (first) { b = r.bounds; first = false; } else b.Encapsulate(r.bounds);
            n++;
        }
        Debug.Log("RAIN SHOT: visible renderers=" + n + " bounds center=" + b.center + " size=" + b.size);

        var cgo = new GameObject("PreviewCam"); var cam = cgo.AddComponent<Camera>();
        cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = new Color(0.25f, 0.3f, 0.35f);
        cam.farClipPlane = Mathf.Max(1000f, b.size.magnitude * 3f); cam.nearClipPlane = 0.3f;
        // 1: top-down orthographic overview
        cam.orthographic = true; cam.orthographicSize = Mathf.Max(b.size.x, b.size.z) * 0.55f;
        cgo.transform.position = b.center + Vector3.up * (b.size.y + 50f); cgo.transform.rotation = Quaternion.Euler(90, 0, 0);
        Save(cam, Path.Combine(outDir, "overview_top.png"));
        // 2: perspective, elevated 3/4 view
        cam.orthographic = false; cam.fieldOfView = 50f;
        cgo.transform.position = b.center + new Vector3(-b.size.x * 0.35f, b.size.magnitude * 0.25f, -b.size.z * 0.35f);
        cgo.transform.LookAt(b.center);
        Save(cam, Path.Combine(outDir, "overview_persp.png"));
        // 3: golden-image poses captured from RPCS3
        string poses = Arg("-rainPoses");
        if (poses == null) return;
        foreach (var line in File.ReadAllLines(poses))
        {
            var p = JsonUtility.FromJson<Pose>(line);
            if (p.position == null || p.position.Length != 3) { Debug.Log("RAIN SHOT skip pose " + p.label); continue; }
            cgo.transform.position = new Vector3(p.position[0], p.position[1], p.position[2]);
            cgo.transform.rotation = new Quaternion(p.rotation[0], p.rotation[1], p.rotation[2], p.rotation[3]);
            cam.fieldOfView = p.fov; cam.nearClipPlane = p.near; cam.farClipPlane = p.far; cam.aspect = p.aspect;
            Save(cam, Path.Combine(outDir, p.label + "_port.png"));
        }
    }

    [Serializable] class Pose { public string label; public float[] position; public float[] rotation; public float aspect, near, far, fov; }

    static void Save(Camera cam, string path)
    {
        var rt = new RenderTexture(1280, 720, 24); cam.targetTexture = rt; cam.Render();
        RenderTexture.active = rt; var tex = new Texture2D(1280, 720, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, 1280, 720), 0, 0); tex.Apply();
        File.WriteAllBytes(path, tex.EncodeToPNG()); RenderTexture.active = null; cam.targetTexture = null;
        Debug.Log("RAIN SHOT saved " + path);
    }
}
