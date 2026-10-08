import sys,re
ISO=sys.argv[1]; base=533486*2048; size=188473344
f=open(ISO,'rb'); f.seek(base); d=f.read(size)
open(sys.argv[2],'wb').write(d)
pat=re.compile(rb'(?:[\x82\x83][\x40-\xfc]){3,}')
import collections
c=collections.Counter()
for m in pat.finditer(d): c[m.start()>>20]+=1
for k in sorted(c): print(k,'MB',c[k])
lz=[m.start() for m in re.finditer(rb'LZR\0',d) if m.start()%2048==0]
print('LZR at sector starts',len(lz))
