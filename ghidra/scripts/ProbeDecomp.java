// Probe: memory blocks, function/relocation counts, decompile a sample of functions to <out>.
// Args: <out_file> <max_funcs> [min_body_bytes]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import java.io.*;
import java.util.*;

public class ProbeDecomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        int max = Integer.parseInt(a[1]);
        long minBody = a.length > 2 ? Long.parseLong(a[2]) : 64;
        try (PrintWriter w = new PrintWriter(new FileWriter(a[0]))) {
            w.println("program=" + currentProgram.getName() + " lang=" + currentProgram.getLanguageID());
            for (MemoryBlock b : currentProgram.getMemory().getBlocks())
                w.println("block " + b.getName() + " " + b.getStart() + "-" + b.getEnd() + " " + (b.isExecute() ? "X" : "") + (b.isWrite() ? "W" : ""));
            FunctionManager fm = currentProgram.getFunctionManager();
            w.println("functions=" + fm.getFunctionCount() + " relocations=" + currentProgram.getRelocationTable().getSize());
            DecompInterface d = new DecompInterface();
            d.openProgram(currentProgram);
            int done = 0, ok = 0, warn = 0;
            List<Function> fs = new ArrayList<>();
            for (Function f : fm.getFunctions(true)) fs.add(f);
            int step = Math.max(1, fs.size() / Math.max(1, max * 3));
            for (int i = 0; i < fs.size() && done < max; i += step) {
                Function f = fs.get(i);
                if (f.getBody().getNumAddresses() < minBody) continue;
                done++;
                DecompileResults r = d.decompileFunction(f, 60, monitor);
                if (r.decompileCompleted()) {
                    ok++;
                    String c = r.getDecompiledFunction().getC();
                    if (c.contains("WARNING")) warn++;
                    w.println("==== " + f.getName() + " @ " + f.getEntryPoint() + " size=" + f.getBody().getNumAddresses());
                    w.println(c);
                } else w.println("==== FAIL " + f.getName() + ": " + r.getErrorMessage());
            }
            w.println("SUMMARY sampled=" + done + " decompiled=" + ok + " with_warnings=" + warn);
        }
    }
}
