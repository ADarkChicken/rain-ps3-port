// Rain's camera colour grade, reconstructed from Assembly-CSharp RainMergePostEffect (E91; decompiled OnRenderImage,
// UpdateTextures, ComputeGaussianValue, ctor). Field names and defaults are the original ones; the shader is the M2
// conversion of Hidden/RainMergePostEffectShader (pass 0 downsample, 1 gauss blur, 5 final merge).
using UnityEngine;

[ExecuteInEditMode]
[RequireComponent(typeof(Camera))]
public class RainMergePostEffect : MonoBehaviour
{
    public float m_GaussIntensity = 1f;
    float m_GaussMultiplier = 1f, m_GaussMean = 0f, m_GaussStdDev = 1f;
    public bool m_UpdateRGBCurve;
    public AnimationCurve m_RGBCurve = new AnimationCurve();
    Texture2D m_RGBCurveTex;
    readonly Color[] m_ColorTbl = new Color[3];
    public int m_SoftFocusBlendMode;
    public float m_SoftFocusBlendIntensity = 0.5f;
    public bool m_ColorVignette;
    public float m_ColorVignetteIntensity;
    public bool m_BlurVignette;
    public float m_BlurVignetteIntensity;
    bool m_UpdateTexturesOnStartup = true;
    public Texture2D m_BlendTexture;
    public float m_TextureBlendIntensity = 1f;
    public int m_TextureBlendMode;
    public float m_SaturationIntensity;
    public bool m_UseMergeShader;
    public int m_DownSizeDiv = 3;
    public Shader m_MergeShader;   // serialized so player builds include it (the original references m_MergeMaterial)
    public static void CopyParameter(RainMergePostEffect from, RainMergePostEffect to)
    {
        if (from == null || to == null) return;
        to.m_GaussIntensity = from.m_GaussIntensity; to.m_UpdateRGBCurve = from.m_UpdateRGBCurve; to.m_RGBCurve = from.m_RGBCurve;
        to.m_SoftFocusBlendMode = from.m_SoftFocusBlendMode; to.m_SoftFocusBlendIntensity = from.m_SoftFocusBlendIntensity;
        to.m_ColorVignette = from.m_ColorVignette; to.m_ColorVignetteIntensity = from.m_ColorVignetteIntensity;
        to.m_BlurVignette = from.m_BlurVignette; to.m_BlurVignetteIntensity = from.m_BlurVignetteIntensity;
        to.m_BlendTexture = from.m_BlendTexture; to.m_TextureBlendIntensity = from.m_TextureBlendIntensity; to.m_TextureBlendMode = from.m_TextureBlendMode;
        to.m_SaturationIntensity = from.m_SaturationIntensity; to.m_UseMergeShader = from.m_UseMergeShader; to.m_DownSizeDiv = from.m_DownSizeDiv;
        to.enabled = from.enabled;
    }
    Material m_MergeMaterial;
    readonly float[] m_aGaussWeight = new float[9];
    readonly Vector2[] m_aGaussOffset = new Vector2[9];

    void CreateMaterials()
    {
        if (m_RGBCurveTex == null)
            m_RGBCurveTex = new Texture2D(256, 4, TextureFormat.ARGB32, false) { hideFlags = HideFlags.DontSave, wrapMode = TextureWrapMode.Clamp };
        if (m_MergeMaterial == null)
            m_MergeMaterial = new Material(m_MergeShader != null ? m_MergeShader : Shader.Find("RainPS3/Hidden/RainMergePostEffectShader")) { hideFlags = HideFlags.DontSave };
    }

    // 256 curve samples over [0,1], clamped, written as (v,v,v,1) into rows 0..2
    void UpdateTextures()
    {
        float t = 0f;
        for (int i = 0; i < 256; i++)
        {
            float v = Mathf.Clamp(m_RGBCurve.Evaluate(t), 0f, 1f);
            m_ColorTbl[0] = m_ColorTbl[1] = m_ColorTbl[2] = new Color(v, v, v, 1f);
            m_RGBCurveTex.SetPixels(i, 0, 1, 3, m_ColorTbl);
            t += 1f / 255f;
        }
        m_RGBCurveTex.Apply();
    }

