"""Minimal RSX fragment-program disassembler (bitfields per RPCS3 rpcs3/Emu/RSX/Program/RSXFragmentProgram.h,
opcodes per Assembler/FPOpcodes.h; see tools/ref_rpcs3/rsx). Usage: rsx_fp_disasm.py <microcode hex>
Each instruction = 4 BE words with bytes swapped inside 16-bit halves; an instruction using a constant
source is followed by a 16-byte inline constant (4 floats, same swap)."""
import struct, sys

OPS = {0x00:"NOP",0x01:"MOV",0x02:"MUL",0x03:"ADD",0x04:"MAD",0x05:"DP3",0x06:"DP4",0x07:"DST",0x08:"MIN",0x09:"MAX",
 0x0A:"SLT",0x0B:"SGE",0x0C:"SLE",0x0D:"SGT",0x0E:"SNE",0x0F:"SEQ",0x10:"FRC",0x11:"FLR",0x12:"KIL",0x13:"PK4",0x14:"UP4",
 0x15:"DDX",0x16:"DDY",0x17:"TEX",0x18:"TXP",0x19:"TXD",0x1A:"RCP",0x1B:"RSQ",0x1C:"EX2",0x1D:"LG2",0x1E:"LIT",0x1F:"LRP",
 0x20:"STR",0x21:"SFL",0x22:"COS",0x23:"SIN",0x24:"PK2",0x25:"UP2",0x26:"POW",0x27:"PKB",0x28:"UPB",0x29:"PK16",0x2A:"UP16",
 0x2B:"BEM",0x2C:"PKG",0x2D:"UPG",0x2E:"DP2A",0x2F:"TXL",0x31:"TXB",0x33:"TEXBEM",0x34:"TXPBEM",0x35:"BEMLUM",0x36:"REFL",
 0x37:"TIMESWTEX",0x38:"DP2",0x39:"NRM",0x3A:"DIV",0x3B:"DIVSQ",0x3C:"LIF",0x3D:"FENCT",0x3E:"FENCB",0x40:"BRK",0x41:"CAL",
 0x42:"IFE",0x43:"LOOP",0x44:"REP",0x45:"RET"}
INPUTS = ["wpos","diff_color","spec_color","fogc","tc0","tc1","tc2","tc3","tc4","tc5","tc6","tc7","tc8","tc9","ssa"]
SW = "xyzw"

def sw(w): return ((w & 0xFFFF) << 16) | (w >> 16)  # stored form = BE word with 16-bit halves exchanged (verified via 1.0f constant)
def bits(v, lo, n): return (v >> lo) & ((1 << n) - 1)

def src(v, attr, const, abs_bit):
    t = bits(v, 0, 2); idx = bits(v, 2, 6); h = bits(v, 8, 1)
    swz = "".join(SW[bits(v, 9 + 2*k, 2)] for k in range(4)); neg = bits(v, 17, 1)
    if t == 0: r = f"{'H' if h else 'R'}{idx}"
    elif t == 1: r = INPUTS[attr] if attr < len(INPUTS) else f"in{attr}"
    elif t == 2: r = "c[" + ",".join(f"{x:g}" for x in const) + "]"
    else: r = "?"
    s = r + ("" if swz == "xyzw" else "." + swz)
    if abs_bit: s = f"|{s}|"
    return ("-" if neg else "") + s

def disasm(code):
    out = []; i = 0
    while i + 16 <= len(code):
        w = [sw(x) for x in struct.unpack(">4I", code[i:i+16])]
        d, s0, s1, s2 = w
        end = bits(d, 0, 1); dreg = bits(d, 1, 6); fp16 = bits(d, 7, 1); mask = "".join(SW[k] for k in range(4) if bits(d, 9 + k, 1))
        attr = bits(d, 13, 4); tex = bits(d, 17, 4); prec = bits(d, 22, 2); op = bits(d, 24, 6) | (bits(s1, 31, 1) << 6)
        nodest = bits(d, 30, 1); sat = bits(d, 31, 1)
        nsrc = {"MOV":1,"TEX":1,"TXP":1,"RCP":1,"RSQ":1,"EX2":1,"LG2":1,"FRC":1,"FLR":1,"COS":1,"SIN":1,"NRM":1,"DDX":1,"DDY":1,
                "MAD":3,"LRP":3}.get(OPS.get(op, ""), 2)
        types = [bits(s, 0, 2) for s in (s0, s1, s2)][:nsrc]
        const = None
        if 2 in types:
            const = struct.unpack(">4f", struct.pack(">4I", *[sw(x) for x in struct.unpack(">4I", code[i+16:i+32])]))
        srcs = [src(s0, attr, const, bits(s0, 29, 1)), src(s1, attr, const, bits(s1, 18, 1)), src(s2, attr, const, bits(s2, 18, 1))]
        name = OPS.get(op, f"op{op:#x}") + ("_SAT" if sat else "")
        dst = "-" if nodest else f"{'H' if fp16 else 'R'}{dreg}" + ("" if mask == "xyzw" else "." + mask)
        texs = f" tex{tex}" if OPS.get(op, "").startswith(("TEX", "TXP", "TXL", "TXB", "TXD")) else ""
        out.append(f"{i//16:3d}: {name:8s} {dst}, {', '.join(srcs[:nsrc])}{texs}  prec={prec}{'  END' if end else ''}")
        i += 32 if const is not None else 16
        if end: break
    return out

if __name__ == "__main__":
    for l in disasm(bytes.fromhex(sys.argv[1])): print(l)
