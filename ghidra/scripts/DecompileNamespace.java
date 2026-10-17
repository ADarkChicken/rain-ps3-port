// Decompile all functions in a namespace (C# type) and write C pseudocode + disassembly.
// Args: <namespace> <out_file>
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;

public class DecompileNamespace extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        Namespace ns = currentProgram.getGlobalNamespace();   // nested types: "Outer/Inner" (as in methods.csv)
        for (String part : a[0].split("/")) if (ns != null) ns = currentProgram.getSymbolTable().getNamespace(part, ns);
        if (ns == null) throw new Exception("namespace not found: " + a[0]);
        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        try (PrintWriter w = new PrintWriter(new FileWriter(a[1]))) {
            for (Symbol s : currentProgram.getSymbolTable().getSymbols(ns)) {
                Function f = getFunctionAt(s.getAddress());
                if (f == null || !f.getParentNamespace().equals(ns)) continue;
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
}
