"""M6 skeleton regeneration: rebuild work/skeleton/Assembly-CSharp.remainder.cs (comment out every type with a real
file in Assets/RainRuntime/Recon) and work/skeleton/_crosstier_stubs.cs (Rain.Firstpass.dll types referenced by
critical-path code), then apply the small set of hand-verified method-body fixups documented in
references/m6-notes.md (PROJECT_STATUS.md 2026-10-26): a handful of deferred types' GetInstance()/PS3 hardware
hint methods are called unconditionally by critical-path code and must not throw, but promoting their whole class
would drag in out-of-scope subsystem logic. Run from DECOMP/: tools/.venv/Scripts/python -I tools/m6_skeleton_fixups.py
Then `cp work/skeleton/Assembly-CSharp.remainder.cs work/skeleton/_crosstier_stubs.cs` destinations into the Unity
project as done at the end of this script (local project, not committed)."""
import os, re, sys, shutil, subprocess

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lift_compile

RECON_DIR = r"G:\Decomp\Rain\port_unity\Assets\RainRuntime\Recon"
SKEL_PROJECT_PATH = r"G:\Decomp\Rain\port_unity\Assets\RainRuntime\_Skeleton.cs"
STUBS_PROJECT_PATH = r"G:\Decomp\Rain\port_unity\Assets\RainRuntime\_RainEngineStubs.cs"
FIRSTPASS_DLL = r"G:\Decomp\Rain\_tools\m0_host_compile\Library\ScriptAssemblies\Rain.Firstpass.dll"

# Types with a real hand-written file OUTSIDE Recon/ (M3 scripts) that must also be excluded from the skeleton,
# else you get a CS0260 duplicate-partial-type error (they're not discoverable by scanning Recon/ alone).
EXTRA_REAL_NAMES = {"RainCommonPostEffect", "RainMergePostEffect"}

# Deferred types' GetInstance() (or equivalent single accessor) that critical-path code calls unconditionally --
# verified against the type's already-reconstructed work/recon/<Type>.cs. Fix ONLY this one method, not the whole
# class, so the subsystem stays genuinely deferred (every other member still throws if ever actually called).
METHOD_FIXUPS = {
    ("BGMManager", "GetInstance"): "return m_self;",
    ("BlackBeltManager", "GetInstance"): "return m_self;",
    ("MenuManager", "GetInstance"): "return m_inst;",
    ("GameSoundManager", "GetInstance"): "return m_inst;",
    ("WatchPointManager", "GetInstance"): "return m_self;",
    ("TargetManager", "GetInstance"): "return m_self;",
    ("DangerManager", "GetInstance"): "return m_self;",
    ("TutorialTextManager", "GetInstance"): "return m_self;",
    ("GimmickManager", "GetInstance"): (
        "if (_inst == null) _inst = global::UnityEngine.Object.FindObjectOfType(typeof(global::GimmickManager)) "
        "as global::GimmickManager; return _inst;"
    ),
    ("EffectManager", "GetInstance"): (
        "if (!s_hasSelf) { s_self = global::UnityEngine.Object.FindObjectOfType(typeof(global::EffectManager)) "
        "as global::EffectManager; s_hasSelf = s_self != null; } return s_self;"
    ),
}

# Single methods of deferred types grafted verbatim from the type's reconstructed work/recon/<Type>.cs (same rationale
# as METHOD_FIXUPS, any signature): static helpers that critical-path code calls unconditionally and that are
# self-contained / null-guarded on their own subsystem instance, so the rest of the class can stay a stub.
# (type file, exact method header as written in BOTH the recon file and the skeleton)
GRAFTS = [
    ("CutSceneManager", "public static bool IsPlaying()"),
    ("EffectManager", "public static bool DeleteEffect(global::EffectObject tgt)"),
    ("EffectManager", "public static void RemoveEffect(global::UnityEngine.GameObject go)"),
    ("AIEvent", "public static void Release(ref global::AIEvent[] tbl)"),
    ("AISensor", "public static void Release(ref global::AISensor ais)"),
    ("DynamicObject", "public static void SetTotal(int max)"),
    ("DynamicObject", "public static void Release(ref global::DynamicObject.RestoreParam[] tbl)"),
    ("Gimmick_Collapse", "public static void CheckCollapseCollider(global::UnityEngine.GameObject[] tbl, global::UnityEngine.GameObject goBase)"),
    ("SoundParam", "public static void UpdateAllCategoryVolume()"),
    ("SoundPackManager", "public static void ReleaseAll()"),
    ("EffectManager", "public static void ChangeCameraCallback()"),
    ("AIEventPadTrigger", "public static void Release(ref global::AIEventPadTrigger[] tbl)"),
    ("DynamicObject", "public static void CheckDeactiveTime()"),
    ("AISensor", "public AISensor(global::AIParameter param)"),   # CharacterPlayer builds one; body is a no-op while TargetManager is absent
]
# static property getters, same idea: (type, property header up to the name) -> getter body
PROP_GRAFTS = {
    ("MenuManager", "public static global::UICamera uiCamera"): "return GetInstance() != null ? GetInstance().m_uiCamera : null;",
}


