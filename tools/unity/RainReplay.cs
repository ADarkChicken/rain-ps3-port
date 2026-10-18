// Differential-test pilot, step (c): replay RPCS3 call samples (tools/probe_calls.py -> tools/replay_cases.py) against the
// reconstructed code compiled to Assets/Plugins/RainRecon.dll (lift_compile.py --out) and report mismatches.
//   Unity.exe -batchmode -quit -projectPath <proj> -executeMethod RainReplay.Run -replayDir <dir with cases.tsv, layouts.tsv>
// Writes <dir>/report.txt. ABI as observed in the samples (PS3 Mono AOT, big-endian, 32-bit pointers): `this`/args from r3,
// float/double args in f1.. (each also using up a GPR slot while r3-r10 last), struct args one 32-bit word per GPR (args past
// r10 from the caller's stack at sp+0x30, one doubleword each, no shadow slots for r3-r10; seen once, PushBody.HitTarget.SetParam), ref/out/array/string args as pointers
// whose memory (0x100 bytes) was sampled at entry and again at return; struct returns via a hidden pointer before `this`.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Serialization;
using System.Text;
using UnityEngine;

public static class RainReplay
{
    const BindingFlags ALL = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;
    const BindingFlags INST = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

    class Skip : Exception { public Skip(string m) : base(m) { } }

    static uint U32(byte[] b, int o) { return (uint)(b[o] << 24 | b[o + 1] << 16 | b[o + 2] << 8 | b[o + 3]); }
    static ulong U64(byte[] b, int o) { return (ulong)U32(b, o) << 32 | U32(b, o + 4); }

