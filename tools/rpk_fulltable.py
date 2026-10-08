import struct,sys
d=open(sys.argv[1],'rb').read(); V=0xFF000
def cs(a):
    o=a-V
    if not 0<=o<len(d): return None
    e=d.find(b'\0',o)
    if e-o>100 or e==o: return None
    try:
        s=d[o:e].decode('ascii')
        return s if all(32<c.__len__()*0+ord(c)<127 for c in s) else None
    except: return None
i=0x597f10; out=[]
while True:
    a,b,c=struct.unpack_from('<3I',d,i)
    n=cs(a)
    if n is None: break
    out.append((b,c,n)); i+=12
print('end',hex(i),len(out),file=sys.stderr)
for b,c,n in out: print(b,c,n)
