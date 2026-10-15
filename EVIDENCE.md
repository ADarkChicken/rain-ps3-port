# EVIDENCE — Rain (NPUA80719)

Confidence: **V** = verified (directly observed/cryptographically checked), **I** = inference, **U** = unknown.
Paths relative to `DECOMP/`. Originals in `../BASE GAME/` are never written.

## Inputs
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E1 | `Rain.pkg` sha1 `0881bcce…41d`: retail PS3 PKG (rev 0x8000), content `UP9000-NPUA80719_00-RAIN000000000001`, 1530 entries, 2.21 GB | V | header parse; full decrypt+extract, PNG/MP4 outputs valid |
| E2 | `RAIN_NPUA80719_FIX_421.pkg` sha1 `6ff365d4…f49`: debug-type PKG `…RAINFUGAZIFIX355` (scene fix), 37 entries: EBOOT + all 25 SPRX + title_flow.mp4 + icons | V | same |
| E3 | Retail EBOOT/SPRX/KEYFILE.EDAT = NPDRM **license 2 (local, needs RAP)**. No RAP available. | V | `tools/npd_info.py` |
| E4 | FIX EBOOT = NPDRM license 3 (free), key rev 0x19; FIX SPRX = license 3, key rev 0x1C, app_type 0x20 | V | `tools/npd_info.py` |

## Decryption
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E5 | FIX EBOOT decrypts with NP_KLIC_FREE → `work/fix_elf/EBOOT.elf` (sha1 `3f9bff49…`), PPC64 BE ELF, entry 0xC38720 | V | RPCS3 v0.0.42 `--decrypt`; `tools/self_decrypt.py --free` output **byte-identical** |
| E6 | FIX SPRX do **not** use NP_KLIC_FREE (RPCS3: "Failed to decrypt SELF metadata info"); they decrypt with an **all-zero klicensee** | V | `tools/klic_check.py` (32 pad bytes zero), then all 25 decrypt with every zlib stream inflating to exact p_filesz |
| E7 | PRXManager.prx segments (0x4998 text / 0x49A0 data, memsz 0x320) match shipped `Media/modules_info.txt` | V | cross-check |
| E8 | `Media/Managed/*.dll.sdat` = SDAT (flags 0x0100000D: compressed+encrypted-key), decrypt without license → 10 valid .NET PE assemblies in `work/managed_il/` | V | `tools/sdat_decrypt.py` (port of RPCS3 unedat/lz), **every block AES-CMAC verified** |

## Content of decrypted code
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E9 | Engine = **Unity 3.5.8f1**, PS3 player, Mono runtime with AOT (146 `mono_*` strings in EBOOT incl. `mono_aot_*`) | V | `mainData` header string "3.5.8f1"; EBOOT strings |
| E10 | **All IL method bodies are stripped**: every non-abstract MethodDef body is the single byte `0x2A` (`ret`) in all 10 assemblies | V | `tools/il_body_check.py`; REA `inspect_managed_members` (0 call edges / 0 ldstr) |
| E11 | IL metadata intact: Assembly-CSharp has 1305 types, 13951 fields, 8490 methods, 295 properties; UnityEngine.dll.mdb (debug symbols) shipped | V | REA `inspect_managed_members` summary |
| E12 | AOT images belong to the same build as retail IL: each `*.dll.prx` embeds its assembly's exact MVID (e.g. Assembly-CSharp `70F9671C-C082-4EEC-9E63-E46AB33DF7DC`) | V | GUID string match |
| E13 | AOT PRX text is valid PPC64-BE (99.96% decode); e_type 0xFFA4 (SCE PRX); no named `mono_aot_*` symbols inside the PRX | V | capstone sweep |
| E14 | FIX binaries are functionally the retail build re-signed (sizes of decrypted AOT ≈ retail SPRX file sizes; MVID match) | I (high) | E12 + size comparison; retail SPRX cannot be decrypted to diff |
| E15 | Native plugins: `ShroudUnityPlugin.prx` (2.4 MB, purpose U), `RainPS3Utility.prx` (6.5 KB), `PRXManager.prx` | V (exist) / U (role) | listing |

