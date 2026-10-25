// M6 compile-only placeholders. These are NOT reconstructed game logic -- they are empty stand-ins for types that
// live outside Assembly-CSharp in the original game (Unity Standard Assets image effects, the Shroud cloth plugin,
// the PS3 SGX audio / system-utility native wrapper classes, and the cutscene system) so that the reconstructed
// Assembly-CSharp scripts (which only *reference* these types, never define them) compile in this project. None of
// them are wired to the pipeline yet; replace with real implementations when that subsystem's track is approved
// (image effects / M6 rain-and-camera polish, Shroud -> M8ish cloth, SGX audio -> M7 platform layer, cutscenes -> M8).
using UnityEngine;

public class PostEffectsBase : MonoBehaviour { }
public class DepthOfFieldSimple : MonoBehaviour { }
public class GlobalFog : MonoBehaviour { }
public class MaskEffect : MonoBehaviour { }
public class DarkenEffect : MonoBehaviour { }
public class ColorCorrectionCurves : MonoBehaviour { }
public class GlowEffect : MonoBehaviour { }
public class ShroudInstance { }
public enum DarkenType { None, Low, Mid, High }
public class CutScene { }
public class CutSceneData { }

namespace UnityEngine
{
    public class SGXSource { }
    public class SGXStream { }
    public class SGXData { }
    public class WavClip { }
    public enum PS3ReturnCode { OK = 0 }
    public class PS3SystemUtility { public delegate void SystemNotificationDelegate(int code); }
}