    static byte[] Hex(string s)
    {
        var b = new byte[s.Length / 2];
        for (int i = 0; i < b.Length; i++) b[i] = Convert.ToByte(s.Substring(i * 2, 2), 16);
        return b;
    }
    static ulong[] Regs(string s) { return s.Length == 0 ? new ulong[0] : s.Split(',').Select(x => Convert.ToUInt64(x, 16)).ToArray(); }
    static Dictionary<int, byte[]> Mems(string s)
    {
        var d = new Dictionary<int, byte[]>();
        foreach (var kv in s.Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries))
        {
            int e = kv.IndexOf('=');
            d[int.Parse(kv.Substring(1, e - 1))] = Hex(kv.Substring(e + 1));
        }
        return d;
    }

    // --- value decoding (sequential layout, natural alignment; same rule as annotate_decomp.struct_size) ---
    static IEnumerable<FieldInfo> StructFields(Type t)
    {
        return t.GetFields(INST).OrderBy(f => f.MetadataToken);
    }
    static int Align(Type t)
    {
        if (t.IsEnum) t = Enum.GetUnderlyingType(t);
        if (t.IsPrimitive) return Size(t);
        if (!t.IsValueType) return 4;
        int a = 1; foreach (var f in StructFields(t)) a = Math.Max(a, Align(f.FieldType)); return a;
    }
    static int Size(Type t)
    {
        if (t.IsEnum) t = Enum.GetUnderlyingType(t);
        if (t == typeof(bool) || t == typeof(byte) || t == typeof(sbyte)) return 1;
        if (t == typeof(short) || t == typeof(ushort) || t == typeof(char)) return 2;
        if (t == typeof(long) || t == typeof(ulong) || t == typeof(double)) return 8;
        if (t.IsPrimitive || !t.IsValueType) return 4;
        int off = 0, al = 1;
        foreach (var f in StructFields(t))
        {
            int a = Align(f.FieldType); off = (off + a - 1) / a * a + Size(f.FieldType); al = Math.Max(al, a);
        }
        return Math.Max(1, (off + al - 1) / al * al);
    }
    static object Read(Type t, byte[] b, int o)
    {
        if (o + Size(t) > b.Length) throw new Skip("memory sample too short for " + t.Name);
        if (t.IsEnum) return Enum.ToObject(t, Read(Enum.GetUnderlyingType(t), b, o));
        if (t == typeof(bool)) return b[o] != 0;
        if (t == typeof(byte)) return b[o];
        if (t == typeof(sbyte)) return (sbyte)b[o];
        if (t == typeof(short)) return (short)(b[o] << 8 | b[o + 1]);
        if (t == typeof(ushort) || t == typeof(char)) { var u = (ushort)(b[o] << 8 | b[o + 1]); return t == typeof(char) ? (object)(char)u : u; }
        if (t == typeof(int)) return (int)U32(b, o);
        if (t == typeof(uint)) return U32(b, o);
        if (t == typeof(float)) return BitConverter.ToSingle(BitConverter.GetBytes(U32(b, o)), 0);
        if (t == typeof(long)) return (long)U64(b, o);
        if (t == typeof(ulong)) return U64(b, o);
        if (t == typeof(double)) return BitConverter.Int64BitsToDouble((long)U64(b, o));
        if (!t.IsValueType || t.IsPrimitive) throw new Skip("reference/unsupported " + t.Name);
        object v = Activator.CreateInstance(t); int off = 0;
        foreach (var f in StructFields(t))
        {
            int a = Align(f.FieldType); off = (off + a - 1) / a * a;
            f.SetValue(v, Read(f.FieldType, b, o + off)); off += Size(f.FieldType);
        }
        return v;
    }
    static bool IsPlainValue(Type t)
    {
        if (t.IsEnum || t.IsPrimitive) return true;
        if (!t.IsValueType) return false;
        return StructFields(t).All(f => IsPlainValue(f.FieldType));
    }
    static object ReadRef(Type t, byte[] mem, uint ptr)
    {
        if (ptr == 0) return null;
        if (mem == null) throw new Skip("no memory for " + t.Name + " pointer");
        if (t == typeof(string))
        {
            int n = (int)U32(mem, 8); if (0xc + 2 * n > mem.Length) throw new Skip("string longer than sample");
            var sb = new StringBuilder(); for (int i = 0; i < n; i++) sb.Append((char)(mem[0xc + 2 * i] << 8 | mem[0xd + 2 * i]));
            return sb.ToString();
        }
        if (t.IsArray && t.GetArrayRank() == 1 && IsPlainValue(t.GetElementType()))
        {
            var et = t.GetElementType(); int n = (int)U32(mem, 0xc), sz = Size(et);
            if (0x10 + n * sz > mem.Length) throw new Skip("array longer than sample");
            var a = Array.CreateInstance(et, n); for (int i = 0; i < n; i++) a.SetValue(Read(et, mem, 0x10 + i * sz), i);
            return a;
        }
        throw new Skip("reference argument " + t.Name);
    }

    // --- comparison ---
    static bool Same(object a, object b)
    {
        if (a == null || b == null) return a == b;
        if (a is float) { float x = (float)a, y = (float)b; return x == y || Math.Abs(x - y) <= 1e-5f * Math.Max(1f, Math.Max(Math.Abs(x), Math.Abs(y))) || float.IsNaN(x) && float.IsNaN(y); }
        if (a is double) { double x = (double)a, y = (double)b; return x == y || Math.Abs(x - y) <= 1e-9 * Math.Max(1.0, Math.Abs(x)); }
        if (a is Array) { var x = (Array)a; var y = (Array)b; if (x.Length != y.Length) return false; for (int i = 0; i < x.Length; i++) if (!Same(x.GetValue(i), y.GetValue(i))) return false; return true; }
        var t = a.GetType();
        if (t.IsValueType && !t.IsPrimitive && !t.IsEnum) return StructFields(t).All(f => Same(f.GetValue(a), f.GetValue(b)));
        return a.Equals(b);
    }
    static string Show(object v)
    {
        if (v == null) return "null";
        if (v is float) return ((float)v).ToString("R");
        if (v is Array) return "[" + string.Join(",", ((Array)v).Cast<object>().Select(Show).ToArray()) + "]";
        var t = v.GetType();
        if (t.IsValueType && !t.IsPrimitive && !t.IsEnum) return "{" + string.Join(",", StructFields(t).Select(f => Show(f.GetValue(v))).ToArray()) + "}";
        return v.ToString();
    }

    static FieldInfo FindField(Type t, string name)
    {
        for (; t != null; t = t.BaseType) { var f = t.GetField(name, INST | BindingFlags.DeclaredOnly); if (f != null) return f; }
        return null;
    }
    static Type FindType(Assembly asm, string name)
    {
        var t = asm.GetType(name.Replace('/', '+'));
        if (t != null) return t;
        var parts = name.Split('/');
        return asm.GetTypes().FirstOrDefault(x => x.Name == parts[parts.Length - 1] && (parts.Length == 1 || x.DeclaringType != null && x.DeclaringType.Name == parts[parts.Length - 2]));
    }
    static MethodInfo FindMethod(Type t, string name, string pars)
    {
        return t.GetMethods(ALL).FirstOrDefault(m => m.Name == name && string.Join(" ", m.GetParameters().Select(p => p.Name).ToArray()) == pars);
    }

    // GPR argument slot k (0 = r3); slots >= 8 come from the caller's stack (doubleword k - 8, low word)
    static ulong Slot(ulong[] gi, byte[] stack, int k)
    {
        if (k < 8) return gi[k];
        if (stack == null || 8 * k - 56 > stack.Length) throw new Skip("arg slot " + k + " beyond the stack sample");
        return U32(stack, 8 * (k - 8) + 4);
    }

    static object MakeThis(Type t, List<UnityEngine.Object> made)
    {
        if (t.IsAbstract) throw new Skip("abstract this " + t.Name);
        if (typeof(Component).IsAssignableFrom(t))
        {
            var go = new GameObject("replay"); made.Add(go);
            var c = go.AddComponent(t); if (c == null) throw new Skip("AddComponent failed");
            return c;
        }
        if (typeof(ScriptableObject).IsAssignableFrom(t)) { var s = ScriptableObject.CreateInstance(t); made.Add(s); return s; }
        if (t.IsValueType) return Activator.CreateInstance(t);
        return FormatterServices.GetUninitializedObject(t);
    }

    // value fields of `this` that lie inside the sampled memory: (field, offset)
    static List<KeyValuePair<FieldInfo, int>> ThisFields(Type t, Dictionary<int, string> layout, int len)
    {
        var l = new List<KeyValuePair<FieldInfo, int>>();
        if (layout == null) return l;
        foreach (var kv in layout)
        {
            var f = FindField(t, kv.Value);
            if (f != null && IsPlainValue(f.FieldType) && kv.Key + Size(f.FieldType) <= len) l.Add(new KeyValuePair<FieldInfo, int>(f, kv.Key));
        }
        return l;
    }

    static string Replay(Assembly asm, string[] c, Dictionary<string, Dictionary<int, string>> layouts, out string status)
    {
        status = "SKIP";
        if (c[1] == ".ctor" || c[1] == ".cctor") return "constructor";
        var t = FindType(asm, c[0]); if (t == null) return "type not found";
        var m = FindMethod(t, c[1], c[2]); if (m == null) return "method not found";
        if (m.ContainsGenericParameters) return "generic";
        ulong[] gi = Regs(c[3]), fi = Regs(c[4]), go = Regs(c[6]), fo = Regs(c[7]);
        var mi = Mems(c[5]); var mo = Mems(c[8]); byte[] stack = c.Length > 9 && c[9].Length > 0 ? Hex(c[9]) : null;
        var made = new List<UnityEngine.Object>();
        try
        {
            int g = 0, f = 0; object self = null;
            var rt = m.ReturnType; int retReg = -1;
            if (rt.IsValueType && !rt.IsPrimitive && !rt.IsEnum && rt != typeof(void)) retReg = 3 + g++;
            Dictionary<int, string> layout; layouts.TryGetValue(c[0], out layout);
            List<KeyValuePair<FieldInfo, int>> tf = null;
            if (!m.IsStatic)
            {
                self = MakeThis(t, made); int r = 3 + g++;
                byte[] tm; if (!mi.TryGetValue(r, out tm)) throw new Skip("no `this` memory");
                tf = ThisFields(t, layout, tm.Length);
                foreach (var kv in tf) kv.Key.SetValue(self, Read(kv.Key.FieldType, tm, kv.Value));
            }
            var ps = m.GetParameters(); var args = new object[ps.Length]; var ptrReg = new int[ps.Length];
            for (int i = 0; i < ps.Length; i++)
            {
                var pt = ps[i].ParameterType; ptrReg[i] = -1;
                if (pt.IsByRef)
                {
                    var et = pt.GetElementType(); if (g >= 8) throw new Skip("args beyond r10");
                    int r = 3 + g++; ptrReg[i] = r; byte[] pm; mi.TryGetValue(r, out pm);
                    if (!IsPlainValue(et)) throw new Skip("ref of reference type " + et.Name);
                    if (pm == null) throw new Skip("no memory for ref arg");
                    args[i] = Read(et, pm, 0);
                }
                else if (pt == typeof(float) || pt == typeof(double))
                {
                    double d = BitConverter.Int64BitsToDouble((long)fi[f++]); if (g < 8) g++;
                    args[i] = pt == typeof(float) ? (object)(float)d : d;
                }
                else if (pt.IsPrimitive || pt.IsEnum)
                {
                    var w = BitConverter.GetBytes((uint)Slot(gi, stack, g++)); Array.Reverse(w);
                    var u = pt.IsEnum ? Enum.GetUnderlyingType(pt) : pt;
                    int sz = Size(u); args[i] = Read(pt, w, 4 - sz);
                }
                else if (pt.IsValueType)
                {
                    int n = (Size(pt) + 3) / 4;
                    var b = new byte[n * 4];
                    for (int k = 0; k < n; k++) { var w = BitConverter.GetBytes((uint)Slot(gi, stack, g++)); Array.Reverse(w); Buffer.BlockCopy(w, 0, b, 4 * k, 4); }
                    args[i] = Read(pt, b, 0);
                }
                else
                {
                    if (g >= 8) throw new Skip("args beyond r10");
                    int r = 3 + g++; byte[] pm; mi.TryGetValue(r, out pm);
                    args[i] = ReadRef(pt, pm, (uint)gi[r - 3]);
                }
            }
            object res;
            try { res = m.Invoke(self, args); }
            catch (TargetInvocationException e)
            {
                status = "EXC"; var x = e.InnerException;
                var frame = (x.StackTrace ?? "").Split('\n').FirstOrDefault() ?? "";
                return x.GetType().Name + ": " + x.Message + " @ " + frame.Trim();
            }
            var diffs = new List<string>();
            if (rt != typeof(void))
            {
                object want = null; bool check = true;
                if (retReg >= 0) { byte[] rm; if (mo.TryGetValue(retReg, out rm)) want = Read(rt, rm, 0); else check = false; }
                else if (rt == typeof(float) || rt == typeof(double)) { double d = BitConverter.Int64BitsToDouble((long)fo[0]); want = rt == typeof(float) ? (object)(float)d : d; }
                else if (rt.IsPrimitive || rt.IsEnum) { var w = BitConverter.GetBytes((uint)go[0]); Array.Reverse(w); var u = rt.IsEnum ? Enum.GetUnderlyingType(rt) : rt; want = Read(rt, w, 4 - Size(u)); }
                else { check = false; if ((go[0] & 0xffffffff) == 0 != (res == null)) diffs.Add("return null-ness: game " + ((go[0] & 0xffffffff) == 0 ? "null" : "non-null") + ", recon " + (res == null ? "null" : "non-null")); }
                if (check && !Same(want, res)) diffs.Add("return: game " + Show(want) + ", recon " + Show(res));
            }
            for (int i = 0; i < ps.Length; i++)
            {
                byte[] pm; if (ptrReg[i] < 0 || !mo.TryGetValue(ptrReg[i], out pm)) continue;
                var want = Read(ps[i].ParameterType.GetElementType(), pm, 0);
                if (!Same(want, args[i])) diffs.Add(ps[i].Name + ": game " + Show(want) + ", recon " + Show(args[i]));
            }
            byte[] om;
            if (tf != null && mo.TryGetValue(3 + (retReg >= 0 ? 1 : 0), out om))
                foreach (var kv in tf)
                {
                    if (kv.Value + Size(kv.Key.FieldType) > om.Length) continue;
                    var want = Read(kv.Key.FieldType, om, kv.Value); var got = kv.Key.GetValue(self);
                    if (!Same(want, got)) diffs.Add("this." + kv.Key.Name + ": game " + Show(want) + ", recon " + Show(got));
                }
            status = diffs.Count == 0 ? "PASS" : "FAIL";
            return string.Join("; ", diffs.ToArray());
        }
        catch (Skip s) { status = "SKIP"; return s.Message; }
        finally { foreach (var o in made) if (o != null) UnityEngine.Object.DestroyImmediate(o); }
    }

    public static void Run()
    {
        System.Threading.Thread.CurrentThread.CurrentCulture = System.Globalization.CultureInfo.InvariantCulture;
        var cl = Environment.GetCommandLineArgs(); int ix = Array.IndexOf(cl, "-replayDir");
        string dir = ix >= 0 ? cl[ix + 1] : ".";
        var asm = AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(a => a.GetName().Name == "RainRecon");
        if (asm == null) { Debug.LogError("RAIN REPLAY: RainRecon.dll not loaded"); return; }
        var layouts = new Dictionary<string, Dictionary<int, string>>();
        foreach (var l in File.ReadAllLines(Path.Combine(dir, "layouts.tsv")))
        {
            var p = l.Split('\t'); if (p.Length < 2) continue;
            layouts[p[0]] = p[1].Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries).Select(x => x.Split('=')).ToDictionary(x => int.Parse(x[0]), x => x[1]);
        }
        var counts = new Dictionary<string, int>(); var lines = new List<string>(); var progress = Path.Combine(dir, "progress.txt");
        foreach (var l in File.ReadAllLines(Path.Combine(dir, "cases.tsv")))
        {
            var c = l.Split('\t'); if (c.Length < 9) continue;
            string id = c[0] + "." + c[1] + "(" + c[2] + ")";
            File.WriteAllText(progress, id);   // last case started, for diagnosing a hang
            string status, detail;
            try { detail = Replay(asm, c, layouts, out status); }
            catch (Exception e) { status = "ERR"; detail = e.GetType().Name + ": " + e.Message; }
            int n; counts.TryGetValue(status, out n); counts[status] = n + 1;
            lines.Add(status + "\t" + id + "\t" + detail);
        }
        lines.Sort(StringComparer.Ordinal);
        var summary = string.Join(" ", counts.OrderBy(k => k.Key).Select(k => k.Key + "=" + k.Value).ToArray());
        lines.Insert(0, "# " + summary);
        File.WriteAllLines(Path.Combine(dir, "report.txt"), lines.ToArray());
        Debug.Log("RAIN REPLAY " + summary);
    }
}
