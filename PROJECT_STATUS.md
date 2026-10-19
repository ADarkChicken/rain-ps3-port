# PROJECT STATUS: Rain (PS3 → Windows x64)

Last updated: 2026-10-19 (M5: queue finished, closure-gap types and M6 decision pending).

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

**Exact next action:** The M5 queue is finished apart from types that are partial by design. Next is a user decision: (a) reconstruct the 3 dependency gaps found outside the closure, (b) the replay-fidelity work, or (c) start M6 integration (new milestone, needs approval). State 2026-10-19 (end of session 3): **209/212 types, 3878/4339 methods**; the 3 remaining "partial" types (UTILITY.CharacterUtility, RuntimeMisc, AsCommandNew) have all their closure methods done, and their other stubs are outside the slice. Everything compiles (`work/recon/QUEUE.csv`, `tools/recon_status.py`). Done this session: CharacterAI 70, GameManager 71, PathCamera 81 (+ClosestInfo), CharacterBase 92 (+MagnetRequestParam, 3 passes), CharacterStatus 143 (2 passes; mostly trivial accessors), about 0.9M subagent tokens. PathCamera's 5 property getters were filled by hand from the asm offsets. **Dependency gaps** (called from recon code but not in the closure; the calls hit empty skeleton stubs or reflection): `GameParam.SetCameraRotate` (PathCamera), `CharacterTrigger` Get/SetCheckFlag (CharacterStatus flag methods and Initialize throw until it is reconstructed), `CharacterCtrlCreep.m_creepState` (CharacterBase.IsCreepTurn reads it by reflection). Each one is probably small; recon_init plus the recon-type agent would handle them. 96 `// unverified` spots across work/recon (grep before M6). Notable ones this session: CharacterAI (SetCharacterActive, ActionJump/JumpOff math, CalcAutoRotationSpeed denominator, IsLadderCollision args), GameManager (reflection on SceneManager.m_Sequence, Placement_Player raycast, KillCamera receivers), PathCamera (Release leaves out `GlobalParam.s_RainCommonPostEffect = null`, LookTarget/UpdateInEditing euler terms), CharacterBase (MoveFrontCheck origin, SetupRagdoll position, ResetParam RootMotionComputer guard, AddWaterEffect enum casts), CharacterStatus (Initialize m_GroundPosY, SetForwardVector). Checked against the asm: CharacterAI.IsHangCollisionUpper's impossible && tag chain is real (sic 0x10d0d4); GameManager.IsBoyDead compares position.y; CharacterStatus.AddMoveAndReset matches. Replay: PASS 1137 / FAIL 227 / EXC 506 / SKIP 641. All new FAILs triaged as environment (m_Instance statics, ctrl-list/route-set/transform refs not restored, harness layer 0; IsSwitchableCtrlMode and PauseSetting match the decomp exactly). **Open items:** (1) engine shim for `CharacterController.MoveMask(move, layerMask)` (E65): reconstructed as plain `Move` in CharacterTaskBase.LateUpdate (sic 0x001018f0); (2) replay fidelity (refs/statics in `probe_calls.py`, restore objects/transforms, feed GlobalParam time) deferred until the queue is done (user decision 2026-10-18; the queue is now done); (3) the unverified spots above; (4) private-field access done through reflection or skipped (AsCommandNew, GameManager, PathCamera.Release, CharacterBase.IsCreepTurn): decide on internal accessors at M6. Probe sessions: stop the probe before a chapter transition; the next census must `--skip` the merged censuses of runs 1-3.
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
