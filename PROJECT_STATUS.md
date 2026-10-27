# PROJECT STATUS: Rain (PS3 → Windows x64)

Last updated: 2026-10-27 (M5 COMPLETE, 311/311 types. M6: the 2 real NullRef bugs + Animation-component gap from
2026-10-26 are now fixed and verified via headless play-mode test, 0 live-game time used; new deeper gaps found
and fixed along the way; 2 remaining NullRefs are genuinely out-of-scope render/animation subsystems, not bugs).

## Where we are
**Phase 5: M0–M4 COMPLETE; M5 (reconstruct the Stage-1 slice closure) APPROVED 2026-10-17, in progress.**
| Item | Result | Evidence |
|---|---|---|
| M0 Host | **Unity 2017.4.40f1** (D9), x64 D3D11 player builds/runs; skeleton + PS3 shims compile; vtable layout resolved | E63–E73 |
| M1 Assets | Class readers byte-exact on all objects; DXT native; Stage 1 exported (now 6,388 GOs, 3,905 renderers incl. 1,482 MapInstantiation copies, 809 meshes, 134 mats, 123 tex incl. 13 lightmaps) and imported with identical counts; materials bound to `RainPS3/*` (134/134); lightmaps (754 renderers, runtime `RainLightmaps`) + render settings applied | E74–E78, E83 |
| M2 Shaders | 1,282/1,282 RSX programs → HLSL compile (d3dcompiler); 183/183 shaders → ShaderLab, all supported in Unity, 0 errors, x64 build OK | E79–E82 |
| M3 VS-1 | **Complete.** x64 player shows Stage 1 (E93); golden structure match edge NCC 0.70/0.79/0.67 ≥ 0.65 (E92). Built: keyword bridge, lightmaps + light probes, MapInstantiation map build (1,482 copies), RainCommon/RainMerge post effects reconstructed from code, shader fixes (scalar uniforms, PS3 depth decode, texture row order). Carried to VS-2: rain systems (wet reflections, rain/mist), sun shafts, DOF | E83–E93 |
| M4 Toolchain | **Complete.** T2 field layout/chains, T3 vtable resolver, T4 0 unresolved generic names, T5 lift packets + compile harness; benchmark 44/53 A (83 %), all compile | E94–E96, BENCHMARK_M4.md |
| M5 Slice logic | **In progress.** Closure (direct calls, level4 + 41 st01 prefabs): 146 script classes → 212 top-level types / 4,339 methods (`work/maps/st01_closure*.csv`). All 238 types decompiled with switch recovery + lifted (`work/decomp_st01`, `work/lift_st01`, local). Layout rule corrected (E97). Queue finished 2026-10-19: 209/212 types full + 3 partial by design, 3878/4339 methods, all compile; replay PASS 1137/FAIL 227 (all environment). Gap: types reached only via fields/inlined accessors are outside the closure (E101) | E97–E101 |

**Exact next action:** the 2 real bugs flagged 2026-10-26 (`CharacterTaskBase.LateUpdate` NullRef x228/10 frames,
`LookControllerBase.UpdateSegment` NullRef x216/10 frames) plus the ~194 `MissingComponentException` "no Animation
attached" gap are now FIXED and verified via headless play-mode test (`tools/unity/RainPlayTest.cs`), 0 live-game
time used. Root causes and fixes, in order found:
1. Both NullRefs traced to `work/m6_dependency_map.md`'s "AI/enemies (no NPCs in walk-only scene)" bucket being
   wrong -- NPC GameObjects (`c_four_01_*`, `c_two_01`, `c_girl_Scene01`) ARE present in st01 even though their AI
   behavior isn't needed; their real controller class (`CharacterAI` + concrete subclasses
   `CharacterEnemy_Big/Four/Small/Two`/`CharacterGirl`, all already fully M5-reconstructed) was excluded, so
   `GetComponent<CharacterBase>()` returned null. Promoted all 6 to critical/`SCRIPT_CLASSES`.
2. One level deeper (`RootMotionComputer.ComputeRootMotion`): `CharacterActionPlayer`/`ActionData` were
   mis-bucketed under "AI-script VM (NPC scripting)" even though `CharacterActionPlayer` is the fundamental
   "which motion is playing" component every character (player included) has, and has no dependency on the real
   AI-VM (`AsBrain`/`AsCommandNew`/etc., correctly still deferred). Promoted both.
