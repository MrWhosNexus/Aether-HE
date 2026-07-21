import json, re, os, sys
base = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(base, 'driver_src')
tables = json.load(open(os.path.join(base, 'hed-strings.json'), encoding='utf-8'))
while isinstance(tables, str):
    tables = json.loads(tables)
FILES = {
 'agreement': ('agreement.min.js', '_0x48e7'),
 'variable': ('variable.min.js', '_0x13f9'),
 'wmIndex': ('wmIndex.min.js', '_0x34da'),
 'gamePad': ('gamePadKey.min.js', '_0x118c'),
 'themes': ('js__themes.min.js', '_0x590e'),
 'language': ('js__language.min.js', '_0x5803'),
 'clearCache': ('js__clearCache.min.js', '_0x3a0b'),
}
outdir = os.path.join(base, 'driver_deobf')
os.makedirs(outdir, exist_ok=True)
for key, (fn, dec) in FILES.items():
    p = os.path.join(src, fn)
    if not os.path.exists(p):
        print('missing', fn); continue
    code = open(p, encoding='utf-8').read()
    tbl = tables.get(key, {})
    # collect aliases: X=DEC
    aliases = set([dec])
    for _ in range(3):
        new = set()
        for a in list(aliases):
            for m in re.finditer(r'(_0x[0-9a-fA-F]+)\s*=\s*' + re.escape(a) + r'\b', code):
                new.add(m.group(1))
        aliases |= new
    pat = re.compile(r'(?:' + '|'.join(re.escape(a) for a in aliases) + r')\((0x[0-9a-fA-F]+)\)')
    hits = [0]
    def rep(m):
        v = tbl.get(m.group(1).lower())
        if v is None:
            return m.group(0)
        hits[0] += 1
        return json.dumps(v, ensure_ascii=False)
    code2 = pat.sub(rep, code)
    # light pretty-print
    code2 = code2.replace(';', ';\n')
    open(os.path.join(outdir, fn.replace('.min.js', '.deobf.js')), 'w', encoding='utf-8').write(code2)
    print(fn, 'aliases=%d' % len(aliases), 'substituted=%d' % hits[0])
