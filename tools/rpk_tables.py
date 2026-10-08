import struct,sys
d=open(sys.argv[1],'rb').read(); V=0xFF000
def isres(a): 
    o=a-V; return 0<=o<len(d)-4 and d[o:o+4]==b'res/'
# find all words pointing to res/ strings
hits=[i for i in range(0,len(d)-4,4) if isres(struct.unpack_from('<I',d,i)[0])]
print(len(hits))
# group into runs
runs=[];cur=[hits[0]]
for h in hits[1:]:
    if h-cur[-1]<=16: cur.append(h)
    else: runs.append(cur);cur=[h]
runs.append(cur)
for r in runs:
    stride=r[1]-r[0] if len(r)>1 else 0
    print(hex(r[0]),hex(r[-1]),len(r),'stride',stride, [hex(x) for x in struct.unpack_from('<4I',d,r[0])])
