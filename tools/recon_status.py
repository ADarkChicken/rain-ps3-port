"""M5 progress: mark work/recon/QUEUE.csv rows done/partial from work/recon/<Type>.cs (stubs left = NotImplemented
bodies) and print totals. Usage: recon_status.py"""
import csv, os, re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RECON = os.path.join(ROOT, "work", "recon")

def main():
    q = os.path.join(RECON, "QUEUE.csv")
    rows = list(csv.DictReader(open(q)))
    for r in rows:
        f = os.path.join(RECON, r["type"] + ".cs")
        if not os.path.exists(f): continue
        left = len(re.findall(r"NotImplementedException", open(f, encoding="utf-8").read()))
        r["status"] = "done" if left == 0 else f"partial({left} stubs)"
    with open(q, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["type", "closure_methods", "all_methods", "status"]); w.writeheader(); w.writerows(rows)
    done = [r for r in rows if r["status"] == "done" or r["status"].startswith("done")]
    print(f"types done {len(done)}/{len(rows)}; methods done {sum(int(r['all_methods']) for r in done)}/"
          f"{sum(int(r['all_methods']) for r in rows)}; partial: {[r['type'] for r in rows if r['status'].startswith('partial')]}")

if __name__ == "__main__":
    main()
