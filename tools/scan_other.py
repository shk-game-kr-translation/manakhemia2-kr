import re, glob, os, collections, sys
root = sys.argv[1]
pat = re.compile(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e])+\x00')
c = collections.Counter(); n = collections.Counter(); lz = collections.Counter()
for f in glob.glob(os.path.join(root, '**', '*'), recursive=True):
    if os.path.isdir(f): continue
    rel = os.path.relpath(f, root).replace(os.sep, '/')
    if rel.startswith('Event/'): continue
    d = open(f, 'rb').read()
    parts = rel.split('/')
    key = '/'.join(parts[:2]) if len(parts) > 2 else parts[0] + '/*' + os.path.splitext(parts[-1])[1]
    if d[:3] == b'LZR':
        lz[key] += 1; continue
    for m in pat.finditer(d):
        try: t = m.group()[:-1].decode('cp932')
        except: continue
        k = sum(1 for ch in t if 0x3040 <= ord(ch) <= 0x30ff)
        if k >= 2:
            c[key] += len(t); n[key] += 1
for k, v in c.most_common(): print('TEXT', k, n[k], v)
for k, v in lz.most_common(): print('LZR', k, v)
