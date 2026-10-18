// Decompile all functions in a namespace (C# type) and write C pseudocode + disassembly.
// Args: <namespace> <out_file>   |   @<list_file> <out_dir>  (one type per line -> <out_dir>/<type with / as .>.decomp.txt)
//       optional 3rd arg <assembly.got.csv>: recover Mono AOT switch tables (bctr through a SWITCH GOT slot; targets are
//       offsets from the method start) as jump-table overrides before decompiling, so case bodies are decompiled.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import ghidra.program.model.pcode.JumpTable;
import ghidra.app.cmd.function.CreateFunctionCmd;
import java.io.*;
import java.util.*;

public class DecompileNamespace extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        if (a.length > 2) loadSwitches(a[2]);
        if (a[0].startsWith("@")) {
            for (String t : java.nio.file.Files.readAllLines(java.nio.file.Paths.get(a[0].substring(1)))) {
                if (t.isBlank()) continue;
                try { dump(t.trim(), a[1] + "/" + t.trim().replace('/', '.').replace('<', '_').replace('>', '_') + ".decomp.txt"); }
                catch (Exception e) { println("SKIP " + t + ": " + e.getMessage()); }
            }
            return;
        }
        dump(a[0], a[1]);
    }

    private void dump(String type, String out) throws Exception {
        String[] a = {type, out};
        Namespace ns = currentProgram.getGlobalNamespace();   // nested types: "Outer/Inner" (as in methods.csv)
        for (String part : a[0].split("/")) if (ns != null) ns = currentProgram.getSymbolTable().getNamespace(part, ns);
        if (ns == null && a[0].contains(".")) {   // C# namespace "A.B": try Ghidra namespace path A::B
            ns = currentProgram.getGlobalNamespace();
            for (String part : a[0].split("[/.]")) if (ns != null) ns = currentProgram.getSymbolTable().getNamespace(part, ns);
        }
        if (ns == null) throw new Exception("namespace not found: " + a[0]);
        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        try (PrintWriter w = new PrintWriter(new FileWriter(a[1]))) {
            for (Symbol s : currentProgram.getSymbolTable().getSymbols(ns)) {
                Function f = getFunctionAt(s.getAddress());
                if (f == null || !f.getParentNamespace().equals(ns)) continue;
                for (int pass = 0; pass < 4 && applySwitches(f); pass++) { }   // case bodies may hold further switches
                w.println("==== " + f.getName() + " @ " + f.getEntryPoint() + "  // " + f.getComment());
                DecompileResults r = d.decompileFunction(f, 120, monitor);
                w.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "DECOMPILE FAILED: " + r.getErrorMessage());
                w.println("---- asm");
                for (Instruction i : currentProgram.getListing().getInstructions(f.getBody(), true)) {
                    String ref = "";
                    for (Reference rf : i.getReferencesFrom()) {
                        Symbol t = getSymbolAt(rf.getToAddress());
                        if (t != null) ref += " ; " + t.getName();
                    }
                    w.println("  " + i.getAddress() + "  " + i + ref);
                }
            }
        }
    }

    private final Map<Long, long[]> switches = new HashMap<>();
    private final Set<Address> done = new HashSet<>();

    private void loadSwitches(String gotCsv) throws IOException {
        for (String l : java.nio.file.Files.readAllLines(java.nio.file.Paths.get(gotCsv))) {
            String[] c = l.split(",", 4);
            if (c.length < 4 || !c[2].equals("SWITCH")) continue;
            String[] t = c[3].split(" ");   // "<n> targets 0x.. 0x.."
            long[] v = new long[t.length - 2];
            for (int k = 2; k < t.length; k++) v[k - 2] = Long.decode(t[k]);
            switches.put(Long.decode(c[1]), v);
        }
    }

    /** One pass: override every not-yet-handled `bctr` fed by `lis/ori r0; lwzx rX,r30,r0` on a SWITCH slot. */
    private boolean applySwitches(Function f) throws Exception {
        if (switches.isEmpty()) return false;
        long hi = 0, lo = -1, slot = -1; boolean changed = false;
        for (Instruction i : currentProgram.getListing().getInstructions(f.getBody(), true)) {
            String m = i.getMnemonicString(), o0 = i.getDefaultOperandRepresentation(0);
            if (m.equals("lis") && o0.equals("r0")) hi = Long.decode(i.getDefaultOperandRepresentation(1)) & 0xFFFF;
            else if (m.equals("ori") && o0.equals("r0")) lo = (hi << 16) | Long.decode(i.getDefaultOperandRepresentation(2));
            else if (m.equals("lwzx") && i.getDefaultOperandRepresentation(1).equals("r30")) slot = lo;
            else if (m.equals("bctr") && switches.containsKey(slot) && done.add(i.getAddress())) {
                ArrayList<Address> dest = new ArrayList<>();
                for (long off : switches.get(slot)) {
                    Address t = f.getEntryPoint().add(off);
                    if (getInstructionAt(t) == null) disassemble(t);
                    currentProgram.getReferenceManager().addMemoryReference(i.getAddress(), t, RefType.COMPUTED_JUMP, SourceType.USER_DEFINED, CodeUnit.MNEMONIC);
                    if (!dest.contains(t)) dest.add(t);
                }
                new JumpTable(i.getAddress(), dest, true, 0).writeOverride(f);
                changed = true;
            }
        }
        if (changed) CreateFunctionCmd.fixupFunctionBody(currentProgram, f, monitor);
        return changed;
    }
}
