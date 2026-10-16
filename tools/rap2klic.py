"""RAP license file -> NPDRM key (RPCS3 Crypto/key_vault.cpp rap_to_rif). Usage: rap2klic.py <file.rap>
Prints the derived key as hex; pass it to self_decrypt.py --klic for license-2 (local) SELF/SPRX files."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Crypto.Cipher import AES
from ps3keys import key

def rap_to_rif(rap):
    pbox, e1, e2 = key("RAP_PBOX"), key("RAP_E1"), key("RAP_E2")
    k = bytearray(AES.new(key("RAP_KEY"), AES.MODE_CBC, bytes(16)).decrypt(rap))
    for _ in range(5):
        for i in range(16): k[pbox[i]] ^= e1[pbox[i]]
        for i in range(15, 0, -1): k[pbox[i]] ^= k[pbox[i-1]]
        o = 0
        for i in range(16):
            p = pbox[i]; kc = (k[p] - o) & 0xFF; ec2 = e2[p]
            if o != 1 or kc != 0xFF:
                o = 1 if kc < ec2 else 0; k[p] = (kc - ec2) & 0xFF
            else:
                k[p] = (kc - ec2) & 0xFF   # kc == 0xFF branch (same arithmetic as RPCS3)
    return bytes(k)

if __name__ == "__main__":
    rap = open(sys.argv[1], "rb").read()
    assert len(rap) == 16, "RAP must be 16 bytes"
    print(rap_to_rif(rap).hex().upper())
