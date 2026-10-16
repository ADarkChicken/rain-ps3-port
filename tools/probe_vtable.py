"""M0 probe: resolve Mono vtable slots (E53) from the running game in RPCS3 (PPU interpreter + GDB stub).
Usage: probe_vtable.py <rpcs3.log> <methods.csv> <out.txt> [method_offset_hex=0x1b0600 (RegionBox.OnRegionTriggerEnter)]
1. reads Assembly-CSharp runtime bases from the RPCS3 log (export of 'methods' NID 0x4f9821c5),
2. sets a breakpoint, waits for a hit, dumps `this` (r3), one element of its trigger array, and that object's vtable,
3. maps each vtable entry (code pointer or function descriptor) back to C# methods via methods.csv."""
import csv, os, re, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdb_rsp import RSP

def wait_base(log, exports="work/acs_exports.txt"):
    """Code base = runtime address of any logged Assembly-CSharp export minus its file address (from prx_exports.py)."""
    nid2addr = {}
    for line in open(exports):
        m = re.search(r"nid=([0-9a-f]{8}) addr=(0x[0-9a-f]+)", line)
        if m and "func" in line: nid2addr[m.group(1)] = int(m.group(2), 16)
    pat = re.compile(r"Assembly_CSharp_dll export: \(0x([0-9a-f]{8})\) at (0x[0-9a-f]+)")
    while True:
        try:
            for m in pat.finditer(open(log, encoding="utf-8", errors="replace").read()):
                if m.group(1) in nid2addr: return int(m.group(2), 16) - nid2addr[m.group(1)]
        except OSError: pass  # log may be locked or not yet created
        time.sleep(3)

def main():
    log, mcsv, out = sys.argv[1:4]
    off = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x1B0600
    base = wait_base(log)
    rows = [r for r in csv.DictReader(open(mcsv)) if r["address"]]
    by_addr = {base + int(r["address"], 16): f'{r["type"]}::{r["method"]}({r["params"]}) {r["token"]}' for r in rows}
    lines = [f"Assembly-CSharp code base {base:#x}; breakpoint at {base + off:#x}"]
    g = RSP()
    lines.append(f"halt reason: {g.halt_reason()}")
    lines.append(f"set bp: {g.bp(base + off)}")
    print("waiting for breakpoint hit (play into the game if needed)...", flush=True)
    lines.append(f"stop: {g.cont()}")
    pc, this = g.reg(64), g.reg(3)
    lines.append(f"pc={pc:#x} this(r3)={this:#x}")
    obj = g.mem(this, 0x34)
    lines.append("RegionBox object: " + obj.hex(" ", 4))
    vt = struct.unpack(">I", obj[0:4])[0]
    arr = struct.unpack(">I", obj[0x10:0x14])[0]
    count = struct.unpack(">i", obj[0x2C:0x30])[0]
    lines.append(f"vtable(RegionBox)={vt:#x} trigger_array={arr:#x} m_Count={count}")
    if arr and count > 0:
        alen = g.u32(arr + 0xC); el = g.u32(arr + 0x10)
        lines.append(f"array length={alen} element0={el:#x}")
        evt = g.u32(el)
        klass = g.u32(evt)
        lines.append(f"element vtable={evt:#x} (MonoVTable.klass={klass:#x})")
        raw = g.mem(evt, 0xD0)
        lines.append("vtable header: " + raw[:0x18].hex(" ", 4))
        for o in range(0x18, 0xD0, 4):
            i = o
            v = struct.unpack(">I", raw[o: o + 4])[0]
            name = by_addr.get(v)
            if name is None and v:
                try:  # function descriptor (OPD): first word = code address
                    c = g.u32(v); name = ("OPD-> " + by_addr[c]) if c in by_addr else None
                except Exception: pass
            lines.append(f"  +{o:#04x} = {v:#010x}  {name or ''}")
    g.bp(base + off, False)
    lines.append(f"detach/continue: {g.cmd('vCont;c', expect_reply=False)}")
    open(out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
