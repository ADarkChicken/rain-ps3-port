#!/bin/bash
# M5 differential replay (E98): RPCS3 call samples vs the work/recon reconstruction, in Unity 2017 batchmode (~1-2 min).
# Usage (from DECOMP/): bash tools/replay.sh        -> work/replay/report.txt (previous run kept as report_prev.txt)
# Scratch project _tools/replay_2017 (.NET 4.6 runtime) must exist; Rain.Firstpass.dll is copied in once.
set -e
cd "$(dirname "$0")/.."
PY=tools/.venv/Scripts/python
P=../_tools/replay_2017
$PY -I tools/replay_cases.py work/replay work/rpcs3_logs/calls/samples_run1.jsonl work/rpcs3_logs/calls/samples_run2.jsonl \
    work/rpcs3_logs/calls3/samples.jsonl 2>/dev/null | tail -1
$PY -I tools/lift_compile.py --out work/replay/RainRecon.dll Assembly-CSharp work/recon/*.cs | tail -1
mkdir -p $P/Assets/Plugins $P/Assets/Editor
cp work/replay/RainRecon.dll $P/Assets/Plugins/
[ -f $P/Assets/Plugins/Rain.Firstpass.dll ] || cp ../_tools/m0_host_compile/Library/ScriptAssemblies/Rain.Firstpass.dll $P/Assets/Plugins/
cp tools/unity/RainReplay.cs $P/Assets/Editor/
[ -f work/replay/report.txt ] && cp work/replay/report.txt work/replay/report_prev.txt
timeout 1200 ../_tools/Unity-2017.4.40f1/Editor/Unity.exe -batchmode -quit -nographics -projectPath "$(cygpath -w "$PWD/$P")" \
    -executeMethod RainReplay.Run -replayDir "$(cygpath -w "$PWD/work/replay")" -logFile ../_tools/replay_run.log
grep "RAIN REPLAY" ../_tools/replay_run.log
# status changes since the previous run
[ -f work/replay/report_prev.txt ] && diff <(cut -f1,2 work/replay/report_prev.txt | sort -u) <(cut -f1,2 work/replay/report.txt | sort -u) | grep '^>' | grep -v '^> #' || true
