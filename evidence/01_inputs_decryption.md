# Evidence — Inputs, decryption, retail verification

Part of the split evidence log; index and conventions: [../EVIDENCE.md](../EVIDENCE.md).


## Inputs
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E1 | `Rain.pkg` sha1 `0881bcce…41d`: retail PS3 PKG (rev 0x8000), content `UP9000-NPUA80719_00-RAIN000000000001`, 1530 entries, 2.21 GB | V | header parse; full decrypt+extract, PNG/MP4 outputs valid |
| E2 | `RAIN_NPUA80719_FIX_421.pkg` sha1 `6ff365d4…f49`: debug-type PKG `…RAINFUGAZIFIX355` (scene fix), 37 entries: EBOOT + all 25 SPRX + title_flow.mp4 + icons | V | same |
| E3 | Retail EBOOT/SPRX/KEYFILE.EDAT = NPDRM **license 2 (local, needs RAP)**. No RAP available. | V | `tools/npd_info.py` |
| E4 | FIX EBOOT = NPDRM license 3 (free), key rev 0x19; FIX SPRX = license 3, key rev 0x1C, app_type 0x20 | V | `tools/npd_info.py` |

## Decryption
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E5 | FIX EBOOT decrypts with NP_KLIC_FREE → `work/fix_elf/EBOOT.elf` (sha1 `3f9bff49…`), PPC64 BE ELF, entry 0xC38720 | V | RPCS3 v0.0.42 `--decrypt`; `tools/self_decrypt.py --free` output **byte-identical** |
| E6 | FIX SPRX do **not** use NP_KLIC_FREE (RPCS3: "Failed to decrypt SELF metadata info"); they decrypt with an **all-zero klicensee** | V | `tools/klic_check.py` (32 pad bytes zero), then all 25 decrypt with every zlib stream inflating to exact p_filesz |
| E7 | PRXManager.prx segments (0x4998 text / 0x49A0 data, memsz 0x320) match shipped `Media/modules_info.txt` | V | cross-check |
| E8 | `Media/Managed/*.dll.sdat` = SDAT (flags 0x0100000D: compressed+encrypted-key), decrypt without license → 10 valid .NET PE assemblies in `work/managed_il/` | V | `tools/sdat_decrypt.py` (port of RPCS3 unedat/lz), **every block AES-CMAC verified** |

## Content of decrypted code
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E9 | Engine = **Unity 3.5.8f1**, PS3 player, Mono runtime with AOT (146 `mono_*` strings in EBOOT incl. `mono_aot_*`) | V | `mainData` header string "3.5.8f1"; EBOOT strings |
| E10 | **All IL method bodies are stripped**: every non-abstract MethodDef body is the single byte `0x2A` (`ret`) in all 10 assemblies | V | `tools/il_body_check.py`; REA `inspect_managed_members` (0 call edges / 0 ldstr) |
| E11 | IL metadata intact: Assembly-CSharp has 1305 types, 13951 fields, 8490 methods, 295 properties; UnityEngine.dll.mdb (debug symbols) shipped | V | REA `inspect_managed_members` summary |
| E12 | AOT images belong to the same build as retail IL: each `*.dll.prx` embeds its assembly's exact MVID (e.g. Assembly-CSharp `70F9671C-C082-4EEC-9E63-E46AB33DF7DC`) | V | GUID string match |
| E13 | AOT PRX text is valid PPC64-BE (99.96% decode); e_type 0xFFA4 (SCE PRX); no named `mono_aot_*` symbols inside the PRX | V | capstone sweep |
| E14 | **Verified (E62)**: FIX binaries are the retail build: all 25 SPRX byte-identical after decryption; EBOOT differs only in 2 SDK-version header fields | V | retail decrypted with owner's RAP |
| E15 | Native plugins: `ShroudUnityPlugin.prx` (2.4 MB, purpose U), `RainPS3Utility.prx` (6.5 KB), `PRXManager.prx` | V (exist) / U (role) | listing |

## Assets
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E16 | Unity serialized files: `mainData`, 582 `levelN`, 583 `sharedassetsN.assets`, `resources.assets` (53 MB), `unity default resources`; format v9, **big-endian**, target platform 10 (PS3) | V | header bytes |
| E17 | Audio: `Resources/SGX/*.sgh/.sgb/.sgd` = Sony **SGXD** banks (magic `SGXD`); `.sgb` bodies start with AC-3 sync `0B77` | V (magic) / I (codec of all banks) | header bytes |
| E18 | Video: 8 MP4 (opening, title flow, ending, endroll; NTSC+PAL), 562 MB | V | `file` |

## Retail verification (2026-10-16)
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| E61 | Owner's rip (`BASE GAME CLEAN/`): PKG byte-identical to `BASE GAME/Rain.pkg` (sha1 0881bcce…); RAP for `UP9000-NPUA80719_00-RAIN000000000001` (16 B). RAP → NPDRM key per RPCS3 `rap_to_rif` (`tools/rap2klic.py`); key passes the strict metadata check on retail EBOOT and SPRX; all 26 retail binaries decrypt (`work/retail_elf/`). Derived key kept only in git-ignored `work/license/` | V | sha1, klic_check, self_decrypt |
| E62 | Retail vs FIX after decryption: **25/25 SPRX byte-identical**; EBOOT differs in exactly 2 bytes = `sdk_version` in `sys_process_param` (@0xC12900) and `sys_process_prx_param` (@0xC12928): retail 0x00430001 (SDK 4.30) → FIX 0x00340001 (3.40), a firmware-compatibility patch. **No code changed** ⇒ all analysis done on FIX binaries applies unchanged to retail | V | segment/byte diff |
