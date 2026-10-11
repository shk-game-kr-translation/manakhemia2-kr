"""Scrolling credits (ending movies): Korean labels on the staff roll.

The roll (text + ornaments + logo) is one layer moving up at a constant speed over the scene. Its strip
is the average of the frames shifted by the scroll: the roll stays sharp, the scene blurs out.
Strip coordinates: Y = screen y + v * (t - t0).

  py -X utf8 tools/movie_scroll.py strip NAME     build 30_build/movie/<NAME>_strip* (+ view sheets)
  py -X utf8 tools/movie_scroll.py align NAME REF shift <REF>'s items onto <NAME>'s strip (prints items)

Spec 20_source/config/movies/<NAME>.json, key "scroll":
  {"t0": frame, "t1": frame, "v": px/frame, "style": {...},
   "items": [{"y": strip y, "x": [x0, x1] search range, "ja": "...", "ko": "...",
              "align": "left"|"right"|"center", "mode": "inpaint" (on the logo), "style": {...}}]}
Only labels are replaced (roles, character names, instruments); people's and company names stay.

Per frame, each visible item's Japanese is removed: the scene under it is rebuilt from frames where the
roll has moved on (movie_subs.clean, motion compensated, the whole roll masked out), pixels on an
ornament of the roll are inpainted; then the Korean label is drawn at the same strip place.
"""
import sys, os, json
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.dirname(__file__))
import paths
import movie_subs as ms

W, H = ms.W, ms.H
STYLE = dict(font='NotoSansKR-Bold.otf', size=14, spacing=1, stroke=2, shadow_blur=1.2, shadow_alpha=0.5)


def strip_base(name):
    return os.path.join(paths.BUILD, 'movie', name + '_strip')


