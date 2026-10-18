"""Differential-test pilot, step (b): turn probe_calls.py samples into replay cases for tools/unity/RainReplay.cs.
Usage: replay_cases.py <out_dir> <samples.jsonl> [...]
Writes <out_dir>/cases.tsv (one sample per line, raw registers + memory, decoded on the C# side by reflection) and
<out_dir>/layouts.tsv (instance field offsets per type from annotate_decomp.layout, so `this` memory maps to fields).
Only types present in work/recon (reconstructed) are kept."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotate_decomp

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

def main(out, files):
    recon = set()
    for f in os.listdir(os.path.join(ROOT, "work", "recon")):
        if f.endswith(".cs"): recon.add(f[:-3])
    cases, types = [], set()
    for f in files:
        for l in open(f):
            d = json.loads(l)
            if d["type"].split("/")[0] not in recon: continue
            e, x = d["entry"], d["exit"]
            mem = lambda m: ";".join(f"{k}={v}" for k, v in m.items() if v)
            cases.append("\t".join([d["type"], d["method"], d["params"], ",".join(e["gpr"]), ",".join(e["fpr"]), mem(e["mem"]),
                                    ",".join(x["gpr"]), ",".join(x["fpr"]), mem(x["mem"]), e.get("stack", "")]))
            types.add(d["type"])
    il = os.path.join(ROOT, "work", "managed_il")
    lay = []
    for t in sorted(types):
        try: L = annotate_decomp.layout(il, "Assembly-CSharp", t)
        except Exception as ex: print("layout failed", t, ex); continue
        lay.append(t + "\t" + ",".join(f"{o}={n}" for o, n in sorted(L.items())))
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "cases.tsv"), "w", newline="\n").write("\n".join(cases) + "\n")
    open(os.path.join(out, "layouts.tsv"), "w", newline="\n").write("\n".join(lay) + "\n")
    print(f"{len(cases)} cases, {len(types)} types -> {out}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
