"""Test NPDRM klicensee candidates against a SELF/SPRX (logic from RPCS3 unself.cpp LoadMetadata/DecryptNPDRM).
A candidate is accepted only if the decrypted metadata info has all 32 pad bytes zero (RPCS3 checks 2).
Usage:
  klic_check.py <self> --free                  test NP_KLIC_FREE
  klic_check.py <self> --hex <32 hex chars>    test one klic
  klic_check.py <self> --scan <file> [align]   test every aligned 16-byte window of <file> (default align 4)"""
import struct, sys
from Crypto.Cipher import AES

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps3keys import key
NP_KLIC_FREE = key("NP_KLIC_FREE")
NP_KLIC_KEY = key("NP_KLIC_KEY")
NPDRM_KEYS = {  # revision: (erk, riv) hex, from keys.local.json
    0x19: (key("NPDRM_ERK_19").hex(), key("NPDRM_RIV_19").hex()),
    0x1C: (key("NPDRM_ERK_1C").hex(), key("NPDRM_RIV_1C").hex()),
}

def load(path):
    b = open(path, "rb").read()
    assert b[:4] == b"SCE\0"
    rev, = struct.unpack(">H", b[8:10]); meta, = struct.unpack(">I", b[0x0C:0x10])
    erk, riv = (bytes.fromhex(x) for x in NPDRM_KEYS[rev])
    return b[0x20 + meta: 0x20 + meta + 0x40], AES.new(erk, AES.MODE_CBC, riv), erk, riv

def check(enc_info, erk, riv, klic):
    k = AES.new(NP_KLIC_KEY, AES.MODE_ECB).decrypt(klic)
    stage = AES.new(k, AES.MODE_CBC, bytes(16)).decrypt(enc_info)
    info = AES.new(erk, AES.MODE_CBC, riv).decrypt(stage)
    return info[16:32] == bytes(16) and info[48:64] == bytes(16)

if __name__ == "__main__":
    enc, _, erk, riv = load(sys.argv[1]); mode = sys.argv[2]
    if mode == "--free": print("NP_KLIC_FREE:", check(enc, erk, riv, NP_KLIC_FREE))
    elif mode == "--hex": print(sys.argv[3], check(enc, erk, riv, bytes.fromhex(sys.argv[3])))
    elif mode == "--scan":
        data = open(sys.argv[3], "rb").read(); al = int(sys.argv[4]) if len(sys.argv) > 4 else 4
        seen = set(); hits = 0
        for off in range(0, len(data) - 15, al):
            c = data[off:off+16]
            if c in seen or c.count(0) > 4: continue
            seen.add(c)
            if check(enc, erk, riv, c): print(f"HIT offset={off:#x} klic={c.hex().upper()}"); hits += 1
        print(f"scanned {len(seen)} unique candidates, hits={hits}")
