# PORTING PLAN: Rain (PS3, NPUA80719) → Windows x64

Status: **PROPOSED, awaiting approval** (2026-10-15). Evidence IDs refer to `EVIDENCE.md`.
Principle: being able to decompile a function does not make the game portable. Portability is demonstrated only by
milestones that run on Windows and match the original's observable behaviour, using RPCS3 as the reference (E44–E51).

---------------------------------------------------------------------------------------------------------------------
## 1. What we are porting (verified decomposition)

| Layer | Content | Size | Evidence | Treatment |
|---|---|---|---|---|
| **Portable game logic** | C# in Assembly-CSharp (+firstpass, UnityScript ×2) | 9,118 methods with code, 1,305 + ~100 types | E21, E56 | **Reconstruct** (C# source, from metadata + AOT decompilation) |
| Third-party managed libs | NGUI (~99 types), Boo/UnityScript runtime libs | | E25 | **Replace** with the matching public library versions where licensable; else reconstruct |
| **Engine** (Unity 3.5.8 PS3 player, Rain-customised) | rendering, physics, animation, particles, scene/asset system, Mono runtime | EBOOT 12.9 MB | E9, E59 | **Replace** with a Windows Unity runtime (no engine RE) |
| **Graphics programs** | 892 fragment + 390 vertex RSX programs, 102 shaders (≈60 custom), ShaderLab state intact | | E27, E41–E43, E55 | **Translate** (RSX microcode → HLSL), keep ShaderLab state |
| **Platform APIs** (Unity PS3 extensions) | SGX audio, save data, trophies, video, pad vibration, system info | ~60 methods, 8 classes | E58 | **Reimplement** as Windows shims behind the same C# API |
| **Native plugins** | RainPS3Utility (gamma, language) | 3 functions | E58 | **Reimplement** (trivial) |
| | CloakWorks Shroud cloth (PPU + SPU) | 2.4 MB | E28 | **Replace** (Unity Cloth or custom solver) |
| **Content** | 1,168 Unity v9 BE files: 516 MB textures, 321 MB meshes, 2,008 anim clips, 29.8 k MonoBehaviours, 3,700 particle systems | | E16, E26, E57 | **Convert** (PS3 BE → PC) |
| Audio content | SGXD banks (AC-3 seen), no Unity AudioClips | | E17, E29 | **Convert** (decode → PC codec) |
| Video | 8 MP4 | 562 MB | E18 | **Reuse** (Windows decoders) |
| Unresolved | vtable-slot mapping (E53); 211 generic refs (E32); 4 data classes (E57); engine customisations (E59); Mono runtime semantics differences | | | Investigate inside milestones |

Out of scope: emulation (RPCS3 is the reference, not the product), recompiling PPC code, reimplementing Unity.

---------------------------------------------------------------------------------------------------------------------
## 2. Key architectural decision: the Windows engine host (needs your approval)

The game logic expects the **Unity 3.5 API and behaviour** (E58: legacy `ParticleEmitter/Animator/Renderer`, legacy
`Animation`, `GameObject.active`, `Cloth`, `WWW`, PhysX-2.8-era `CharacterController`/joints, `Application.LoadLevelAdditiveAsync`).

| Option | Fidelity | x64 | Effort | Risk |
|---|---|---|---|---|
| **A. Unity 4.7.x** (recommended *candidate*) | High: same API generation, PhysX 2.8, legacy particles/animation/cloth still present; `active` deprecated but available | Yes | Medium | Editor availability/activation unverified; some 3.5→4.x semantic changes (`active`, Cloth) |
| B. Unity 3.5.7 | Highest (same engine line as the original) | **Unverified** (may be 32-bit only) | Medium | Same availability risk; may fail the x64 requirement |
| C. Modern Unity LTS (2022+) | Lower: legacy particles, old Cloth, `active` removed; PhysX 4 behaviour drift | Yes | High (API shims + re-tuning) | Physics/timing drift is hard to match |
| D. Custom engine implementing the used Unity subset | Can be exact in principle | Yes | Very high | Reimplementing a large engine slice |

