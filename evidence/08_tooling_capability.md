# Evidence — Tooling available on this host (REA, Ghidra, ...)

Part of the split evidence log; index and conventions: [../EVIDENCE.md](../EVIDENCE.md).


## Tooling capability (this host)
| ID | Finding | Conf | Method |
|----|---------|------|--------|
| T1 | REA rejects PS3 PKG ("unsupported binary format") and PPC64 ELF ("unsupported ELF architecture", also with provider_id=ghidra) | V |
| T2 | REA rizin/objdump providers unavailable (`ERR_REA_WINDOWS_NATIVE` — not installed) | V |
| T3 | REA managed (.NET metadata) tools work on the decrypted assemblies | V |
| T4 | Installed: Python 3.14 (venv `tools/.venv`: pycryptodome, capstone 5, dnfile), JDK 21, RPCS3 v0.0.42 (FW 4.93), git, **Ghidra 12.1.4** (`%USERPROFILE%\tools\ghidra_12.1.4_PUBLIC`; Phase 1 missed it). Not installed: IDA, rizin, ILSpy, AssetRipper, Unity 3.5, MSVC/cmake | V |
| T5 | REA 6.5.0 providers on this host: ghidra=available, ida=not_configured, hopper/native-macos=unsupported_host; rea-dotnet-static + rea-artifact-graph available. Full list: `work/rea_capabilities.txt` | V | `binary_session` |
| T6 | REA's PPC64 rejection happens in its own ELF validation, before the Ghidra provider → REA's native tools (decompile, xrefs, annotate) are unusable for this target even though Ghidra is present | V | open_binary with provider_id=ghidra |
| T7 | Ghidra headless directly (outside REA) imports PS3 PRX with generic ELF loader as `PowerPC:BE:64:64-32addr` (PS3 ABI language exists in stock Ghidra); no PS3-specific loader installed (NID imports/relocs not resolved by Ghidra itself) | V | `ghidra/probe/import_prx.log` |
| T8 | Ghidra headless full analysis of Assembly-CSharp.dll.prx: succeeded (~25 min), 8303 functions found (vs 8396 mapped methods), 0 relocations applied; 4/4 sampled functions decompile without warnings, but GOT accesses appear as `PTR_DAT_00000000+off` and runtime/PLT calls as anonymous `FUN_*` → readability depends on resolving Mono GOT slots (got_info_offsets + blob) and PLT targets | V | `ghidra/probe/acs_sample.txt`, project `ghidra/probe/probe.gpr` |
