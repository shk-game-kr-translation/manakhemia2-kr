"""Write the video elementary stream (stream E0 payloads) of an .SFD file.
usage: sfd_es.py <in.SFD> <out.m1v>"""
import sys
import sfd

d = open(sys.argv[1], 'rb').read()
es = b''.join(d[x['data_off']:x['data_off'] + x['data_len']] for x in sfd.packets(d) if x['sid'] == 0xE0)
open(sys.argv[2], 'wb').write(es)
print(len(es), 'bytes')
