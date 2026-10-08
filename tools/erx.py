"""Minimal reader for PS2 ERX (relocatable MIPS ELF, e_type 0xff91) modules."""
import struct, re

SJIS = re.compile(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x09\x0a\x20-\x7e])+\x00')


class Erx:
    def __init__(self, data):
        self.d = bytearray(data)
        d = self.d
        assert d[:4] == b'\x7fELF'
        (self.type, self.machine, _, self.entry, self.phoff, self.shoff, _, _, _, _,
         self.shentsize, self.shnum, self.shstrndx) = struct.unpack_from('<HHIIIIIHHHHHH', d, 16)
        self.sections = []
        for i in range(self.shnum):
            o = self.shoff + i * self.shentsize
            name, typ, flags, addr, off, size, link, info, align, entsize = struct.unpack_from('<10I', d, o)
            self.sections.append(dict(i=i, name_off=name, type=typ, flags=flags, addr=addr, off=off,
                                      size=size, link=link, info=info, align=align, entsize=entsize, hdr=o))
        st = self.sections[self.shstrndx]
        for s in self.sections:
            n = s['name_off']
            s['name'] = d[st['off'] + n: d.index(b'\0', st['off'] + n)].decode('ascii', 'replace')

    def sec(self, name):
        return next(s for s in self.sections if s['name'] == name)

    def relocs(self):
        """yield (section_index_patched, offset_in_section, type, symidx, rel_entry_file_off)"""
        for s in self.sections:
            if s['type'] == 9:  # SHT_REL
                tgt = s['info']
                for k in range(s['size'] // 8):
                    o = s['off'] + k * 8
                    r_off, r_info = struct.unpack_from('<II', self.d, o)
                    yield tgt, r_off, r_info & 0xff, r_info >> 8, o


if __name__ == '__main__':
    import sys, collections
    e = Erx(open(sys.argv[1], 'rb').read())
    for s in e.sections:
        print(s['i'], s['name'], hex(s['type']), 'addr', hex(s['addr']), 'off', hex(s['off']), 'size', hex(s['size']), 'info', s['info'])
    c = collections.Counter((t, ty) for t, o, ty, sy, ro in e.relocs())
    print(c)