    static float ComputeGaussianValue(float x, float mean, float stdDev)
    {
        return 1f / Mathf.Sqrt(2f * Mathf.PI * stdDev * stdDev) * Mathf.Exp(-((x - mean) * (x - mean)) / (2f * stdDev * stdDev));
    }

    void OnRenderImage(RenderTexture source, RenderTexture destination)
    {
        CreateMaterials();
        if (m_UpdateRGBCurve || m_UpdateTexturesOnStartup) { UpdateTextures(); m_UpdateTexturesOnStartup = false; }
        m_GaussIntensity = Mathf.Clamp(m_GaussIntensity, 0f, 6f);
        if (!m_UseMergeShader)
        {   // shortcut: the separate-material path (m_UseMergeShader = false) is not reconstructed; Stage 1 uses the merge path
            Graphics.Blit(source, destination);
            return;
        }
        var full = RenderTexture.GetTemporary(source.width, source.height);
        var a = RenderTexture.GetTemporary(source.width / m_DownSizeDiv, source.height / m_DownSizeDiv);
        var b = RenderTexture.GetTemporary(source.width / m_DownSizeDiv, source.height / m_DownSizeDiv);
        Graphics.Blit(source, a, m_MergeMaterial, 0);

        float sum = 0f;
        for (int i = 0; i < 9; i++) { m_aGaussWeight[i] = m_GaussMultiplier * ComputeGaussianValue((i - 4f) / 4f, m_GaussMean, m_GaussStdDev); sum += m_aGaussWeight[i]; }
        for (int i = 0; i < 9; i++) { m_aGaussWeight[i] /= sum; m_MergeMaterial.SetFloat("_SampleWeight" + (i + 1), m_aGaussWeight[i]); }

        for (int i = 0; i < 9; i++) { m_aGaussOffset[i] = new Vector2(1f / a.width * m_GaussIntensity * (i - 4) * 0.5f, 0f); m_MergeMaterial.SetVector("_SampleOffset" + (i + 1), m_aGaussOffset[i]); }
        Graphics.Blit(a, b, m_MergeMaterial, 1);
        for (int i = 0; i < 9; i++) { m_aGaussOffset[i] = new Vector2(0f, 1f / a.height * m_GaussIntensity * (i - 4) * 0.5f); m_MergeMaterial.SetVector("_SampleOffset" + (i + 1), m_aGaussOffset[i]); }
        Graphics.Blit(b, a, m_MergeMaterial, 1);

        m_MergeMaterial.SetTexture("_ColorCurveTex", m_RGBCurveTex);
        m_MergeMaterial.SetTexture("_BlurTex", a);
        m_MergeMaterial.SetFloat("_BlurBlendIntensity", m_SoftFocusBlendIntensity);
        m_MergeMaterial.SetFloat("_ColorVignetteIntensity", m_ColorVignette ? m_ColorVignetteIntensity : 0f);
        m_MergeMaterial.SetFloat("_BlurVignetteIntensity", m_BlurVignette ? m_BlurVignetteIntensity : 0f);
        m_MergeMaterial.SetTexture("_BlendTex", m_BlendTexture);
        m_MergeMaterial.SetFloat("_BlendIntensity", m_TextureBlendIntensity);
        float up = Mathf.Min(1f, 1f + m_SaturationIntensity), down = Mathf.Min(1f, 1f - m_SaturationIntensity);
        m_MergeMaterial.SetFloat("_Intensity", down <= 0f ? 1f : up / down);
        Graphics.Blit(source, destination, m_MergeMaterial, 5);
        RenderTexture.ReleaseTemporary(full); RenderTexture.ReleaseTemporary(a); RenderTexture.ReleaseTemporary(b);
    }

    void OnDisable()
    {
        if (m_MergeMaterial != null) DestroyImmediate(m_MergeMaterial);
        if (m_RGBCurveTex != null) DestroyImmediate(m_RGBCurveTex);
    }
}
