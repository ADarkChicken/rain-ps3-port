"""Write the Unity project's ProjectSettings from the game's own global managers (mainData; readers byte-exact):
InputManager (13): the 60 original axes verbatim (they already carry the developers' keyboard alternates: arrows = left
  stick, home/end/delete/page down = right stick, w/s/d/c = triangle/cross/square/circle, ...);
TagManager (78): user tags + the 32 layer names (the game uses CompareTag / LayerMask.NameToLayer everywhere);
PhysicsManager (55): gravity, layer collision matrix, raycastsHitTriggers; TimeManager (5): fixed/max timestep.
Only the listed fields are replaced in the existing 2017 assets; everything else keeps the Unity 2017 default.
Usage: gen_projectsettings.py <Media dir> <Unity project dir>"""
import os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unity_inventory as u
import unity35_classes as c

def fnum(x): return repr(round(x, 6)) if x != int(x) else str(int(x))

if __name__ == "__main__":
    media, proj = sys.argv[1], sys.argv[2]
    objs = {cid: b for pid, cid, b in u.objects(os.path.join(media, "mainData")) if cid in (13, 78, 55, 5)}
    ps = lambda n: os.path.join(proj, "ProjectSettings", n)
    def sub(text, pat, repl):
        out, n = re.subn(pat, lambda m: repl, text, count=1, flags=re.S | re.M); assert n == 1, pat; return out

    axes = c.inputmanager(c.R(objs[13]))["axes"]
    out = ["%YAML 1.1", "%TAG !u! tag:unity3d.com,2011:", "--- !u!13 &1", "InputManager:", "  m_ObjectHideFlags: 0", "  serializedVersion: 2", "  m_Axes:"]
    for a in axes:
        out += ["  - serializedVersion: 3", f"    m_Name: {a['name']}"]
        out += [f"    {k}: {a[k]}" for k in ("descriptiveName", "descriptiveNegativeName", "negativeButton", "positiveButton", "altNegativeButton", "altPositiveButton")]
        out += [f"    gravity: {fnum(a['gravity'])}", f"    dead: {fnum(a['dead'])}", f"    sensitivity: {fnum(a['sensitivity'])}",
                f"    snap: {int(a['snap'])}", f"    invert: {int(a['invert'])}", f"    type: {a['type']}", f"    axis: {a['axis']}", f"    joyNum: {a['joyNum']}"]
    open(ps("InputManager.asset"), "w", newline="\n").write("\n".join(out) + "\n")

    tm = c.tagmanager(c.R(objs[78])); t = open(ps("TagManager.asset")).read()
    t = sub(t, r"^  tags:.*?(?=^  layers:)", "  tags:\n" + "".join(f"  - {x}\n" for x in tm["tags"]))
    t = sub(t, r"^  layers:.*?(?=^  m_SortingLayers:)", "  layers:\n" + "".join(f"  - {x}\n" for x in tm["layers"]))
    open(ps("TagManager.asset"), "w", newline="\n").write(t)

    pm = c.physicsmanager(c.R(objs[55])); t = open(ps("DynamicsManager.asset")).read(); g = pm["gravity"]
    t = sub(t, r"^  m_Gravity:.*?$", "  m_Gravity: {x: %s, y: %s, z: %s}" % tuple(fnum(x) for x in g))
    t = sub(t, r"^  m_QueriesHitTriggers:.*?$", f"  m_QueriesHitTriggers: {int(pm['raycastsHitTriggers'])}")
    t = sub(t, r"^  m_LayerCollisionMatrix:.*?$", "  m_LayerCollisionMatrix: " + b"".join(struct.pack("<I", x) for x in pm["layerCollisionMatrix"]).hex())
    open(ps("DynamicsManager.asset"), "w", newline="\n").write(t)

    ti = c.timemanager(c.R(objs[5])); t = open(ps("TimeManager.asset")).read()
    t = sub(t, r"^  Fixed Timestep:.*?$", f"  Fixed Timestep: {fnum(ti['fixedTimestep'])}")
    t = sub(t, r"^  Maximum Allowed Timestep:.*?$", f"  Maximum Allowed Timestep: {fnum(ti['maximumAllowedTimestep'])}")
    open(ps("TimeManager.asset"), "w", newline="\n").write(t)
    print(f"{len(axes)} axes, {len(tm['tags'])} tags, layers {[x for x in tm['layers'] if x]}, gravity {g}, "
          f"raycastsHitTriggers {pm['raycastsHitTriggers']}, fixed dt {ti['fixedTimestep']:.4f}")
