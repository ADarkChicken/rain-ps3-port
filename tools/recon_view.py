"""Compact M5 view: skeleton declaration (fields + signatures) and lift packets of the given types, limited to the methods
that are still stubs in work/recon/<Type>.cs (all methods when no recon file exists yet).
Usage: recon_view.py [--all] <Type> [...]     (Type = packet name, e.g. BGMManager.BGMProperty; --all = ignore recon state)"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lift_compile import top_level_types, ROOT

NI = " { throw new global::System.NotImplementedException(); }"

def member_names(line):
    """IL method names a skeleton/recon declaration line stands for (properties -> get_/set_, ctors -> .ctor/.cctor)."""
    m = re.search(r"(\w+)\s*\{\s*(get|set)\b", line)
    if m: return {"get_" + m.group(1), "set_" + m.group(1)}
    m = re.search(r"(?:~\s*)?(\w+)\s*\(", line)
    return {m.group(1)} if m else set()

def stub_names(src):
    return set().union(*[member_names(l) for l in src.splitlines() if "NotImplementedException" in l])

def recon_file(t):
    parts = t.split(".")
    for k in range(len(parts), 0, -1):
        p = os.path.join(ROOT, "work", "recon", ".".join(parts[:k]) + ".cs")
        if os.path.exists(p): return p, ".".join(parts[:k])
    return None, None

def main(args):
    show_all = "--all" in args
    skel = open(os.path.join(ROOT, "work", "skeleton", "Assembly-CSharp.cs"), encoding="utf-8").read()
    decl = {n: skel[st:en] for n, st, en in top_level_types(skel)}
    shown = set()
    for t in (a for a in args if a != "--all"):
        rf, top = recon_file(t)
        stubs = None if show_all or not rf else stub_names(open(rf, encoding="utf-8").read())
        top = top or t.split(".")[0]
        print(f"######## {t}" + ("" if stubs is None else f"  ({len(stubs)} stub names left in {os.path.basename(rf)})"))
        key = top if top in decl else top.split(".")[-1]   # "N.Type" for namespaced types
        if top not in shown and key in decl:
            shown.add(top)
            for l in decl[key].splitlines():
                if NI in l and stubs is not None and not member_names(l) & stubs: continue
                if l.strip(): print(l.replace(NI, ";").replace(" { get { throw new global::System.NotImplementedException(); } }", " { get; }"))
        pkt = os.path.join(ROOT, "work", "lift_st01", t.replace("/", ".").replace("<", "_").replace(">", "_") + ".md")
        if not os.path.exists(pkt): print(f"(no packet {os.path.relpath(pkt, ROOT)})"); continue
        own = t.split(".")[-1]
        for sec in re.split(r"(?m)^(?=## )", open(pkt, encoding="utf-8").read())[1:]:
            name = re.match(r"## \S*?::([^(]+)\(", sec).group(1)
            name = {".ctor": own, ".cctor": own}.get(name, name.split(".")[-1])
            if stubs is None or name in stubs: print(sec.rstrip())

if __name__ == "__main__":
    main(sys.argv[1:])
