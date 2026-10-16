"""Unity 3.5.8 (PS3, serialized v9 big-endian, no type trees) class readers, validated by byte-exact consumption.
Usage: unity35_classes.py <Media dir> <classID>[,<classID>...] [--dump N]
Each reader consumes an object's bytes; validation = consumed length == stored object size for every object.
Layouts are hypotheses until they pass on ALL objects of the class (results recorded in EVIDENCE.md)."""
import glob, os, struct, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unity_inventory as u

class R:
    def __init__(self, b): self.b = b; self.p = 0
    def align(self): self.p = (self.p + 3) & ~3
    def u8(self): v = self.b[self.p]; self.p += 1; return v
    def boolean(self): return self.u8() != 0
    def u16(self): v = struct.unpack(">H", self.b[self.p:self.p+2])[0]; self.p += 2; return v
    def i32(self): v = struct.unpack(">i", self.b[self.p:self.p+4])[0]; self.p += 4; return v
    def u32(self): v = struct.unpack(">I", self.b[self.p:self.p+4])[0]; self.p += 4; return v
    def f32(self): v = struct.unpack(">f", self.b[self.p:self.p+4])[0]; self.p += 4; return v
    def fs(self, n): v = struct.unpack(f">{n}f", self.b[self.p:self.p+4*n]); self.p += 4*n; return v
    def string(self):
        n = self.i32()
        if n < 0 or self.p + n > len(self.b): raise ValueError("bad string")
        s = self.b[self.p:self.p+n].decode("utf-8", "replace"); self.p += n; self.align(); return s
    def pptr(self): return (self.i32(), self.i32())
    def count(self, limit=10_000_000):
        n = self.i32()
        if n < 0 or n > limit: raise ValueError(f"bad count {n}")
        return n
    def vec(self, fn):
        n = self.count(); out = [fn() for _ in range(n)]; self.align(); return out
    def bytes_(self):
        n = self.count(); v = self.b[self.p:self.p+n]
        if len(v) != n: raise ValueError("eof")
        self.p += n; self.align(); return v

# ---------------- readers (hypotheses validated byte-exact) ----------------
def gameobject(r):
    comps = r.vec(lambda: (r.i32(), r.pptr()))
    return {"components": comps, "layer": r.u32(), "name": r.string(), "tag": r.u16(), "active": r.boolean()}   # last field: no trailing pad

def transform(r):
    return {"go": r.pptr(), "rot": r.fs(4), "pos": r.fs(3), "scale": r.fs(3),
            "children": r.vec(r.pptr), "father": r.pptr()}

def meshfilter(r): return {"go": r.pptr(), "mesh": r.pptr()}

def renderer_base(r):
    d = {"go": r.pptr(), "enabled": r.boolean(), "castShadows": r.boolean(), "receiveShadows": r.boolean(),
         "lightmapIndex": r.u8(), "lightmapTilingOffset": r.fs(4), "materials": r.vec(r.pptr),
         "subsetIndices": r.vec(r.u32), "staticBatchRoot": r.pptr(), "useLightProbes": (r.boolean(), r.align())[0],
         "lightProbeAnchor": r.pptr()}
    return d

def material(r):
    d = {"name": r.string(), "shader": r.pptr()}
    texenvs = r.vec(lambda: (r.string(), {"tex": r.pptr(), "scale": r.fs(2), "offset": r.fs(2)}))
    floats = r.vec(lambda: (r.string(), r.f32()))
    colors = r.vec(lambda: (r.string(), r.fs(4)))
    d.update(texenvs=texenvs, floats=floats, colors=colors)
    return d

def texture2d(r):
    d = {"name": r.string(), "width": r.i32(), "height": r.i32(), "completeImageSize": r.i32(), "format": r.i32(),
         "mipMap": r.boolean(), "isReadable": r.boolean(), "readAllowed": r.boolean()}
    r.align()
    d.update(imageCount=r.i32(), dimension=r.i32(), filterMode=r.i32(), aniso=r.i32(), mipBias=r.f32(), wrapMode=r.i32(),
             lightmapFormat=r.i32(), colorSpace=r.i32())
    n = r.count(); d["data_offset"] = r.p; d["data_size"] = n; r.p += n; r.align()
    return d

CM_SIZE = 172   # empty CompressedMesh block in PS3 builds (all meshes uncompressed); validated to be zeros

def mesh(r):
    d = {"name": r.string()}
    d["submeshes"] = r.vec(lambda: {"firstByte": r.u32(), "indexCount": r.u32(), "topology": r.i32(), "triangleCount": r.u32(),
                                    "firstVertex": r.u32(), "vertexCount": r.u32(), "aabb": r.fs(6)})
    d["meshCompression"] = r.u8(); r.align()
    n = r.count(); d["index_offset"] = r.p; d["index_size"] = n; r.p += n; r.align()
    d["skin"] = r.vec(lambda: (r.fs(4), (r.i32(), r.i32(), r.i32(), r.i32())))
    d["bindPose"] = r.vec(lambda: r.fs(16))
    d["channels"] = r.u32(); d["vertexCount"] = r.u32()
    d["streams"] = [(r.u32(), r.u32(), r.u32(), r.u32()) for _ in range(4)]
    d["vd_unknown"] = r.u32()
    n = r.count(); d["vertex_offset"] = r.p; d["vertex_size"] = n; r.p += n; r.align()
    cm = r.b[r.p:r.p + CM_SIZE]
    if len(cm) != CM_SIZE or any(cm): raise ValueError("non-empty compressed mesh")
    r.p += CM_SIZE
    d["aabb"] = r.fs(6); d["usageFlags"] = r.i32()
    d["collisionTriangles"] = r.vec(r.u32); d["collisionVertexCount"] = r.i32()
    return d

READERS = {43: mesh, 28: texture2d, 1: gameobject, 4: transform, 33: meshfilter, 23: renderer_base, 21: material}

def validate(media, cids, dump=0):
    files = sorted(glob.glob(os.path.join(media, "level*"))) + sorted(glob.glob(os.path.join(media, "*.assets"))) \
        + [os.path.join(media, "mainData"), os.path.join(media, "Resources", "unity default resources")]
    stats = collections.defaultdict(collections.Counter); fails = collections.defaultdict(collections.Counter); shown = collections.Counter()
    for f in files:
        for pid, cid, b in u.objects(f):
            if cid not in cids: continue
            r = R(b)
            try:
                d = READERS[cid](r)
                if r.p == len(b): stats[cid]["exact"] += 1
                else: stats[cid]["mismatch"] += 1; fails[cid][f"end {r.p} vs {len(b)}"] += 1
                if shown[cid] < dump: shown[cid] += 1; print(f"[{cid}] {os.path.basename(f)}:{pid} {str(d)[:300]}")
            except Exception as e:
                stats[cid]["error"] += 1; fails[cid][str(e)[:50]] += 1
    for cid in cids:
        s = stats[cid]; tot = sum(s.values())
        print(f"class {cid} ({u.CLASS.get(cid,'?')}): {tot} objects, exact={s['exact']} mismatch={s['mismatch']} error={s['error']}  top: {fails[cid].most_common(3)}")

if __name__ == "__main__":
    cids = [int(x) for x in sys.argv[2].split(",")]
    dump = int(sys.argv[sys.argv.index("--dump")+1]) if "--dump" in sys.argv else 0
    validate(sys.argv[1], cids, dump)
