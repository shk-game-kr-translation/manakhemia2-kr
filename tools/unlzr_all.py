import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lzr
src, dst = sys.argv[1:3]
for f in glob.glob(os.path.join(src, '**', '*'), recursive=True):
    if os.path.isdir(f): continue
    d = open(f, 'rb').read()
    if d[:4] != b'LZR\0': continue
    rel = os.path.relpath(f, src)
    o = os.path.join(dst, rel)
    os.makedirs(os.path.dirname(o), exist_ok=True)
    open(o, 'wb').write(lzr.decompress(d))
