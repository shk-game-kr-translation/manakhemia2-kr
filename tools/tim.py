"""PS1-style TIM (4/8bpp CLUT) read/write helpers. usage: tim.py in.tim out.png"""
import struct, sys
from PIL import Image


def read(d):
    magic, flags = struct.unpack_from('<II', d, 0)
    assert magic == 0x10
    bpp = flags & 3
    o = 8
    clut = None
    if flags & 8:
        ln, cx, cy, cw, ch = struct.unpack_from('<IHHHH', d, o)
        clut = list(struct.unpack_from('<%dH' % (cw * ch), d, o + 12))
        clut_off = o
        o += ln
    ln, ix, iy, iw, ih = struct.unpack_from('<IHHHH', d, o)
    pix = d[o + 12:o + ln]
    w = iw * (4 if bpp == 0 else 2 if bpp == 1 else 1)
    return dict(bpp=bpp, clut=clut, w=w, h=ih, pix=pix, img_off=o + 12, clut_off=clut_off if clut else None)


def c16(c):
    r = (c & 31) << 3; g = ((c >> 5) & 31) << 3; b = ((c >> 10) & 31) << 3
    a = 0 if c == 0 else 255
    return (r, g, b, a)


def to_image(t, pal=0):
    w, h = t['w'], t['h']
    idx = []
    if t['bpp'] == 2:
        im = Image.new('RGBA', (w, h))
        px = struct.unpack_from('<%dH' % (w * h), t['pix'])
        im.putdata([c16(c) if c else (0, 0, 0, 0) for c in px])
        return im
    if t['bpp'] == 0:
        for b in t['pix']:
            idx += [b & 15, b >> 4]
        base = pal * 16
    else:
        idx = list(t['pix'])
        base = pal * 256
    cl = [c16(c) for c in t['clut']]
    im = Image.new('RGBA', (w, h))
    im.putdata([cl[base + i] for i in idx[:w * h]])
    return im


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    t = read(d)
    print(t['w'], t['h'], t['bpp'], len(t['clut']))
    to_image(t).save(sys.argv[2])
