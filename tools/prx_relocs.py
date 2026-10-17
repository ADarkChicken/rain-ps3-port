"""Dump PS3 PRX relocations (program header type 0x700000A4) as CSV for ghidra/scripts/ApplyAotAnnotations.java.
Usage: prx_relocs.py <decrypted.prx> <out.csv>
Entry (24 B, big-endian, RPCS3 ppu_reloc): u64 offset, u16 unk, u8 value segment, u8 address segment, u32 type, u64 ptr.
address = seg[addr_seg].vaddr + offset; value = seg[value_seg].vaddr + ptr (value_seg 0xFF: ptr as-is).
Output columns: address,type,value (hex) -- same as the Assembly-CSharp CSV used in Phase 3 (E36)."""
import struct, sys

def relocs(path):
    b = open(path, "rb").read()
    phoff, = struct.unpack(">Q", b[32:40]); phes, phnum = struct.unpack(">HH", b[54:58])
    ph = [struct.unpack(">IIQQQQQQ", b[phoff + i * phes: phoff + (i + 1) * phes]) for i in range(phnum)]
    loads = [p for p in ph if p[0] == 1]
    for t, fl, off, va, pa, fs, ms, al in ph:
        if t != 0x700000A4: continue
        for e in range(off, off + fs, 24):
            o, unk, vseg, aseg, typ, ptr = struct.unpack(">QHBBIQ", b[e:e + 24])
            value = ptr if vseg == 0xFF else loads[vseg][3] + ptr
            yield loads[aseg][3] + o, typ, value

if __name__ == "__main__":
    with open(sys.argv[2], "w") as f:
        f.write("address,type,value\n")
        for a, t, v in relocs(sys.argv[1]): f.write(f"{a:#x},{t},{v:#x}\n")
