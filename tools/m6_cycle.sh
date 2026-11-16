#!/bin/bash
# M6 headless cycle (from DECOMP/): export -> sync scripts -> reimport -> playtest -> tally. Usage: bash tools/m6_cycle.sh [frames] [noimport]
cd "$(dirname "$0")/.." || exit 1   # DECOMP/
P=G:/Decomp/Rain/port_unity; U=../_tools/Unity-2017.4.40f1/Editor/Unity.exe; F=${1:-10}
cp tools/unity/Rain*.cs $P/Assets/Editor/
if [ "$2" != "noimport" ]; then
  PL=$(grep "st01_Prefab_" work/maps/level_names.txt | cut -f1 | tr '\n' ' ')
  tools/.venv/Scripts/python -I tools/rain_export.py extracted/Rain/USRDIR/Media work/export/st01 level4 $PL --resident=level0 --resident=mainData > work/export/st01_export.log 2>&1 || { echo EXPORT FAILED; tail -5 work/export/st01_export.log; exit 1; }
  tail -c 420 work/export/st01_export.log; echo
  rm -rf $P/Assets/Rain/st01 $P/Assets/Rain/st01.meta
  $U -batchmode -quit -projectPath $P -executeMethod RainImport.Run -rainExport G:/Decomp/Rain/DECOMP/work/export/st01 -rainScene st01 -logFile G:/Decomp/Rain/_tools/port_import_st01.log
  grep -a "^RAIN IMPORT\|error CS" ../_tools/port_import_st01.log | cut -c1-300 | tail -8
fi
$U -batchmode -projectPath $P -executeMethod RainPlayTest.Run -rainScenePath Assets/Rain/st01/st01.unity -rainFrames $F -rainShot G:/Decomp/Rain/DECOMP/work/m6_play.png -logFile G:/Decomp/Rain/_tools/port_playtest.log
grep -a "error CS" ../_tools/port_playtest.log | sort -u | cut -c1-260 | head -20
grep -a "RAIN PLAYTEST: \|^DIAG" ../_tools/port_playtest.log | cut -c1-400
tools/.venv/Scripts/python -I tools/unity_log_tally.py G:/Decomp/Rain/_tools/port_playtest.log 40 1 | cut -c1-170