**Recommendation:** decide in milestone M0 by measured spike. Primary candidate A; B kept as a fidelity reference if it
turns out x64-capable; C only if A/B are unobtainable. Nothing else in this plan depends on the choice except the API
shim layer (S2) and the asset target format (S3).

---------------------------------------------------------------------------------------------------------------------
## 3. Subsystem specifications

Format per subsystem: **Original (verified)** · **Windows implementation** · **Prerequisites** · **Gaps / assumptions** ·
**Validation & acceptance**.

### S1 Game logic reconstruction (C#)
- **Original:** 9,118 AOT-compiled methods, fully mapped to IL tokens (E21, E56). All GOT/PLT references decoded (E32, E33,
  E56). Runtime field layout rule known (E52). Two classes reconstructed; they type-check against original metadata (E38, E54).
  A short play session reaches ≥3,518 methods / 30 % of the code (E60), so core systems are shared by everything.
- **Windows:** C# source compiled by the host Unity. Built on a **whole-assembly skeleton** generated from IL metadata
  (every type, field, attribute, signature, with stub bodies); stubs are replaced by reconstructed bodies class by class
  (E54 shows partial replacement cannot type-check otherwise).
- **Prerequisites:** (T1) skeleton generator; (T2) Ghidra structure types per class from the layout rule (field names in
  pseudocode); (T3) vtable-slot resolver (E53); (T4) generic-instance naming (E32); (T5) **AOT→C# assisted translator**:
  Mono's AOT codegen is regular and unoptimised (E23), so a pattern-based lifter over annotated pseudocode can draft most
  bodies, with human review. Without T5, reconstruction is essentially manual.
