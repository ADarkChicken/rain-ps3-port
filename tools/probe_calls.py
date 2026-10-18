"""M5 differential tests, step 1+2: census + raw call samples from the running game (RPCS3 PPU interpreter + GDB stub).
Usage: probe_calls.py <rpcs3.log> <out dir> [--hits N=1] [--samples K=1] [--only Type,Type.Method,...]
       [--skip census.csv]  (skip methods already hit in an earlier run)
Sets an entry breakpoint on every Stage-1 closure method (work/maps/st01_closure.methods.csv), counts hits and drops a
method's breakpoint after N hits. The first K hits of each method are sampled: at entry all registers, 0x100 bytes at
each GPR arg r3-r10 that is a readable pointer, and the caller's parameter area (sp+0x30, overflow args); then a
one-shot breakpoint at LR catches the return on the same thread/sp and records registers + the same memory again
(return buffers, out/ref args, `this` after the call). Arg -> register mapping is left to the replay side.
Output: <out>/census.csv (rewritten every 10 s and at the end), <out>/samples.jsonl.
Stop: create <out>/stop.req -> all breakpoints removed, emulator resumed. The connection is then held until RPCS3
exits (its stub crashes on a drop, E69). Watchdog: after 5 s without a stop it interrupts and makes a thread parked on
one of our breakpoints the vCont thread, since a breakpoint that fires while another is handled leaves its thread in
dbg_pause (GDB.cpp only un-pauses pausedBy and the continue thread)."""
import csv, json, os, socket, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdb_rsp import RSP
from probe_vtable import wait_base

def parse_g(h):
    """'g' reply -> dict: gpr[32], fpr[32] (u64 bits), pc, lr. Layout: ids 0-65 16 hex chars each, cr 8, lr 16, ctr 16."""
    r = [int(h[16 * i:16 * i + 16], 16) for i in range(65)]
    return {"gpr": r[:32], "fpr": r[32:64], "pc": r[64], "lr": int(h[16 * 66 + 8:16 * 67 + 8], 16)}

def readable(g, a, n=0x100):
    if not 0x10000 <= a < 0xF0000000: return None
    try: return g.mem(a, n).hex()
    except IOError: return None

