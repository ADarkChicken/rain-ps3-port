"""PS3 PKG extractor (read-only on input). Usage: pkg_extract.py <in.pkg> <out_dir> [--list]
Retail (type 0x8000): AES-128-CTR, PS3 pkg key, IV = header[0x70:0x80].
Debug  (type 0x0000): keystream = SHA1(digest-derived 0x40 block with BE counter)[:16].
Writes <out_dir>/_manifest.csv (name, offset, size, flags, sha1)."""
import hashlib, os, struct, sys
from Crypto.Cipher import AES
from Crypto.Util import Counter

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps3keys import key
PS3_PKG_KEY = key("PS3_PKG_KEY")

class Pkg:
    def __init__(self, path):
        self.f = open(path, "rb")
        h = self.f.read(0xC0)
        assert h[:4] == b"\x7fPKG", "bad magic"
        self.rev, self.ptype = struct.unpack(">HH", h[4:8])
        self.item_count, = struct.unpack(">I", h[0x14:0x18])
        self.data_off, self.data_size = struct.unpack(">QQ", h[0x20:0x30])
        self.content_id = h[0x30:0x60].rstrip(b"\0").decode()
        self.digest = h[0x60:0x70]
        self.iv = h[0x70:0x80]
        self.retail = bool(self.rev & 0x8000)

    def read(self, rel, size):
        """Decrypt `size` bytes at data-relative offset `rel` (any alignment)."""
        start = rel & ~0xF
        self.f.seek(self.data_off + start)
        enc = self.f.read(size + (rel - start))
        blk = start // 16
        if self.retail:
            ctr = Counter.new(128, initial_value=int.from_bytes(self.iv, "big") + blk)
            dec = AES.new(PS3_PKG_KEY, AES.MODE_CTR, counter=ctr).decrypt(enc)
        else:
            d = self.digest
            base = d[0:8] * 2 + d[8:16] * 2 + bytes(24)
            ks = bytearray()
            for i in range((len(enc) + 15) // 16):
                ks += hashlib.sha1(base + struct.pack(">Q", blk + i)).digest()[:16]
            dec = bytes(a ^ b for a, b in zip(enc, ks))
        return dec[rel - start:]

    def entries(self):
        tbl = self.read(0, self.item_count * 32)
        for i in range(self.item_count):
            no, ns, do, ds, fl, _ = struct.unpack(">IIQQII", tbl[i*32:(i+1)*32])
            name = self.read(no, ns).decode("utf-8")
            assert name.isprintable() and ".." not in name.split("/"), f"suspicious name {name!r}"
            assert do + ds <= self.data_size, "entry beyond data"
            yield name, do, ds, fl

def main():
    src, out = sys.argv[1], sys.argv[2]
    p = Pkg(src)
    print(f"content_id={p.content_id} retail={p.retail} items={p.item_count} data_size={p.data_size}")
    ents = list(p.entries())
    if "--list" in sys.argv:
        for n, o, s, fl in ents: print(f"{fl:08x} {s:>12} {n}")
        return
    os.makedirs(out, exist_ok=True)
    man = ["name,offset,size,flags,sha1"]
    for n, o, s, fl in ents:
        dst = os.path.join(out, *n.split("/"))
        if (fl & 0xFF) == 4 or s == 0 and n.endswith("/"):  # directory entry
            os.makedirs(dst, exist_ok=True); man.append(f"{n},{o},{s},{fl:08x},DIR"); continue
        os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
        h = hashlib.sha1()
        with open(dst, "xb") as w:  # never overwrite
            pos, CH = 0, 16 << 20
            while pos < s:
                b = p.read(o + pos, min(CH, s - pos)); w.write(b); h.update(b); pos += len(b)
        man.append(f"{n},{o},{s},{fl:08x},{h.hexdigest()}")
    with open(os.path.join(out, "_manifest.csv"), "x") as m: m.write("\n".join(man) + "\n")
    print(f"extracted {len(ents)} entries to {out}")

if __name__ == "__main__":
    main()
