"""Print fields (with decoded signature types, flags, field offsets if any) and methods of one IL type.
Usage: il_type_info.py <dll> <TypeName>"""
import sys, dnfile
ET = {1:"void",2:"bool",3:"char",4:"sbyte",5:"byte",6:"short",7:"ushort",8:"int",9:"uint",10:"long",11:"ulong",12:"float",13:"double",14:"string",0x18:"IntPtr",0x1c:"object"}
pe = dnfile.dnPE(sys.argv[1]); t = pe.net.mdtables
def tdor(v):
    tag, row = v & 3, v >> 2
    tbl = [t.TypeDef, t.TypeRef, t.TypeSpec][tag]
    r = tbl.rows[row-1]
    return str(getattr(r, "TypeName", f"TypeSpec#{row}"))
def cu(b, i):
    x = b[i]
    if x & 0x80 == 0: return x, i+1
    if x & 0x40 == 0: return ((x & 0x3f) << 8) | b[i+1], i+2
    return ((x & 0x1f) << 24) | (b[i+1] << 16) | (b[i+2] << 8) | b[i+3], i+4
def typ(b, i):
    e = b[i]; i += 1
    if e in ET: return ET[e], i
    if e in (0x11, 0x12): v, i = cu(b, i); return tdor(v), i
    if e == 0x1d: s, i = typ(b, i); return s + "[]", i
    if e == 0x15:
        g, i = typ(b, i); n, i = cu(b, i); args = []
        for _ in range(n): a, i = typ(b, i); args.append(a)
        return f"{g}<{','.join(args)}>", i
    if e == 0x10: s, i = typ(b, i); return "ref " + s, i
    return f"et{e:#x}", i
name = sys.argv[2]
for ti, r in enumerate(t.TypeDef.rows, 1):
    if str(r.TypeName) != name: continue
    print(f"type {name} extends {r.Extends.row.TypeName if r.Extends and r.Extends.row else '?'}  ")
    for f in (r.FieldList or []):
        fr = f.row; b = bytes(fr.Signature.value)
        ty, _ = typ(b, 1)
        print(f"  field {fr.Name}: {ty}{'  [static]' if fr.Flags.fdStatic else ''}{'  [public]' if fr.Flags.fdPublic else ''}{'  [NonSerialized]' if fr.Flags.fdNotSerialized else ''}")
    for m in (r.MethodList or []):
        mr = m.row; b = bytes(mr.Signature.value)
        i = 1; n, i = cu(b, i); ret, i = typ(b, i); ps = []
        for _ in range(n): p, i = typ(b, i); ps.append(p)
        pn = [str(p.row.Name) for p in (mr.ParamList or []) if p.row and p.row.Sequence > 0]
        print(f"  method 0x06{m.row_index:06x} {ret} {mr.Name}({', '.join(f'{a} {b}' for a, b in zip(ps, pn + ['']*len(ps)))})")
