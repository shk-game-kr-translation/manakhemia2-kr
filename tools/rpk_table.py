import struct,sys
ELF=sys.argv[1]; d=open(ELF,'rb').read(); V=0xFF000
def cstr(va):
    o=va-V; e=d.index(b'\0',o); return d[o:e].decode('cp932')
start=0x597f10
# walk backward
s=start
while True:
    a,b,c=struct.unpack_from('<3I',d,s-12)
    if V<=a<len(d)+V and d[a-V:a-V+4]==b'res/': s-=12
    else: break
ents=[];o=s
while True:
    a,b,c=struct.unpack_from('<3I',d,o)
    if not(V<=a<len(d)+V and d[a-V:a-V+4]==b'res/'): break
    ents.append((cstr(a),b,c)); o+=12
print('table',hex(s),hex(o),len(ents),file=sys.stderr)
for n,b,c in ents: print(f'{b:8d} {c:10d} {n}')
