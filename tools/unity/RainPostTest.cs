// Diagnostic: run single passes of the converted Hidden/RainMergePostEffectShader on a solid colour and print the result.
//   Unity.exe -batchmode -quit -projectPath <proj> -executeMethod RainPostTest.Run
using UnityEngine;

public static class RainPostTest
{
    static Color Read(RenderTexture rt)
    {
        RenderTexture.active = rt; var t = new Texture2D(rt.width, rt.height, TextureFormat.RGBAFloat, false);
        t.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0); t.Apply(); RenderTexture.active = null;
        return t.GetPixel(rt.width / 2, rt.height / 2);
    }

    public static void Run()
    {
        var m = new Material(Shader.Find("RainPS3/Hidden/RainMergePostEffectShader"));
        var src = new Texture2D(64, 64, TextureFormat.RGBA32, false);
        var px = new Color[64 * 64]; for (int i = 0; i < px.Length; i++) px[i] = new Color(0.8f, 0.2f, 0.1f, 1f);
        src.SetPixels(px); src.Apply();
        var a = new RenderTexture(64, 64, 0, RenderTextureFormat.ARGBFloat); var b = new RenderTexture(64, 64, 0, RenderTextureFormat.ARGBFloat);
        for (int i = 1; i <= 9; i++) { m.SetFloat("_SampleWeight" + i, i == 5 ? 1f : 0f); m.SetVector("_SampleOffset" + i, Vector4.zero); }
        Graphics.Blit(src, a, m, 0); Debug.Log("RAIN POSTTEST pass0 " + Read(a));
        Graphics.Blit(a, b, m, 1); Debug.Log("RAIN POSTTEST pass1 " + Read(b));
        var curve = new Texture2D(256, 4, TextureFormat.ARGB32, false) { wrapMode = TextureWrapMode.Clamp };
        var cp = new Color[256 * 4]; for (int y = 0; y < 4; y++) for (int x = 0; x < 256; x++) cp[y * 256 + x] = new Color(x / 255f, x / 255f, x / 255f, 1f);
        curve.SetPixels(cp); curve.Apply();   // identity curve
        m.SetTexture("_ColorCurveTex", curve); m.SetTexture("_BlurTex", b); m.SetTexture("_BlendTex", Texture2D.whiteTexture);
        foreach (var bb in new[] { 0f, 0.3f })
            foreach (var bl in new[] { 0f, 0.3f })
                foreach (var it in new[] { 1f, 0.7f })
                {
                    m.SetFloat("_BlurBlendIntensity", bb); m.SetFloat("_BlendIntensity", bl); m.SetFloat("_Intensity", it);
                    m.SetFloat("_ColorVignetteIntensity", 0f); m.SetFloat("_BlurVignetteIntensity", 0f);
                    Graphics.Blit(src, a, m, 5);
                    Debug.Log(string.Format("RAIN POSTTEST pass5 blur={0} blend={1} intensity={2} -> {3}", bb, bl, it, Read(a)));
                }
    }
}
