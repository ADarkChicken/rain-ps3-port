// Headless play-mode smoke test for an imported Rain scene (M6): enters Play mode, runs for N frames, logs whatever
// GameManager/CharacterPlayer state is reachable, then exits the process itself (no -quit on the command line --
// entering Play mode triggers a domain reload in Unity 2017.4 (no "disable domain reload" option until 2019.3),
// which wipes any EditorApplication.update subscription made before the reload and resets static fields. Use
// [InitializeOnLoad] (its static ctor reruns after every reload, including the play-mode one) to re-subscribe, and
// SessionState (survives the reload, unlike a plain static field) to carry the frame target/counter across it.
//   Unity.exe -batchmode -projectPath <proj> -executeMethod RainPlayTest.Run -rainScenePath <Assets/...unity> -rainFrames <N> -logFile <log>
using System;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class RainPlayTest
{
    const string K_ARMED = "RainPlayTest.armed", K_MAX = "RainPlayTest.max", K_FRAME = "RainPlayTest.frame";
    static string Arg(string n) { var a = Environment.GetCommandLineArgs(); for (int i = 0; i < a.Length - 1; i++) if (a[i] == n) return a[i + 1]; return null; }

    static RainPlayTest() { EditorApplication.update += Tick; }

    public static void Run()
    {
        EditorSceneManager.OpenScene(Arg("-rainScenePath"));
        var fArg = Arg("-rainFrames");
        SessionState.SetInt(K_MAX, fArg != null ? int.Parse(fArg) : 120);
        SessionState.SetInt(K_FRAME, 0);
        SessionState.SetBool(K_ARMED, true);
        Debug.Log("RAIN PLAYTEST: entering play mode for " + SessionState.GetInt(K_MAX, 120) + " frames");
        EditorApplication.isPlaying = true;
    }

    static void Tick()
    {
        if (!SessionState.GetBool(K_ARMED, false)) return;
        if (!EditorApplication.isPlaying) return;   // still waiting for the async domain reload into play mode
        int frame = SessionState.GetInt(K_FRAME, 0) + 1;
        SessionState.SetInt(K_FRAME, frame);
        if (frame == 1)
        {
            var gm = GameObject.Find("GameManager");
            Debug.Log("RAIN PLAYTEST: frame1 GameManager go=" + (gm != null) + " player=" + GameObject.Find(GameDefine.GAMEOBJECT_PLAYER));
        }
        if (frame >= SessionState.GetInt(K_MAX, 120)) Report(frame);
    }

    static void Report(int frame)
    {
        SessionState.SetBool(K_ARMED, false);
        var playerGo = GameObject.Find(GameDefine.GAMEOBJECT_PLAYER);
        string pos = playerGo != null ? playerGo.transform.position.ToString("F3") : "none";
        var cams = UnityEngine.Object.FindObjectsOfType<Camera>();
        string camInfo = "count=" + cams.Length;
        foreach (var c in cams) if (c.enabled && c.gameObject.activeInHierarchy) camInfo += " active=" + c.gameObject.name + "@" + c.transform.position.ToString("F2");
        Debug.Log("RAIN PLAYTEST: frame=" + frame + " playerPos=" + pos + " cameras(" + camInfo + ")");
        EditorApplication.isPlaying = false;
        EditorApplication.delayCall += () => { Debug.Log("RAIN PLAYTEST: done, exiting"); EditorApplication.Exit(0); };
    }
}
