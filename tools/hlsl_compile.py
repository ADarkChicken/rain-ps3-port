"""Compile HLSL with the system d3dcompiler_47.dll (D3DCompile). Usage: hlsl_compile.py <file> <entry> <profile>"""
import ctypes, sys
from ctypes import c_void_p, c_char_p, c_size_t, c_uint, POINTER, byref
d = ctypes.WinDLL("d3dcompiler_47.dll")
class Blob(ctypes.Structure): pass
src = open(sys.argv[1], "rb").read()
code, err = c_void_p(), c_void_p()
hr = d.D3DCompile(src, c_size_t(len(src)), c_char_p(sys.argv[1].encode()), None, None, c_char_p(sys.argv[2].encode()),
                  c_char_p(sys.argv[3].encode()), c_uint(0), c_uint(0), byref(code), byref(err))
def blob_bytes(p):
    vt = ctypes.cast(ctypes.cast(p, POINTER(c_void_p))[0], POINTER(c_void_p))
    getptr = ctypes.WINFUNCTYPE(c_void_p, c_void_p)(vt[3]); getsize = ctypes.WINFUNCTYPE(c_size_t, c_void_p)(vt[4])
    return ctypes.string_at(getptr(p), getsize(p))
if err.value: print(blob_bytes(err.value).decode(errors="replace"))
print(f"hr=0x{hr & 0xffffffff:08x}", "OK" if hr == 0 else "FAILED", f"bytecode={len(blob_bytes(code.value)) if code.value else 0} bytes")
sys.exit(0 if hr == 0 else 1)
