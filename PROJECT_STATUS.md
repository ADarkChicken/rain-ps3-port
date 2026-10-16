# PROJECT STATUS: Rain (PS3 → Windows x64)

Last updated: 2026-10-17 (M3 in progress: keyword bridge, lightmaps, light probes done).

## Where we are
**Phase 5: M0, M1, M2 (compile) COMPLETE; M3 (VS-1) IN PROGRESS (approved 2026-10-17; defaults: static scene only, poses from the opening of Stage 1, threshold set after first captures).**
| Item | Result | Evidence |
|---|---|---|
| M0 Host | **Unity 2017.4.40f1** (D9), x64 D3D11 player builds/runs; skeleton + PS3 shims compile; vtable layout resolved | E63–E73 |
| M1 Assets | Class readers byte-exact on all objects; DXT native; Stage 1 exported (4,238 GOs, 2,075 renderers, 809 meshes, 134 mats, 123 tex incl. 13 lightmaps) and imported with identical counts; materials bound to `RainPS3/*` (134/134); lightmaps (754 renderers, runtime `RainLightmaps`) + render settings applied | E74–E78, E83 |
| M2 Shaders | 1,282/1,282 RSX programs → HLSL compile (d3dcompiler); 183/183 shaders → ShaderLab, all supported in Unity, 0 errors, x64 build OK | E79–E82 |
| M3 VS-1 | Done: variant selection via Unity built-in keywords (no RAINV), engine lightmap sampler, light-probe SH bridge (`RainLightProbes`). Open: golden captures, game-set global uniforms, render-texture samplers (`rain_*`), 1,118 ambient-only renderers + untextured planes to judge vs RPCS3 | E84–E85 |

**Exact next action:** RPCS3 reference captures (user plays to 3 spots in Stage 1; camera pose read via the GDB harness) → port renders the same poses → compare; then fix the largest differences (inferred SH convention/ambient scale E85, custom global uniforms set by Rain scripts, render-texture inputs).
**Local-only artefacts:** `work/export/st01`, `work/unity_shaders7` (generated shaders, game-derived — never commit), Unity project `G:/Decomp/Rain/port_unity` (runtime scripts from `tools/unity/Runtime/` → `Assets/RainRuntime/`, editor scripts → `Assets/Editor/`).
**Housekeeping:** hosts file restored (backup `hosts.bak-rain`); Unity 4.7 removal approved by user.

## Completed and verified (details + evidence IDs in EVIDENCE.md)
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
