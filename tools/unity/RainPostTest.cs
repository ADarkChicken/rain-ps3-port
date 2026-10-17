// Diagnostic: run single passes of converted post-effect shaders on a solid colour and print the centre pixel.
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
    static Texture2D Solid(Color c, int w = 64, int h = 64)
    {
        var t = new Texture2D(w, h, TextureFormat.RGBA32, false); var px = new Color[w * h];
        for (int i = 0; i < px.Length; i++) px[i] = c; t.SetPixels(px); t.Apply(); return t;
    }
    static Texture2D IdentityCurve(int rows)
    {
        var t = new Texture2D(256, rows, TextureFormat.ARGB32, false) { wrapMode = TextureWrapMode.Clamp };
        var cp = new Color[256 * rows]; for (int y = 0; y < rows; y++) for (int x = 0; x < 256; x++) cp[y * 256 + x] = new Color(x / 255f, x / 255f, x / 255f, 1f);
        t.SetPixels(cp); t.Apply(); return t;
    }

    public static void Run()
    {
        var src = Solid(new Color(0.8f, 0.2f, 0.1f, 1f));
        var a = new RenderTexture(64, 64, 0, RenderTextureFormat.ARGBFloat); var b = new RenderTexture(64, 64, 0, RenderTextureFormat.ARGBFloat);

        // RainMergePostEffect shader (E91)
        var m = new Material(Shader.Find("RainPS3/Hidden/RainMergePostEffectShader"));
        for (int i = 1; i <= 9; i++) { m.SetFloat("_SampleWeight" + i, i == 5 ? 1f : 0f); m.SetVector("_SampleOffset" + i, Vector4.zero); }
        Graphics.Blit(src, a, m, 0); Debug.Log("RAIN POSTTEST merge pass0 " + Read(a));
        Graphics.Blit(a, b, m, 1); Debug.Log("RAIN POSTTEST merge pass1 " + Read(b));
        m.SetTexture("_ColorCurveTex", IdentityCurve(4)); m.SetTexture("_BlurTex", b); m.SetTexture("_BlendTex", Texture2D.whiteTexture);
        m.SetFloat("_BlurBlendIntensity", 0f); m.SetFloat("_BlendIntensity", 0f); m.SetFloat("_Intensity", 1f);
        Graphics.Blit(src, a, m, 5); Debug.Log("RAIN POSTTEST merge pass5 identity " + Read(a));

        // RainCommonAdvancedShader (E92): identity curves, fog density 0, mask intensity 0 -> expect the source colour
        var c = new Material(Shader.Find("RainPS3/Hidden/RainCommonAdvancedShader"));
        c.SetTexture("_RgbTex", IdentityCurve(4)); c.SetTexture("_MaskTex", Texture2D.whiteTexture);
        c.SetFloat("_MaskIntensity", 0f); c.SetVector("_MaskColor", Vector4.zero);
        c.SetFloat("_GlobalFogDensity", 0f); c.SetVector("_GlobalFogY", new Vector4(-100f, 1f, 0f, 0f)); c.SetFloat("g_fDepthClip", 25f);
        c.SetVector("_GlobalFogStartDistance", new Vector4(20f, 19f, 0f, 0f)); c.SetMatrix("_FrustumCornersWS", Matrix4x4.identity);
        for (int pass = 0; pass < c.passCount; pass++) { Graphics.Blit(src, a, c, pass); Debug.Log("RAIN POSTTEST common pass" + pass + " identity " + Read(a)); }
        c.SetFloat("_MaskIntensity", 0.4f); c.SetVector("_MaskColor", new Vector4(0.07f, 0.07f, 0.11f, 0f));
        Graphics.Blit(src, a, c, 1); Debug.Log("RAIN POSTTEST common pass1 mask0.4 " + Read(a));
        c.SetFloat("_MaskIntensity", 0f); c.SetFloat("_GlobalFogDensity", 0.01f); c.SetColor("_GlobalFogColor", new Color(0.235f, 0.235f, 0.235f, 1f));
        Graphics.Blit(src, a, c, 1); Debug.Log("RAIN POSTTEST common pass1 fog0.01 " + Read(a));
        // channel-order check: curve rows R=0, G=0.5, B=1 (constant per row) -> expect output (0, 0.5, 1) if rows map R,G,B
        var rows = new Texture2D(256, 4, TextureFormat.ARGB32, false) { wrapMode = TextureWrapMode.Clamp };
        var rp = new Color[256 * 4];
        for (int x = 0; x < 256; x++) { rp[x] = new Color(0f, 0f, 0f, 1f); rp[256 + x] = new Color(0.5f, 0.5f, 0.5f, 1f); rp[512 + x] = new Color(1f, 1f, 1f, 1f); rp[768 + x] = new Color(0.25f, 0.25f, 0.25f, 1f); }
        rows.SetPixels(rp); rows.Apply();
        Shader.SetGlobalTexture("_CameraDepthTexture", Solid(new Color(0.5f, 0.5f, 0.5f, 0.5f)));
        c.SetTexture("_RgbTex", rows); c.SetFloat("_GlobalFogDensity", 0f); c.SetFloat("_MaskIntensity", 0f);
        Graphics.Blit(src, a, c, 1); Debug.Log("RAIN POSTTEST common pass1 rows(R0,G.5,B1) " + Read(a));
        m.SetTexture("_ColorCurveTex", rows); m.SetFloat("_Intensity", 1f);
        Graphics.Blit(src, a, m, 5); Debug.Log("RAIN POSTTEST merge pass5 rows(R0,G.5,B1) " + Read(a));
        c.SetTexture("_RgbTex", IdentityCurve(4));
        Graphics.Blit(src, a, c, 1); Debug.Log("RAIN POSTTEST common pass1 identity+depth0.5 " + Read(a));
    }
}
