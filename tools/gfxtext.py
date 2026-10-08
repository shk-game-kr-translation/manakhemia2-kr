"""Replace text drawn in textures (graphics text) with Korean.

Spec files: config/gfx/*.json
  {"pack": "fpack/menu.fp",
   "chunks": {"0": {"ow": 1, "labels": [{"box": [x, y, w, h], "ko": "아이템", "align": "left"}, ...]}}}
For each label the original pixels inside box are analysed (per-row fill colour, outline colour),
the box is cleared, and the Korean text is drawn in that style and mapped to the texture's own
palette (no palette change). Optional per-label keys: align (left/center/right), size (px),
fill / outline ([r,g,b]) overrides, ow (outline width, 0 = none), weight ("Bold"/"Black"/"Medium"),
dy (vertical offset).

usage:
  gfxtext.py seg <pack> <chunk>                 print ink segments (to author boxes)
  gfxtext.py preview <spec.json> <out_dir>      render replaced chunks to PNG (before/after)
"""
import sys, os, json, struct, collections
import paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
import fp, rpk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(paths.FONTS, 'NotoSansKR-%s.otf')


# ---------------------------------------------------------------- texture access
class Tex:
    """indexed texture inside a chunk (TIM2 first picture, or PS1 TIM 4/8bpp)"""

    def __init__(self, data):
        self.d = bytearray(data)
        d = self.d
        if d[:4] == b'TIM2':
            o = 16
            total, clut_size, img_size, hdr_size, ncol, fmt, mip, ctype, itype, w, h = \
                struct.unpack_from('<IIIHHBBBBHH', d, o)
            self.kind = 'tim2'
            self.bpp = {4: 4, 5: 8}[itype]
            self.w, self.h = w, h
            self.pix_off = o + hdr_size
            self.clut_off = o + hdr_size + img_size
            raw = [tuple(d[self.clut_off + 4 * i:self.clut_off + 4 * i + 4]) for i in range(ncol)]
            pal = [(r, g, b, min(255, a * 2)) for r, g, b, a in raw]
            if self.bpp == 8 and ncol == 256 and (ctype & 0x80) == 0:  # CSM1 swizzle
                pal = [pal[self._swz(i)] for i in range(256)]
            self.pal = pal
        elif d[:4] == b'\x10\0\0\0':
            flags = struct.unpack_from('<I', d, 4)[0]
            self.kind = 'tim'
            self.bpp = {0: 4, 1: 8}[flags & 3]
            o = 8
            ln, cx, cy, cw, ch = struct.unpack_from('<IHHHH', d, o)
            cl = struct.unpack_from('<%dH' % (cw * ch), d, o + 12)
            o += ln
            ln, ix, iy, iw, ih = struct.unpack_from('<IHHHH', d, o)
            self.pix_off = o + 12
            self.w, self.h = iw * (4 if self.bpp == 4 else 2), ih
            self.pal = [self._c16(c) for c in cl]
        else:
            raise ValueError('not a texture')
        n = self.w * self.h
        p = self.d[self.pix_off:]
        if self.bpp == 4:
            self.idx = [0] * n
            for i in range(n // 2):
                b = p[i]; self.idx[2 * i] = b & 15; self.idx[2 * i + 1] = b >> 4
        else:
            self.idx = list(p[:n])

    @staticmethod
    def _swz(i):
        return (i & ~0x18) | ((i & 8) << 1) | ((i & 16) >> 1)

    @staticmethod
    def _c16(c):
        r = (c & 31) << 3; g = ((c >> 5) & 31) << 3; b = ((c >> 10) & 31) << 3
        return (r, g, b, 0 if c == 0 else 255)

    def to_bytes(self):
        n = self.w * self.h
        if self.bpp == 4:
            out = bytes((self.idx[2 * i] & 15) | ((self.idx[2 * i + 1] & 15) << 4) for i in range(n // 2))
        else:
            out = bytes(self.idx)
        self.d[self.pix_off:self.pix_off + len(out)] = out
        return bytes(self.d)

    def pal_index_pal(self, i):
        return self.pal[i] if i < len(self.pal) else (255, 0, 255, 255)

    def image(self):
        im = Image.new('RGBA', (self.w, self.h))
        im.putdata([self.pal_index_pal(i) for i in self.idx])
        return im

    def px(self, x, y):
        return self.pal_index_pal(self.idx[y * self.w + x])

    def transparent(self):
        cnt = collections.Counter(self.idx)
        cands = [i for i in cnt if self.pal_index_pal(i)[3] == 0]
        if cands:
            return max(cands, key=lambda i: cnt[i])
        return min(range(len(self.pal)), key=lambda i: self.pal[i][3])


# ---------------------------------------------------------------- analysis
def ink(t, x, y):
    return t.px(x, y)[3] >= 64


def segments(t, gap=3):
    rows = [any(ink(t, x, y) for x in range(t.w)) for y in range(t.h)]
    bands, y = [], 0
    while y < t.h:
        if rows[y]:
            y0 = y
            while y < t.h and rows[y]:
                y += 1
            bands.append((y0, y))
        y += 1
    out = []
    for y0, y1 in bands:
        cols = [any(ink(t, x, y) for y in range(y0, y1)) for x in range(t.w)]
        segs, x = [], 0
        while x < t.w:
            if cols[x]:
                x0 = x
                while x < t.w and (cols[x] or any(cols[x:x + gap])):
                    x += 1
                segs.append((x0, x))
            x += 1
        out.append(((y0, y1), segs))
    return out


def analyse(t, box):
    x0, y0, w, h = box
    pts = [(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w) if ink(t, x, y)]
    if not pts:
        return None
    inkset = set(pts)
    edge, inner = [], []
    for x, y in pts:
        if all((x + dx, y + dy) in inkset for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            inner.append((x, y))
        else:
            edge.append((x, y))
    ys = [y for _, y in pts]; xs = [x for x, _ in pts]
    bb = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    def far(c1, c2):
        return sum((a - b) ** 2 for a, b in zip(c1, c2)) > 60 ** 2
    ce = collections.Counter(t.px(x, y)[:3] for x, y in edge if t.px(x, y)[3] >= 200)
    ce = ce.most_common(1)[0][0] if ce else collections.Counter(t.px(x, y)[:3] for x, y in edge).most_common(1)[0][0]
    fillpts = [(x, y) for x, y in pts if t.px(x, y)[3] >= 128 and far(t.px(x, y)[:3], ce)]
    outlined = len(fillpts) > 0.15 * len(pts)
    ow = 0
    if outlined:
        n_out = sum(1 for x, y in pts if not far(t.px(x, y)[:3], ce))
        ow = max(1, min(3, round(n_out / max(1, len(edge)) + 0.2)))
    src = fillpts if outlined else pts
    # fill colour as a smooth function of y (quadratic fit over the solid fill pixels): taking the
    # most common colour per row picked up outline/antialias shades on some rows -> visible stripes
    solid = [(y, t.px(x, y)[:3]) for x, y in src if t.px(x, y)[3] >= 200]
    if outlined:
        solid = [(y, c) for y, c in solid if sum((a - b) ** 2 for a, b in zip(c, ce)) > 90 ** 2] or solid
    if not solid:
        solid = [(y, t.px(x, y)[:3]) for x, y in src]
    lum = lambda c: c[0] * 3 + c[1] * 6 + c[2]
    byrow = collections.defaultdict(list)
    for y, c in solid:
        byrow[y].append(c)
    med = {y: sorted(cs, key=lum)[len(cs) // 2] for y, cs in byrow.items()}  # per-row median
    allc = sorted((c for _, c in solid), key=lum)
    top = allc[len(allc) // 2:] or allc  # brighter half = the flat fill of the original glyphs
    flat = tuple(sorted(c[k] for c in top)[len(top) // 2] for k in range(3))
    rowcol = {}
    for y in range(bb[1], bb[3]):
        near = [(abs(yy - y), c) for yy, c in med.items() if abs(yy - y) <= 3]
        if not near:
            near = [min(((abs(yy - y), c) for yy, c in med.items()), key=lambda v: v[0])]
        wsum = sum(4 - d for d, _ in near) or 1
        rowcol[y] = tuple(int(round(sum((4 - d) * c[k] for d, c in near) / wsum)) for k in range(3))
    return dict(bb=bb, rowcol=rowcol, outline=ce if outlined else None, outlined=outlined, ow=ow, flat=flat)


# ---------------------------------------------------------------- rendering
_fonts = {}


def font(weight, size):
    k = (weight, size)
    if k not in _fonts:
        path = paths.font(weight) if '.' in weight.split('#')[0] else FONTS % weight
        var = None
        if '#' in path:
            path, var = path.split('#')
        _fonts[k] = ImageFont.truetype(path, size)
        if var:
            _fonts[k].set_variation_by_name(var)
    return _fonts[k]


def vtext_mask(text, weight, width, maxh, pitch=None):
    """vertical text: glyphs stacked top to bottom, each about `width` px wide"""
    cells = []
    for ch in text:
        if ch == ' ':
            cells.append(None); continue
        m = text_mask(ch, weight, width, width + 4)
        cells.append(m)
    p = pitch or (width + 1)
    H = sum((p // 2 if c is None else p) for c in cells)
    if H > maxh:  # squeeze to fit
        p = max(width - 3, int(maxh / max(1, sum(0.5 if c is None else 1 for c in cells))))
        H = sum((p // 2 if c is None else p) for c in cells)
    out = Image.new('L', (width + 4, max(1, H)), 0)
    y = 0
    for c in cells:
        if c is None:
            y += p // 2; continue
        out.paste(c, ((width + 4 - c.width) // 2, y + max(0, (p - c.height) // 2)))
        y += p
    return out


def text_mask(text, weight, height, maxw, spacing=0):
    """antialiased L mask whose ink height == height (px), width <= maxw"""
    S = 4
    best = None
    for size in range(height * S, height * S * 3):
        f = font(weight, size)
        b = f.getbbox('한글')
        if b[3] - b[1] >= height * S:
            best = size; break
    f = font(weight, best)
    asc = f.getbbox('한글')
    widths = [f.getlength(ch) for ch in text]
    W = int(sum(widths) + spacing * S * (len(text) - 1)) + 8
    im = Image.new('L', (W, height * S + 4 * S), 0)
    dr = ImageDraw.Draw(im)
    x = 0
    for ch, cw in zip(text, widths):
        dr.text((x, -asc[1]), ch, font=f, fill=255)
        x += cw + spacing * S
    bb = im.getbbox() or (0, 0, 1, 1)
    im = im.crop((bb[0], 0, bb[2], height * S))
    w = max(1, round(im.width / S))
    if w <= maxw:
        return im.resize((w, height), Image.LANCZOS)
    # too wide: shrink proportionally first (down to 75 %), squeeze only the rest; the result is
    # vertically centred in the original height so baselines of neighbouring labels stay aligned
    k = max(0.75, maxw / w)
    h2 = max(6, round(height * k))
    small = im.resize((min(maxw, round(w * k)), h2), Image.LANCZOS)
    out = Image.new('L', (small.width, height), 0)
    out.paste(small, (0, (height - h2) // 2))
    return out


def render_label(t, lab, ow_default):
    box = lab['box']
    a = None if lab.get('noanalyse') else analyse(t, box)
    if a is None:
        if 'th' not in lab:
            raise ValueError(f'empty box {box}')
        a = dict(bb=(box[0], box[1], box[0] + box[2], box[1] + box[3]), rowcol={box[1]: (255, 255, 255)},
                 outline=None, outlined=False, ow=0, flat=(255, 255, 255))
    x0, y0, x1, y1 = a['bb']
    ow = lab.get('ow', a['ow'])
    sh = lab.get('shadow')  # [r, g, b, a, dx, dy]
    o2w = lab['outline2'][3] if lab.get('outline2') else 0
    th = (y1 - y0) - 2 * (ow + o2w) + lab.get('grow', 0) - (sh[5] if sh else 0)
    th = lab.get('th', th)
    maxw = box[0] + box[2] - x0 - 2 * ow if lab.get('align', 'left') == 'left' else box[2] - 2 * ow
    if not lab.get('noanalyse') and not lab.get('wide') and lab.get('align', 'left') in ('left', 'orig'):
        # the game crops each label to the original label's extent: never draw wider than it
        maxw = min(maxw, (x1 - x0) - 2 * ow + 1)
    lab['_maxw'] = maxw
    if lab.get('vertical') and lab.get('sideways'):  # horizontal text turned 90 deg clockwise
        m = text_mask(lab['ko'], lab.get('weight', 'Bold'), lab['vw'], box[3], lab.get('spacing', 0))
        m = m.rotate(-90, expand=True, resample=Image.BICUBIC)
        ox = (box[2] - m.width) // 2
    elif lab.get('vertical'):
        m = vtext_mask(lab['ko'], lab.get('weight', 'Bold'), lab['vw'], box[3], lab.get('pitch'))
        ox = (box[2] - m.width) // 2
    else:
        m = text_mask(lab['ko'], lab.get('weight', 'Bold'), th, maxw, lab.get('spacing', 0))
        if lab.get('fit') and len(lab['ko']) > 1 and m.width < 0.9 * maxw:
            sp = min(1.5, (0.95 * maxw - m.width) / (len(lab['ko']) - 1))
            m = text_mask(lab['ko'], lab.get('weight', 'Bold'), th, maxw, sp)
    if lab.get('rot'):
        m = m.rotate(lab['rot'], expand=True, resample=Image.BICUBIC)
    # canvas over the box
    W, H = box[2], box[3]
    if lab.get('align', 'left') == 'left':
        ox = x0 - box[0] + ow
    elif lab['align'] == 'center':
        ox = (W - m.width) // 2
    elif lab['align'] == 'orig':  # centred where the original label was centred
        ox = (x0 + x1) // 2 - box[0] - m.width // 2
    else:
        ox = W - m.width - ow
    oy = y0 - box[1] + ow + lab.get('dy', 0)
    if lab.get('valign') == 'center':
        oy = (H - m.height) // 2 + lab.get('dy', 0)
    if lab.get('vertical'):
        ox = (W - m.width) // 2
        oy = lab.get('dy', 0)
    if 'cx' in lab:  # explicit centre (box coords)
        ox = lab['cx'] - m.width // 2
        oy = lab['cy'] - m.height // 2
    mask = Image.new('L', (W, H), 0)
    if ow and not lab.get('soft'):  # crisp edges like the original pixel glyphs (no fill/outline blend)
        m = m.point(lambda v: 0 if v < 70 else 255 if v > 150 else int((v - 70) * 255 / 80))
    mask.paste(m, (ox, oy))
    if 'ring' in lab:  # [cx, cy, r, width] drawn in the fill colour (stamps)
        cx, cy, r, rw = lab['ring']
        rm = Image.new('L', (W * 4, H * 4), 0)
        ImageDraw.Draw(rm).ellipse([(cx - r) * 4, (cy - r) * 4, (cx + r) * 4, (cy + r) * 4], outline=255, width=rw * 4)
        rm = rm.resize((W, H), Image.LANCZOS)
        mask = ImageChops.lighter(mask, rm)
    rgba = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    if sh:
        sm = mask.point(lambda v: 255 if v > 40 else 0)
        if ow:
            sm = sm.filter(ImageFilter.MaxFilter(2 * ow + 1))
        sm2 = Image.new('L', (W, H), 0)
        sm2.paste(sm, (sh[4], sh[5]))
        rgba.paste(Image.new('RGBA', (W, H), tuple(sh[:4])), (0, 0), sm2)
    o2 = lab.get('outline2')  # [r, g, b, extra width]
    if o2:
        om2 = mask.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(2 * (ow + o2[3]) + 1))
        rgba.paste(Image.new('RGBA', (W, H), tuple(o2[:3]) + ((o2[4] if len(o2) > 4 else 255),)), (0, 0), om2)
    if ow:
        om = mask.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(2 * ow + 1))
        oc = tuple(lab.get('outline', a['outline'] or (0, 0, 0)))
        rgba.paste(Image.new('RGBA', (W, H), oc[:3] + ((oc[3] if len(oc) > 3 else 255),)), (0, 0), om)
    fill = Image.new('RGBA', (W, H))
    rows = a['rowcol']
    ks = sorted(rows)
    fpx = []
    for y in range(H):
        yy = y + box[1] - ow if ow else y + box[1]
        if 'grad' in lab:  # [[r,g,b] at text top, [r,g,b] at text bottom]
            (r0, g0, b0), (r1, g1, b1) = lab['grad']
            f = min(1, max(0, (y - oy) / max(1, m.height - 1)))
            c = (round(r0 + (r1 - r0) * f), round(g0 + (g1 - g0) * f), round(b0 + (b1 - b0) * f))
        elif 'fill' in lab:
            c = tuple(lab['fill'])
        elif lab.get('rowfill'):  # per-row colour of the original (genuine vertical gradients)
            near = min(ks, key=lambda k: abs(k - (y + box[1])))
            c = rows[near]
        else:
            c = a['flat']
        fpx += [c + (255,)] * W
    fill.putdata(fpx)
    if not ow:
        fill.putalpha(mask)
        return fill
    return _over(rgba, fill, mask)


def _over(base, top, mask):
    out = base.copy()
    out.paste(top, (0, 0), mask)
    return out


def inpaint(t, box, lum_min, engrave=None):
    """replace bright (text) pixels in box by neighbouring background pixels.
    engrave=lum_max: the text is cut out (transparent) with a dark edge: fill those instead."""
    x0, y0, w, h = box
    lum = lambda c: c[0] * 0.3 + c[1] * 0.59 + c[2] * 0.11
    if engrave == 'all':  # repaint the whole box with pixels sampled from its top/bottom 3 rows
        import random
        rnd = random.Random(x0 * 7919 + y0)
        pool = [t.idx[y * t.w + x] for y in list(range(y0, y0 + 3)) + list(range(y0 + h - 3, y0 + h))
                for x in range(x0, x0 + w)]
        pool = [i for i in pool if t.pal_index_pal(i)[3] >= 200] or pool
        for y in range(y0 + 3, y0 + h - 3):
            for x in range(x0, x0 + w):
                t.idx[y * t.w + x] = rnd.choice(pool)
        return
    if engrave is not None:
        hole = {(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w)
                if t.px(x, y)[3] < 128 or t.px(x, y)[2] < engrave[0] or t.px(x, y)[2] >= engrave[1]}
    elif lum_min < 0:  # dark text on a light background
        hole = {(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w)
                if t.px(x, y)[3] >= 64 and lum(t.px(x, y)) <= -lum_min}
    else:
        hole = {(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w)
                if t.px(x, y)[3] >= 64 and lum(t.px(x, y)) >= lum_min}
    if engrave is not None:  # noisy textures: fill with random background pixels from nearby rows
        import random
        rnd = random.Random(x0 * 7919 + y0)
        rows = {}
        for y in range(y0, y0 + h):
            rows[y] = [t.idx[yy * t.w + x] for yy in range(max(y0, y - 4), min(y0 + h, y + 5))
                       for x in range(x0, x0 + w) if (x, yy) not in hole]
        for x, y in hole:
            if rows[y]:
                t.idx[y * t.w + x] = rnd.choice(rows[y])
        return
    # dilate the hole by 1 so text outlines go too
    hole |= {(x + dx, y + dy) for x, y in hole for dx in (-1, 0, 1) for dy in (-1, 0, 1)
             if x0 <= x + dx < x0 + w and y0 <= y + dy < y0 + h and t.px(x + dx, y + dy)[3] >= 64}
    while hole:
        done = {}
        for x, y in hole:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                q = (x + dx, y + dy)
                if q not in hole and 0 <= q[0] < t.w and 0 <= q[1] < t.h and t.px(*q)[3] >= 64:
                    done[(x, y)] = t.idx[q[1] * t.w + q[0]]
                    break
        if not done:
            break
        for (x, y), i in done.items():
            t.idx[y * t.w + x] = i
        hole -= set(done)


def inpaint_caption(t, box, strict=False):
    """HELP screenshot captions: remove blue/red/orange/white caption pixels in box, fill from surroundings.
    strict: only the saturated outline colours and near-white (for captions over bluish backgrounds)"""
    x0, y0, w, h = box
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(t.w, x0 + w), min(t.h, y0 + h)

    def cap(c):
        r, g, b = c[:3]
        if strict:
            return (b > 200 and r < 60 and g < 60) or (r > 200 and g < 60 and b < 60) or \
                   (r > 225 and g > 225 and b > 225)
        return (b > 150 and r < 90 and g < 110 and b - r > 90) or (b >= 230 and b - r > 35) or \
               (r > 190 and g < 80 and b < 80) or (r > 215 and r - g > 55 and r - b > 55) or \
               (r > 238 and g > 238 and b > 238)
    hole = {(x, y) for y in range(y0, y1) for x in range(x0, x1) if cap(t.px(x, y))}
    # keep only pixels connected to the caption's saturated outline (drop stray matches in the scene)
    sat = {(x, y) for x, y in hole if (lambda c: (c[2] > 200 and c[0] < 60) or (c[0] > 200 and c[1] < 60))(t.px(x, y))}
    if sat:
        keep, stack = set(sat), list(sat)
        while stack:
            x, y = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (x + dx, y + dy)
                    if q in hole and q not in keep:
                        keep.add(q); stack.append(q)
        hole = keep
    for _ in range(2):
        hole |= {(x + dx, y + dy) for x, y in hole for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if x0 <= x + dx < x1 and y0 <= y + dy < y1}
    # vertical interpolation per column between the nearest clean pixels above / below
    n = min(len(t.pal), 16 if t.bpp == 4 else 256)
    cache = {}

    def nearest(c):
        if c not in cache:
            cache[c] = min(range(n), key=lambda i: sum((a - b) ** 2 for a, b in zip(t.pal[i][:3], c)) +
                           (0 if t.pal[i][3] >= 128 else 10 ** 6))
        return cache[c]
    cols = collections.defaultdict(list)
    for x, y in hole:
        cols[x].append(y)
    for x, ys in cols.items():
        ys = set(ys)
        y = min(ys)
        while y <= max(ys):
            if y not in ys:
                y += 1; continue
            ya = y
            while y in ys:
                y += 1
            yb = y - 1
            top = t.px(x, ya - 1)[:3] if ya - 1 >= 0 else None
            bot = t.px(x, yb + 1)[:3] if yb + 1 < t.h else None
            top = top or bot; bot = bot or top
            for yy in range(ya, yb + 1):
                f = (yy - ya + 1) / (yb - ya + 2)
                c = tuple(round(a + (b - a) * f) for a, b in zip(top, bot))
                t.idx[yy * t.w + x] = nearest(c)
    return
    while hole:
        done = {}
        for x, y in hole:
            vals = [t.idx[(y + dy) * t.w + x + dx] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    if (dx or dy) and (x + dx, y + dy) not in hole and 0 <= x + dx < t.w and 0 <= y + dy < t.h]
            if len(vals) >= 2 or (vals and len(done) == 0):
                done[(x, y)] = collections.Counter(vals).most_common(1)[0][0]
        if not done:
            for x, y in hole:
                vals = [t.idx[(y + dy) * t.w + x + dx] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                        if (dx or dy) and (x + dx, y + dy) not in hole and 0 <= x + dx < t.w and 0 <= y + dy < t.h]
                if vals:
                    done[(x, y)] = vals[0]
        if not done:
            break
        for (x, y), i in done.items():
            t.idx[y * t.w + x] = i
        hole -= set(done)


def quantize_into(t, box, rgba, trans, keep_bg=False):
    pal = t.pal
    n = min(len(pal), 16 if t.bpp == 4 else 256)
    cands = [i for i in range(n) if i == trans or pal[i][3] > 0]
    cache = {}
    x0, y0, W, H = box
    px = rgba.load()

    def dist(i, r, g, b, a):
        pr, pg, pb, pa = pal[i]
        w = min(a, pa) / 255
        return ((pr - r) ** 2 * 3 + (pg - g) ** 2 * 4 + (pb - b) ** 2 * 2) * w + (pa - a) ** 2 * 9

    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            if a < 12:
                if not keep_bg:
                    t.idx[(y0 + y) * t.w + x0 + x] = trans
                continue
            if (r, g, b) == (1, 2, 3) and a >= 128:  # engraved: cut out
                t.idx[(y0 + y) * t.w + x0 + x] = trans
                continue
            k = (r, g, b, a)
            if k not in cache:
                cache[k] = min(cands, key=lambda i: dist(i, r, g, b, a))
            t.idx[(y0 + y) * t.w + x0 + x] = cache[k]


def apply_chunk(data, spec):
    t = Tex(data)
    trans = t.transparent()
    ow = spec.get('ow', 1)
    defaults = {k: v for k, v in spec.items() if k != 'labels'}
    labs = [dict(defaults, **lab) for lab in spec['labels']]
    rendered = [(lab, render_label(t, lab, ow)) for lab in labs]
    for lab, _ in rendered:  # clear all boxes first (labels may be analysed from originals)
        x0, y0, w, h = lab['box']
        if lab.get('bg') == 'auto':  # solid badge background: most common index in the box
            lab['bg'] = collections.Counter(t.idx[y * t.w + x] for y in range(y0, y0 + h)
                                            for x in range(x0, x0 + w)).most_common(1)[0][0]
        if lab.get('caption'):
            inpaint_caption(t, lab['clear'] if 'clear' in lab else lab['box'], lab.get('strict', False))
            continue
        if 'inpaint' in lab or 'engrave' in lab:
            inpaint(t, lab['box'], lab.get('inpaint', 0), lab.get('engrave'))
            continue
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                t.idx[y * t.w + x] = lab.get('bg', trans)
    for lab, im in rendered:
        quantize_into(t, lab['box'], im, lab.get('bg', trans),
                      keep_bg='inpaint' in lab or 'engrave' in lab or lab.get('caption'))
    return t


def load_pack(name):
    elf = bytearray(open(paths.game('SLPM_550.05'), 'rb').read())
    for n, o, s in rpk.read_table(elf):
        if n == name:
            with open(paths.game('RPK.BIN'), 'rb') as f:
                f.seek(o * 2048)
                return f.read(s)
    raise KeyError(name)


def apply_join(texs, join):
    """labels drawn across several textures placed side by side.
    join: {"chunks": [a, b], "offsets": [[x, y], ...], "labels": [...]}; boxes in joined coordinates,
    labels need explicit th / colours (no analysis)."""
    defaults = {k: v for k, v in join.items() if k not in ('labels', 'chunks', 'offsets')}
    for lab0 in join['labels']:
        lab = dict(defaults, **lab0)
        bx, by, bw, bh = lab['box']
        local = dict(lab, box=[0, 0, bw, bh], noanalyse=True)
        im = render_label(texs[join['chunks'][0]], local, 0)
        for ci, (ox, oy) in zip(join['chunks'], join['offsets']):
            t = texs[ci]
            x0, y0 = max(bx, ox), max(by, oy)
            x1, y1 = min(bx + bw, ox + t.w), min(by + bh, oy + t.h)
            if x0 >= x1 or y0 >= y1:
                continue
            sub = [x0 - ox, y0 - oy, x1 - x0, y1 - y0]
            if 'inpaint' in lab:
                inpaint(t, sub, lab['inpaint'])
            crop = im.crop((x0 - bx, y0 - by, x1 - bx, y1 - by))
            quantize_into(t, sub, crop, t.transparent(), keep_bg=True)


def build_pack(raw, spec):
    cs = fp.chunks(raw)
    texs = {}
    for k, cspec in spec.get('chunks', {}).items():
        texs[int(k)] = apply_chunk(cs[int(k)]['data'], cspec)
    for join in spec.get('joins', []):
        for ci in join['chunks']:
            if ci not in texs:
                texs[ci] = Tex(cs[ci]['data'])
        apply_join(texs, join)
    return fp.rebuild(raw, {k: t.to_bytes() for k, t in texs.items()})


def build_file(raw, fspec):
    """single image file (optionally LZR-compressed TIM/TIM2) -> new file bytes"""
    import lzr
    packed = raw[:4] == b'LZR\0'
    data = lzr.decompress(raw) if packed else raw
    out = apply_chunk(data, fspec).to_bytes()
    return lzr.compress(out) if packed else out


def specs():
    d = os.path.join(paths.CONFIG, 'gfx')
    if not os.path.isdir(d):
        return []
    return [json.load(open(os.path.join(d, f), encoding='utf-8')) for f in sorted(os.listdir(d)) if f.endswith('.json')]


def main():
    cmd = sys.argv[1]
    if cmd == 'seg':
        raw = load_pack(sys.argv[2])
        t = Tex(fp.chunks(raw)[int(sys.argv[3])]['data'])
        print(t.kind, t.bpp, t.w, t.h, 'pal', len(t.pal), 'trans', t.transparent())
        for (y0, y1), segs in segments(t, int(sys.argv[4]) if len(sys.argv) > 4 else 3):
            print(f'y {y0}-{y1}:', ' '.join(f'{a}-{b}' for a, b in segs))
    elif cmd == 'preview':
        spec = json.load(open(sys.argv[2], encoding='utf-8'))
        out = sys.argv[3]; os.makedirs(out, exist_ok=True)
        if 'files' in spec:
            import lzr
            only = sys.argv[4:]  # optional subset of file names (substring match)
            for fname, fspec in spec['files'].items():
                if only and not any(o in fname for o in only):
                    continue
                raw = load_pack(fname)
                data = lzr.decompress(raw) if raw[:4] == b'LZR\0' else raw
                before = Tex(data).image()
                after = Tex(lzr.decompress(build_file(raw, fspec))).image()
                sc = 2
                W, H = before.width * sc, before.height * sc
                sheet = Image.new('RGBA', (W, H * 2 + 6), (30, 60, 30, 255))
                sheet.alpha_composite(before.resize((W, H), Image.NEAREST), (0, 0))
                sheet.alpha_composite(after.resize((W, H), Image.NEAREST), (0, H + 6))
                sheet.save(os.path.join(out, os.path.basename(fname) + '.png'))
            print('files ok')
            return
        raw = load_pack(spec['pack'])
        cs = fp.chunks(raw)
        new = build_pack(raw, spec)
        ncs = fp.chunks(new)
        keys = sorted(set(int(k) for k in spec.get('chunks', {})) | {c for j in spec.get('joins', []) for c in j['chunks']})
        for k in keys:
            before = Tex(cs[k]['data']).image()
            after = Tex(ncs[k]['data']).image()
            sc = 3
            W, H = before.width * sc, before.height * sc
            sheet = Image.new('RGBA', (W * 2 + 8, H), (30, 60, 30, 255))
            sheet.alpha_composite(before.resize((W, H), Image.NEAREST), (0, 0))
            sheet.alpha_composite(after.resize((W, H), Image.NEAREST), (W + 8, 0))
            sheet.save(os.path.join(out, f'{os.path.basename(spec["pack"])}_{k}.png'))
        print('pack ok', len(new), len(raw))


if __name__ == '__main__':
    main()
