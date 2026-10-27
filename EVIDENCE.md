# EVIDENCE — Rain (NPUA80719)

Confidence: **V** = verified (directly observed/cryptographically checked), **I** = inference, **U** = unknown.
Paths relative to `DECOMP/`. Originals in `../BASE GAME/` are never written.


The evidence log is split into topic pools so a session loads only what it needs.
Each finding keeps its permanent ID; look up an ID here, then open its pool.

| Pool | Topic | IDs |
|---|---|---|
| [evidence/01_inputs_decryption.md](evidence/01_inputs_decryption.md) | Inputs, decryption, retail verification | E1–E18, E61–E62 |
| [evidence/02_code_reverse_engineering.md](evidence/02_code_reverse_engineering.md) | IL/AOT code analysis, call graph, vtables, skeleton, PoC reconstructions | E19–E43, E52–E60, E64–E65, E68, E73 |
| [evidence/03_rpcs3_oracle_captures.md](evidence/03_rpcs3_oracle_captures.md) | RPCS3 oracle, GDB harness, golden-image capture sessions | E44–E51, E66, E69, E86, E88 |
| [evidence/04_unity_host.md](evidence/04_unity_host.md) | Host engine choice and setup (Unity 4.7 / 2017.4), player builds | E63, E70–E72, E93 |
| [evidence/05_assets_scene_import.md](evidence/05_assets_scene_import.md) | Asset classes, export/import, lightmaps, probes, map instantiation, textures | E67, E74–E78, E83, E85, E87, E89, E105 |
| [evidence/06_shaders_post_effects.md](evidence/06_shaders_post_effects.md) | Shader translation, keyword bridge, post effects, colour grade | E79–E82, E84, E90–E92 |
| [evidence/07_logic_toolchain_m4.md](evidence/07_logic_toolchain_m4.md) | M4 reconstruction toolchain (T2-T5) and benchmark; M5 corrections and queue result | E94–E104 |
| [evidence/08_tooling_capability.md](evidence/08_tooling_capability.md) | Tooling available on this host (REA, Ghidra, ...) | T1–T8 |

New findings: add the row to the matching pool (next free ID: E106) and extend this table's ID list.
