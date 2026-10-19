"""Start a reconstruction file: copy the skeleton declaration of top-level type(s) to work/recon/<Type>.cs (refuses to
overwrite). Bodies stay `throw NotImplementedException` until reconstructed from work/lift_st01/<Type>.md.
Usage: recon_init.py <assembly> <Type> [...]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lift_compile import top_level_types, ROOT

def main(asm, types):
    skel = open(os.path.join(ROOT, "work", "skeleton", asm + ".cs"), encoding="utf-8").read()
    decl = {n: skel[st:en] for n, st, en in top_level_types(skel)}
    for t in types:
        out = os.path.join(ROOT, "work", "recon", t + ".cs")
        d = decl[t] if "." not in t else f"namespace {t.split('.')[0]}\n{{\n{decl[t]}\n}}"   # "N.Type": keep the namespace
        with open(out, "x", encoding="utf-8") as f:
            f.write(f"// Reconstructed from Rain (NPUA80719) {asm} AOT code (M5). Source: work/lift_st01/{t}*.md\n{d}\n")
        print(out)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
