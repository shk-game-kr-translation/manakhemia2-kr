"""Render a TIM2 (first picture) to PNG. usage: tim2png.py in.tm2 out.png [palette_index_grayscale]"""
import sys, struct
from PIL import Image


def read_tim2(d):
    assert d[:4] == b'TIM2'
    o = 16
    total, clut_size, img_size, hdr_size, clut_colors, fmt, mip, clut_type, img_type, w, h = \
        struct.unpack_from('<IIIHHBBBBHH', d, o)
    pix = d[o + hdr_size:o + hdr_size + img_size]
    clut = d[o + hdr_size + img_size:o + hdr_size + img_size + clut_size]
    return dict(w=w, h=h, img_type=img_type, clut_type=clut_type, clut_colors=clut_colors,
                pix=pix, clut=clut, hdr_off=o, hdr_size=hdr_size)


def to_image(t, gray=False):
    w, h = t['w'], t['h']
    if t['img_type'] == 4:
        idx = []
        for b in t['pix']:
            idx += [b & 15, b >> 4]
    elif t['img_type'] == 5:
        idx = list(t['pix'])
    else:
        raise ValueError('img_type %d' % t['img_type'])
    if gray:
        n = 16 if t['img_type'] == 4 else 256
        im = Image.new('L', (w, h))
        im.putdata([i * 255 // (n - 1) for i in idx[:w * h]])
        return im
    pal = []
    c = t['clut']
    for i in range(t['clut_colors']):
        r, g, b, a = c[4 * i:4 * i + 4]
        pal.append((r, g, b, min(255, a * 2)))
    im = Image.new('RGBA', (w, h))
    im.putdata([pal[i] if i < len(pal) else (255, 0, 255, 255) for i in idx[:w * h]])
    return im


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    t = read_tim2(d)
    print(t['w'], t['h'], t['img_type'], t['clut_type'], t['clut_colors'])
    im = to_image(t, gray=len(sys.argv) > 3)
    if len(sys.argv) > 3:
        im = im.resize((im.width * 2, im.height * 2), Image.NEAREST)
    im.save(sys.argv[2])
