// Feeds the 3.5 SH lighting (rain_SH*, see rsx2unity_shader.py BRIDGED) from the original LightProbes (E85).
// 2017.4 cannot rebuild a probe set from script, so interpolation is done here: tetrahedron barycentrics, as 3.5 did.
// Renderers without probes get the 3.5 ambient-only SH (L0 = ambient) as the global value.
using UnityEngine;

[ExecuteInEditMode]
public class RainLightProbes : MonoBehaviour
{
    public float[] positions;      // 3 per probe
    public float[] coefficients;   // 27 per probe: 9 SH coefficients x RGB
    public int[] tetrahedra;       // 4 probe indices per tetrahedron, -1 = outer cell
    public Renderer[] renderers;
    public Transform[] anchors;    // optional lightProbeAnchor per renderer
    public Color ambient;

    void Awake() { Apply(); }

    public void Apply()
    {
        if (positions == null) return;   // Awake during AddComponent in the editor, before the importer fills the fields
        float[] amb = new float[27]; amb[0] = ambient.r / C0; amb[1] = ambient.g / C0; amb[2] = ambient.b / C0;
        var v = Constants(amb);
        for (int k = 0; k < 7; k++) Shader.SetGlobalVector(Names[k], v[k]);
        var mpb = new MaterialPropertyBlock();
        for (int i = 0; i < renderers.Length; i++)
        {
            if (renderers[i] == null) continue;
            Vector3 p = anchors[i] != null ? anchors[i].position : renderers[i].bounds.center;
            v = Constants(Interpolate(p));
            renderers[i].GetPropertyBlock(mpb);
            for (int k = 0; k < 7; k++) mpb.SetVector(Names[k], v[k]);
            renderers[i].SetPropertyBlock(mpb);
        }
    }

    static readonly string[] Names = { "rain_SHAr", "rain_SHAg", "rain_SHAb", "rain_SHBr", "rain_SHBg", "rain_SHBb", "rain_SHC" };
    const float C0 = 0.2820948f, C1 = 0.3257350f, C2 = 0.2731371f, C3 = 0.0788479f, C4 = 0.1365686f;

    // SH9 (D3DX basis order/signs) -> ShadeSH9 constants, irradiance convolution folded in (Sloan, "Stupid SH Tricks").
    // Inferred for 3.5 (E85): to be confirmed by the golden images.
    public static Vector4[] Constants(float[] sh)
    {
        var o = new Vector4[7];
        for (int c = 0; c < 3; c++)
        {
            System.Func<int, float> s = i => sh[i * 3 + c];
            o[c] = new Vector4(-C1 * s(3), -C1 * s(1), C1 * s(2), C0 * s(0) - C3 * s(6));
            o[3 + c] = new Vector4(C2 * s(4), -C2 * s(5), 3 * C3 * s(6), -C2 * s(7));
        }
        o[6] = new Vector4(C4 * sh[24], C4 * sh[25], C4 * sh[26], 1);
        return o;
    }

    public float[] Interpolate(Vector3 p)
    {
        var r = new float[27];
        for (int t = 0; t + 3 < tetrahedra.Length; t += 4)
        {
            int a = tetrahedra[t], b = tetrahedra[t + 1], c = tetrahedra[t + 2], d = tetrahedra[t + 3];
            if (a < 0 || b < 0 || c < 0 || d < 0) continue;
            Vector3 pd = P(d), e0 = P(a) - pd, e1 = P(b) - pd, e2 = P(c) - pd, q = p - pd;
            float det = Vector3.Dot(e0, Vector3.Cross(e1, e2));
            if (Mathf.Abs(det) < 1e-12f) continue;
            float w0 = Vector3.Dot(q, Vector3.Cross(e1, e2)) / det, w1 = Vector3.Dot(e0, Vector3.Cross(q, e2)) / det,
                  w2 = Vector3.Dot(e0, Vector3.Cross(e1, q)) / det, w3 = 1 - w0 - w1 - w2;
            const float eps = -1e-4f;
            if (w0 < eps || w1 < eps || w2 < eps || w3 < eps) continue;
            for (int k = 0; k < 27; k++)
                r[k] = w0 * coefficients[a * 27 + k] + w1 * coefficients[b * 27 + k] + w2 * coefficients[c * 27 + k] + w3 * coefficients[d * 27 + k];
            return r;
        }
        // shortcut: outside the inner hull we take the nearest probe instead of 3.5's hull-ray extrapolation; upgrade if golden images differ at the level edges
        int best = 0; float bd = float.MaxValue;
        for (int i = 0; i * 3 < positions.Length; i++) { float dd = (P(i) - p).sqrMagnitude; if (dd < bd) { bd = dd; best = i; } }
        System.Array.Copy(coefficients, best * 27, r, 0, 27);
        return r;
    }

    Vector3 P(int i) { return new Vector3(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]); }

    // Self-check (run by the importer): interpolating at a probe position must return that probe's coefficients.
    public string SelfTest()
    {
        int bad = 0, n = positions.Length / 3;
        for (int i = 0; i < n; i++)
        {
            var r = Interpolate(P(i));
            for (int k = 0; k < 27; k++) if (Mathf.Abs(r[k] - coefficients[i * 27 + k]) > 1e-3f) { bad++; break; }
        }
        return string.Format("probes={0} selftest_mismatch={1}", n, bad);
    }
}
