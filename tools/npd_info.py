"""Print NPD (NPDRM) block info for SELF/SPRX/EDAT/SDAT files. Usage: npd_info.py files..."""
import struct, sys
for p in sys.argv[1:]:
    b = open(p, "rb").read(0x2000); i = b.find(b"NPD\0")
    if i < 0: print(f"{p}: no NPD block"); continue
    ver, lic, app = struct.unpack(">III", b[i+4:i+16]); cid = b[i+16:i+0x40].rstrip(b"\0").decode(errors="replace")
    print(f"{p}: npd@{i:#x} ver={ver} license={lic} ({ {1:'network',2:'local/RAP',3:'free'}.get(lic,'?') }) app_type={app:#x} cid={cid!r}")