class Probe:
    def __init__(self, g, base, methods, hits, samples, out):
        self.g, self.base, self.out, self.N, self.K = g, base, out, hits, samples
        self.m = {base + int(r["address"], 16): r for r in methods}
        self.count = dict.fromkeys(self.m, 0); self.first = {}
        self.active = set(); self.ret = {}   # ret bp addr -> list of pending (tid, sp, sample)
        self.ever = set(); self.released = []; self.hc = False; self.t0 = time.time()

    def snap(self, regs):
        return {f"r{i}": v for i in range(3, 11) if (v := readable(self.g, regs["gpr"][i] & 0xFFFFFFFF))}

    def on_entry(self, pc, tid, regs):
        self.count[pc] += 1; self.first.setdefault(pc, round(time.time() - self.t0, 1))
        if self.count[pc] <= self.K:
            sp = regs["gpr"][1] & 0xFFFFFFFF; r = self.m[pc]
            s = {"type": r["type"], "method": r["method"], "params": r.get("params", ""), "address": r["address"],
                 "n": self.count[pc], "tid": tid, "t": round(time.time() - self.t0, 2),
                 "entry": {"gpr": [hex(x) for x in regs["gpr"][3:11]], "fpr": [hex(x) for x in regs["fpr"][1:14]],
                           "lr": hex(regs["lr"]), "sp": hex(sp), "mem": self.snap(regs), "stack": readable(self.g, sp + 0x30, 0x80)}}
            lr = regs["lr"] & 0xFFFFFFFF
            if lr not in self.ret and lr not in self.active: self.g.bp(lr); self.ever.add(lr)
            self.ret.setdefault(lr, []).append((tid, sp, s))
        if self.count[pc] >= self.N: self.g.bp(pc, False); self.active.discard(pc)

    def on_return(self, pc, tid, regs):
        sp = regs["gpr"][1] & 0xFFFFFFFF; pend = self.ret[pc]
        for i, (t, s0, s) in enumerate(pend):
            if t == tid and s0 == sp:
                s["exit"] = {"gpr": [hex(x) for x in regs["gpr"][3:5]], "fpr": [hex(x) for x in regs["fpr"][1:5]],
                             "mem": {k: readable(self.g, int(s["entry"]["gpr"][int(k[1:]) - 3], 16) & 0xFFFFFFFF)
                                     for k in s["entry"]["mem"]}}
                with open(os.path.join(self.out, "samples.jsonl"), "a") as f: f.write(json.dumps(s) + "\n")
                del pend[i]; break
        if not pend:
            del self.ret[pc]
            if pc not in self.active: self.g.bp(pc, False)

    def release_stuck(self):
        """Watchdog stop: make a thread parked on any breakpoint we ever set (also ones already removed) the vCont thread,
        so its dbg_pause is cleared; rotates through such threads on successive idle stops."""
        parked = []
        for t in [t for t in self.g.cmd("qfThreadInfo")[1:].split(",") if t]:
            if self.g.cmd(f"Hg{t}") == "OK" and ((self.g.reg(64) or 0) & 0xFFFFFFFF) in self.ever: parked.append(t)
        if not parked: return
        t = next((t for t in parked if t not in self.released), None) or parked[0]
        self.released = [x for x in self.released if x != t] + [t]
        self.g.cmd(f"Hc{t}"); self.hc = True; print(f"watchdog: released thread {t}", flush=True)

    def write_census(self):
        with open(os.path.join(self.out, "census.csv"), "w", newline="") as f:
            w = csv.writer(f); w.writerow(["type", "method", "params", "address", "hits", "first_s"])
            for a, r in sorted(self.m.items(), key=lambda kv: -self.count[kv[0]]):
                w.writerow([r["type"], r["method"], r.get("params", ""), r["address"], self.count[a], self.first.get(a, "")])

    def wait_stop(self, req):
        """vCont;c, then wait for a stop. Every 1 s check stop.req; after 5 s without a stop interrupt (watchdog).
        Returns 'bp', 'idle' or 'stop'. A breakpoint stop racing our 0x03 makes the stub answer the stray 0x03 with an
        empty packet, which the '?' sync below absorbs."""
        g = self.g
        if os.path.exists(req): return "stop"
        g.cmd("vCont;c", expect_reply=False); t = time.time()
        g.s.settimeout(1.0)
        try:
            while True:
                try: g._read_packet(); return "bp"
                except socket.timeout: pass
                why = "stop" if os.path.exists(req) else "idle" if time.time() - t > 5 else None
                if why:
                    g.s.sendall(b""); g.s.settimeout(30.0); g._read_packet()
                    if g.cmd("?") == "": g._read_packet()
                    return why
        finally: g.s.settimeout(30.0)

    def run(self, req):
        g = self.g
        for a in self.m:
            if g.bp(a) == "OK": self.active.add(a); self.ever.add(a)
        print(f"{len(self.active)}/{len(self.m)} breakpoints set; play now. Stop: create stop.req", flush=True)
        last_w = 0
        while True:
            why = self.wait_stop(req)
            if self.hc: g.cmd("Hc0"); self.hc = False
            if why == "stop": break
            if why == "idle": self.release_stuck(); continue
            tid = g.cmd("qC")[2:]                  # right after the stop, selected_thread = pausedBy
            g.cmd(f"Hg{tid}"); regs = parse_g(g.cmd("g")); pc = regs["pc"] & 0xFFFFFFFF
            if pc in self.ret: self.on_return(pc, tid, regs)
            if pc in self.active: self.on_entry(pc, tid, regs)
            if time.time() - last_w > 10:
                self.write_census(); last_w = time.time()
                print(f"{time.time() - self.t0:.0f}s: {sum(1 for c in self.count.values() if c)} methods hit, "
                      f"{len(self.active)} bps active, {len(self.ret)} pending returns", flush=True)
        for a in self.active | set(self.ret): g.bp(a, False)
        self.write_census(); g.cmd("vCont;c", expect_reply=False)
        print("stopped: breakpoints removed, emulator running", flush=True)

def main():
    a = sys.argv[1:]; opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    log, out = a[0], a[1]; os.makedirs(out, exist_ok=True)
    params = {r["address"]: r["params"] for r in csv.DictReader(open("work/maps/Assembly-CSharp.methods.csv")) if r["address"]}
    methods = [dict(r, params=params.get(r["address"], "")) for r in csv.DictReader(open("work/maps/st01_closure.methods.csv"))]
    if (only := opt("--only", None)):
        keys = set(only.split(",")); methods = [r for r in methods if r["type"] in keys or f'{r["type"]}.{r["method"]}' in keys]
    if (skip := opt("--skip", None)):
        done = {r["address"] for r in csv.DictReader(open(skip)) if int(r["hits"])}; methods = [r for r in methods if r["address"] not in done]
    base = wait_base(log); print(f"Assembly-CSharp code base {base:#x}", flush=True)
    g = RSP(); print("halt:", g.halt_reason(), flush=True)
    p = Probe(g, base, methods, int(opt("--hits", 1)), int(opt("--samples", 1)), out)
    try: p.run(os.path.join(out, "stop.req"))
    finally:
        print("holding connection open until RPCS3 exits...", flush=True)
        try:
            while g.s.recv(1): pass
        except Exception: pass

if __name__ == "__main__":
    main()
