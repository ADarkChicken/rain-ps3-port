# Phase 1 Feasibility Report — Rain (PS3, NPUA80719)

## 1. Bottom line
A Windows-native port is **technically feasible**. The best path does not port the engine. It reconstructs the game's
C# scripts and runs them on a Windows Unity runtime. All game code is now decrypted and readable (E5–E8, E12).
The main cost and risk is reconstructing behavior from **PPC64 AOT machine code**, because the IL bodies were stripped (E10).
REA cannot analyze PPC64 on this host (T1, T2), so a PPC64 disassembler/decompiler is a prerequisite.

## 2. What we have (verified)
- Full retail content (assets, audio, video, IL metadata) and the decrypted code for the same build: Unity player EBOOT
  (12.9 MB ELF), 10 AOT assemblies, and 3 native PRX (`work/fix_elf/`).
- Complete C# **metadata**: every type, field, method name, signature, and property of the game scripts. This gives
  names and structure for free. There is **no IL logic**.
- Engine: Unity **3.5.8f1** (2012-era). Assets are Unity v9 big-endian PS3 serialized files.

## 3. What this means
| Task | Status |
|------|--------|
| Decompilation of C# from IL (ILSpy-style) | **Not possible**: bodies stripped (E10) |
| Decompilation of game logic from PPC64 AOT | Possible; needs Ghidra-class tool + Mono-AOT method→token mapping (U: tables located but format not yet parsed) |
| Reimplementing PS3 engine (EBOOT) | Not needed for strategy S1 |
| Asset reuse | Feasible in principle; PS3→PC conversion tooling for Unity 3.5 BE is **unverified** |
| Audio | SGXD banks (AC-3 seen); converter support **unverified** |
| Shaders | PS3 Unity builds normally ship only RSX-compiled programs → custom shaders likely need re-authoring (**U**, not yet inspected) |
| Native plugins | `ShroudUnityPlugin` (2.4 MB) role unknown; requires RE |

## 4. Candidate strategies (for approval — none started)
**S1 — Unity re-host (recommended).** Rebuild the scripts (Assembly-CSharp and friends) as C# source. Use the IL
metadata as the skeleton and the decompiled PPC64 AOT as the behavior source. Then build for Windows x64 on a
compatible Unity version with converted assets. Fidelity checks run differentially against RPCS3 running the FIX build
as a reference oracle.
Scale (estimate): ~8.5k methods / 3.75 MB of PPC64 text in Assembly-CSharp. Many will be trivial accessors.
Risks: Unity 3.5 editor/licensing availability or the need to target a newer Unity (behavior drift); asset/shader
conversion; plugin RE.

**S2 — Static recompilation (PPC64→x64) + HLE of PS3 OS/RSX.** Highest fidelity to the binary, but it reimplements a
large part of an emulator (LV2 syscalls, ~76+ cell* libs, RSX graphics, SPU). Very large effort. Not recommended as primary.

**S3 — RPCS3 emulation.** This is not a port. It is useful only as the **reference oracle** for S1 and is not yet tested.

## 5. Decisions needed from you before Phase 2
1. Approve S1 as the working strategy (or choose S2).
2. Allow installing analysis tools: **Ghidra** (JDK 21 is present) plus a PS3 PRX/ELF loader extension (to be evaluated).
   Optionally rizin, so REA's rizin provider works, and ILSpy for metadata browsing.
3. Allow installing the FIX build into your RPCS3 (`dev_hdd0`) to test whether it runs as a reference oracle.
   This changes emulator state, not the originals.
4. Optional: if you own the title and have its RAP, it would let the retail binaries be decrypted and diffed against
   the FIX build, which would turn E14 from inference into verified fact.

## 7. Phase 2 foundation update (2026-10-15) — supersedes §3/§6 where they differ
**Resolved since Phase 1:** Native↔C# method mapping is verified (E21/E22). Ghidra 12.1.4 is installed and decompiles
the AOT PPC64 code (T8). Shaders keep their ShaderLab state, and their programs are RSX microcode, which can be
translated mechanically (E27). Shroud = CloakWorks cloth middleware (E28). Audio is fully non-Unity (E29).
NGUI accounts for ~99 types (E25).

