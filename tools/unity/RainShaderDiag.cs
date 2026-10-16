// Print Unity's internal compile messages for RainPS3/* shaders (ShaderUtil internals via reflection, Unity 2017.4).
//   Unity.exe -batchmode -quit -projectPath <proj> -executeMethod RainShaderDiag.Run
using System;
using System.Reflection;
using UnityEditor;
using UnityEngine;

public static class RainShaderDiag
{
    public static void Run()
    {
        var su = typeof(ShaderUtil);
        var getCount = su.GetMethod("GetShaderMessageCount", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
        var getMsgs = su.GetMethod("GetShaderMessages", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public, null, new[] { typeof(Shader) }, null);
        var hasErr = su.GetMethod("ShaderHasError", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
        int shown = 0, withErr = 0, total = 0;
        foreach (var guid in AssetDatabase.FindAssets("t:Shader", new[] { "Assets/RainShaders" }))
        {
            var path = AssetDatabase.GUIDToAssetPath(guid); var sh = AssetDatabase.LoadAssetAtPath<Shader>(path); total++;
            bool err = hasErr != null && (bool)hasErr.Invoke(null, new object[] { sh });
            if (err) withErr++;
            if (shown < 6 && (err || !sh.isSupported))
            {
                shown++;
                Debug.Log("RAIN DIAG " + path + " supported=" + sh.isSupported + " hasError=" + err +
                          " messages=" + (getCount != null ? getCount.Invoke(null, new object[] { sh }) : "?"));
                if (getMsgs != null)
                {
                    var arr = getMsgs.Invoke(null, new object[] { sh }) as Array;
                    if (arr != null) foreach (var m in arr)
                    {
                        var t = m.GetType();
                        Debug.Log("RAIN DIAG   " + t.GetField("message").GetValue(m) + " | line " + t.GetField("line").GetValue(m) +
                                  " | " + t.GetField("platform").GetValue(m));
                    }
                }
            }
        }
        Debug.Log("RAIN DIAG total=" + total + " withError=" + withErr);
    }
}
