// Applies the original Unity 3.5 lightmaps (st01 LightmapSettings, E83) at load time.
// Runtime instead of baked LightingData: 2017.4 only persists lightmaps written by its own bake.
// Lives in port_unity/Assets/RainRuntime (source of truth: DECOMP/tools/unity/Runtime).
using UnityEngine;

[ExecuteInEditMode]
public class RainLightmaps : MonoBehaviour
{
    public Texture2D[] far;    // 3.5 m_Lightmap
    public Texture2D[] near;   // 3.5 m_IndirectLightmap (dual mode); unused until the M3 unity_LightmapInd bridge
    public Renderer[] renderers;
    public int[] indices;
    public Vector4[] scaleOffsets;

    void Awake() { Apply(); }

    public void Apply()
    {
        if (far == null) return;   // Awake during AddComponent in the editor, before the importer fills the fields
        var data = new LightmapData[far.Length];
        for (int i = 0; i < far.Length; i++) data[i] = new LightmapData { lightmapColor = far[i] };
        LightmapSettings.lightmapsMode = LightmapsMode.NonDirectional;
        LightmapSettings.lightmaps = data;
        for (int i = 0; i < renderers.Length; i++)
        {
            if (renderers[i] == null) continue;
            renderers[i].lightmapIndex = indices[i];
            renderers[i].lightmapScaleOffset = scaleOffsets[i];
        }
    }
}