**Feasible analysis forms**
| Form | Status |
|------|--------|
| Disassembly (PPC64) | Yes: capstone, Ghidra |
| Decompilation (PPC64→C pseudo) | Yes via Ghidra headless; readable only after Mono GOT/PLT annotation (to build) |
| Static analysis via REA | .NET metadata only; REA native tools blocked for PPC64 (T6) |
| Source reconstruction (C#) | Yes, manual/assisted: metadata skeleton + annotated pseudocode. No IL to auto-decompile |
| Dynamic analysis | RPCS3 can run PS3 code and has a debugger; whether Rain boots is **unverified** (not tested, needs install into RPCS3) |
| Asset extraction | Container/object level verified; per-class decoding needs Unity 3.5 class layouts (type trees stripped) |

**Licensing / access concerns**
The game, code and assets are Sony IP, so a port must be "bring your own copy" (convert the user's files at install
time; ship no game data). NGUI (Asset Store license) and CloakWorks Shroud (commercial) are third-party. Unity runtime
licensing applies to whatever Unity version is used. The FIX pkg is an unofficial re-sign. The retail RAP is absent.

**Effort (ESTIMATES, low confidence)**
| Workstream | Size driver | Estimate |
|------------|-------------|----------|
| AOT annotation tooling (GOT/PLT/class info → Ghidra names/types) | Mono AOT format version-specific | 2–4 weeks |
| C# reconstruction | ~8.4k methods; NGUI (~99 types) reusable; many accessors trivial | largest item, months |
| Asset conversion pipeline | 63 classes, no type trees, BE | weeks–months (less if an existing tool supports 3.5/PS3) |
| Shader translation (RSX→HLSL) | 2588 small programs, ~60 custom shaders | weeks (automatable) |
| Audio (SGXD + Sound* logic) | codec + mixer behavior | weeks |
| Cloth (Shroud replacement) | visual fidelity only | weeks |
Overall: a playable faithful port is realistic as a multi-month effort. These are not commitments.

**Top uncertainties (ranked)**
1. Mono AOT GOT/PLT/blob decoding for this Mono version (decides how readable decompilation is). Unknown Mono version.
2. Whether a Windows Unity 3.5.x editor/player is obtainable and licensable, and otherwise how much behavior drifts on a newer Unity.
3. Asset conversion without type trees: does any existing tool support Unity 3.5 PS3 big-endian, or must we write decoders?
   Includes unknown class IDs 549/550 (24 MB).
4. Whether RPCS3 runs Rain well enough to serve as a behavioral oracle.
5. RSX microcode translation fidelity (RPCS3's decompiler can be used as a reference).

**Recommended direction:** S1 (Unity re-host).

**Smallest useful proof of concept: "one gameplay class, end to end"**
- PoC-1 Tooling: a Ghidra script that (a) creates and names every function from `code_offsets` + metadata
  (`Type::Method`), and (b) resolves GOT slots and PLT calls for the selected class's methods.
- PoC-2 Reconstruction: pick one small, self-contained MonoBehaviour from Assembly-CSharp (≤15 methods, a gimmick or
  trigger) and hand-reconstruct it to C# that compiles against the UnityEngine API.
- PoC-3 Data: decode that class's serialized MonoBehaviour fields from one level file, using the IL field layout.
- PoC-4 Shader: translate one custom shader (`Custom/RainSplash`, 11+7 instructions) from RSX microcode to HLSL.
- Side checks (each needs your OK): boot the FIX build in RPCS3, and test AssetStudio/AssetRipper on one level file.

**Acceptance criteria for that PoC phase**
1. ≥95% of the 8,396 mapped Assembly-CSharp methods are named in Ghidra as `Type::Method`, with the count verified by script.
2. For the PoC class, every GOT access and call in its methods resolves to a named field, method, class or runtime
   helper. Unresolved items are listed explicitly.
3. The reconstructed class compiles. Each method has an evidence note (address, pseudocode excerpt). Any deviation is
   marked as inference.
4. Serialized field values for ≥1 instance of the class are decoded, and the decoded types are consistent with the
   IL field list (sizes and alignment add up to the object byte size).
5. The RainSplash HLSL compiles, and its instruction semantics are documented against the microcode.
6. A go/no-go recommendation on full-scale reconstruction is made, with revised effort estimates based on measured
   per-method effort.

## 6. Proposed Phase 2 scope (Phase 1 proposal; see §7)
1. Load EBOOT + Assembly-CSharp PRX in Ghidra. Resolve PRX imports/exports (NIDs) and `.b.sprx` companions.
2. Parse Mono AOT tables to map native functions → IL MethodDef tokens. Generate `FUNCTION_INDEX.csv` with names
   from metadata. This is the key enabler; acceptance = sampled methods verified by signature and behavior.
3. Inventory assets by Unity class ID, and check converter support for v9 big-endian, shaders, and SGXD.
4. Map subsystems (game flow, player, AI, rendering hooks, Shroud plugin role) into ARCHITECTURE.md.
