// Build an imported Rain scene as a Windows x64 D3D11 player (M3 acceptance). The scene asset is not modified: a copy
// with a RainPlayerSmoke object is built.
//   Unity.exe -batchmode -quit -projectPath <proj> -executeMethod RainBuild.Run -rainScenePath <Assets/...unity> -rainOut <exe>
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class RainBuild
{
    static string Arg(string n) { var a = Environment.GetCommandLineArgs(); for (int i = 0; i < a.Length - 1; i++) if (a[i] == n) return a[i + 1]; return null; }

    public static void Run()
    {
        string src = Arg("-rainScenePath"), exe = Arg("-rainOut");
        string copy = Path.Combine(Path.GetDirectoryName(src), Path.GetFileNameWithoutExtension(src) + "_build.unity").Replace('\\', '/');
        AssetDatabase.CopyAsset(src, copy);
        var sc = EditorSceneManager.OpenScene(copy);
        new GameObject("RainPlayerSmoke").AddComponent<RainPlayerSmoke>();
        EditorSceneManager.SaveScene(sc);
        PlayerSettings.runInBackground = true;   // unattended run: keep updating without focus
        PlayerSettings.displayResolutionDialog = ResolutionDialogSetting.Disabled;
        PlayerSettings.SetGraphicsAPIs(BuildTarget.StandaloneWindows64, new[] { UnityEngine.Rendering.GraphicsDeviceType.Direct3D11 });
        var r = BuildPipeline.BuildPlayer(new[] { copy }, exe, BuildTarget.StandaloneWindows64, BuildOptions.None);
        Debug.Log("RAIN BUILD: " + (string.IsNullOrEmpty(r) ? "OK " + exe : "FAILED " + r));
    }
}
