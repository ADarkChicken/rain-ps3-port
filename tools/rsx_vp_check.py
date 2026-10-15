"""Structural check of RSX vertex programs stored in Unity 3.5 PS3 shaders (bitfields per RPCS3 RSXVertexProgram.h).
Each instruction = 4 x u32 (D0..D3). Valid program: D3.end set on the last instruction only, every vec/sca opcode known.
Usage: rsx_vp_check.py <Media dir>   (tests both raw-BE and halfword-swapped word order)"""
import glob, re, struct, sys, collections

VEC = {0:"NOP",1:"MOV",2:"MUL",3:"ADD",4:"MAD",5:"DP3",6:"DPH",7:"DP4",8:"DST",9:"MIN",10:"MAX",11:"SLT",12:"SGE",13:"ARL",
       14:"FRC",15:"FLR",16:"SEQ",17:"SFL",18:"SGT",19:"SLE",20:"SNE",21:"STR",22:"SSG",25:"TXL"}
SCA = {0:"NOP",1:"MOV",2:"RCP",3:"RCC",4:"RSQ",5:"EXP",6:"LOG",7:"LIT",8:"BRA",9:"BRI",10:"CAL",11:"CLI",12:"RET",13:"LG2",
       14:"EX2",15:"SIN",16:"COS",17:"BRB",18:"CLB",19:"PSH",20:"POP"}

def words(code, swap):
    w = struct.unpack(f">{len(code)//4}I", code)
    return [((x & 0xFFFF) << 16) | (x >> 16) for x in w] if swap else list(w)

def check(code, swap):
    w = words(code, swap); n = len(w) // 4; ops = collections.Counter()
    for i in range(n):
        d1, d3 = w[4*i+1], w[4*i+3]
        vo, so = (d1 >> 22) & 0x1F, (d1 >> 27) & 0x1F
        if vo not in VEC or so not in SCA: return False, ops
        ops["v" + VEC[vo]] += 1; ops["s" + SCA[so]] += 1
        if (d3 & 1) != (1 if i == n - 1 else 0): return False, ops
    return True, ops

if __name__ == "__main__":
    media = sys.argv[1]
    pat = re.compile(rb'"sce_vp_rsx[^"]*?\[Microcode\]\s*(\d+)\s*([0-9a-f\s]+)"')
    seen = set(); res = {False: 0, True: 0}; ops = collections.Counter(); badlen = 0
    for f in glob.glob(media + "/*.assets") + [media + "/Resources/unity default resources"]:
        for m in pat.finditer(open(f, "rb").read()):
            hx = re.sub(rb"\s", b"", m.group(2)).decode()
            if hx in seen: continue
            seen.add(hx); code = bytes.fromhex(hx)
            if len(code) != int(m.group(1)) or len(code) % 16: badlen += 1; continue
            for swap in (False, True):
                ok, o = check(code, swap)
                if ok: res[swap] += 1
                if ok and not swap: ops.update(o)
    print(f"unique VPs={len(seen)} bad_length={badlen} valid_raw_BE={res[False]} valid_halfword_swapped={res[True]}")
    print("vec/sca opcode use (raw BE):", ops.most_common(20))
