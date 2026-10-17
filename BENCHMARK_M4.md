# M4 benchmark: logic reconstruction throughput (fixed before starting, 2026-10-17)

Acceptance (PORTING_PLAN.md §6): on a ≥50-method set, **≥70 % of methods "need only review"** after the toolchain;
minutes per method recorded. Result decides go/no-go for M5.

## Set (53 methods, 6 Assembly-CSharp classes attached in Stage 1, chosen by size spread and use count)
| Class | Methods | Code bytes | Instances in st01 |
|---|---|---|---|
| RegionTriggerCameraArea | 6 | 864 | 142 |
| TriggerCondition_EventFlag | 5 | 1,808 | 42 |
| ActiveSwitchTrigger | 10 | 2,144 | 52 |
| PathCameraArea | 12 | 2,320 | 142 |
| DisplayRange | 12 | 2,768 | 7 |
| RegionTriggerEmitter | 8 | 3,456 | 367 |
Excluded: classes already reconstructed (RegionBox, CameraConstrainForRainEffect, RainMergePostEffect).

## Procedure per class
1. Ghidra decompile (`DecompileNamespace.java`) → `tools/lift.py` lift packets (T2–T5).
2. Write the complete class in C# from the packets, starting from the skeleton class (fields/attributes verbatim).
3. `tools/lift_compile.py Assembly-CSharp <class>.cs` until 0 errors.
4. Record per method: class A/B/C and notes; per class: wall-clock start/end.

## Classification
- **A — review only:** written from the packet alone; any fixes were mechanical (C# types for temporaries, casts,
  bool tests, 3.5→2017 API renames, struct temporaries).
- **B — extra RE:** needed sources beyond the packet (disassembly, another type's decompile, metadata lookups the packet
  did not provide, runtime knowledge) or semantic rework after a compile/logic problem.
- **C — not reconstructed** (left as stub, with reason).
Metric: A / (A+B+C). Minutes/method = class wall-clock / methods.

## Limits of this benchmark
Correctness is checked statically (compiles against the full skeleton + reviewed line by line against the
pseudocode). Runtime differential tests (RPCS3 captures) are M5 work and will re-grade a sample.

## Results (2026-10-17)
| Class | Methods | A | B | Wall-clock (s) |
|---|---|---|---|---|
| RegionTriggerCameraArea | 6 | 4 | 2 | 59 |
| TriggerCondition_EventFlag | 5 | 5 | 0 | 52 |
| ActiveSwitchTrigger | 10 | 10 | 0 | 57 |
| PathCameraArea | 12 | 8 | 4 | 84 |
| DisplayRange | 12 | 9 | 3 | 47 |
| RegionTriggerEmitter | 8 | 8 | 0 | 67 |
| **Total** | **53** | **44 (83 %)** | **9** | **366 (≈ 7 s/method)** |

**Acceptance met: 83 % ≥ 70 %.** All 6 classes (+ the 2 Phase-3 classes) compile together against the full skeleton
(`lift_compile.py`, 0 errors); C = 0. Per-method grades and notes: `work/bench_results.csv`; reconstructions:
`work/recon/*.cs` (local; reconstructed game code is not committed).

**Causes of B (9):** static fields reached through the raw GOT pointer (`PTR_got_IMAGE + off`, not named in the packet)
×6; private field read = getter inlined by the AOT compiler (`IsAreaActive`, `TargetManager.GetInstance`) ×2; Ghidra
lost two arguments of a virtual call (asm showed them) ×1. Seven of the nine are tool-addressable (raw-GOT naming,
inlined-getter index), which would put the set at ≈ 96 % A.

**Caveats (read before using the number):**
- The reviewer is Claude in this session; the wall-clock time is the AI's and says nothing about a human's speed.
- Tool fixes made during the run (before a class's clock started): base-class reference alignment, field chains,
  cross-assembly enums, METHOD_RGCTX generic arguments at call sites, local-variable types, refreshed Ghidra labels
  after T4. Time spent on those is not in the table.
- Correctness is static (compiles + reviewed against pseudocode). Behaviour is not yet tested; M5's RPCS3 differential
  tests will re-grade a sample. Observed so far: Ghidra pseudocode can drop arguments (1 case), so asm spot-checks stay
  part of review.

**Go/no-go: GO** on throughput; risk moves to behavioural validation in M5.
