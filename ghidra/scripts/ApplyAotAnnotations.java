// Apply Mono AOT annotations: PRX ADDR32 relocations, GOT slot labels, PLT stub functions.
// Args: <relocs.csv> <got.csv> <plt.csv> <got_base_hex> <report.txt>
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class ApplyAotAnnotations extends GhidraScript {
    static String clean(String s) {
        String c = s.replace("::", "__").replaceAll("[^A-Za-z0-9_.<>\\[\\]]", "_");
        return c.length() > 150 ? c.substring(0, 150) : c;
    }
    List<String[]> csv(String path) throws IOException {
        List<String[]> rows = new ArrayList<>();
        try (BufferedReader r = new BufferedReader(new FileReader(path))) {
            r.readLine();
            for (String l; (l = r.readLine()) != null; ) if (l.split("	", -1).length >= 4 || !path.endsWith(".tsv")) rows.add(l.split(path.endsWith(".tsv") ? "	" : ",", -1));
        }
        return rows;
    }
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        long gotBase = Long.decode(a[3]);
        int rel = 0, relFail = 0, got = 0, plt = 0, pltCreated = 0, fail = 0;
        for (String[] c : csv(a[0])) {
            try { setInt(toAddr(Long.decode(c[0])), (int) (long) Long.decode(c[2])); rel++; }
            catch (Exception e) { relFail++; println("reloc fail " + c[0] + ": " + e.getMessage()); }
        }
        SymbolTable st = currentProgram.getSymbolTable();
        for (String[] c : csv(a[1])) {
            // slot,got_byte_offset,patch_type,target (target may contain commas -> rejoin)
            String target = c[3];
            Address ad = toAddr(gotBase + 4L * Long.parseLong(c[0]));
            try { st.createLabel(ad, clean("got_" + c[2] + "_" + target), SourceType.ANALYSIS); got++; }
            catch (Exception e) { fail++; }
        }
        FunctionManager fm = currentProgram.getFunctionManager();
        for (String[] c : csv(a[2])) {
            String target = c[4];
            Address ad = toAddr(Long.decode(c[1]));
            Address gs = toAddr(gotBase + 4L * Long.parseLong(c[2]));
            String nm = clean("plt_" + target);
            try {
                st.createLabel(gs, clean("gotplt_" + target), SourceType.ANALYSIS);
                Function f = fm.getFunctionAt(ad);
                if (f == null) {
                    new DisassembleCommand(ad, null, true).applyTo(currentProgram, monitor);
                    f = createFunction(ad, nm); pltCreated++;
                }
                if (f != null) { f.setName(nm, SourceType.ANALYSIS); f.setComment("PLT -> " + c[3] + " " + target); plt++; }
                else fail++;
            } catch (Exception e) { fail++; }
        }
        try (PrintWriter w = new PrintWriter(new FileWriter(a[4]))) {
            w.printf("relocs_applied=%d reloc_fail=%d got_labels=%d plt_named=%d plt_created=%d failures=%d%n",
                rel, relFail, got, plt, pltCreated, fail);
        }
    }
}