def build_strip(name, frames, t0, t1, v, step=3):
    """frac (share of frames where a strip pixel is roll text), mean image, luminance std"""
    Hs = int(H + v * (t1 - t0)) + 2
    acc = np.zeros((Hs, W), np.float32)
    cnt = np.zeros((Hs, 1), np.float32)
    rgb = np.zeros((Hs, W, 3), np.float32)
    sq = np.zeros((Hs, W), np.float32)
    for t in range(int(np.ceil(t0)), t1 + 1, step):
        off = v * (t - t0)
        io = int(np.floor(off)); fr = off - io
        M = np.float32([[1, 0, 0], [0, 1, fr]])
        m = cv2.warpAffine(ms.text_pixels(frames[t], False).astype(np.float32), M, (W, H + 1))
        im = cv2.warpAffine(np.asarray(frames[t], np.float32), M, (W, H + 1))
        lum = im.mean(2)
        acc[io:io + H + 1] += m
        rgb[io:io + H + 1] += im
        sq[io:io + H + 1] += lum * lum
        cnt[io:io + H + 1] += 1
    cnt = np.maximum(cnt, 1)
    frac = acc / cnt
    img = rgb / cnt[..., None]
    std = np.sqrt(np.maximum(sq / cnt - img.mean(2) ** 2, 0))
    b = strip_base(name)
    np.save(b + '_frac.npy', frac)
    np.save(b + '_std.npy', std.astype(np.float16))
    cv2.imwrite(b + '.png', cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    return frac, img, std


def view_sheets(name, items=None, chunk=800, per=3, x0=100):
    im = cv2.imread(strip_base(name) + '.png')
    if items:
        for it in items:
            y = it['y']
            cv2.line(im, (x0, y), (x0 + 8, y), (0, 0, 255), 2)
    tiles = []
    for y in range(0, im.shape[0], chunk):
        t = np.zeros((chunk, W - x0, 3), np.uint8)
        p = im[y:y + chunk, x0:]
        t[:p.shape[0]] = p
        for yy in range(0, chunk, 50):
            cv2.putText(t, str(y + yy), (2, yy + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        tiles.append(t)
    sep = np.full((chunk, 6, 3), (255, 0, 255), np.uint8)
    out = []
    for k in range(0, len(tiles), per):
        row = []
        for t in tiles[k:k + per]:
            row += [t, sep]
        p = os.path.join(paths.TEST, 'movie', '%s_strip_%d.png' % (name, k // per))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        cv2.imwrite(p, np.concatenate(row, 1))
        out.append(p)
    return out


def render_label(text, st, fill, stroke_rgb):
    """RGBA patch (h, w, 4) float32 0..1 of one text line; returns (patch, ink box (x0, y0, x1, y1))"""
    scale = 4
    big = ImageFont.truetype(paths.font(st['font']), st['size'] * scale)
    sw = int(round(st['stroke'] * scale))
    pad = 6 * scale
    w = int(sum(big.getlength(c) for c in text) + st['spacing'] * scale * max(0, len(text) - 1)) + 2 * pad
    asc, desc = big.getmetrics()
    h = asc + desc + 2 * pad
    tx = Image.new('L', (w, h), 0)
    ed = Image.new('L', (w, h), 0)
    dt, de = ImageDraw.Draw(tx), ImageDraw.Draw(ed)
    x = pad
    for c in text:
        de.text((x, pad), c, font=big, fill=255, stroke_width=sw, stroke_fill=255)
        dt.text((x, pad), c, font=big, fill=255)
        x += big.getlength(c) + st['spacing'] * scale
    ws, hs = w // scale, h // scale
    tx = np.asarray(tx.resize((ws, hs), Image.LANCZOS), np.float32) / 255
    ed_i = ed.resize((ws, hs), Image.LANCZOS)
    sh = np.asarray(ed_i.filter(ImageFilter.GaussianBlur(st['shadow_blur'])), np.float32) / 255
    ed = np.asarray(ed_i, np.float32) / 255
    rgb = np.zeros((hs, ws, 3), np.float32)
    alpha = np.zeros((hs, ws), np.float32)
    sc = np.array(stroke_rgb, np.float32) / 255
    for col, a in ((sc, sh * st['shadow_alpha']), (sc, ed), (np.array(fill, np.float32) / 255, tx)):
        rgb = rgb * (1 - a[..., None]) + col * a[..., None]
        alpha = alpha + a * (1 - alpha)
    rgb = np.where(alpha[..., None] > 1e-4, rgb / np.maximum(alpha[..., None], 1e-4), 0)
    ys, xs = np.nonzero(tx > 0.3)
    return np.dstack([rgb, alpha]), (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)


class Scroll:
    def __init__(self, name, frames, spec, motion_cls=None):
        self.name = name
        self.f = frames
        sp = spec['scroll']
        self.t0, self.t1, self.v = sp['t0'], sp['t1'], sp['v']
        b = strip_base(name)
        if not os.path.exists(b + '_std.npy'):
            build_strip(name, frames, self.t0, self.t1, self.v)
        self.frac = np.load(b + '_frac.npy')
        self.std = np.load(b + '_std.npy').astype(np.float32)
        self.img = cv2.cvtColor(cv2.imread(b + '.png'), cv2.COLOR_BGR2RGB).astype(np.float32)
        self.Hs = len(self.frac)
        st0 = dict(STYLE, **sp.get('style', {}))
        # text of the roll, found on the (sharp) strip image: pale fill next to its dark outline. The
        # per-frame white-text share (frac) misses tinted labels (pale green / lilac sections)
        lum = self.img.mean(2)
        near = cv2.dilate((lum < 60).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        self.tx = ((lum > 140) & near) | (self.frac > 0.3)
        text = self.tx | (self.frac > 0.06)
        # the roll: text (+ outline) and the ornaments/logo. In the strip the scene is smeared along y,
        # the roll is not: ornaments = vertical detail. Sampling source frames must avoid all of it
        hf = cv2.blur(np.abs(lum - cv2.GaussianBlur(lum, (1, 0), sigmaX=0.1, sigmaY=3)), (9, 9))
        orn = hf > 4
        # (the text's own detail spreads ~8 px through the blur and outline: not an ornament)
        self.orn = orn & ~cv2.dilate(text.astype(np.uint8), np.ones((17, 17), np.uint8)).astype(bool)
        self.roll = cv2.dilate((text | orn).astype(np.uint8), np.ones((11, 11), np.uint8)).astype(bool)
        # thinner version for the frame being rebuilt: movie_subs.clean checks each sample against a ring
        # of untouched pixels around the erased label, which the wide mask would cover entirely
        self.roll_thin = cv2.dilate(text.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) | orn
        self.items = []
        for it in sp['items']:
            self.items.append(self._item(it, st0))
        self.motion = Motion(frames, self.roll_at)
        self.prepared = None
        # a rotating magic circle behind the roll (ED_ROZE/ED_URU): it turns and glows, so other frames
        # don't match it; erased pixels on it are interpolated along its rings instead (polar coordinates)
        self.circle = sp.get('circle')
        self.reach = sp.get('reach', 90)
        self._cache = {}

    def _item(self, it, st0):
        st = dict(st0, **it.get('style', {}))
        y = it['y']
        x0, x1 = it.get('x', [100, 600])
        band = np.zeros_like(self.frac, bool)
        h = it.get('h', 13)
        band[max(0, y - h):y + h + 1, x0:x1] = True
        core = self.tx & band
        if core.sum() < 10:
            raise SystemExit('%s: no text found for %r at y %d' % (self.name, it.get('ja', it['ko']), y))
        ys, xs = np.nonzero(core)
        by0, by1, bx0, bx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        box = np.zeros_like(band)
        box[by0 - 2:by1 + 2, bx0 - 2:bx1 + 2] = True
        glyph = (self.tx | (self.frac > 0.04)) & box
        erase = cv2.dilate(glyph.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & band
        if it.get('mode') == 'inpaint':
            # small text on the logo (navy outline, busy artwork around): looser test, inside the band only
            # (on a semi-transparent logo the strip shows the text dimmer: brighter than its surroundings)
            y0b, y1b = max(0, y - h - 8), y + h + 9
            lum = self.img[y0b:y1b].mean(2)
            loc = cv2.medianBlur(np.clip(lum, 0, 255).astype(np.uint8), 9).astype(np.float32)
            nb = cv2.dilate((lum < 95).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            g = np.zeros_like(glyph)
            g[y0b:y1b] = (lum > loc + 18) & (lum > 100) & nb
            glyph = (g | glyph) & band
            erase = cv2.dilate(glyph.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & band
        ey0, ey1 = np.nonzero(erase.any(1))[0][[0, -1]]
        ex0, ex1 = np.nonzero(erase.any(0))[0][[0, -1]]
        ey1 += 1; ex1 += 1
        # colours of the original label: fill = its brightest core pixels, outline = darkest around them
        img = self.img
        lum = img.mean(2)
        cv = img[core]
        fill = it.get('fill') or np.median(cv[cv.mean(1) >= np.percentile(cv.mean(1), 50)], 0).tolist()
        ring = erase & ~cv2.dilate(core.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        rv = img[ring]
        dark = rv[rv.mean(1) <= np.percentile(rv.mean(1), 10)]
        stroke = it.get('stroke') or np.median(dark, 0).tolist()
        patch, ink = render_label(it['ko'], st, fill, stroke)
        # place: Korean ink box aligned with the Japanese core box (left / right / centre), centred vertically
        al = it.get('align', 'right')
        if al == 'left':
            px = bx0 - ink[0]
        elif al == 'right':
            px = bx1 - ink[2]
        else:
            px = (bx0 + bx1) / 2.0 - (ink[0] + ink[2]) / 2.0
        py = (by0 + by1) / 2.0 - (ink[1] + ink[3]) / 2.0
        if px + ink[0] < 4 or px + ink[2] > W - 4:
            raise SystemExit('%s: %r does not fit the frame' % (self.name, it['ko']))
        # erased pixels next to an ornament: the ornament moves with the roll, so it can't come from other
        # frames; these are inpainted from the ornament around them instead
        o = self.orn[max(0, ey0 - 12):ey1 + 12, max(0, ex0 - 12):ex1 + 12]
        near = cv2.dilate(o.astype(np.uint8), np.ones((21, 21), np.uint8)).astype(bool)
        orn_here = np.zeros_like(erase)
        orn_here[max(0, ey0 - 12):ey1 + 12, max(0, ex0 - 12):ex1 + 12] = near
        orn_here &= erase
        return dict(it, box=(ex0, ey0, ex1, ey1), erase=erase[ey0:ey1, ex0:ex1],
                    orn=orn_here[ey0:ey1, ex0:ex1], patch=patch, px=px, py=py,
                    fill=fill, stroke=stroke, lines=[it['ko']])

    # strip <-> screen
    def off(self, t):
        return self.v * (t - self.t0)

    def roll_at(self, t, src=None):
        """screen mask of the roll in frame t (the wide one cached: asked for again and again while
        rebuilding neighbouring frames)"""
        if src is None:
            c = self._cache.get(t)
            if c is None:
                if len(self._cache) > 800:
                    self._cache.clear()
                c = self._cache[t] = self.roll_at(t, self.roll)
            return c
        o = int(round(self.off(t)))
        m = np.zeros((H, W), bool)
        a, b = max(0, o), min(self.Hs, o + H)
        if a < b:
            m[a - o:b - o] = src[a:b]
        return m

    def visible(self, t):
        o = self.off(t)
        return [it for it in self.items if it['box'][3] > o - 2 and it['box'][1] < o + H + 2]

    def range(self):
        """frames in which some item is on screen"""
        ts = [t for t in range(len(self.f)) if self.visible(t)]
        return (ts[0], ts[-1]) if ts else None

    def _prepare(self, t):
        if self.prepared and self.prepared[0] + 400 <= t <= self.prepared[1] - 400:
            return
        lo, hi = max(0, t - 450), min(len(self.f), t + 1500)
        self.motion.prepare(lo, hi)
        self.prepared = (lo if lo > 0 else -10 ** 9, hi if hi < len(self.f) else 10 ** 9)

    def frame(self, t, im=None):
        items = self.visible(t)
        im = np.array(self.f[t]) if im is None else im
        if not items:
            return im
        self._prepare(t)
        o = self.off(t)
        io = int(round(o))
        on_circle = np.zeros((H, W), bool)
        filled = np.zeros((H, W), bool)
        orig = np.array(im)
        for it in items:
            ex0, ey0, ex1, ey1 = it['box']
            # item mask on screen (integer shift; the erase mask has a margin for the sub-pixel part)
            m = np.zeros((H, W), bool)
            sy0, sy1 = ey0 - io, ey1 - io
            a, b = max(0, sy0), min(H, sy1)
            if a >= b:
                continue
            m[a:b, ex0:ex1] = it['erase'][a - sy0:b - sy0]
            orn = np.zeros((H, W), bool)
            orn[a:b, ex0:ex1] = it['orn'][a - sy0:b - sy0]
            if it.get('mode') == 'inpaint':
                im = cv2.inpaint(np.ascontiguousarray(im), m.astype(np.uint8), 3, cv2.INPAINT_TELEA)
                filled |= m
                continue
            thin = self.roll_at(t, self.roll_thin)
            # the roll passes at ~1.5 px/frame: every pixel is uncovered again within a few dozen frames,
            # and nearer frames match the (often animated) scene better
            im = clean(self.f, t, m, lambda s: thin if s == t else self.roll_at(s), self.motion, base=im,
                       reach=self.reach, want=5)
            if orn.any():
                im = cv2.inpaint(np.ascontiguousarray(im), orn.astype(np.uint8), 3, cv2.INPAINT_TELEA)
            on_circle |= m & ~orn
            filled |= m
        if self.circle is not None and on_circle.any():
            im = self.ring_fill(t, im, on_circle)
        # feather the edge of the rebuilt area into the untouched frame (no visible box around a label)
        if filled.any():
            d = cv2.distanceTransform(filled.astype(np.uint8), cv2.DIST_L2, 3)
            k = np.clip(d / 2.5, 0, 1)[..., None]
            im = (im.astype(np.float32) * k + orig.astype(np.float32) * (1 - k) + 0.5).astype(np.uint8)
        out = im.astype(np.float32) / 255
        for it in items:
            P = it['patch']
            ph, pw = P.shape[:2]
            x, y = it['px'], it['py'] - o
            ix, iy = int(np.floor(x)), int(np.floor(y))
            M = np.float32([[1, 0, x - ix], [0, 1, y - iy]])
            Q = cv2.warpAffine(P, M, (pw + 1, ph + 1))
            a0, a1 = max(0, iy), min(H, iy + ph + 1)
            b0, b1 = max(0, ix), min(W, ix + pw + 1)
            if a0 >= a1 or b0 >= b1:
                continue
            q = Q[a0 - iy:a1 - iy, b0 - ix:b1 - ix]
            al = q[..., 3:4]
            out[a0:a1, b0:b1] = out[a0:a1, b0:b1] * (1 - al) + q[..., :3] * al
        return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)


    def ring_fill(self, t, im, mask):
        """pixels of mask inside the circle: linear interpolation along the circle through each pixel,
        between the nearest pixels that show neither the roll nor anything erased (gaps up to max_gap px
        of arc; longer ones keep the frame-sampled result)"""
        (cx, cy), R = self.circle['c'], self.circle['r']
        if not hasattr(self, '_rad'):
            yy, xx = np.mgrid[0:H, 0:W]
            self._rad = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        inside = mask & (self._rad < R)
        if not inside.any():
            return im
        A = 1024
        P = cv2.warpPolar(np.ascontiguousarray(np.asarray(self.f[t])).astype(np.float32), (R, A), (cx, cy), R,
                          cv2.WARP_POLAR_LINEAR)
        bad = (self.roll_at(t, self.roll_thin) | mask).astype(np.float32)
        frame = np.ones((H, W), np.float32)
        B = cv2.warpPolar(bad, (R, A), (cx, cy), R, cv2.WARP_POLAR_LINEAR)
        F = cv2.warpPolar(frame, (R, A), (cx, cy), R, cv2.WARP_POLAR_LINEAR)
        valid = (B < 0.01) & (F > 0.99)
        idx = np.arange(A)
        out = P.copy()
        max_gap = self.circle.get('max_gap', 400)
        out[~valid] = np.nan                # filled below where the gap allows, else left to the caller
        rr = self._rad[inside]
        j0, j1 = max(4, int(rr.min()) - 2), min(R, int(rr.max()) + 3)
        v = valid[:, j0:j1]
        # previous / next valid row along each circle (angles wrap): running max / min over the doubled column
        v2 = np.concatenate([v, v], 0)
        ii = np.arange(2 * A)[:, None]
        pv = np.maximum.accumulate(np.where(v2, ii, -10 ** 9), 0)[A:]                  # rows A..2A-1 = i + A
        nv = np.minimum.accumulate(np.where(v2, ii, 10 ** 9)[::-1], 0)[::-1][:A]
        exist = (pv >= 0) & (nv < 10 ** 8)
        dp = (idx[:, None] + A) - pv
        dn = nv - idx[:, None]
        gap = dp + dn
        cols = np.arange(j0, j1)[None, :]
        ok = ~v & exist & (gap * 2 * np.pi * cols / A <= max_gap)
        if ok.any():
            w = (dp / np.maximum(gap, 1))[..., None]
            pr, nr = np.where(exist, pv % A, 0), np.where(exist, nv % A, 0)
            cc = np.broadcast_to(cols, pr.shape)
            val = P[pr, cc] * (1 - w) + P[nr, cc] * w
            sub = out[:, j0:j1]
            sub[ok] = val[ok]
        back = cv2.warpPolar(np.nan_to_num(out, nan=-1), (W, H), (cx, cy), R,
                             cv2.WARP_POLAR_LINEAR | cv2.WARP_INVERSE_MAP)
        use = inside & (back.min(2) >= 0)
        im = im.copy()
        im[use] = np.clip(back[use] + 0.5, 0, 255).astype(np.uint8)
        return im


def clean(frames, t, mask, masks_at, motion, base, reach=90, want=5, need_k=3):
    """movie_subs.clean (same sampling and checks), faster for many small masks: incremental coverage
    count, NaN-sorting median instead of numpy's masked nanmedian"""
    im = base.copy()
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return im
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    bw, bh = x1 - x0, y1 - y0
    gx, gy = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))
    pts = np.stack([gx, gy, np.ones_like(gx)], -1).reshape(-1, 3)
    need = mask[y0:y1, x0:x1].reshape(-1)
    big = cv2.dilate(mask.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    ring = (big & ~mask)[y0:y1, x0:x1].reshape(-1)
    own = masks_at(t)
    if own is not None:
        ring &= ~own[y0:y1, x0:x1].reshape(-1)
    tgt = im[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)
    cand = [s for s in motion.same_shot(t) if s != t and abs(s - t) <= reach]
    cand.sort(key=lambda s: abs(s - t))
    samples, oks = [], []
    cnt = np.zeros(need.shape, np.int32)
    for s in cand:
        h = motion.to(t, s)
        if h is None:
            continue
        q = pts @ h.T
        qx, qy = q[:, 0] / q[:, 2], q[:, 1] / q[:, 2]
        ok = (qx >= 0) & (qx <= W - 1) & (qy >= 0) & (qy <= H - 1)
        msk = masks_at(s)
        if msk is not None:
            ix = np.clip(np.round(qx).astype(int), 0, W - 1)
            iy = np.clip(np.round(qy).astype(int), 0, H - 1)
            ok &= ~msk[iy, ix]
        if not (ok & need).any():
            continue
        warped = cv2.remap(np.ascontiguousarray(frames[s]), qx.reshape(bh, bw).astype(np.float32),
                           qy.reshape(bh, bw).astype(np.float32), cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REPLICATE).reshape(-1, 3)
        r = ring & ok
        if r.sum() > 50 and np.abs(warped[r].astype(np.float32) - tgt[r]).mean() > 12:
            continue
        samples.append(warped); oks.append(ok)
        cnt += ok
        if len(samples) >= want and (cnt[need] >= need_k).all() or len(samples) >= 2 * want:
            break
    out = im[y0:y1, x0:x1].reshape(-1, 3).copy()
    hole = need.copy()
    if samples:
        st = np.stack(samples).astype(np.float32)
        okm = np.stack(oks)
        st[~okm] = np.nan
        st.sort(axis=0)                          # NaN last
        n = okm.sum(0)
        mid = np.maximum(n - 1, 0) // 2
        lo = np.take_along_axis(st, mid[None, :, None].repeat(3, 2), 0)[0]
        hi = np.take_along_axis(st, (n // 2)[None, :, None].repeat(3, 2), 0)[0]
        med = (lo + hi) / 2
        good = need & (n > 0)
        out[good] = np.clip(med[good], 0, 255).astype(np.uint8)
        hole = need & (n == 0)
    patch = out.reshape(bh, bw, 3)
    if hole.any():
        patch = cv2.inpaint(patch, hole.reshape(bh, bw).astype(np.uint8), 5, cv2.INPAINT_TELEA)
    im[y0:y1, x0:x1] = patch
    return im


class Motion(ms.Motion):
    """movie_subs.Motion with a per-frame exclusion mask (the roll moves against the scene)"""

    def _feat(self, t):
        if t not in self.kp:
            g = cv2.cvtColor(np.ascontiguousarray(self.f[t]), cv2.COLOR_RGB2GRAY)
            m = np.full((H, W), 255, np.uint8)
            m[self.ex(t)] = 0
            self.kp[t] = self.orb.detectAndCompute(g, m)
        return self.kp[t]

    def step(self, t):
        if t not in self.H:
            k0, d0 = self._feat(t)
            k1, d1 = self._feat(t + 1)
            h = None
            if d0 is not None and d1 is not None and len(k0) > 30 and len(k1) > 30:
                ms_ = self.bf.match(d1, d0)
                if len(ms_) > 25:
                    p1 = np.float32([k1[m.queryIdx].pt for m in ms_])
                    p0 = np.float32([k0[m.trainIdx].pt for m in ms_])
                    h, inl = cv2.findHomography(p1, p0, cv2.RANSAC, 2.0)
                    if h is None or inl.sum() < 20:
                        h = None
            a0 = np.asarray(self.f[t], np.float32)
            keep = ~(self.ex(t) | self.ex(t + 1))
            if h is None:
                if np.abs(a0 - np.asarray(self.f[t + 1], np.float32))[keep].mean() < 4:
                    h = np.eye(3)
            else:
                w = cv2.warpPerspective(np.ascontiguousarray(self.f[t + 1]), np.linalg.inv(h), (W, H))
                if np.abs(a0 - w.astype(np.float32))[keep].mean() > 30:
                    h = None
            self.H[t] = h
        return self.H[t]


def refine(frames, frac, t0, t1, v, step=40):
    """measure the roll's offset in frames t0..t1 against the strip (text share, sub-pixel) and fit a
    line: returns (t0', v') such that offset(t) = v' * (t - t0') in the strip's coordinates"""
    ts, offs = [], []
    ref = cv2.GaussianBlur(frac[:, 300:600], (0, 0), 1.0)
    for t in range(t0 + 100, t1 - 100, step):
        m = cv2.GaussianBlur(ms.text_pixels(frames[t], False)[:, 300:600].astype(np.float32), (0, 0), 1.0)
        if m.sum() < 200:
            continue
        p = v * (t - t0)
        sc = {}
        for d in range(-25, 26):
            o = int(round(p)) + d
            if o < 0 or o + H > len(ref):
                continue
            r = ref[o:o + H]
            sc[o] = (r * m).sum() / (np.sqrt((r * r).sum() * (m * m).sum()) + 1e-6)
        if not sc:
            continue
        o = max(sc, key=sc.get)
        if sc[o] < 0.3 or o - 1 not in sc or o + 1 not in sc:
            continue
        l, c, r = sc[o - 1], sc[o], sc[o + 1]
        den = l - 2 * c + r
        ts.append(t)
        offs.append(o + (0.5 * (l - r) / den if den < 0 else 0))
    ts, offs = np.array(ts, float), np.array(offs)
    k, c = np.polyfit(ts, offs, 1)
    res = offs - (k * ts + c)
    keep = np.abs(res) < 3 * max(0.3, np.std(res))
    k, c = np.polyfit(ts[keep], offs[keep], 1)
    res = offs[keep] - (k * ts[keep] + c)
    print('refine: %d frames, v %.5f, residual rms %.2f px, max %.2f' % (keep.sum(), k, np.sqrt((res ** 2).mean()),
                                                                          np.abs(res).max()))
    return -c / k, k


def align_items(name, ref, spec_ref, frac_ref, frac):
    """move REF's items onto NAME's strip: per item the local shift (window +-160 rows) with the best
    match of the text share; items whose neighbourhood does not match are reported"""
    out = []
    for it in spec_ref['scroll']['items']:
        y = it['y']
        a = frac_ref[max(0, y - 160):y + 160, 250:600]
        best = None
        for dy in range(-130, 131):
            y0 = max(0, y - 160) + dy
            if y0 < 0 or y0 + len(a) > len(frac):
                continue
            b = frac[y0:y0 + len(a), 250:600]
            s = (a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6)
            if best is None or s > best[0]:
                best = (s, dy)
        out.append(dict(it, y=y + best[1], score=round(float(best[0]), 2)))
    return out


def main():
    cmd, name = sys.argv[1], sys.argv[2]
    import movie_build as mb
    spec = json.load(open(mb.spec_path(name), encoding='utf-8'))
    _, f = mb.raw_frames(name)
    sp = spec['scroll']
    if cmd == 'strip':
        build_strip(name, f, sp['t0'], sp['t1'], sp['v'])
        for p in view_sheets(name, sp.get('items')):
            print(p)
    elif cmd == 'refine':
        # iterate: strip -> measured offsets -> better t0/v. t0 stays an integer-free float; the strip
        # origin is kept (items stay valid) by expressing the fit in the current strip's coordinates
        frac = np.load(strip_base(name) + '_frac.npy') if os.path.exists(strip_base(name) + '_frac.npy') else \
            build_strip(name, f, sp['t0'], sp['t1'], sp['v'])[0]
        for _ in range(2):
            t0, v = refine(f, frac, int(round(sp['t0'])), sp['t1'], sp['v'])
            print('  t0 %.3f -> %.3f, v %.5f -> %.5f' % (sp['t0'], t0, sp['v'], v))
            sp['t0'], sp['v'] = round(float(t0), 3), round(float(v), 6)
            frac = build_strip(name, f, sp['t0'], sp['t1'], sp['v'])[0]
        if '--write' in sys.argv:
            write_spec(mb.spec_path(name), spec)
            print('written', mb.spec_path(name))
    elif cmd == 'align':
        ref = sys.argv[3]
        spec_ref = json.load(open(mb.spec_path(ref), encoding='utf-8'))
        frac_ref = np.load(strip_base(ref) + '_frac.npy')
        if not os.path.exists(strip_base(name) + '_frac.npy'):
            build_strip(name, f, sp['t0'], sp['t1'], sp['v'])
        frac = np.load(strip_base(name) + '_frac.npy')
        items = align_items(name, ref, spec_ref, frac_ref, frac)
        for it in items:
            print(json.dumps(it, ensure_ascii=False))
        if '--write' in sys.argv:
            low = [it.get('ja', it['ko']) for it in items if it['score'] < 0.5]
            if low:
                raise SystemExit('poor match, not written: %s' % low)
            sp['items'] = [{k: v for k, v in it.items() if k != 'score'} for it in items]
            write_spec(mb.spec_path(name), spec)
            print('written', mb.spec_path(name))


def write_spec(path, spec):
    """spec json with one item per line"""
    sp = spec['scroll']
    head = {k: v for k, v in spec.items() if k != 'scroll'}
    lines = ['{']
    for k, v in head.items():
        lines.append(' %s: %s,' % (json.dumps(k), json.dumps(v, ensure_ascii=False)))
    lines.append(' "scroll": {')
    for k, v in sp.items():
        if k != 'items':
            lines.append('  %s: %s,' % (json.dumps(k), json.dumps(v, ensure_ascii=False)))
    lines.append('  "items": [')
    lines.append(',\n'.join('   ' + json.dumps(it, ensure_ascii=False) for it in sp['items']))
    lines.append('  ]')
    lines.append(' }')
    lines.append('}')
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
