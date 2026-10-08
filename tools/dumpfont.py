"""Dump ELF glyph fonts to a PNG sheet. usage: dumpfont.py ELF font_id out.png [start count]"""
import sys, struct
from PIL import Image
V = 0xFF000
LISTS = {0: 0x8aa030, 1: 0x8ab150}
GLYPHS = {0: 0x8ac058, 1: 0x946018}
GW, GH = 24, 24
GB = GW * GH // 2


def load(elf, fid):
    d = open(elf, 'rb').read()
    o = LISTS[fid] - V
    e = d.find(b'\0', o)
    chars = d[o:e].decode('cp932')
    return d, chars


def glyph(d, fid, i):
    o = GLYPHS[fid] - V + i * GB
    px = []
    for b in d[o:o + GB]:
        px += [b & 15, b >> 4]
    return px


if __name__ == '__main__':
    elf, fid, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    d, chars = load(elf, fid)
    st = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    n = int(sys.argv[5]) if len(sys.argv) > 5 else len(chars) - st
    cols = 32
    rows = (n + cols - 1) // cols
    im = Image.new('L', (cols * (GW + 2), rows * (GH + 2)), 40)
    for k in range(n):
        g = glyph(d, fid, st + k)
        t = Image.new('L', (GW, GH)); t.putdata([v * 17 for v in g])
        im.paste(t, ((k % cols) * (GW + 2), (k // cols) * (GH + 2)))
    im.save(out)
    print(len(chars))
