// Rain's main camera colour curves + global/height fog + mask, reconstructed from Assembly-UnityScript-firstpass
// RainCommonPostEffect (E92; decompiled OnRenderImage, UpdateParameters, CreateMaterials, CustomGraphicsBlit, OnEnable).
// It is Unity 3.x's ColorCorrectionCurves (depth variant) merged with GlobalFog; shader = M2 conversion of
// Hidden/RainCommonAdvancedShader (pass 0 with depth correction, pass 1 without), FXAA = Hidden/FXAA2Shader.
using UnityEngine;

[ExecuteInEditMode]
[RequireComponent(typeof(Camera))]
public class RainCommonPostEffect : MonoBehaviour
{
    public AnimationCurve redChannel = new AnimationCurve(), greenChannel = new AnimationCurve(), blueChannel = new AnimationCurve();
    public bool useDepthCorrection;
    public AnimationCurve zCurve = new AnimationCurve(), depthRedChannel = new AnimationCurve(), depthGreenChannel = new AnimationCurve(), depthBlueChannel = new AnimationCurve();
    public Texture2D maskTexture;
    public Color maskColor;
    public float maskIntensity;
    public float globalFogStartDistance, globalFogDensity, globalFogHeightScale, globalFogHeight, globalFogHeightDensity, globalFogFarClip;
    public Color globalFogColor, globalFogHeightColor;
    public int m_FXAASampleCount;
    public bool m_SunShaftEnable;   // shortcut: sun shafts (RenderSunShaft) and the shine pass are not reconstructed yet (E92)
    public Shader ccDepthShader, fxaaShader;   // serialized so player builds include them (the original references materials)
    Material ccDepthMaterial, m_FXAAmaterial;
    Texture2D rgbChannelTex, rgbDepthChannelTex, zCurveTex;
    bool updateTexturesOnStartup = true;

    void OnEnable() { GetComponent<Camera>().depthTextureMode |= DepthTextureMode.Depth; }

    void CreateMaterials()
    {
        if (ccDepthMaterial == null) ccDepthMaterial = new Material(ccDepthShader != null ? ccDepthShader : Shader.Find("RainPS3/Hidden/RainCommonAdvancedShader")) { hideFlags = HideFlags.DontSave };
        if (m_FXAAmaterial == null) m_FXAAmaterial = new Material(fxaaShader != null ? fxaaShader : Shader.Find("RainPS3/Hidden/FXAA2Shader")) { hideFlags = HideFlags.DontSave };
        if (rgbChannelTex == null) rgbChannelTex = NewTex(4);
        if (rgbDepthChannelTex == null) rgbDepthChannelTex = NewTex(4);
        if (zCurveTex == null) zCurveTex = NewTex(1);
    }
    static Texture2D NewTex(int h) { return new Texture2D(256, h, TextureFormat.ARGB32, false) { hideFlags = HideFlags.DontSave, wrapMode = TextureWrapMode.Clamp }; }

    void UpdateParameters()
    {
        for (float i = 0f; i <= 1f; i += 1f / 255f)
        {
            int x = (int)Mathf.Floor(i * 255f);
            float r = Mathf.Clamp(redChannel.Evaluate(i), 0f, 1f), g = Mathf.Clamp(greenChannel.Evaluate(i), 0f, 1f), b = Mathf.Clamp(blueChannel.Evaluate(i), 0f, 1f);
            rgbChannelTex.SetPixel(x, 0, new Color(r, r, r)); rgbChannelTex.SetPixel(x, 1, new Color(g, g, g)); rgbChannelTex.SetPixel(x, 2, new Color(b, b, b));
            float z = Mathf.Clamp(zCurve.Evaluate(i), 0f, 1f); zCurveTex.SetPixel(x, 0, new Color(z, z, z));
            r = Mathf.Clamp(depthRedChannel.Evaluate(i), 0f, 1f); g = Mathf.Clamp(depthGreenChannel.Evaluate(i), 0f, 1f); b = Mathf.Clamp(depthBlueChannel.Evaluate(i), 0f, 1f);
            rgbDepthChannelTex.SetPixel(x, 0, new Color(r, r, r)); rgbDepthChannelTex.SetPixel(x, 1, new Color(g, g, g)); rgbDepthChannelTex.SetPixel(x, 2, new Color(b, b, b));
        }
        rgbChannelTex.Apply(); rgbDepthChannelTex.Apply(); zCurveTex.Apply();
    }

