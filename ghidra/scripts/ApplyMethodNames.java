// Create/rename functions from an aot_method_map.py CSV. Names: namespace = C# type (nested via '/'), name = method.
// Args: <methods.csv> <report.txt>
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class ApplyMethodNames extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        SymbolTable st = currentProgram.getSymbolTable();
        FunctionManager fm = currentProgram.getFunctionManager();
        int total = 0, created = 0, renamed = 0, failed = 0, startMismatch = 0;
        List<String> problems = new ArrayList<>();
        try (BufferedReader r = new BufferedReader(new FileReader(a[0]))) {
            String line = r.readLine(); // header
            while ((line = r.readLine()) != null) {
                String[] c = line.split(",", -1);
                if (c[1].isEmpty()) continue;
                total++;
                Address addr = toAddr(Long.decode(c[1]));
                try {
                    Function f = fm.getFunctionAt(addr);
                    if (f == null) {
                        Function containing = fm.getFunctionContaining(addr);
                        if (containing != null) { startMismatch++; removeFunction(containing); }
                        new DisassembleCommand(addr, null, true).applyTo(currentProgram, monitor);
                        f = createFunction(addr, null);
                        if (f == null) { failed++; problems.add("create failed " + c[0] + " " + c[1]); continue; }
                        created++;
                    }
                    Namespace ns = currentProgram.getGlobalNamespace();
                    for (String part : c[3].replace('.', '_').split("/"))
                        ns = getOrCreate(st, ns, part);
                    f.setParentNamespace(ns);
                    f.setName(c[4].replace('.', '_'), SourceType.IMPORTED);
                    f.setComment("C# " + c[3] + "::" + c[4] + "(" + c[5] + ")  token " + c[0]);
                    renamed++;
                } catch (Exception e) { failed++; problems.add(c[0] + " " + c[1] + ": " + e.getMessage()); }
            }
        }
        try (PrintWriter w = new PrintWriter(new FileWriter(a[1]))) {
            w.printf("mapped=%d named=%d created=%d replaced_misaligned=%d failed=%d functions_now=%d%n",
                total, renamed, created, startMismatch, failed, fm.getFunctionCount());
            for (String p : problems) w.println(p);
        }
    }
    private Namespace getOrCreate(SymbolTable st, Namespace parent, String name) throws Exception {
        Namespace ns = st.getNamespace(name, parent);
        return ns != null ? ns : st.createNameSpace(parent, name, SourceType.IMPORTED);
    }
}
