#!/usr/bin/env bash
# M0 reproduction: build the host-compile Unity 2017.4 project from generated skeletons + PS3 shims (run from DECOMP/).
# Needs: Unity 2017.4.40f1 at $U (activated: C:/ProgramData/Unity/Unity_lic.ulf), work/managed_il/*.dll (phase 1).
set -euo pipefail
U="${U:-G:/Decomp/Rain/_tools/Unity-2017.4.40f1/Editor/Unity.exe}"; P="${P:-G:/Decomp/Rain/_tools/m0_host_compile}"
PY="tools/.venv/Scripts/python -I"; M=work/managed_il; S=work/skeleton; mkdir -p "$S"
R="$M/UnityEngine.dll $M/mscorlib.dll $M/System.dll $M/Boo.Lang.dll $M/UnityScript.Lang.dll"
$PY tools/skeleton_gen.py $M/Assembly-CSharp-firstpass.dll $S/Assembly-CSharp-firstpass.cs $R
$PY tools/skeleton_gen.py $M/Assembly-UnityScript-firstpass.dll $S/Assembly-UnityScript-firstpass.cs $R
$PY tools/skeleton_gen.py $M/Assembly-CSharp.dll $S/Assembly-CSharp.cs $R $M/Assembly-CSharp-firstpass.dll $M/Assembly-UnityScript-firstpass.dll
$PY tools/skeleton_gen.py $M/Assembly-UnityScript.dll $S/Assembly-UnityScript.cs $R $M/Assembly-CSharp-firstpass.dll $M/Assembly-UnityScript-firstpass.dll
$PY tools/skeleton_gen.py $M/UnityEngine.dll $S/Rain.Platform.Shims.cs --only PS3DRMUtility,PS3Info,PS3Move,PS3Pad,PS3ReturnCode,PS3SaveDataUtility,PS3SystemUtility,PS3TrophyUtility,PS3VideoPlayer,SGXBody,SGXData,SGXHeader,SGXListener,SGXSettings,SGXSource,SGXStream,WavClip $M/mscorlib.dll
"$U" -batchmode -quit -createProject "$(cygpath -w "$P")"
A="$P/Assets"; MONO="$(dirname "$U")/Data/Mono/lib/mono/unity"; mkdir -p "$A/Plugins" "$A/Scripts" "$A/Rain.Firstpass" "$A/Rain.UnityScript"
cp "$MONO/Boo.Lang.dll" "$MONO/UnityScript.Lang.dll" "$A/Plugins/"
cp $S/Rain.Platform.Shims.cs $S/Assembly-CSharp-firstpass.cs $S/Assembly-UnityScript-firstpass.cs "$A/Rain.Firstpass/"
cp $S/Assembly-UnityScript.cs "$A/Rain.UnityScript/"; cp $S/Assembly-CSharp.cs "$A/Scripts/"
printf '{\n    "name": "Rain.Firstpass"\n}\n' > "$A/Rain.Firstpass/Rain.Firstpass.asmdef"
printf '{\n    "name": "Rain.UnityScript",\n    "references": [ "Rain.Firstpass" ]\n}\n' > "$A/Rain.UnityScript/Rain.UnityScript.asmdef"
"$U" -batchmode -quit -projectPath "$(cygpath -w "$P")" -logFile "$(cygpath -w "$P.compile.log")"
echo "compile errors: $(grep -cE 'error CS[0-9]+' "$P.compile.log")"