## Assets
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E16 | Unity serialized files: `mainData`, 582 `levelN`, 583 `sharedassetsN.assets`, `resources.assets` (53 MB), `unity default resources`; format v9, **big-endian**, target platform 10 (PS3) | V | header bytes |
| E17 | Audio: `Resources/SGX/*.sgh/.sgb/.sgd` = Sony **SGXD** banks (magic `SGXD`); `.sgb` bodies start with AC-3 sync `0B77` | V (magic) / I (codec of all banks) | header bytes |
| E18 | Video: 8 MP4 (opening, title flow, ending, endroll; NTSC+PAL), 562 MB | V | `file` |

## Phase 2 foundation findings (2026-10-15)
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E19 | Each `<asm>.dll.sprx.b.prx` imports the main PRX's exports and holds the **Mono AOT symbol names** (`methods`, `methods_end`, `code_offsets`, `method_info_offsets`, `class_info_offsets`, `class_name_table`, `got_info_offsets`, `ex_info_offsets`, `unwind_info`, `mono_aot_file_info`, `mono_assembly_guid`, `blob`, `ut_e_N`…) | V | strings; `tools/prx_exports.py` |
| E20 | Main PRX export NIDs = standard PS3 NID (SHA1(name+suffix), LE u32) of those names: 185/186 resolved. Assembly-CSharp: `methods`=0x8, `methods_end`=0x331CC8, `code_offsets`=0x3778A0, `method_info_offsets`=0x382D30, `class_info_offsets`=0x393048, `mono_aot_file_info`=0x394108 | V | `work/acs_exports.txt` |
| E21 | **Native↔IL mapping solved for Assembly-CSharp**: `code_offsets[MethodDef row−1]` + `methods` = code address. 8396/8490 entries in range, distinct, monotonic; the 94 `-1` entries are exactly the 94 abstract/extern methods (RVA 0) | V | structural check vs IL metadata |
| E22 | Mapped addresses start with PPC64 prologues; arg spills match C# signatures (e.g. `UIDrawCall.set_depthPass(bool)` → `stb r4`; `TweenScale.set_scale(Vector3)` → this + 3 words) | V (7 samples) | capstone |
| E23 | AOT code is unoptimised-style Mono codegen (full frames, GOT via `bl`/`mflr r30` PIC idiom) → regular, pattern-friendly | V (samples) / I (whole) | capstone |
| E24 | Assembly-CSharp: 673 top-level types, almost all in global namespace; largest areas by method count: Character 963, UI 764, Gimmick 665, As(ActionScript) 401, Game 298, Path 269, AI 268, Menu 190, Sound 180 | V | metadata |
| E25 | ~99 top-level types are **NGUI** (third-party Unity UI lib: UIWidget, UICamera, Tween*, BMFont, Inv* example classes, NGUITools) | V (names) / I (exact NGUI version) | metadata |
| E26 | Assets: 1168 serialized files, all v9 / 3.5.8f1 / platform 10, **type trees stripped**; 63 class IDs, 159,407 objects. Top bytes: Texture2D 703 obj 516 MB, Mesh 5069 obj 321 MB, AnimationClip 2008, MonoBehaviour 30,504, ParticleSystem 3700, Shader 183. **No AudioClip objects**. Unknown IDs 549/550/197/15/26/12/144/141/149 | V | `tools/unity_inventory.py` → `work/asset_class_inventory.csv` |
| E27 | Shaders: ShaderLab text retained (Properties, SubShader, Tags, Blend/ZWrite/Cull state, bindings); programs compiled **only** as `SubProgram "ps3"` (2588) = RSX microcode (`sce_vp_rsx`/`sce_fp_rsx`, hex) — no PC variants. 102 distinct shader names, ~60 custom (Rain2/*, Custom/*, Rain Effect/*) | V | grep of asset files; sample Custom/RainSplash (vp 11 instr, fp 7 instr) |
| E28 | `ShroudUnityPlugin` = **CloakWorks Shroud** commercial cloth-simulation middleware (sheets/tubes, skinned constraints, capsule collision; SPU modules embedded; DRM FileSignature) | V | strings (`C:\CloakWorks\Code\Shroud\…`) |
| E29 | Audio is entirely outside Unity (no AudioClip; SGXD banks + Sound* C# classes) → audio backend must be replaced | V (no AudioClip) / I (all audio via SGXD) | E26, E17 |

## Phase 3 findings: AOT code readability, PoC reconstruction, data and shader decoding (2026-10-15)
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E30 | Mono AOT format = **file version 67** = upstream mono/mono ~Feb–May 2010 (reference commit `8219a5b`, `tools/ref_mono/`). `MonoAotFileInfo` layout matches exactly (incl. `flags`/`opts`); flags=2 = FULL_AOT. Public Unity Mono 2.6 branches are v66 → Rain uses a newer, private console build | V | `mini.h` diff vs binary `mono_aot_file_info` |
| E31 | GOT = 0x3FE400 (bss, 0xF420 B = 15,624 slots × 4 B) = 11,065 data slots + 4,559 PLT slots (= `plt_got_offset_base` + `plt_size`) | V | arithmetic over file_info + segment layout |
| E32 | **All 11,065 data GOT slots decode** (0 errors): R4 6062, LDSTR 1547, SFLDA 960, VTABLE 656, METHOD_RGCTX 446, METHODCONST 353, SWITCH 306, CLASS 228, TYPE_FROM_HANDLE 216, RVA 197, … 211 still shown as unresolved TypeSpec#/MethodSpec# generic instantiations | V | `tools/aot_decode.py` → `work/maps/Assembly-CSharp.got.csv` |
| E33 | **All 4,558 PLT stubs decode** (entry 0 reserved by design); each stub's `lis/ori` GOT offset == (base+index)×4 for all 4,559 (0 mismatches). PLT at 0x34F780–0x37789C, 36-B entries (function-descriptor variant). Types: METHOD 4480, INTERNAL_METHOD 26, RGCTX_FETCH 22, CLASS_INIT 19, ICALL_ADDR 10 | V | `work/maps/Assembly-CSharp.plt.csv` |
| E34 | Independent cross-checks of the decoders against code: GOT slot 248 = VTABLE System.Boolean and PLT 9 = `mono_object_new_ptrfree_box`, used together by a function that boxes a byte at +8; slot 10539 = INTERRUPTION_REQUEST_FLAG, tested then followed by a helper call (safepoint) | V | Ghidra sample `FUN_002abe90` |
| E35 | PRX relocations: 199, all ADDR32. Word @0x0 := GOT base; every method loads r30 from it (`bl;mflr r30; r30 += −0x60000+…; lwz r30,0(r30)` → address 0) | V | reloc table + asm of `Release` |
| E36 | Ghidra annotation result: 8,392/8,396 methods named `Type::Method` (4 creation failures: tokens 0x06000002, 0x060001D7, 0x06000229, 0x0600023D), 11,065 GOT labels, 4,559 PLT stubs named after targets, 199 relocs applied; 0 failures | V | `ghidra/probe/apply_names_report.txt`, `aot_annot_report.txt` |
| E37 | Object layout (32-bit refs): header 8 B + `UnityEngine.Object.ReferenceData {int instanceID; IntPtr cachedPtr}` → first script field at +0x10, fields in IL declaration order, 4 B per reference | V | UnityEngine metadata + PoC class offsets 0x10–0x20 matching IL types by usage |
| E38 | **PoC class `CameraConstrainForRainEffect` (8 methods) reconstructed** to C# (`work/poc/CameraConstrainForRainEffect.cs`); pseudocode cross-checked against asm for `Release`; **compiles with 0 errors/0 warnings** against the original UnityEngine + Assembly-CSharp metadata (csc 4.0) | V (compile, asm check) / I (behavioural equivalence: no runtime test) | `work/poc/` |
| E39 | MonoScript (class 115) layout 3.5: name, int, u32 hash, className, namespace, assemblyName, bool; 994 scripts in sharedassets0. 29,820 MonoBehaviours across levels/sharedassets → 296 distinct scripts, 0 unresolved refs (v9 externals table parsed) | V | `tools/unity_inventory.py` |
| E40 | **Serialized MonoBehaviour data decodes from IL metadata alone**: 27,307/29,820 instances (91.6%) decode to the exact stored byte length; 278/296 classes exact on every instance (e.g. RegionBox 3996/3996). Rules: public or [SerializeField], minus static/const/initonly/[NonSerialized]; bool/byte padded to 4; string/array = int32 count + data, padded to 4; UnityEngine.Object refs = PPtr (2×int32); [Serializable] classes inline. 18 classes still fail (unmodelled types, e.g. curves/masks — U) | V | `tools/unity_mb_decode.py` → `work/maps/monobehaviour_decode_summary.csv` |
| E41 | RSX fragment microcode as stored by Unity = BE words with 16-bit halves exchanged (verified via inline 1.0f constant); format per RPCS3 `RSXFragmentProgram.h` | V | `tools/rsx_fp_disasm.py` |
| E42 | **All 892 unique fragment programs** in the game disassemble with END exactly at the declared microcode length, with 0 unknown opcodes (structural validation only) | V | sweep over all shader assets |
| E43 | `Custom/RainSplash` FP (6 instr + 1 const) translated to HLSL (`work/poc/RainSplash_fp.hlsl`); compiles with d3dcompiler_47 (ps_3_0). Vertex programs **not yet decoded** (tc1 projection semantics = inference) | V (compile) / I (visual equivalence) | `tools/hlsl_compile.py` |

## Tooling capability (this host)
| ID | Finding | Conf |
|----|---------|------|
| T1 | REA rejects PS3 PKG ("unsupported binary format") and PPC64 ELF ("unsupported ELF architecture", also with provider_id=ghidra) | V |
| T2 | REA rizin/objdump providers unavailable (`ERR_REA_WINDOWS_NATIVE` — not installed) | V |
| T3 | REA managed (.NET metadata) tools work on the decrypted assemblies | V |
| T4 | Installed: Python 3.14 (venv `tools/.venv`: pycryptodome, capstone 5, dnfile), JDK 21, RPCS3 v0.0.42 (FW 4.93), git, **Ghidra 12.1.4** (`%USERPROFILE%\tools\ghidra_12.1.4_PUBLIC`; Phase 1 missed it). Not installed: IDA, rizin, ILSpy, AssetRipper, Unity 3.5, MSVC/cmake | V |
| T5 | REA 6.5.0 providers on this host: ghidra=available, ida=not_configured, hopper/native-macos=unsupported_host; rea-dotnet-static + rea-artifact-graph available. Full list: `work/rea_capabilities.txt` | V | `binary_session` |
| T6 | REA's PPC64 rejection happens in its own ELF validation, before the Ghidra provider → REA's native tools (decompile, xrefs, annotate) are unusable for this target even though Ghidra is present | V | open_binary with provider_id=ghidra |
| T8 | Ghidra headless full analysis of Assembly-CSharp.dll.prx: succeeded (~25 min), 8303 functions found (vs 8396 mapped methods), 0 relocations applied; 4/4 sampled functions decompile without warnings, but GOT accesses appear as `PTR_DAT_00000000+off` and runtime/PLT calls as anonymous `FUN_*` → readability depends on resolving Mono GOT slots (got_info_offsets + blob) and PLT targets | V | `ghidra/probe/acs_sample.txt`, project `ghidra/probe/probe.gpr` |
| T7 | Ghidra headless directly (outside REA) imports PS3 PRX with generic ELF loader as `PowerPC:BE:64:64-32addr` (PS3 ABI language exists in stock Ghidra); no PS3-specific loader installed (NID imports/relocs not resolved by Ghidra itself) | V | `ghidra/probe/import_prx.log` |
