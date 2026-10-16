// M2 check: force compilation of every variant of every RainPS3/* shader by building a Windows x64 player whose scene
// references one material per shader (multi_compile variants are all compiled at build time).
//   Unity.exe -batchmode -quit -projectPath <proj> -executeMethod RainShaderBuildCheck.Run -rainOut <buildDir>
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class RainShaderBuildCheck
{
    public static void Run()
    {
        string outDir = null; var a = Environment.GetCommandLineArgs();
        for (int i = 0; i < a.Length - 1; i++) if (a[i] == "-rainOut") outDir = a[i + 1];
        Directory.CreateDirectory("Assets/RainShaderCheck");
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        int n = 0, bad = 0;
        foreach (var guid in AssetDatabase.FindAssets("t:Shader", new[] { "Assets/RainShaders" }))
        {
            var sh = AssetDatabase.LoadAssetAtPath<Shader>(AssetDatabase.GUIDToAssetPath(guid));
            if (sh == null) { bad++; continue; }
            var mat = new Material(sh);
            AssetDatabase.CreateAsset(mat, "Assets/RainShaderCheck/m" + n + ".mat");
            var go = GameObject.CreatePrimitive(PrimitiveType.Quad); go.GetComponent<Renderer>().sharedMaterial = mat;
            if (!sh.isSupported) bad++;
            n++;
        }
        EditorSceneManager.SaveScene(scene, "Assets/RainShaderCheck/check.unity");
        Debug.Log("RAIN SHADER CHECK: shaders=" + n + " unsupported=" + bad);
        var opts = new BuildPlayerOptions { scenes = new[] { "Assets/RainShaderCheck/check.unity" }, locationPathName = outDir + "/check.exe",
                                            target = BuildTarget.StandaloneWindows64, options = BuildOptions.None };
        var report = BuildPipeline.BuildPlayer(opts);
        Debug.Log("RAIN SHADER CHECK BUILD: " + (string.IsNullOrEmpty(report) ? "OK" : report));
    }
}
