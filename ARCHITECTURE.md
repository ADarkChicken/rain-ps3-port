# ARCHITECTURE — Rain (PS3, NPUA80719)

Only verified structure (EVIDENCE.md IDs). Subsystem internals: not yet analyzed.

## Binary components
```
EBOOT.BIN  Unity 3.5.8f1 PS3 player: engine + Mono runtime + AOT loader          [E5,E9]
 ├─ Media/PRXManager.sprx          symbol-registration hub for AOT/plugin PRXs  [E7,E19]
 ├─ Media/Managed/<asm>.dll.sprx   Mono full-AOT PPC64 code ("main" PRX)          [E12,E13]
 │    exports AOT tables by NID: methods, code_offsets, method_info_offsets,
 │    class_info_offsets, class_name_table, got/ex/unwind info, mono_aot_file_info [E20]
 ├─ Media/Managed/<asm>.dll.sprx.b.sprx  "B_" bridge PRX: imports the main PRX's
 │    exports and registers them by name with PRXManager                        [E19]
 ├─ Media/Managed/<asm>.dll.sdat   IL: full metadata, bodies stripped             [E8,E10,E11]
 ├─ Media/Plugins/ShroudUnityPlugin.sprx   CloakWorks Shroud cloth sim (+SPU)    [E28]
 └─ Media/Plugins/RainPS3Utility.sprx      small game-specific native helper (role U)
```

## Native ↔ C# mapping (verified for Assembly-CSharp) [E21,E22]
`address(MethodDef token t) = methods + code_offsets[(t & 0xFFFFFF) − 1]`, −1 = no code (abstract/extern).
Expected to hold for the other assemblies (same AOT layout); verify per assembly before use.

## Mono AOT runtime contract (verified for Assembly-CSharp) [E30–E37]
- AOT file v67 (upstream Mono ~2010-04), FULL_AOT. 32-bit pointers on PPC64 (ILP32). Function descriptors (OPD) used.
- Each method: prologue `mflr/std/stdu`, then `bl .+4; mflr r30; r30 += k; lwz r30,0(r30)` → r30 = GOT base (0x3FE400),
  read from the relocated word at address 0x0.
- Data access: `lwz rX, slot*4(r30)` → GOT slot → patch (class vtable, static field address, string literal, float
  constant, method constant, switch table, …). Decoded table: `work/maps/Assembly-CSharp.got.csv`.
- Calls: same-assembly calls are direct `bl`; everything else goes through a PLT stub
  (`lis/ori r11,slot*4; add r11,r30; lwz; lwz r2,4; lwz; mtctr; bctr` + info word) → `work/maps/Assembly-CSharp.plt.csv`.
- Object layout: 8 B header + UnityEngine.Object.ReferenceData (8 B) → script fields from +0x10 in IL order.
- Platform vs game logic: PLT targets prefixed `INTERNAL_METHOD`/`ICALL_ADDR`/`CLASS_INIT`/safepoint flag are
  Mono runtime/platform mechanics (no game behaviour); METHOD targets are C#/UnityEngine calls = game behaviour.

## Serialized content contract [E39,E40]
MonoBehaviour data = header (GameObject PPtr, enabled, Script PPtr, name) + IL-derived serializable fields
(rules in EVIDENCE E40). Scripts referenced via sharedassets0 MonoScripts (994).

## Game code (Assembly-CSharp) [E24,E25]
673 top-level types, global namespace. Main areas (by method count): Character, UI (largely NGUI), Gimmick,
ActionScript (`As*`, scripted events), Game, Path, AI, Menu, Sound, Region, Cut(scene), Trigger, Move, Motion,
Save, Camera, Effect, Rain. Also `Assembly-CSharp-firstpass`, `Assembly-UnityScript(-firstpass)` (Boo/UnityScript).

## Content [E16,E26,E27,E17,E18]
- Unity v9 big-endian serialized files without type trees: textures 516 MB, meshes 321 MB, 2008 animation clips,
  30.5k MonoBehaviours (serialized script data), 3700 particle systems, 183 shaders.
- Shaders: ShaderLab state + RSX microcode programs only.
- Audio: SGXD banks driven by game `Sound*` code (no Unity AudioClips). Video: 8 MP4.

## Port boundary (strategy S1, not yet approved)
Replace: Unity PS3 player → Windows Unity runtime; RSX shaders → HLSL/GLSL; SGXD audio → PC audio;
Shroud → PC cloth solution. Reconstruct: game C# (Assembly-CSharp & co.); NGUI part from its public library version.
