#!/usr/bin/env bash
# Rebuilds all Phase 1 derived artifacts from the original PKGs (read-only). Run from DECOMP/.
# Prereq: python -m venv tools/.venv && tools/.venv/Scripts/python -m pip install pycryptodome capstone dnfile
set -euo pipefail
PY="tools/.venv/Scripts/python -I"
$PY tools/pkg_extract.py "../BASE GAME/RAIN_NPUA80719_FIX_421.pkg" extracted/FIX_421
$PY tools/pkg_extract.py "../BASE GAME/Rain.pkg" extracted/Rain
mkdir -p work/managed_il work/fix_elf
for f in extracted/Rain/USRDIR/Media/Managed/*.sdat; do $PY tools/sdat_decrypt.py "$f" "work/managed_il/$(basename "$f" .sdat)"; done
cp extracted/Rain/USRDIR/Media/Managed/UnityEngine.dll.mdb work/managed_il/
$PY tools/self_decrypt.py extracted/FIX_421/USRDIR/EBOOT.BIN work/fix_elf/EBOOT.elf --free
find extracted/FIX_421/USRDIR/Media -name '*.sprx' | while read -r f; do
  $PY tools/self_decrypt.py "$f" "work/fix_elf/$(basename "$f" .sprx).prx"   # zero klicensee (default)
done
$PY tools/il_body_check.py work/managed_il/*.dll
