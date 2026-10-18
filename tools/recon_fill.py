"""fill(type, {key: body | (new_declaration, body)}): replace skeleton stubs in work/recon/<type>.cs.
key = exact line prefix (starts with spaces) or 'Name(' to match a method by name ('' body = empty)."""
import re
NI = ' { throw new global::System.NotImplementedException(); }'
def fill(t, subs):
    p = f'work/recon/{t}.cs'; s = open(p, encoding='utf-8').read()
    for pre, val in subs.items():
        decl, body = val if isinstance(val, tuple) else (None, val)
        lead = re.escape(pre) if pre.startswith(' ') else r'[ \t]+[^\n(]*?\b' + re.escape(pre)
        m = re.search(r'(?m)^' + lead + r'[^\n]*?' + re.escape(NI) + '$', s)
        assert m, (t, pre)
        d = decl or m.group(0)[:-len(NI)]
        ind = re.match(r'\s*', d).group(0)
        b = body.strip('\n')
        rep = d + ' { }' if not b.strip() else d + '\n' + ind + '{\n' + '\n'.join(ind + '    ' + l if l.strip() else '' for l in b.splitlines()) + '\n' + ind + '}'
        s = s[:m.start()] + rep + s[m.end():]
    open(p, 'w', encoding='utf-8').write(s)
