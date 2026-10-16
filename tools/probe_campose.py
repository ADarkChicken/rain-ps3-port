"""M3 golden images: read the main camera pose from the running game in RPCS3 (PPU interpreter + GDB stub).
Usage: probe_campose.py <rpcs3.log> <out dir>
Lets the game run; whenever <out dir>/capture.req appears (its text = label) it interrupts, breaks in
CameraConstrainForRainEffect.OnPreCull (copies the main camera's world pose every frame, work/poc), reads
position/rotation/aspect/near/far/fov, captures the RPCS3 window while still paused, resumes and appends to <out dir>/poses.jsonl.
The .req file is renamed to <label>.done. Never closes the connection (RPCS3's stub crashes on a drop, E69)."""
import json, os, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdb_rsp import RSP
from probe_vtable import wait_base

# call sites inside OnPreCull (file addresses, work/poc/CameraConstrainForRainEffect.decomp.txt)
SET_LOCALROTATION = 0x56E0C   # r4..r7 = rotation; world position still at r1+0x8c (passed to set_localPosition)
F1_SITES = [("aspect", 0x56E7C), ("near", 0x56EA8), ("far", 0x56ED4), ("fov", 0x56F00)]   # setter arg in f1

def f32(bits): return struct.unpack(">f", struct.pack(">I", bits & 0xFFFFFFFF))[0]
def f64(bits): return struct.unpack(">d", struct.pack(">Q", bits))[0]

def hit(g, addr):
    """Run until a PPU thread stops at addr (only this breakpoint set); leaves that thread selected."""
    g.bp(addr)
    try:
        g.cont()
        if g.reg(64) == addr: return
        for t in [t for t in g.cmd("qfThreadInfo")[1:].split(",") if t]:
            if g.cmd(f"Hg{t}") == "OK" and g.reg(64) == addr: return
        raise RuntimeError(f"no thread stopped at {addr:#x}")
    finally:
        g.bp(addr, False)

def capture(g, base):
    hit(g, base + SET_LOCALROTATION)
    pos = struct.unpack(">3f", g.mem(g.reg(1) + 0x8C, 12))
    rot = [f32(g.reg(r)) for r in (4, 5, 6, 7)]
    pose = {"position": list(pos), "rotation": rot}
    for name, off in F1_SITES:
        hit(g, base + off); pose[name] = f64(g.reg(33))
    return pose

def main():
    log, out = sys.argv[1:3]; os.makedirs(out, exist_ok=True)
    req = os.path.join(out, "capture.req"); here = os.path.dirname(os.path.abspath(__file__))
    base = wait_base(log); print(f"Assembly-CSharp code base {base:#x}", flush=True)
    g = RSP(); print("halt:", g.halt_reason(), flush=True)
    g.cmd("vCont;c", expect_reply=False)   # connecting paused the emulator
    print("running; waiting for capture.req ...", flush=True)
    while True:
        if not os.path.exists(req): time.sleep(0.5); continue
        label = open(req).read().strip() or time.strftime("pose_%H%M%S")
        g.s.sendall(b"\x03"); print("interrupted:", g._read_packet(), flush=True)
        try: pose = dict(label=label, **capture(g, base))
        except Exception as e: pose = {"label": label, "error": f"{type(e).__name__}: {e}"}
        # capture while still paused: the window shows the last presented frame, i.e. the pose just read (E86: capturing
        # after resuming let the camera move after the multi-second pause)
        png = os.path.join(out, label + "_rpcs3.png")
        subprocess.run(["powershell", "-NoProfile", "-File", os.path.join(here, "rpcs3_window_capture.ps1"), "-Out", png])
        pose["window_capture"] = png
        g.cmd("vCont;c", expect_reply=False)
        with open(os.path.join(out, "poses.jsonl"), "a") as f: f.write(json.dumps(pose) + "\n")
        os.replace(req, os.path.join(out, label + ".done"))
        print(json.dumps(pose), flush=True)

if __name__ == "__main__":
    main()