def _brace_body(src, start):
    """Text of the {...} block starting at the first '{' at/after `start` (inclusive braces)."""
    i = src.index("{", start); depth = 0
    for j in range(i, len(src)):
        if src[j] == "{": depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0: return src[i:j + 1]
    raise ValueError("unbalanced")


def apply_grafts(skel, real_names=()):
    stub = "{ throw new global::System.NotImplementedException(); }"
    for typename, header in GRAFTS:
        if typename in real_names: continue   # promoted since: the whole real file is compiled
        recon = open(os.path.join(ROOT, "work", "recon", typename + ".cs"), encoding="utf-8").read().replace("\r\n", "\n")
        assert recon.count(header) == 1, f"{typename}: recon header matched {recon.count(header)}x: {header}"
        body = _brace_body(recon, recon.index(header))
        tpos = skel.index(f"public partial class {typename}")
        pos = skel.index(header + " " + stub, tpos)
        skel = skel[:pos] + header + "\n    " + body + skel[pos + len(header) + 1 + len(stub):]
    for (typename, header), body in PROP_GRAFTS.items():
        tpos = skel.index(f"public partial class {typename}")
        old = header + " { get " + stub + " }"; pos = skel.index(old, tpos)
        skel = skel[:pos] + header + " { get { " + body + " } }" + skel[pos + len(old):]
    return skel


# PS3Info: pure hardware memory-residency/debug hints with no Windows equivalent -- safe real no-ops, not throws
# (critical-path code, e.g. GameManager.Start()'s first line, calls these unconditionally).
PS3INFO_NOOPS = {
    "DBOutput": "{ }", "MemoryResidenceVertex": "{ }", "MemoryResidenceDArray": "{ }",
    "MemoryResidenceInvoke": "{ }", "MemoryResidenceShroud": "{ }", "SnapInc": "{ }",
    "CurrentMemoryLogout": "{ }", "GetRainCustomVersion": "{ return 0; }",
    "IsAsyncLoading": "{ return false; }", "SetLoadingScene": "{ }",
    # PS3SystemUtility: system setting "enter button" (0 = circle, 1 = cross). NPUA80719 is the US release -> cross.
    # Platform-layer choice for the port, not reconstructed code (GameInput.Start reads it unconditionally).
    "GetEnterButtonAssignment": "{ return 1; }",
}

CROSSTIER_ONLY = ("PostEffectsBase,GlobalFog,MaskEffect,GlowEffect,DepthOfFieldSimple,DarkenEffect,"
                   "ColorCorrectionCurves,ColorCorrectionMode,DofSimpleQualitySetting,DarkenType,ShroudInstance,"
                   "ShroudObjectManager,CutScene,CutSceneData,CutSceneClip,AudioClip,AudioSource,PS3Info,"
                   "PS3SystemUtility,SGXBody,SGXHeader,SGXSource,SGXStream,SGXData,SGXSettings,WavClip,PS3ReturnCode")

