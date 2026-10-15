#!/usr/bin/env bash
# Phase 3 pipeline for one assembly (Assembly-CSharp). Run from DECOMP/ after reproduce_phase1.sh.
# Ghidra project ghidra/probe must contain the analyzed Assembly-CSharp.dll.prx (see PROJECT_STATUS.md).
set -euo pipefail
PY="tools/.venv/Scripts/python -I"; A=Assembly-CSharp
$PY tools/prx_exports.py work/fix_elf/$A.dll.prx work/aot_names_acs.txt > work/acs_exports.txt
$PY tools/aot_method_map.py work/managed_il/$A.dll work/fix_elf/$A.dll.prx work/acs_exports.txt work/maps/$A.methods.csv
$PY tools/aot_decode.py work/fix_elf/$A.dll.prx work/acs_exports.txt work/managed_il work/maps/$A.got.csv
$PY tools/aot_decode.py work/fix_elf/$A.dll.prx work/acs_exports.txt work/managed_il work/maps/$A.got.csv --plt
# relocs CSV, TSV conversion and Ghidra scripts: see PROJECT_STATUS.md "Phase 3 pipeline" (ApplyMethodNames, ApplyAotAnnotations)
$PY tools/unity_mb_decode.py extracted/Rain/USRDIR/Media work/managed_il work/maps/monobehaviour_decode_summary.csv
