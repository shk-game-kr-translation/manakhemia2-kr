import sys,collections
ISO=sys.argv[1]; base=533486*2048; size=188473344
f=open(ISO,'rb'); f.seek(base)
mag=collections.Counter(); first={}
for s in range(size//2048):
    b=f.read(2048)
    m=b[:4]
    if m==b'\0\0\0\0' : continue
    k=m if all(32<=x<127 for x in m) else None
    if k: 
        mag[k]+=1; first.setdefault(k,s)
for k,v in mag.most_common(40): print(k,v,first[k])
