import sys,os
tbl,rpk,out=sys.argv[1:4]
r=open(rpk,'rb')
ents=[l.split(None,2) for l in open(tbl)]
for o,s,n in ents[:4596]:
    n=n.strip(); p=os.path.join(out,n); os.makedirs(os.path.dirname(p),exist_ok=True)
    r.seek(int(o)*2048); open(p,'wb').write(r.read(int(s)))