STUBS_HEADER = """// M6 compile-only stubs for types that live outside Assembly-CSharp in the original game (Unity Standard
// Assets image effects, the Shroud cloth plugin, PS3 SGX audio / system-utility wrappers, cutscene system,
// and a few game-specific audio shim classes Rain.Firstpass.dll defines itself in the global namespace --
// AudioClip/AudioSource/CutSceneClip here are NOT UnityEngine's, they are the game's own PS3 platform wrappers).
// Generated from the real Rain.Firstpass.dll IL metadata via tools/skeleton_gen.py --only (member signatures are
// real; non-parameterless-ctor method bodies are NotImplementedException stubs, same convention as
// work/skeleton/Assembly-CSharp.cs -- NOT reconstructed game logic. Parameterless ctors are a real no-op `{ }`,
// never a throw: they can run implicitly (AddComponent, array/field construction, Activator.CreateInstance) from
// code we don't control, so throwing there would crash an unrelated caller instead of just losing fidelity).
// PS3Info's methods are ALSO hand-fixed to real no-ops (not throws): they're pure PS3 hardware memory-residency/
// debug hints with no Windows equivalent, called unconditionally from critical-path code (e.g. GameManager.Start())
// as PS3->PC engine-adaptation boilerplate -- a no-op is the CORRECT behavior here, not a fidelity loss.
// Regenerated by tools/m6_skeleton_fixups.py -- edit the fixup dicts there, don't hand-edit this file.
"""
PRAGMA = "#pragma warning disable 0108, 0114, 0414, 0169, 0649, 0067, 0659, 0661, 0660, 0628, 0109\n"


def build_assembly_csharp_remainder():
    skel = open(os.path.join(ROOT, "work", "skeleton", "Assembly-CSharp.cs"), encoding="utf-8").read()
    files = [os.path.join(RECON_DIR, f) for f in os.listdir(RECON_DIR) if f.endswith(".cs")]
    recon = {f: open(f, encoding="utf-8").read() for f in files}
    names = {n for s in recon.values() for n, _, _ in lift_compile.top_level_types(s)} | EXTRA_REAL_NAMES
    for n, st, en in sorted(lift_compile.top_level_types(skel), key=lambda t: -t[1]):
        if n in names:
            skel = skel[:st] + f"/* {n}: reconstructed */" + skel[en:]
    for (typename, methname), body in METHOD_FIXUPS.items():
        if typename in names: continue   # promoted since: the whole real file is compiled
        pat = re.compile(rf"((?:public|private|internal|protected) static global::{typename} {methname}\(\)[^;{{]*\{{)[^}}]*(\}})")
        skel, n = pat.subn(lambda m: m.group(1) + " " + body + " " + m.group(2), skel)
        assert n == 1, f"{typename}.{methname} fixup matched {n} times, expected 1"
    skel = apply_grafts(skel, names)
    out_path = os.path.join(ROOT, "work", "skeleton", "Assembly-CSharp.remainder.cs")
    open(out_path, "w", encoding="utf-8", newline="").write(skel)
    shutil.copy(out_path, SKEL_PROJECT_PATH)
    print(f"{len(files)} real files, {len(names)} excluded-from-skeleton names, {len(skel)} chars -> {SKEL_PROJECT_PATH}")


def build_crosstier_stubs():
    out_path = os.path.join(ROOT, "work", "skeleton", "_crosstier_stubs.cs")
    subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "skeleton_gen.py"),
                     FIRSTPASS_DLL, out_path, "--only", CROSSTIER_ONLY], check=True)
    content = open(out_path, encoding="utf-8").read()
    for meth, body in PS3INFO_NOOPS.items():
        pat = re.compile(rf"(public static [\w.:<>\[\]]+ {meth}\([^)]*\))\s*\{{[^}}]*\}}")
        content, n = pat.subn(lambda m: m.group(1) + " " + body, content)
        assert n == 1, f"PS3Info.{meth} fixup matched {n} times, expected 1"
    # PS3Info.memFreeSize: free main memory, only feeds GameManager's unload-pressure heuristic. Constant = the PS3's
    # 256 MB (never any pressure on PC); platform-layer value, not reconstructed code.
    old = "public static int memFreeSize { get { throw new global::System.NotImplementedException(); } }"
    assert content.count(old) == 1; content = content.replace(old, "public static int memFreeSize { get { return 0x10000000; } }")
    body = "\n".join(content.split("\n")[2:])   # drop skeleton_gen's own banner+pragma, we supply ours
    final = STUBS_HEADER + PRAGMA + body
    open(out_path, "w", encoding="utf-8", newline="").write(final)
    shutil.copy(out_path, STUBS_PROJECT_PATH)
    shutil.copy(out_path, os.path.join(ROOT, "tools", "unity", "Runtime", "_RainEngineStubs.cs"))
    print(f"{len(final)} chars -> {STUBS_PROJECT_PATH}")


if __name__ == "__main__":
    build_assembly_csharp_remainder()
    build_crosstier_stubs()
