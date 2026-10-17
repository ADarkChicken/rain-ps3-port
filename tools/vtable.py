"""Mono vtable slot layout from IL metadata (T3, E95), using the rule verified at runtime (E68):
MonoVTable header 0x24 bytes, slot k at 0x24 + 4k; slots are inherited from the base class; each class appends its new
virtual methods (virtual + newslot, or virtual with no base method of that name/signature) in REVERSE declaration order;
overrides reuse the base slot. Interface methods use the IMT, not these slots.
Usage: vtable.py <il_dir> <TypeName>        (prints offset -> Class::Method(sig))
       vtable.py --selftest <il_dir>        (checks the E68 runtime observations)"""
import os, sys
import dnfile

class Types:
    def __init__(self, il_dir):
        self.asms = []
        for f in sorted(os.listdir(il_dir)):
            if f.endswith(".dll"):
                try: self.asms.append(dnfile.dnPE(os.path.join(il_dir, f)))
                except Exception: pass
        self.by_name = {}
        for pe in self.asms:
            t = pe.net.mdtables
            for r in t.TypeDef.rows:
                ns = str(r.TypeNamespace); full = (ns + "." if ns else "") + str(r.TypeName)
                self.by_name.setdefault(full, (pe, r)); self.by_name.setdefault(str(r.TypeName), (pe, r))
    def find(self, name): return self.by_name.get(name)
    def base_name(self, pe, r):
        e = r.Extends
        if not e or not getattr(e, "row_index", 0) or not e.row: return None   # coded index 0 = no base type
        ns = str(getattr(e.row, "TypeNamespace", "") or ""); n = str(getattr(e.row, "TypeName", ""))
        return (ns + "." if ns else "") + n if n else None

def sig_key(m):
    return str(m.Name), bytes(m.Signature.value)

def layout(T, name, _cache={}, _busy=set()):
    """[(slot method name, declaring type)] for type `name`."""
    if name in _cache: return _cache[name]
    if name in _busy: raise ValueError(f"inheritance cycle at {name}")
    _busy.add(name)
    hit = T.find(name)
    if hit is None: _cache[name] = []; _busy.discard(name); return []
    pe, r = hit
    b = T.base_name(pe, r)
    slots = list(layout(T, b)) if b and b != name else []
    new = []
    for mr in (r.MethodList or []):
        m = mr.row; fl = m.Flags
        if not fl.mdVirtual: continue
        key = sig_key(m)
        idx = next((i for i, (k, _) in enumerate(slots) if k == key), None) if not fl.mdNewSlot else None
        if idx is not None: slots[idx] = (key, str(r.TypeName))   # override
        else: new.append((key, str(r.TypeName)))
    slots += list(reversed(new))
    _cache[name] = slots; _busy.discard(name)
    return slots

def offsets(T, name):
    return {0x24 + 4 * i: f"{owner}::{k[0]}" for i, (k, owner) in enumerate(layout(T, name))}

if __name__ == "__main__":
    if sys.argv[1] == "--selftest":
        T = Types(sys.argv[2])
        obj = offsets(T, "System.Object")
        want_obj = {0x24: "ToString", 0x28: "GetHashCode", 0x2C: "Finalize", 0x30: "Equals"}
        rb = offsets(T, "RegionTrigger")
        want_rt = {0x38: "GetVisible", 0x40: "SetActive", 0x44: "OnRegionTriggerExit", 0x54: "Initialize", 0x48: "OnRegionTriggerEnter", 0x4C: "Release"}
        bad = {hex(k): (v, obj.get(k)) for k, v in want_obj.items() if not obj.get(k, "").endswith("::" + v)}
        bad.update({hex(k): (v, rb.get(k)) for k, v in want_rt.items() if not rb.get(k, "").endswith("::" + v)})
        assert not bad, bad
        print("vtable selftest ok:", len(want_obj) + len(want_rt), "E68 slots; RegionTrigger has", len(rb), "slots")
    else:
        T = Types(sys.argv[1])
        for off, n in sorted(offsets(T, sys.argv[2]).items()): print(f"+{off:#05x} {n}")
