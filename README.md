# Rain (PS3) — reverse engineering toward a Windows-native port

Research workspace for *Rain* (PlayStation 3, NPUA80719, Unity 3.5.8f1). It holds tooling, Ghidra scripts and
documentation for analysing a copy of the game you own, plus a small amount of reconstructed source.

**This repository contains no game data, no game binaries and no decryption keys.**
You need your own copy of the game, and you must supply the PS3 crypto constants locally (see below).

## Status
Stage 1 runs in Unity 2017.4 (x64): scene, shaders, lightmaps, reconstructed gameplay scripts, physics and
animation data import from the original game files; the walk/camera loop is being validated (milestone M6).
See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) (entry point), [`FEASIBILITY.md`](FEASIBILITY.md),
[`ARCHITECTURE.md`](ARCHITECTURE.md), [`EVIDENCE.md`](EVIDENCE.md) and [`DECISIONS.md`](DECISIONS.md).

## Layout
| Path | Content |
|------|---------|
| `tools/` | Python tools: PKG extraction, SDAT/SELF decryption, PRX export/NID resolution, Mono AOT (v67) method map + GOT/PLT decoder, Unity 3.5 serialized-file inventory, byte-exact class readers, scene exporter and MonoBehaviour decoder, RSX fragment-program disassembler, HLSL compile check |
| `tools/unity/` | Unity 2017.4 editor/runtime scripts: scene importer, headless play test, player build |
| `tools/native/` | Windows stand-ins for PS3 native plugins (platform layer, not reconstructed code) |
| `ghidra/scripts/` | Ghidra 12 headless scripts: apply C# method names, apply Mono AOT annotations (relocs, GOT labels, PLT stubs), decompile a type |
| `work/poc/` | Proof-of-concept reconstruction (one C# class, one HLSL shader) |
| `FUNCTION_INDEX.csv` | Method index (token, address, type, method) for Assembly-CSharp |

## Setup
1. Python 3.11+: `python -m venv tools/.venv && tools/.venv/Scripts/python -m pip install -r tools/requirements.txt`
2. Copy `tools/keys.example.json` to `tools/keys.local.json` and fill in the values. The file's `_comment` lists
   where each constant is defined in the public RPCS3 source. `keys.local.json` is git-ignored.
3. Put your game PKG files in `../BASE GAME/` and run `bash tools/reproduce_phase1.sh` from this directory.
4. Ghidra 12.x for the native analysis (see `PROJECT_STATUS.md`, "Phase 3 pipeline").

## Legal
*Rain* is © Sony Interactive Entertainment. This is an independent research project, not affiliated with or endorsed
by Sony, Unity Technologies, CloakWorks or the NGUI authors. Algorithms ported from RPCS3 and Mono are credited in the
respective tool headers.
