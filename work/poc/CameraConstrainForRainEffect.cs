// Reconstructed from Rain (NPUA80719) Assembly-CSharp AOT code. Phase 3 PoC.
// Sources: IL metadata (names/types/field order) + Ghidra pseudocode/asm of the Mono AOT PPC64 code
// (work/poc/CameraConstrainForRainEffect.decomp.txt). Field offsets verified: 0x10..0x20 = IL field order (E30).
// Confidence: every statement below is observed in asm unless marked INFERENCE.
using UnityEngine;

public class CameraConstrainForRainEffect : MonoBehaviour
{
    private RainManager m_Rain;               // +0x10
    private Camera m_targetCamera;            // +0x14
    private GameObject m_targetCameraObj;     // +0x18
    private Transform m_Tr;                   // +0x1C
    private Camera m_Cam;                     // +0x20

    // 0x06000468 @ 0x56A80: isPlaying -> disable + null all five fields (stw 0 to 0x10..0x20).
    public void Release()
    {
        if (Application.isPlaying)
        {
            enabled = false;
            m_Rain = null;
            m_targetCamera = null;
            m_targetCameraObj = null;
            m_Tr = null;
            m_Cam = null;
        }
    }

    // 0x06000469 @ 0x56B10
    private void OnDestroy() { Release(); }

    // 0x0600046A @ 0x56B60 / 0x0600046B @ 0x56BB0 / 0x0600046C @ 0x56C00: all call init().
    private void Start() { init(); }
    private void Awake() { init(); }
    private void OnEnable() { init(); }

    // 0x0600046D @ 0x56C50. Unity Object implicit bool == op_Implicit calls in asm.
    private void init()
    {
        if (!m_Tr) m_Tr = transform;
        if (!m_Cam) m_Cam = camera;
        if (!m_Rain) m_Rain = RainManager.GetInstance();
        if (m_Rain)
        {
            m_targetCameraObj = m_Rain.getMainCameraObject();
            m_targetCamera = m_Rain.getMainCamera();
        }
        else
        {
            m_targetCameraObj = null;
            m_targetCamera = null;
        }
    }

    // 0x0600046E @ 0x56D40: copies main camera's WORLD pose into this object's LOCAL pose (observed:
    // get_position -> set_localPosition, get_rotation -> set_localRotation), then mirrors projection params.
    private void OnPreCull()
    {
        init();
        if (m_targetCameraObj)
        {
            Transform t = m_targetCameraObj.transform;
            m_Tr.localPosition = t.position;
            m_Tr.localRotation = t.rotation;
            m_Tr.localScale = t.localScale;
        }
        if (m_targetCamera)
        {
            m_Cam.aspect = m_targetCamera.aspect;
            m_Cam.nearClipPlane = m_targetCamera.nearClipPlane;
            m_Cam.farClipPlane = m_targetCamera.farClipPlane;
            m_Cam.fieldOfView = m_targetCamera.fieldOfView;
        }
    }
}