3. One level deeper still (`HeadLookController.Initialize`, `charBase.m_CharacterParameter` null): two causes --
   (a) Unity's Script Execution Order is per the *concrete* attached class, not an inherited base setting
   (`CharacterBase`/`CharacterAI` are never directly attached, only their subclasses are) -- `RainImport.cs` now
   sets execution order on `CharacterPlayer`/`CharacterEnemy_*`/`CharacterGirl` (early) vs
   `LookControllerBase`/`HeadLookController`/`CharacterTaskBase`/`RootMotionComputer` (after); (b) `GirlParameter`
   (same already-critical `AIParameter` family as `FourParameter`/`TwoParameter`) was the one remaining missing
   promotion, needed for `c_girl_Scene01`'s `CharacterParameter` to resolve via inheritance.
4. `RestartManager.GetCurrentRestartTransform` NullRef: found a general exporter bug, not a bucketing gap -- a
   PPtr field typed as a *Component* (e.g. `RestartTrigger`) stores a direct pointer to that component object,
   not to its owning GameObject, but `scene.json` only lists GameObjects. Fixed in `tools/rain_export.py`'s
   `_decode_value`: a PPtr leaf whose resolved object isn't a GameObject (classID != 1) now resolves one level
   further via that component's own leading `m_GameObject` field (every Unity Component's first serialized field)
   -- a general fix benefiting any other component-typed PPtr field project-wide, not special-cased.
5. The `MissingComponentException` "no Animation"/CharacterController gaps: wrote and **validated byte-exact**
   native binary readers for Unity's `CharacterController` (classID 143, 83/83 instances exact project-wide) and
   `Animation` (classID 111, 1553/1553 instances exact project-wide) in `tools/unity35_classes.py` (neither had a
   reader before -- both were just silently skipped by the exporter). Wired into `rain_export.py` + `RainImport.cs`.
   Animation clip *playback* is deliberately not wired yet (no AnimationClip asset pipeline) -- an empty enabled
   component is enough to stop the crash; clip fidelity is separate, bigger scope.

