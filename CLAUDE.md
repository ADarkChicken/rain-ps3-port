# Rain PS3 → Windows port: standing rules for Claude

State lives in `PROJECT_STATUS.md` (read it first, then only the evidence pool you need via `EVIDENCE.md`).
Never start a new phase/milestone without the user's approval. Keep chat reports short; details go in workspace files.

## Hard rules
- Repo is **public** (github.com/ADarkChicken/rain-ps3-port). `.gitignore` is an allow-list; never commit game data,
  decompiled dumps, `work/recon`, GOT/PLT CSVs or `tools/keys.local.json` (`.git/hooks/pre-commit` refuses them). Push only when asked.
- `../BASE GAME*` is read-only. Python: `tools/.venv/Scripts/python -I tools/<tool>.py` from `DECOMP/`.
- `port_unity/` is not in git; its scripts are copies of `tools/unity/` (source of truth).
- New findings: next free evidence ID is in `EVIDENCE.md`; add the row to the matching `evidence/*.md` pool.

## M5 reconstruction workflow (one type). Applies only while PROJECT_STATUS says M5 is the current work
1. `tools/recon_init.py Assembly-CSharp <Type>` (skip if `work/recon/<Type>.cs` exists)
2. `bash tools/recon_view.sh <Type> [<Type>.<Nested> ...]`: skeleton fields/signatures + packets of the methods still stubbed
   (`--all` = every method). Open `work/decomp_st01/<Type>.decomp.txt` only when a packet says `recv? check asm`,
   `arg missing: check asm` (~9 %: Ghidra drops int args after floats), `SWITCH:`, or shows mangled vector math.
3. Fill with `tools/recon_fill.py`: `fill(type, {"Name(": body})` replaces stubs (key = `'Name('` or exact line prefix).
4. `tools/lift_compile.py Assembly-CSharp work/recon/*.cs` (~1 s; also runs automatically after edits to `work/recon/*.cs`)
5. `tools/recon_status.py` updates `work/recon/QUEUE.csv`. Work the queue smallest-first.

Conventions:
- Stores that come before the base .ctor call become field initializers.
- Unity 3.5 `Component.renderer/camera/collider` → `GetComponent<T>()`.
- Inlined getters/setters listed in a packet → call the method, not the field.
- PS3 engine API → Unity 2017: `Transform.TransformPoint2(in, ref out)` = `TransformPoint`,
  `Vector3.Normalize2(in, out)` = `.normalized`, `InteractiveCloth` = `Cloth`.
- Keep the original's quirks and mark them `// sic 0x<asm addr>`.

Lookups:
- Field offsets: `annotate_decomp.layout(il_dir, asm, type)` gives {offset: field}.
- Virtual slots: `tools/vtable.py work/managed_il <Type>`.

Re-lift after a tool change (~4 min):
`lift.py work/managed_il Assembly-CSharp @work/decomp_st01/types.txt work/decomp_st01 work/lift_st01`.
`RendererCollectorManager/{RendererArray2D,OBBArray2D}` fail there (generic TypeSpec base): ctor only, read the decomp.
DecompileNamespace takes `work/maps/Assembly-CSharp.got.csv` as its 3rd arg (switch recovery).

Delegation: the `recon-type` subagent (`.claude/agents/recon-type.md`) does one type per fresh context. Prefer it for
queue batches, so the main session only tracks progress. Cost is ~40-80k tokens/type. Ask the user before a type
predicted to be bigger, and before tool changes, Ghidra mass runs or RPCS3 sessions.
