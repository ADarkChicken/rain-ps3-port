"""Compile harness for reconstructed classes (T5, E96): replaces the skeleton declaration of every class defined in the
given .cs files, compiles the whole assembly with csc against Unity 2017.4 (module assemblies) + Rain.Firstpass, and
reports errors per reconstructed method.
Usage: lift_compile.py <assembly> <recon.cs> [...]      (assembly = Assembly-CSharp, skeleton from work/skeleton)
A reconstruction file holds complete top-level classes (fields + all methods; unreconstructed methods keep the skeleton
stub). Exit code 0 = no errors."""
import os, re, subprocess, sys, tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
UNITY = os.path.join(ROOT, "..", "_tools", "Unity-2017.4.40f1", "Editor", "Data")
SA = os.path.join(ROOT, "..", "_tools", "m0_host_compile", "Library", "ScriptAssemblies")
CSC = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

def top_level_types(src):
    """[(name, start, end)] of top-level type declarations (brace-matched, strings/comments-aware enough for skeletons)."""
    out, i = [], 0
    for m in re.finditer(r"(?m)^(?:\[[^\n]*\]\s*)*(?:public |internal )?(?:sealed |abstract |static )*(?:partial )?(?:class|struct|interface|enum) (\w+)", src):
        if m.start() < i: continue
        j = src.index("{", m.end()); depth = 0; k = j
        while True:
            c = src[k]
            if c == '"':
                k = src.index('"', k + 1)
                while src[k - 1] == "\\": k = src.index('"', k + 1)
            elif c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0: break
            k += 1
        out.append((m.group(1), m.start(), k + 1)); i = k + 1
    return out

def main(asm, files):
    skel = open(os.path.join(ROOT, "work", "skeleton", asm + ".cs"), encoding="utf-8").read()
    recon = {f: open(f, encoding="utf-8").read() for f in files}
    names = {n for s in recon.values() for n, _, _ in top_level_types(s)}
    for n, st, en in sorted(top_level_types(skel), key=lambda t: -t[1]):
        if n in names: skel = skel[:st] + f"/* {n}: reconstructed */" + skel[en:]
    tmp = tempfile.mkdtemp()
    sk = os.path.join(tmp, asm + ".skeleton.cs"); open(sk, "w", encoding="utf-8").write(skel)
    refs = [os.path.join(UNITY, "Managed", "UnityEngine", f) for f in os.listdir(os.path.join(UNITY, "Managed", "UnityEngine")) if f.endswith(".dll")]
    refs += [os.path.join(SA, "Rain.Firstpass.dll"), os.path.join(UNITY, "Mono", "lib", "mono", "unity", "Boo.Lang.dll"),
             os.path.join(UNITY, "Mono", "lib", "mono", "unity", "UnityScript.Lang.dll")]
    cmd = [CSC, "-nologo", "-target:library", "-nowarn:0108,0114,0162,0168,0219,0414,0649,0169,0067,1685,0436",
           "-out:" + os.path.join(tmp, asm + ".dll")] + ["-r:" + os.path.abspath(r) for r in refs] + [sk] + [os.path.abspath(f) for f in files]
    r = subprocess.run(cmd, capture_output=True, text=True)
    errs = [l for l in r.stdout.splitlines() if "error CS" in l]
    for f, s in recon.items():
        lines = s.splitlines(); mine = [e for e in errs if os.path.basename(f) in e]
        for e in mine:
            ln = int(re.search(r"\((\d+),", e).group(1))
            meth = next((re.search(r"(\w+)\s*\(", lines[k]).group(1) for k in range(ln - 1, -1, -1)
                         if re.match(r"\s*(public|private|protected|internal|static|override|virtual)\b.*\(", lines[k]) and re.search(r"(\w+)\s*\(", lines[k])), "?")
            print(f"[{meth}] {e.split(': ', 1)[-1]}")
    other = [e for e in errs if not any(os.path.basename(f) in e for f in files)]
    for e in other[:10]: print("[skeleton]", e)
    print(f"RESULT: {'OK' if not errs else str(len(errs)) + ' errors'} ({len(names)} reconstructed types)")
    return 0 if not errs else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
