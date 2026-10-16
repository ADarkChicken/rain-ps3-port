"""Minimal GDB Remote Serial Protocol client for RPCS3's GDB stub (rpcs3/Emu/GDB.cpp).
Supported by RPCS3: ? g p m M Z0/z0 (software breakpoints, PPU interpreter only) c/vCont H qC qfThreadInfo.
Register ids: 0-31 GPR, 32-63 FPR, 64 PC(cia), 66 CR, 67 LR, 68 CTR.  All values big-endian hex."""
import socket, struct, time

class RSP:
    def __init__(self, host="127.0.0.1", port=2345, timeout=30.0):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.buf = b""

    def _recv_byte(self):
        if not self.buf:
            self.buf = self.s.recv(65536)
            if not self.buf: raise ConnectionError("GDB stub closed the connection")
        c, self.buf = self.buf[:1], self.buf[1:]
        return c

    def _read_packet(self):
        while True:
            c = self._recv_byte()
            if c == b"$": break
        data = b""
        while True:
            c = self._recv_byte()
            if c == b"#": break
            data += c
        cs = self._recv_byte() + self._recv_byte()
        if int(cs, 16) != sum(data) % 256:
            self.s.sendall(b"-"); raise IOError("bad checksum")
        self.s.sendall(b"+")
        return data.decode("latin-1")

    def cmd(self, payload, expect_reply=True):
        pkt = payload.encode("latin-1")
        frame = b"$" + pkt + b"#" + f"{sum(pkt) % 256:02x}".encode()
        for _ in range(3):
            self.s.sendall(frame)
            ack = self._recv_byte()
            while ack not in (b"+", b"-"): ack = self._recv_byte()
            if ack == b"+": break
        return self._read_packet() if expect_reply else None

    # --- helpers ---
    def halt_reason(self): return self.cmd("?")
    def reg(self, rid):
        r = self.cmd(f"p{rid:x}")
        return int(r, 16) if r and "x" not in r and not r.startswith("E") else None
    def mem(self, addr, n):
        r = self.cmd(f"m{addr:x},{n:x}")
        if r.startswith("E") or len(r) != 2 * n: raise IOError(f"read {addr:#x}+{n}: {r[:20]}")
        return bytes.fromhex(r)
    def u32(self, addr): return struct.unpack(">I", self.mem(addr, 4))[0]
    def bp(self, addr, on=True): return self.cmd(f"{'Z' if on else 'z'}0,{addr:x},4")
    def cont(self):
        """Resume; returns the stop reply when a breakpoint is hit (blocks)."""
        self.s.settimeout(None)
        try: return self.cmd("vCont;c")
        finally: self.s.settimeout(30.0)
    def close(self): self.s.close()
