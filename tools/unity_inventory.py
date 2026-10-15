"""Inventory Unity v9 serialized files (big-endian PS3) by classID: count + bytes.
Usage: unity_inventory.py <Media dir> <out.csv>
Header: metaSize,fileSize,version,dataOffset (BE) + endian byte; metadata: version str, platform,
typeCount(+trees), bigIDEnabled, objectCount, objects{pathID i32, start u32, size u32, typeID i32, classID u16, destroyed u16}."""
import collections, glob, os, struct, sys

CLASS = {1:"GameObject",4:"Transform",20:"Camera",21:"Material",23:"MeshRenderer",25:"Renderer",28:"Texture2D",33:"MeshFilter",
 43:"Mesh",48:"Shader",49:"TextAsset",54:"Rigidbody",64:"MeshCollider",65:"BoxCollider",74:"AnimationClip",82:"AudioSource",
 83:"AudioClip",89:"Cubemap",95:"Animator",104:"RenderSettings",108:"Light",111:"Animation",114:"MonoBehaviour",115:"MonoScript",
 128:"Font",135:"SphereCollider",136:"CapsuleCollider",137:"SkinnedMeshRenderer",142:"AssetBundle",143:"CharacterController",
 147:"ResourceManager",150:"PreloadData",157:"LightmapSettings",196:"NavMeshSettings",198:"ParticleSystem",199:"ParticleSystemRenderer",
 27:"Texture",121:"Flare",124:"Behaviour",156:"TerrainData",218:"Terrain",91:"AnimatorController",117:"Texture3D"}

def parse(path):
    with open(path, "rb") as f: hdr = f.read(20); meta_size, fsize, ver, doff = struct.unpack(">IIII", hdr[:16]); meta = f.read(meta_size)
    e = ">" if hdr[16] else "<"
    p = meta.index(b"\0") + 1; uver = meta[:p-1].decode()
    plat, ntypes = struct.unpack(e + "Ii", meta[p:p+8]); p += 8
    if ntypes: raise ValueError(f"{path}: type trees present ({ntypes}) - parser not implemented")
    _big, nobj = struct.unpack(e + "ii", meta[p:p+8]); p += 8
    objs = [struct.unpack(e + "iIIiHH", meta[p + i*20: p + i*20 + 20]) for i in range(nobj)]
    return ver, uver, plat, objs

if __name__ == "__main__":
    root, out = sys.argv[1], sys.argv[2]
    files = [f for f in glob.glob(os.path.join(root, "*")) if os.path.isfile(f) and (f.endswith(".assets") or os.path.basename(f).startswith("level") or os.path.basename(f) == "mainData")]
    files += glob.glob(os.path.join(root, "Resources", "unity default resources"))
    cnt, size, nfiles, vers = collections.Counter(), collections.Counter(), collections.Counter(), set()
    for f in files:
        ver, uver, plat, objs = parse(f); vers.add((ver, uver, plat))
        for o in objs: cnt[o[4]] += 1; size[o[4]] += o[2]
        nfiles.update({o[4] for o in objs})
    with open(out, "x") as w:
        w.write("classID,name,objects,files,total_bytes\n")
        for c, n in sorted(cnt.items(), key=lambda kv: -size[kv[0]]):
            w.write(f"{c},{CLASS.get(c,'?')},{n},{nfiles[c]},{size[c]}\n")
    print(f"files={len(files)} formats={vers} classes={len(cnt)} objects={sum(cnt.values())}")

def objects(path, class_id=None):
    """Yield (pathID, classID, bytes) for objects in a v9 file."""
    ver, uver, plat, objs = parse(path)
    with open(path, "rb") as f:
        hdr = f.read(20); doff = struct.unpack(">I", hdr[12:16])[0]
        for pid, start, size, tid, cid, _ in objs:
            if class_id is None or cid == class_id:
                f.seek(doff + start); yield pid, cid, f.read(size)

def externals(path):
    """v9 externals after the object table: count, then {emptyAsset cstr, guid[16], type i32, pathName cstr}."""
    with open(path, "rb") as f:
        hdr = f.read(20); meta_size = struct.unpack(">I", hdr[:4])[0]; meta = f.read(meta_size)
    e = ">" if hdr[16] else "<"
    p = meta.index(b"\0") + 1 + 8; p += 4  # version str, platform, typeCount(0), bigID
    nobj = struct.unpack(e + "i", meta[p:p+4])[0]; p += 4 + 20 * nobj
    n = struct.unpack(e + "i", meta[p:p+4])[0]; p += 4; out = []
    for _ in range(n):
        z = meta.index(b"\0", p); p = z + 1          # emptyAsset
        p += 16 + 4                                    # guid, type
        z = meta.index(b"\0", p); out.append(meta[p:z].decode(errors="replace")); p = z + 1
    return out

def rstr(b, p, e=">"):
    n = struct.unpack(e + "i", b[p:p+4])[0]; s = b[p+4:p+4+n].decode(errors="replace"); p += 4 + n
    return s, (p + 3) & ~3

def monoscripts(path):
    out = {}
    for pid, _, b in objects(path, 115):
        name, p = rstr(b, 0); p += 8; cls, p = rstr(b, p); ns, p = rstr(b, p); asm, p = rstr(b, p)
        out[pid] = (cls, ns, asm)
    return out
