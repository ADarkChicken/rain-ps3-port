# DECISIONS

| # | Date | Decision | Rationale | Alternatives / open trade-offs |
|---|------|----------|-----------|-------------------------------|
| D1 | 2026-10-15 | Own Python extract/decrypt tools in `tools/` (venv), algorithms ported from RPCS3 open source (`tools/ref_rpcs3/`) | REA cannot open PS3 PKG/SELF; RPCS3 CLI can't take a zero klic nor SDAT; ports are verifiable (byte-identical to RPCS3, CMAC per block) | Installing PKG into RPCS3 (mutates emulator state); scetool/TrueAncestor (unvetted binaries) |
| D2 | 2026-10-15 | Use FIX_421 binaries (free/zero-klic) as the code source; do not pursue retail RAP | Same build as retail per MVID match (E12); no license file present | If user owns the title, a RAP would allow a direct retail diff to upgrade E14 to verified |
| D3 | 2026-10-15 | No full decompilation or port design started | Phase 1 scope; awaiting approval of strategy (FEASIBILITY.md) | — |

| D4 | 2026-10-15 | Use Ghidra headless directly (not via REA) for PPC64; use REA for .NET metadata | REA rejects PPC64 ELF before provider dispatch (T6); Ghidra supports PowerPC:BE:64:64-32addr (T7/T8) | IDA (not configured); rizin (not installed) |
| D5 | 2026-10-15 | Map native code to C# via Mono AOT `code_offsets` rather than heuristics | Verified exact mapping (E21) | Signature/pattern matching (unnecessary) |

| D6 | 2026-10-15 | Phase 3 subsystem = "AOT code readability" (GOT/PLT/relocs) + 1 PoC class, then bounded checks of data (MonoBehaviour) and shader (RSX FP) decoding | Highest-impact unknown from Phase 2; each check generalised to the whole game for a measurable coverage figure | Starting with gameplay subsystems before tooling (would be slow and error-prone) |
| D7 | 2026-10-15 | Mono reference = upstream mono/mono@8219a5b (v67) rather than Unity's public 2.6 branches (v66) | Exact struct/symbol match with binary | Unity 3.x branches (version mismatch) |

Pending user decisions: see FEASIBILITY.md §5.
