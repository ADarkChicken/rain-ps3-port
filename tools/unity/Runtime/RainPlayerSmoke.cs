// Player smoke test (M3 acceptance "x64 build shows the scene"): with `-rainSmoke <png>` on the player command line,
// saves a screenshot after a few frames and quits; otherwise does nothing.
using System;
using UnityEngine;

public class RainPlayerSmoke : MonoBehaviour
{
    string path; int frame;

    void Awake()
    {
        var a = Environment.GetCommandLineArgs();
        for (int i = 0; i < a.Length - 1; i++) if (a[i] == "-rainSmoke") path = a[i + 1];
        if (path == null) enabled = false;
    }

    void Update()
    {
        frame++;
        if (frame == 60) ScreenCapture.CaptureScreenshot(path);
        if (frame == 70) { Debug.Log("RAIN SMOKE: frames=" + frame + " screenshot=" + path); Application.Quit(); }
    }
}
