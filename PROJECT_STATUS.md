# PROJECT STATUS — Rain (PS3 → Windows x64)

**Current phase:** 3 (targeted RE & behavioural reconstruction) — first iteration **COMPLETE, awaiting approval** (2026-10-15)
**Next action:** user decides between (a) one more Phase 3 iteration (recommended scope below) or (b) Phase 4 port design.
Do not change scope or start Phase 4 without approval.

## Phase 3 result (details: EVIDENCE.md E30–E43)
Subsystem chosen: **AOT code readability** (the top-ranked unknown), proven on one class, plus bounded generalisation checks.
| Goal (FEASIBILITY §7 criteria) | Result |
|---|---|
| ≥95% methods named in Ghidra | 8,392/8,396 (99.95%) |
| All GOT/PLT refs resolved for PoC class | All data GOT slots (11,065) and PLT stubs (4,558) decoded program-wide; PoC class has 0 unresolved refs |
| PoC class reconstructed + compiles | `CameraConstrainForRainEffect` (8 methods), 0 errors/warnings; asm cross-check done; no runtime test |
| Serialized data consistent with IL layout | 91.6% of all 29,820 MonoBehaviours decode byte-exact; 278/296 classes fully exact |
| One shader translated + compiles | RainSplash FP → HLSL compiles; all 892 FPs decode structurally; VPs not yet decoded |
| Go/no-go + revised estimate | See "Recommendation" |

**Recommendation:** proceed toward Phase 4 (port design) after one short additional iteration that closes the
remaining *decision-relevant* gaps:
1. RSX **vertex** program decoder (all VPs) — needed to finalise the shader-translation approach.
2. Resolve the 211 generic TypeSpec/MethodSpec names and the 18 non-exact MonoBehaviour classes (type modelling).
3. Run the same AOT pipeline on the other 3 game assemblies (firstpass, UnityScript ×2) and UnityEngine boundary check.
4. Reconstruct 2–3 larger, logic-heavy classes (e.g. a Character/AI method) to measure per-method effort on real
   gameplay code (CameraConstrainForRainEffect is simple; effort data from it is not representative).
5. Optional (needs approval): RPCS3 boot test of the FIX build as behavioural oracle.

## Workspace layout (`G:\Decomp\Rain\DECOMP`)
| Path | Content |
|------|---------|
| `FEASIBILITY.md` | Phase 1/2 reports, estimates, PoC criteria (§7) |
| `EVIDENCE.md` / `ARCHITECTURE.md` / `DECISIONS.md` | Findings E1–E43/T1–T8 / verified structure incl. Mono AOT contract / decision log D1–D7 |
| `FUNCTION_INDEX.csv` | All 8,490 Assembly-CSharp methods: token, address, size, type, method, params, status, evidence |
| `extracted/`, `work/managed_il/`, `work/fix_elf/` | PKG contents, IL metadata, decrypted PPC64 binaries |
| `work/maps/` | `Assembly-CSharp.{methods,got,plt,relocs}.csv` (+ `.ghidra.tsv`), `monobehaviour_decode_summary.csv` |
| `work/poc/` | Decompiled PoC (`*.decomp.txt`), `CameraConstrainForRainEffect.cs`, `RainSplash.fp.asm.txt`, `RainSplash_fp.hlsl` |
| `ghidra/probe/probe.gpr` | Ghidra project: Assembly-CSharp.dll.prx fully annotated (names, GOT labels, PLT, relocs) |
| `ghidra/scripts/` | `ApplyMethodNames.java`, `ApplyAotAnnotations.java`, `DecompileNamespace.java`, `ProbeDecomp.java` |
| `tools/` | Phase 1: pkg/sdat/self/klic/npd tools. Phase 2–3: `prx_exports.py`, `aot_method_map.py`, `aot_decode.py`, `unity_inventory.py`, `unity_mb_decode.py`, `il_type_info.py`, `rsx_fp_disasm.py`, `hlsl_compile.py`; `ref_mono/` (mono@8219a5b), `ref_rpcs3/` (+`rsx/`); `reproduce_phase1.sh`, `reproduce_phase3.sh` |

## Phase 3 pipeline (per assembly; Assembly-CSharp done)
1. `reproduce_phase3.sh` steps (exports → method map → GOT/PLT decode).
2. Relocs CSV + TSV conversion (see EVIDENCE E35; snippet in session history: parse PH type 0x700000A4, 24-B entries).
3. Ghidra headless: `-process <prx> -noanalysis -postScript ApplyMethodNames.java <methods.csv> <report>` then
   `ApplyAotAnnotations.java <relocs.csv> <got.ghidra.tsv> <plt.ghidra.tsv> 0x3fe400 <report>` (GOT base is per assembly).
4. Decompile a class: `-readOnly -postScript DecompileNamespace.java <Type> <out.txt>`.
Ghidra: `%USERPROFILE%\tools\ghidra_12.1.4_PUBLIC` (full analysis of a PRX ≈ 25 min).

## Remaining uncertainties
- Behavioural equivalence of reconstructed code is verified only statically (no runtime oracle yet).
- Vertex programs undecoded; FP decode validated structurally, semantically for 1 shader only.
- 18 MonoBehaviour classes / 211 generic refs not yet modelled; other assemblies not yet processed.
- Unity version for the port, asset conversion beyond MonoBehaviours (meshes/textures/animations) untested.
