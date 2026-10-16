using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class BuildM0
{
    // M0: build an empty Windows x64 player headless (Unity 2017.4).
    public static void Build()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
        EditorSceneManager.SaveScene(scene, "Assets/M0.unity");
        PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.StandaloneWindows64, false);
        PlayerSettings.SetGraphicsAPIs(BuildTarget.StandaloneWindows64, new[] { UnityEngine.Rendering.GraphicsDeviceType.Direct3D11 });
        var opts = new BuildPlayerOptions
        {
            scenes = new[] { "Assets/M0.unity" },
            locationPathName = "../m0_build_x64/M0.exe",
            target = BuildTarget.StandaloneWindows64,
            options = BuildOptions.None
        };
        var report = BuildPipeline.BuildPlayer(opts);
        Debug.Log("M0 BUILD RESULT: " + (string.IsNullOrEmpty(report) ? "OK" : report));
        if (!string.IsNullOrEmpty(report)) EditorApplication.Exit(1);
    }
}