- **Gaps:** E53 unresolved; exception handling/try-finally recovery not yet examined; delegates/coroutines (IEnumerator
  state machines generated by the C# compiler) not yet examined; behavioural equivalence only statically checked so far.
- **Validation:** (a) compile with zero errors against the skeleton; (b) per-method **differential tests**: arguments and
  results captured at method entry/exit in RPCS3 (GDB stub, E49), replayed against the reconstruction; (c) scene-level
  comparison (see §7). **Acceptance per class:** compiles; every method has an evidence note; no unresolved symbol;
  differential tests pass for every method with captured samples.

### S2 Engine host and API compatibility layer
- **Original:** Rain-customised Unity 3.5.8 PS3 player (E9, E59), Mono full-AOT (E30).
- **Windows:** chosen Unity version (§2) as the engine. A `Rain.Platform` compatibility assembly provides the PS3-only Unity
  classes **with identical names and signatures** (`UnityEngine.PS3*`, `SGX*` as listed in E58) implemented on Windows, so
  reconstructed game code compiles unmodified. Where the host's API differs from 3.5 (e.g. `GameObject.active`), add thin
  extension shims, never edit game semantics silently.
- **Prerequisites:** host decision (M0).
- **Gaps:** Rain-specific engine customisations (E59) are unknown; they surface as behavioural diffs in validation.
- **Validation:** shim unit tests; the API surface list (E58) fully covered (each method implemented or explicitly marked
  no-op with justification).

### S3 Asset pipeline (content conversion)
- **Original:** v9 big-endian serialized files, no type trees (E16, E26). Externals and MonoScripts resolved (E39).
  MonoBehaviour data decodes from metadata alone, 99.96 % byte-exact (E57). Textures, meshes, animations and particles
  are **not yet decoded**.
- **Windows:** offline converter `rain-convert` (Python) reading PS3 data and producing host-Unity project assets (scenes,
  prefabs, materials, meshes, textures, animation clips, MonoBehaviour data) or host-format serialized files. Bring-your-own-
  copy: the converter runs on the user's legally owned files; no game data is redistributed.
- **Prerequisites:** class layouts for Texture2D/Mesh/AnimationClip/ParticleSystem/Material/legacy particles in 3.5
  (from public Unity format knowledge, verified by the byte-exact method of E57); PS3 texture/mesh encodings (swizzling,
  vertex stream formats); unknown class IDs 549/550/197/15/26/12/144/141/149 identified.
- **Gaps:** existing tools (AssetStudio/AssetRipper) untested on Unity 3.5 PS3 BE; may need our own decoders.
- **Validation:** byte-exact consumption per object (decoded length == stored size, as E57) for **100 %** of objects of each
  converted class; visual comparison of textures/meshes against RPCS3 captures; round-trip counts (objects in = objects out).

### S4 Rendering and shaders
- **Original:** ShaderLab text with RSX microcode for PS3 only (E27). FP and VP formats validated over all programs (E42,
  E55). One FP translated to HLSL, which compiles (E43). Post effects use RenderTextures (E58: Graphics, GL, RenderTexture,
  Projector).
- **Windows:** Direct3D 11 through the host Unity (default and best-supported Windows backend). An automatic translator
  `rsx2hlsl` turns FP+VP microcode into HLSL; the ShaderLab wrapper (properties, state, tags, passes) is re-emitted with HLSL
  programs. Constant bindings from the `Matrix/Vector/Bind/SetTexture` lines map to Unity built-ins.
- **Prerequisites:** VP disassembler (structure done; semantics to add); register/semantic mapping (RSX input attributes ↔
  Unity vertex inputs; VP outputs ↔ FP inputs); half-precision and PS3-specific behaviours (H registers, saturation,
  `TXP`, gamma/sRGB).
- **Gaps:** RSX-specific numerics (fp16 paths, `prec` modifiers) may differ slightly; driver-level states (e.g. alpha-test
  quirks) need checking; Rain's custom engine rendering features (E59) unknown.
- **Validation:** all 1,282 programs translate and compile (automatic); per-shader golden-image tests: render the same mesh,
  texture and camera in the port and in RPCS3; acceptance = visual match within a defined tolerance, judged per shader class
  (characters, rain, puddles, post).

### S5 Audio
- **Original:** no Unity audio clips; SGXD banks driven through `SGXSource/SGXStream/SGXSettings` (bus volumes, categories,
  distance attenuation, low-pass, markers, effects file) by game Sound* classes (E17, E29, E58).
- **Windows:** convert SGXD streams offline to Ogg Vorbis (or PCM) with metadata (loops, markers, categories). Implement the
  `SGX*` API on the host's audio system (Unity AudioSource / AudioMixer-equivalent buses), or on XAudio2 / FMOD Core if the
  bus/category model needs it.
- **Prerequisites:** SGXD container format (header/body, codecs seen: AC-3), marker/loop semantics; category/bus parameters
  from `SGXSettings` calls.
- **Gaps:** full SGXD codec list unknown; the 3D attenuation curves of the Sony library are unknown and must be measured.
- **Validation:** every bank decodes (count, durations); A/B listening against RPCS3 on fixed scenes; logged API call
  sequences (port vs RPCS3 breakpoints on SGX* calls) match.

### S6 Input
- **Original:** `UnityEngine.Input` axes/buttons, `PS3Pad.SetVibration/StopVibration`, `PS3SystemUtility.GetEnterButtonAssignment`
  (circle/cross swap) (E58). User confirmed controls work in RPCS3.
- **Windows:** XInput (Xbox pads) plus DualShock 4/DualSense via the host's input system (or SDL GameController), mapped to
  the same Input axis/button names the game queries. Vibration through XInput/HID. Enter-button assignment is a setting.
  Keyboard/mouse added as a port feature, flagged as a deviation.
- **Validation:** an input-map table covering every axis/button name the code queries (extracted from LDSTR in GOT, E32);
  manual checklist per action against RPCS3.

### S7 Video
- **Original:** `PS3VideoPlayer` (Init/Play/Update/Stop/CurrentTime/EndTime/IsPlaying) plays the MP4s; `PS3SystemUtility.get_pal`
  selects `_pal` variants (E18, E58).
- **Windows:** Media Foundation (built into Windows) or the host's video player behind the same API. Default to the NTSC files.
- **Validation:** all 8 videos play with correct timing and audio; `CurrentTime/EndTime` semantics match RPCS3 logs.

### S8 Save data, trophies, system services
- **Original:** `PS3SaveDataUtility` auto load/save + message dialogs; `PlayerPrefs`; `PS3TrophyUtility` (unlock/state);
  `RainPS3Utility` gamma + system language; `PS3Info` memory/debug helpers (E58).
- **Windows:** saves as files under `%LOCALAPPDATA%\Rain\` with an atomic write (temp + rename) and the same data blob
  (`GetData`) the game produces. Trophies become local achievements (and optionally a platform service later). Language from
  Windows UI culture, overridable. Gamma via shader/post-process. `PS3Info` memory APIs are no-ops returning plausible values.
- **Gaps:** save-blob format and versioning (`SaveData` class) to be reconstructed; whether PS3 saves should be importable
  is a product decision.
- **Validation:** save/load round-trip tests; save from scene X, load, compare state against RPCS3 behaviour.

### S9 Cloth (Shroud replacement)
- **Original:** CloakWorks Shroud: sheet/tube cloth with skinned constraints and capsule collisions, PPU+SPU (E28). Its
  data lives in assets (Shroud objects) and the plugin API (`ShroudUnityPlugin_stub.a`).
- **Windows:** first, cloth disabled (static skinned mesh) for early milestones; then a replacement solver (host Unity
  Cloth or a small position-based-dynamics solver driven by the Shroud asset parameters).
- **Gaps:** Shroud asset format and parameter semantics unknown; the vendor product is discontinued (licensing for any
  original library is a concern: we do not use it).
- **Validation:** visual comparison of character cloth motion in reference scenes; no explosions/tunnelling in a stress run.

### S10 Timing, threading, memory, physics
- **Original:** stable 30 FPS on PS3 (RPCS3 shows a 30 FPS lock, E48); `QualitySettings.set_vSyncCount`, `Time.timeScale` used;
  async additive level loading (`LoadLevelAdditiveAsync`, `backgroundLoadingPriority`) (E58); PhysX via Unity.
- **Windows:** keep the original frame-rate semantics first (30 FPS fixed: vSync interval 2 or a frame limiter), with
  physics/fixed timestep values taken from the original project settings (in `mainData`, to decode). Higher frame rates are
  a later, opt-in deviation, only after logic is verified frame-rate-independent. Threading stays on Unity's model (game
  logic is single-threaded on UnityMain, E46). Memory: managed by the host; PS3 memory-residence APIs become no-ops.
- **Gaps:** physics-engine behaviour differences between host and original; exact fixed timestep (to decode).
- **Validation:** frame pacing measurement; physics-sensitive scenes compared against RPCS3 recordings.

### S11 Tooling (enablers)
| Tool | State | Needed for |
|---|---|---|
| PKG/SDAT/SELF tools, AOT method map, GOT/PLT decoder, Ghidra annotators | **Done** (E5–E8, E30–E36, E56) | all |
| MonoBehaviour decoder | **Done** 99.96 % (E57) | S3 |
| RSX FP disassembler / VP checker | FP done, VP structure only (E42, E55) | S4 |
| Call-graph closure | Done, direct calls only (E60) | planning, S1 |
| Skeleton generator (T1), struct types (T2), vtable resolver (T3), generic naming (T4) | To build | S1 |
| AOT→C# assisted lifter (T5) | To evaluate | S1 scale |
| RPCS3 probe harness (GDB scripts: breakpoints, arg/ret capture, object dumps) | To build | validation |

---------------------------------------------------------------------------------------------------------------------
## 4. Minimum implementation for a working vertical slice

Because one short play session already reaches ≥42 % of the game methods (E60), "small" has to be defined by **layers**,
not by gameplay scope:

- **VS-1 "Scene renders"**: one converted gameplay scene (static geometry, materials, lighting/lightmaps, custom shaders) in a
  Windows x64 build with a free camera. Game logic not required.
- **VS-2 "Boy walks in the rain"**: VS-1 + player character control, camera, region streaming, rain/silhouette rendering, input.
  Needs the reconstructed closure for that scene (lower bound to measure; expect hundreds to ~2,000 methods).
- **VS-3 "Opening sequence"**: boot → title → first scenes as in the RPCS3 session, with audio and video.

---------------------------------------------------------------------------------------------------------------------
## 5. Dependency graph

```
M0 Host decision + tooling base ─┬─> M1 Asset conversion (geometry/textures/materials) ──┐
  (Unity version, skeleton T1,   │                                                        ├─> M3 VS-1 Scene renders
   RPCS3 probe harness)          ├─> M2 Shader translation (rsx2hlsl, all programs) ──────┘          │
                                 │                                                                    v
                                 ├─> M4 Logic reconstruction toolchain (T2–T5) ──> M5 Slice logic ─> M6 VS-2 Boy walks
                                 │                                                                    │
                                 └─> M7 Platform layer (input, save, SGX audio, video, system) ───────┤
                                                                                                      v
                                                                         M8 VS-3 Opening sequence ─> M9 Full game (iterative)
```

---------------------------------------------------------------------------------------------------------------------
## 6. Milestones, acceptance tests, estimates

Estimates are **calendar weeks of focused work for one engineer plus agent assistance; low confidence (±50 %)**. They are
re-estimated after each milestone from measured throughput.

| M | Goal | Acceptance tests (observable) | Est. |
|---|---|---|---|
| **M0** | Host decision; skeleton generator (T1); RPCS3 probe harness | Candidate Unity version installed + activated; empty x64 D3D11 build runs. Skeleton of all 4 game assemblies + shim stubs compiles with 0 errors in the host. RPCS3 harness captures args/return of one chosen method at runtime and dumps one object, resolving E53 for RegionTrigger. Decision record in DECISIONS.md | 1–2 |
| M1 | Convert Texture2D, Mesh, Material, GameObject/Transform/renderers for one scene | 100 % of objects of these classes in the chosen scene consumed byte-exact; scene opens in the host editor with correct hierarchy (object counts equal) | 2–4 |
| M2 | `rsx2hlsl` over all programs | All 892 FP + 390 VP translate; 100 % compile (d3dcompiler); ShaderLab state preserved; golden-image test passes for 5 representative shaders | 2–4 |
| **M3 (VS-1)** | Scene renders in Windows build | x64 build shows the scene; screenshots from 3 fixed camera poses match RPCS3 captures (manual review + perceptual metric, threshold agreed at M3 start) | 1–2 |
| M4 | Logic toolchain T2–T5 | On a 50-method benchmark set: T5 drafts ≥70 % of bodies needing only review; measured minutes/method recorded | 3–6 |
| M5 | Reconstruct slice closure | Closure (incl. virtual calls once E53 is solved) compiles; differential tests pass on all methods with captured samples (target ≥90 % of closure covered by samples) | 6–16 |
| M6 (VS-2) | Boy walks in the rain | Same scene: walk route, camera follow, region enter/exit, silhouettes in rain; side-by-side with RPCS3 shows the same region/trigger events (logged) and visually matching rendering | 2–4 |
| M7 | Platform layer | API surface (E58) 100 % implemented or justified no-op; save round-trip; pad + vibration; videos; SGX banks play with correct bus/category behaviour in 3 test scenes | 4–8 |
| M8 (VS-3) | Opening sequence | Boot → title → first chapter scenes as in RPCS3 session 1, with audio/video; no crash in a 30-min run | 4–8 |
| M9 | Full game | Every scene converted; full playthrough; per-chapter comparison checklist | many months |

**Indicative total to VS-3: roughly 6–12 months; full game: 12–24+ months.** The largest swing factor is M4/M5 throughput.

---------------------------------------------------------------------------------------------------------------------
## 7. Comparing the port against the original (RPCS3 as oracle)

1. **Method-level differential testing**: RPCS3 GDB stub (E49) breakpoints at AOT method addresses (known for every method,
   E21) capture `this` fields (layout E52), arguments (PPC64 ABI: r3.., f1..) and return values; the port replays them in
   unit tests. Pure/state-light methods first.
2. **Event traces**: log the same high-level events in both (scene loads, region enter/exit, trigger fires, SGX calls, save
   calls) through breakpoints on known methods in RPCS3 and instrumentation in the port; compare sequences.
3. **Golden images**: fixed scenes/camera poses captured from RPCS3 (its own screenshot facility, not desktop capture) vs the
   port at the same resolution.
4. **Audio A/B** on fixed triggers; **timing**: frame pacing and scripted sequence durations.
5. **Content round-trip**: object counts and byte-exact consumption per converted file.

Limits: RPCS3 is not a perfect PS3 (minor emulation inaccuracies are possible); its inputs are not deterministic, so
comparisons use event sequences and fixed poses, not frame-exact replays.

---------------------------------------------------------------------------------------------------------------------
## 8. Risks and uncertainties that could change the plan

| Risk | Impact | Likelihood | Mitigation / decision point |
|---|---|---|---|
| Suitable Unity host version unobtainable or unactivatable | High: forces option C/D | Unknown | M0 spike first |
| Reconstruction throughput too low (manual) | High: timeline ×2–3 | Medium | M4 lifter benchmark; go/no-go after M4 |
| Rain-custom engine behaviour (E59) with no host equivalent | Medium | Unknown | Detected by M3/M6 comparisons |
| Asset formats (textures/meshes/particles) harder than MonoBehaviours | Medium | Medium | M1 decides between own decoders and existing tools |
| Physics/animation drift vs PhysX 2.8 / legacy systems | Medium | Medium (higher for option C) | Prefer option A/B |
| SGXD codecs/semantics | Medium | Medium | Early bank survey in M7 (can start in parallel) |
| Shroud cloth replacement quality | Low–Medium (visual) | Medium | Accept "cloth off" until M8 |
| FIX build differs from retail beyond re-signing (E50) | Medium (validation trust) | Unknown | Owner's RAP → decrypt retail, diff (pending) |
| Legal: redistribution | High | — | Bring-your-own-copy converter; no game data or keys in repo |

---------------------------------------------------------------------------------------------------------------------
## 9. First implementation milestone for approval: M0

1. **Host spike**: obtain and activate the candidate Unity version(s) (A, and B if x64-capable); build an empty x64 D3D11
   player; record versions/licensing in DECISIONS.md.
2. **Skeleton generator (T1)**: emit C# for all types of the 4 game assemblies + NGUI/Boo/UnityScript references and the
   PS3 API shim stubs; compile in the chosen host.
3. **RPCS3 probe harness**: connect to the GDB stub; break on `RegionBox.OnRegionTriggerEnter` (0x1B0600), dump `this` (E52
   layout) and the `RegionTrigger` vtable, and resolve E53.
4. **Slice scene choice**: identify the VS-1/VS-2 scene from the session-1 load order (E51) and the `SceneTable` data.

Acceptance: items 1–3 demonstrated with logs/artifacts committed (no game data); item 4 recorded with evidence.
Each item needs installs or state changes outside the workspace (Unity editor; RPCS3 debugger use), so I will ask before each.
