"""Tally exceptions (type, message, first stack frames) in a Unity -logFile. Usage: unity_log_tally.py <log> [N] [frames]"""
import re, collections, sys
L = open(sys.argv[1], encoding="utf-8", errors="replace").read().split("\n")
depth = int(sys.argv[3]) if len(sys.argv) > 3 else 1
c = collections.Counter()
for i, l in enumerate(L):
    m = re.match(r"(\w*Exception)\b:?(.*)", l)
    if m:
        fr = [re.sub(r" \[0x[0-9a-f]+\] in .*[\/]", " ", x.strip())[3:100] for x in L[i + 1:i + 12] if x.strip().startswith("at ")][:depth]
        c[(m.group(1), m.group(2).strip()[:40], " <- ".join(re.sub(r"\(.*?\)", "()", f) for f in fr))] += 1
for k, v in c.most_common(int(sys.argv[2]) if len(sys.argv) > 2 else 30): print(v, *k, sep=" | ")
print("total", sum(c.values()))