    void OnRenderImage(RenderTexture source, RenderTexture destination)
    {
        CreateMaterials();
        if (updateTexturesOnStartup) { UpdateParameters(); updateTexturesOnStartup = false; }
        ccDepthMaterial.SetTexture("_RgbTex", rgbChannelTex);
        if (useDepthCorrection) { ccDepthMaterial.SetTexture("_ZCurve", zCurveTex); ccDepthMaterial.SetTexture("_RgbDepthTex", rgbDepthChannelTex); }

        var cam = GetComponent<Camera>(); var tr = cam.transform;
        float fovWHalf = cam.fieldOfView * 0.5f, t = Mathf.Tan(fovWHalf * Mathf.Deg2Rad);
        Vector3 toRight = tr.right * cam.nearClipPlane * t * cam.aspect, toTop = tr.up * cam.nearClipPlane * t, fwd = tr.forward * cam.nearClipPlane;
        Vector3 topLeft = fwd - toRight + toTop;
        float camScale = topLeft.magnitude * cam.farClipPlane / cam.nearClipPlane;
        topLeft = topLeft.normalized * camScale;
        Vector3 topRight = (fwd + toRight + toTop).normalized * camScale;
        Vector3 bottomRight = (fwd + toRight - toTop).normalized * camScale;
        Vector3 bottomLeft = (fwd - toRight - toTop).normalized * camScale;
        var corners = Matrix4x4.identity;
        corners.SetRow(0, topLeft); corners.SetRow(1, topRight); corners.SetRow(2, bottomRight); corners.SetRow(3, bottomLeft);

        ccDepthMaterial.SetVector("_GlobalFogStartDistance", new Vector4(cam.farClipPlane / globalFogStartDistance, cam.farClipPlane - globalFogStartDistance, 0f, 0f));
        ccDepthMaterial.SetFloat("_GlobalFogDensity", globalFogDensity * 0.01f);
        ccDepthMaterial.SetColor("_GlobalFogColor", globalFogColor);
        ccDepthMaterial.SetVector("_GlobalFogY", new Vector4(globalFogHeight, 1f / globalFogHeightScale, globalFogHeightDensity, globalFogHeightDensity * globalFogHeightDensity));
        ccDepthMaterial.SetColor("_GlobalFogHeightColor", globalFogHeightColor);
        ccDepthMaterial.SetMatrix("_FrustumCornersWS", corners);
        ccDepthMaterial.SetVector("_CameraWS", tr.position);
        ccDepthMaterial.SetFloat("g_fDepthClip", globalFogFarClip);
        ccDepthMaterial.SetTexture("_MaskTex", maskTexture);
        ccDepthMaterial.SetVector("_MaskColor", maskColor);
        ccDepthMaterial.SetFloat("_MaskIntensity", maskIntensity);

        int pass = useDepthCorrection ? 0 : 1;
        if (m_FXAASampleCount < 1) { CustomGraphicsBlit(source, destination, ccDepthMaterial, pass); return; }
        var tmp = RenderTexture.GetTemporary(source.width, source.height, 0);
        CustomGraphicsBlit(source, tmp, ccDepthMaterial, pass);
        if (m_FXAASampleCount == 1) Graphics.Blit(tmp, destination, m_FXAAmaterial);
        else { Graphics.Blit(tmp, source, m_FXAAmaterial); Graphics.Blit(source, destination, m_FXAAmaterial); }
        RenderTexture.ReleaseTemporary(tmp);
    }

    // full-screen quad whose vertex z carries the frustum-corner row index (0 top-left .. 3 bottom-left)
    static void CustomGraphicsBlit(RenderTexture source, RenderTexture dest, Material fxMaterial, int passNr)
    {
        RenderTexture.active = dest;
        fxMaterial.SetTexture("_MainTex", source);
        GL.PushMatrix(); GL.LoadOrtho(); fxMaterial.SetPass(passNr);
        GL.Begin(GL.QUADS);
        GL.MultiTexCoord2(0, 0f, 0f); GL.Vertex3(0f, 0f, 3f);
        GL.MultiTexCoord2(0, 1f, 0f); GL.Vertex3(1f, 0f, 2f);
        GL.MultiTexCoord2(0, 1f, 1f); GL.Vertex3(1f, 1f, 1f);
        GL.MultiTexCoord2(0, 0f, 1f); GL.Vertex3(0f, 1f, 0f);
        GL.End(); GL.PopMatrix();
    }

    void OnDisable()
    {
        foreach (Object o in new Object[] { ccDepthMaterial, m_FXAAmaterial, rgbChannelTex, rgbDepthChannelTex, zCurveTex }) if (o != null) DestroyImmediate(o);
    }
}