Remaining NullRefs (21, down from 224) all now trace to genuinely out-of-scope subsystems, not wiring bugs (both
match the original PS3 asm's own unconditional-access shape, i.e. not recon errors):
- 19x `LookControllerBase.MakeWindingActionOrgLocal` (`cur.weight` on a null `AnimationState`) -- needs the real
  AnimationClip playback pipeline (same gap as above, one level deeper: an attached-but-empty Animation component
  has nothing to return from `GetPlayAnimationState()`).
- 2x `RainRenderEffect.Start`/`IlluminationCameraController.Start` (`GetComponent<Camera>().targetTexture.width`)
  -- these special post-process cameras need a real `RenderTexture` asset generated and assigned, which
  `RainImport.cs`'s camera import currently only tracks as a bool flag (`hasTargetTexture`). Same deferred bucket
  as M3's already-known VS-2 carryover (wet reflections, sun shafts, DOF).

0 compile errors, 0 AttachScripts errors throughout. 311/311 M5 types still compile clean
(`tools/lift_compile.py`). `work/m6_dependency_map.md` updated with 4 new promotion entries (2026-10-27 dates);
rewrite its stale "11 promotions" 2026-10-26 reference next time it's touched, not urgent.

Next real decision point: either build the AnimationClip import pipeline (bigger, new RE-adjacent scope -- ask
first) to get real motion playback, or move on to validating the actual "boy walks, camera follows" loop with a
live RPCS3/Unity side-by-side session (needs the user; ask before starting).


**M6 dependency map** (local only, `work/m6_dependency_map.md`): of the 311 reconstructed types, 152 are critical-path for the walk/camera/region/rain vertical slice (player movement+anim, core game/input/scene loop, PathCamera family, PathGraph/nav, Region*/Trigger*, Rain*/CreateRainDrop); 159 are deferred (AI/enemy behaviour, audio, UI/save/menu -- already done separately, cutscenes, the Gimmick/AcqObject interactive-object system, misc render effects, the AsCommandNew AI-script VM).

**Data pipeline extended and verified:** `tools/rain_export.py` generalised `post_effect()` into `script_component()` (E40's MonoBehaviour-field decoder, already proven byte-exact at M1, just never run for gameplay classes): decodes any of the 93 critical-path classes that actually have MonoBehaviour instances (59 of the 152 are base/abstract/singleton with 0 instances, nothing to extract), resolves PPtr fields to scene object ids. Verified against a real export: 1,272 script-component instances across 77 classes, 0 decode errors; spot-checked against known figures (RegionBox count 239 matches E77 exactly) and PPtr resolution (e.g. `m_RegionTriggerArray` resolves to a real `level4@N` id). Re-ran into `work/export/st01/scene.json` (local, unpushed) -- this is live and correct.

**Unity-side importer extended, not yet working:** `tools/unity/RainImport.cs` gained a small hand-written MiniJSON parser + reflection-based `AttachScripts()` (generic field setter: Vector/Quaternion/Color/Rect/Bounds/curves/arrays/List<T>/enums/LayerMask/Color32, PPtr fields resolved against the imported GameObjects or materials) so any of the 93 classes' decoded fields can be set on a real attached component without per-class C# boilerplate. Also added (tracked, hand-written, not decompiled): sun-shaft parameter fields + `CopyParameter`/`ChangeColorCollectionMode` on `RainCommonPostEffect`/`RainMergePostEffect` (M3 left these out; PathCamera/GlobalParam/CutSceneManager need them to compile -- data fields only, no actual sun-shaft rendering yet), and `tools/unity/Runtime/_RainEngineStubs.cs` (compile-only empty placeholders for engine-extension types the recon scripts merely *reference*: Unity Standard Assets image effects PostEffectsBase/DepthOfFieldSimple/GlobalFog/GlowEffect/etc., Shroud cloth `ShroudInstance`, PS3 SGX audio wrapper classes, `CutScene`/`CutSceneData`; NOT reconstructed logic).

**Resolved this session (was "Blocked on"):** excluded the 159 deferred-bucket files from `Assets/RainRuntime/Recon`
(moved to `port_unity/_deferred_recon/`, outside `Assets/` so Unity ignores them) and regenerated `_Skeleton.cs` for
the reduced 155-file set (`tools/skeleton_gen.py`'s own `top_level_types()`/comment-out logic, run directly instead
of via `lift_compile.py`'s temp-file path, writing the result to `work/skeleton/Assembly-CSharp.remainder.cs`).
That alone surfaced two more gaps, both fixed: (1) `RainCommonPostEffect`/`RainMergePostEffect` are hand-written M3
files that were never in `Recon/`, so the skeleton re-declared them too -- add their names to the "already has a
real file" set even though they have no `Recon/*.cs`. (2) the empty `_RainEngineStubs.cs` placeholders weren't
enough once only critical-path files remained: `CharacterShaderConection`/`PathCamera`/`GameManager`/`SceneManager`/
etc. (all critical-path, not excludable) call real members on `ShroudInstance`/`CutScene`/`PS3Info`/
`PS3SystemUtility`/`ColorCorrectionCurves`/`DepthOfFieldSimple`/`DarkenEffect`/`SGXBody`/`SGXHeader` -- empty classes
aren't enough once something is more than a field type (per the cross-tier-types note below). Fix: `tools/skeleton_gen.py`
already existed for exactly this (its docstring says "used to generate platform shim stubs") -- ran it with `--only`
against the real `Rain.Firstpass.dll` (which defines all of these with real members, plus 3 surprises: `AudioClip`/
`AudioSource`/`CutSceneClip` are the GAME's own global-namespace shim classes in Firstpass, not `UnityEngine`'s) to
get real signatures, bodies still `NotImplementedException` stubs (same convention as the Assembly-CSharp skeleton,
not reconstructed logic). Result: 0 compile errors, `RainShaderDiag` withError=0, and a real `RainImport.Run` scene
import completes end-to-end (see Exact next action above for the remaining 76+41 runtime AttachScripts/static-init
errors to triage next).

**Previously done (2026-10-25):** M5 reconstruction queue COMPLETE: AsCommandNew (322 stubs, 6 sequential split passes, sonnet-5-5) was the last partial type, all passes compiled clean on the first or second try. RuntimeMisc's last stub (`ObjectArray_NameSort`) was mislabeled `nopacket` by an earlier agent - it actually had a packet (`work/lift_st01/RuntimeMisc.md:1791`, a cost-keyed selection sort) and is now implemented. Queue: 311/311 types done, 5819/5819 methods, 315 recon types, all compile. Replay: PASS 660 / PASS~ 958 / FAIL 121 / FAIL~ 182 / EXC 124 / EXC~ 279 / SKIP 187 (AsCommandNew's AI-script methods aren't exercised by the current replay samples, so no new PASS/FAIL - expected, not a red flag). AsCommandNew `// unverified` highlights: `EnableResistant` BigParameter+0x180 write omitted (no recon field), `Command_AutoMoveAlternativePoint_vs` confirmed correct against the packet (discards `FindNearestPoint`'s result, moves to the original point either way), 1 `sic` (`Command_IsRangeOut_bfu10TargetType` uses `< 0` vs `IsRangeIn`'s `0 <`, asm `blt` confirmed). UI/save/menu track DONE: all 23 UI todo types reconstructed and compiling.
**Local-only artefacts:** `work/export/st01`, `work/unity_shaders8` (generated shaders, game-derived — never commit), Unity project `G:/Decomp/Rain/port_unity` (runtime scripts from `tools/unity/Runtime/` → `Assets/RainRuntime/`, editor scripts → `Assets/Editor/`).
**Housekeeping:** hosts file restored (backup `hosts.bak-rain`); Unity 4.7 removal approved by user.

## Completed and verified (evidence IDs: look up the pool in EVIDENCE.md, then open only that file in evidence/)
| Phase | Result | Evidence |
|---|---|---|
| 1 Feasibility | Both PKGs extracted; IL decrypted (SDAT, CMAC-verified); FIX EBOOT + 25 SPRX decrypted (zero klic); IL bodies stripped; same build as retail (MVIDs) | E1–E18 |
| 2 Foundation | REA capability map (no PPC64; .NET OK); Ghidra 12.1.4 works headless; native↔IL method mapping solved | T1–T8, E19–E29 |
| 3 RE (2 iterations) | Mono AOT v67 decoded (GOT/PLT/relocs) for all 4 game assemblies (9,118 methods); Ghidra fully annotated (Assembly-CSharp); 2 classes reconstructed; MonoBehaviour data 99.96 % byte-exact; all 892 FP + 390 VP validated; 1 shader → HLSL; game↔engine boundary (~60 PS3 APIs); call-graph closure | E30–E43, E52–E60 |
| Oracle | Retail+FIX installed in RPCS3; game fully playable (user: shaders, controls OK); FIX swaps title video/PARAM.SFO/KEYFILE | E44–E51 |
| 4 Planning | `PORTING_PLAN.md` (S1–S11, M0–M9, oracle method, risks) + target architecture in `ARCHITECTURE.md` | — |

## Outstanding tasks and blockers
- Approval of the plan / M0 (blocker for implementation).
- E53 vtable-slot mapping unresolved (planned in M0 via the RPCS3 GDB stub).
- 211 generic TypeSpec/MethodSpec names (E32); 4 MonoBehaviour classes not exact (E57).
- Ghidra annotation only done for Assembly-CSharp (other 3 assemblies have CSV maps but no Ghidra import yet).
- Optional, offered: restore the original `title_flow.mp4` in the RPCS3 install (removes the repack splash).
- Optional: switch the RPCS3 install to pure retail (RAP in exdata + retail EBOOT/files), removing the repack's splash.

## Environment needed to resume (verified 2026-10-15)
| Component | Version / path | Used for |
|---|---|---|
| Workspace | `G:\Decomp\Rain\DECOMP` (git, remote `origin` = github.com/ADarkChicken/rain-ps3-port, **public**) | everything |
| Original game files | `G:\Decomp\Rain\BASE GAME\Rain.pkg`, `RAIN_NPUA80719_FIX_421.pkg`; owner's rip `G:\Decomp\Rain\BASE GAME CLEAN\` (PKG + RAP); all read-only, never modified | source |
| Python | 3.14.5, venv `tools\.venv` (pycryptodome 4.0.0, capstone 5.0.9, dnfile 0.18.0: `tools/requirements.txt`) | all tools |
| Crypto constants | `tools\keys.local.json` (local only, git-ignored; template `tools/keys.example.json`) | pkg/sdat/self/klic/prx tools |
| Ghidra | 12.1.4 at `%USERPROFILE%\tools\ghidra_12.1.4_PUBLIC`, JDK 21.0.12 (Eclipse Adoptium) | native analysis |
| Ghidra project | `ghidra\probe\probe.gpr` (Assembly-CSharp.dll.prx annotated; RainPS3Utility.prx) | decompilation |
| RPCS3 | v0.0.42 at `G:\Games\rpcs3-v0.0.42-20024-9e86f165_win64_msvc`, FW 4.93, game installed as `dev_hdd0\game\NPUA80719` | oracle |
| GitHub CLI | 2.102.0 at `C:\Program Files\GitHub CLI\gh.exe`, logged in as ADarkChicken | push |
| C# compiler | `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe` | compile checks |
| HLSL compiler | system `d3dcompiler_47.dll` via `tools/hlsl_compile.py` | shader checks |
| REA MCP | rea-agents 6.5.0 (ghidra provider available; PPC64 unsupported) | .NET metadata |
| Unity host | **2017.4.40f1** at `G:/Decomp/Rain/_tools/Unity-2017.4.40f1` (license `C:/ProgramData/Unity/Unity_lic.ulf`; Unity Hub 3.22.3 via winget). Host-compile project: `G:/Decomp/Rain/_tools/m0_host_compile` (rebuild: `bash tools/m0_host_setup.sh`); empty x64 build test: `_tools/m0_empty_2017` + `tools/unity/BuildM0.cs`. Unity 4.7.2 also installed (unusable, E70) | engine host |
| RPCS3 probe config | `work/rpcs3_cfg/config_probe.yml` (= user config with PPU Decoder: Interpreter (static)); launch: `rpcs3.exe --no-gui --config <that> <EBOOT>`; RAP installed in `dev_hdd0/home/00000001/exdata` | debugger probes |

## Key commands
```
# Python tools (always from DECOMP\, isolated mode)
tools/.venv/Scripts/python -I tools/<tool>.py ...
tools/.venv/Scripts/python -I tools/rap2klic.py <file.rap> > work/license/rif_key.hex   # then self_decrypt.py --klic <hex>
bash tools/reproduce_phase1.sh        # extract PKGs, decrypt IL + FIX binaries (outputs must not pre-exist)
bash tools/reproduce_phase3.sh        # exports → method map → GOT/PLT decode → MonoBehaviour decode (Assembly-CSharp)
# Ghidra headless (project ghidra\probe)
"%USERPROFILE%\tools\ghidra_12.1.4_PUBLIC\support\analyzeHeadless.bat" G:\Decomp\Rain\DECOMP\ghidra\probe probe ^
   -process Assembly-CSharp.dll.prx -noanalysis -readOnly -scriptPath G:\Decomp\Rain\DECOMP\ghidra\scripts ^
   -postScript DecompileNamespace.java <TypeName> <out.txt>
#   new PRX: -import <prx> -processor PowerPC:BE:64:64-32addr -cspec default   (≈25 min analysis)
#   then ApplyMethodNames.java <methods.csv> <report> ; ApplyAotAnnotations.java <relocs.csv> <got.ghidra.tsv> <plt.ghidra.tsv> 0x3fe400 <report>
# RPCS3
rpcs3.exe --no-gui "<RPCS3>\dev_hdd0\game\NPUA80719\USRDIR\EBOOT.BIN"     # log: <RPCS3>\log\RPCS3.log (overwritten each launch)
powershell -File tools\rpcs3_window_capture.ps1 -Out <png>                # captures ONLY the RPCS3 window (PrintWindow)
```
### M5 differential replay (E98, bash from DECOMP/)
```
bash tools/replay.sh                     # samples -> cases, compile recon to RainRecon.dll, Unity batch replay -> work/replay/report.txt
# new call samples (user plays; RPCS3 with work/rpcs3_cfg/config_probe.yml, launched in background):
#   once in game: cp "<RPCS3>/log/RPCS3.log" work/rpcs3_logs/callsN/rpcs3_snapshot.log
#   tools/.venv/Scripts/python -I -u tools/probe_calls.py work/rpcs3_logs/callsN/rpcs3_snapshot.log work/rpcs3_logs/callsN --skip <merged census, hits>0>   (background)
#   stop: touch work/rpcs3_logs/callsN/stop.req (before a chapter load); user closes RPCS3 after; add the new samples.jsonl to tools/replay.sh
```
### M1–M3 pipeline (bash, from DECOMP/; U=../_tools/Unity-2017.4.40f1/Editor/Unity.exe, P=G:/Decomp/Rain/port_unity)
```
# 1 export Stage 1 (st01 = level4 + 41 st01_Prefab_* registries)
PL=$(grep "st01_Prefab_" work/maps/level_names.txt | cut -f1 | tr '\n' ' ')
tools/.venv/Scripts/python -I tools/rain_export.py extracted/Rain/USRDIR/Media work/export/st01 level4 $PL
# 2 shaders (only after generator changes; keep the .meta files in Assets/RainShaders)
tools/.venv/Scripts/python -I tools/rsx2unity_shader.py extracted/Rain/USRDIR/Media work/unity_shaders7
cp work/unity_shaders7/*.shader $P/Assets/RainShaders/
# 3 sync scripts into the Unity project (source of truth is tools/unity/; BuildM0.cs is not used there)
cp tools/unity/Rain*.cs $P/Assets/Editor/ ; cp tools/unity/Runtime/*.cs $P/Assets/RainRuntime/
# 4 import (delete $P/Assets/Rain/st01 first), checks, renders
$U -batchmode -quit -projectPath $P -executeMethod RainImport.Run -rainExport <abs DECOMP>/work/export/st01 -rainScene st01 -logFile <log>
$U -batchmode -quit -projectPath $P -executeMethod RainShaderDiag.Run -logFile <log>                        # expect withError=0
$U -batchmode -quit -projectPath $P -executeMethod RainShaderBuildCheck.Run -rainOut <dir> -logFile <log>   # x64 player, all variants
$U -batchmode -quit -projectPath $P -executeMethod RainShot.Run -rainScenePath Assets/Rain/st01/st01.unity -rainOut <dir> [-rainPoses work/rpcs3_logs/campose/poses.jsonl]
# 5 golden capture session (user plays; RPCS3 must use the interpreter config; slow)
rpcs3.exe --no-gui --config work/rpcs3_cfg/config_probe.yml "<RPCS3>/dev_hdd0/game/NPUA80719/USRDIR/EBOOT.BIN"   (run in background)
#   once the user is in game: copy the log (Python cannot open the live one), start the probe in background
cp "<RPCS3>/log/RPCS3.log" work/rpcs3_logs/campose/rpcs3_snapshot.log
tools/.venv/Scripts/python -I -u tools/probe_campose.py work/rpcs3_logs/campose/rpcs3_snapshot.log work/rpcs3_logs/campose
#   per pose: user stands still -> echo <label> > work/rpcs3_logs/campose/capture.req -> wait for <label>.done -> tell user they may move
#   end: user closes RPCS3, then kill the probe process (it keeps the GDB connection open on purpose, E69)
```

## Workspace layout
| Path | Content | In git? |
|---|---|---|
| `*.md`, `FUNCTION_INDEX.csv` | project docs, Assembly-CSharp method index | yes |
| `tools/` | own tools (`*.py`, `*.sh`, `*.ps1`), `keys.example.json`, `requirements.txt` | yes (keys.local.json, .venv, ref_* excluded) |
| `tools/ref_rpcs3/`, `tools/ref_mono/` | third-party reference sources (RPCS3, mono@8219a5b) | no (re-downloadable) |
| `ghidra/scripts/` | Ghidra scripts | yes |
| `ghidra/probe/` | Ghidra project database | no (embeds game code) |
| `work/poc/*.cs`, `*.hlsl` | reconstructed classes, translated shader | yes |
| `work/poc/*.decomp.txt`, `*.asm.txt` | decompiler/disassembly dumps | no |
| `work/maps/` | per-assembly method/GOT/PLT/relocs/exports CSVs, closure, decode summary | only `monobehaviour_decode_summary.csv` |
| `work/managed_il/`, `work/fix_elf/`, `work/retail_elf/` | decrypted IL / PPC64 binaries (retail = canonical) | no |
| `work/license/` | RAP-derived key (personal license material) | no |
| `work/rpcs3_logs/` | RPCS3 session/install logs + 2 window captures | no |
| `extracted/` | raw PKG contents (2.1 GB) | no |

Git policy: `.gitignore` is an allow-list; never commit game data, decompiled dumps, GOT/PLT CSVs (they contain game string
literals) or `tools/keys.local.json`. The repo is public.
