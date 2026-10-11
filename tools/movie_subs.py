"""Burned-in movie subtitles: find them, remove them, draw Korean ones.

Frames come from a raw RGB dump (ffmpeg -pix_fmt rgb24) opened as a numpy memmap.

  detect_cards(frames)          subtitle intervals (outlined white text in the centre area)
  card_mask(frames, a, b)       static text mask of one card (pixels white in most plateau frames)
  Motion                        chained frame-to-frame homographies (ORB + RANSAC, text area excluded)
  clean(frames, t, mask, ...)   background under the mask rebuilt from neighbouring frames
                                (motion compensated, median of valid samples, inpaint fallback)
"""
import numpy as np
import cv2

W, H = 640, 448
REGION = (40, 40, 600, 420)        # subtitles live in the centre of the picture


def load(path):
    return np.memmap(path, dtype=np.uint8, mode='r').reshape(-1, H, W, 3)


def text_pixels(im, region=True):
    """white, unsaturated pixels next to a dark outline"""
    a = im.astype(np.int16)
    lum = a.mean(2)
    sat = a.max(2) - a.min(2)
    white = (lum > 215) & (sat < 40)
    dark = (lum < 70).astype(np.uint8)
    near = cv2.dilate(dark, np.ones((7, 7), np.uint8)) > 0
    t = white & near
    if not region:
        return t
    m = np.zeros_like(t)
    x0, y0, x1, y1 = REGION
    m[y0:y1, x0:x1] = t[y0:y1, x0:x1]
    return m


def detect_cards(frames, thr=300, min_len=20):
    sc = np.array([text_pixels(frames[i], False).sum() for i in range(len(frames))])
    cards = []
    on = None
    for i, s in enumerate(list(sc) + [0]):
        if s > thr and on is None:
            on = i
        elif s <= thr and on is not None:
            if i - on >= min_len:
                cards.append([on, i - 1])
            on = None
    return cards, sc


def card_mask(frames, a, b, sc=None):
    """pixels that are text in >= 80% of the plateau (score >= 70% of the card's peak);
    returns (core mask, dilated mask covering outline/shadow/antialiasing)"""
    idx = list(range(a, b + 1))
    if sc is not None:
        peak = sc[a:b + 1].max()
        idx = [i for i in idx if sc[i] >= 0.7 * peak]
    acc = np.zeros((H, W), np.float32)
    for i in idx:
        acc += text_pixels(frames[i])
    core = acc >= 0.8 * len(idx)
    # drop isolated specks (background highlights that happened to stay white)
    n, lab, st, _ = cv2.connectedComponentsWithStats(core.astype(np.uint8), 8)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 3
    core = keep[lab]
    # glyph clusters: close gaps between strokes, then grow over outline + shadow
    full = cv2.dilate(core.astype(np.uint8), np.ones((11, 11), np.uint8))
    return core, full > 0


def visibility(frame, core, full):
    """how strongly the card's text shows in a frame: core (glyph fill) vs outline ring luminance"""
    lum = frame.astype(np.float32).mean(2)
    ring = full & ~cv2.dilate(core.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return float(lum[core].mean() - lum[ring].mean())


def extend(frames, a, b, core, full, floor=None, limit=150):
    """grow [a, b] over the fade-in / fade-out frames where the text is still faintly visible
    (long limit: a caption can stay on while the whole picture fades to black, ABAN02 ending)"""
    base = floor if floor is not None else min(visibility(frames[max(0, a - limit)], core, full),
                                               visibility(frames[min(len(frames) - 1, b + limit)], core, full))
    peak = visibility(frames[(a + b) // 2], core, full)
    thr = base + max(1.5, 0.02 * (peak - base))     # until the text is really gone (fades to black)
    while a > 0 and b - a < 10000 and visibility(frames[a - 1], core, full) > thr and limit > 0:
        a -= 1; limit -= 1
    lim2 = 150
    while b < len(frames) - 1 and visibility(frames[b + 1], core, full) > thr and lim2 > 0:
        b += 1; lim2 -= 1
    return a, b


class Motion:
    """H[t] maps frame t+1 coordinates -> frame t (computed on demand, text area excluded)."""

    def __init__(self, frames, exclude=None):
        self.f = frames
        self.ex = exclude
        self.H = {}
        self.orb = cv2.ORB_create(1500)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.kp = {}

    def _feat(self, t):
        if t not in self.kp:
            g = cv2.cvtColor(np.ascontiguousarray(self.f[t]), cv2.COLOR_RGB2GRAY)
            m = np.full((H, W), 255, np.uint8)
            if self.ex is not None:
                m[self.ex] = 0
            self.kp[t] = self.orb.detectAndCompute(g, m)
        return self.kp[t]

    def step(self, t):
        """homography frame t+1 -> frame t, or None at a cut"""
        if t not in self.H:
            k0, d0 = self._feat(t)
            k1, d1 = self._feat(t + 1)
            h = None
            if d0 is not None and d1 is not None and len(k0) > 30 and len(k1) > 30:
                ms = self.bf.match(d1, d0)
                if len(ms) > 25:
                    p1 = np.float32([k1[m.queryIdx].pt for m in ms])
                    p0 = np.float32([k0[m.trainIdx].pt for m in ms])
                    h, inl = cv2.findHomography(p1, p0, cv2.RANSAC, 2.0)
                    if h is None or inl.sum() < 20:
                        h = None
            a0 = np.asarray(self.f[t], np.float32)
            if h is None:
                # featureless (black / flat) frames: still the same shot if nothing changed
                if np.abs(a0 - np.asarray(self.f[t + 1], np.float32)).mean() < 4:
                    h = np.eye(3)
            else:
                # verify: a cut can still produce a homography from a few chance matches
                w = cv2.warpPerspective(np.ascontiguousarray(self.f[t + 1]), np.linalg.inv(h), (W, H))
                m = np.ones((H, W), bool) if self.ex is None else ~self.ex
                if np.abs(a0 - w.astype(np.float32))[m].mean() > 30:
                    h = None
            self.H[t] = h
        return self.H[t]

    def prepare(self, lo=0, hi=None):
        """all steps in [lo, hi); shots (split at cuts) and transforms to each shot's first frame"""
        hi = len(self.f) if hi is None else hi
        self.shot = {}
        self.A = {}
        sid = 0
        self.shot[lo] = sid; self.A[lo] = np.eye(3)
        for u in range(lo, hi - 1):
            st = self.step(u)
            self.kp.pop(u, None)          # features of frame u are no longer needed (memory)
            if st is None:
                sid += 1
                self.A[u + 1] = np.eye(3)
            else:
                self.A[u + 1] = self.A[u] @ st      # (u+1) -> u -> ... -> anchor
            self.shot[u + 1] = sid
        self.kp.clear()

    def to(self, t, s):
        """homography mapping frame t coordinates -> frame s coordinates (None if in another shot)"""
        if self.shot.get(t) is None or self.shot.get(t) != self.shot.get(s):
            return None
        return np.linalg.inv(self.A[s]) @ self.A[t]

    def same_shot(self, t):
        return [s for s, k in self.shot.items() if k == self.shot[t]]


def clean(frames, t, mask, masks_at, motion, reach=400, want=9, base=None):
    """rebuild frame t under mask from other frames of the same shot: text-free frames first
    (nearest first), then frames whose text sits elsewhere relative to the moving background.
    masks_at(s) -> dilated text mask present in frame s (or None)
    base: start from this image instead of frames[t] (second pass)"""
    im = np.array(frames[t]) if base is None else base.copy()
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return im
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    bw, bh = x1 - x0, y1 - y0
    gx, gy = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))
    pts = np.stack([gx, gy, np.ones_like(gx)], -1).reshape(-1, 3)
    need = mask[y0:y1, x0:x1].reshape(-1)
    # ring of untouched pixels around the text: a sample must agree with the frame there
    # (rejects frames across dissolves, animated overlays, bad motion estimates)
    big = cv2.dilate(mask.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    ring = (big & ~mask)[y0:y1, x0:x1].reshape(-1)
    own = masks_at(t)
    if own is not None:
        ring &= ~own[y0:y1, x0:x1].reshape(-1)
    tgt = im[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)
    samples = []
    cand = [s for s in motion.same_shot(t) if s != t and abs(s - t) <= reach]
    order = sorted(cand, key=lambda s: (masks_at(s) is not None, abs(s - t)))
    for s in order:
        h = motion.to(t, s)
        if h is None:
            continue
        q = pts @ h.T
        qx, qy = q[:, 0] / q[:, 2], q[:, 1] / q[:, 2]
        inside = (qx >= 0) & (qx <= W - 1) & (qy >= 0) & (qy <= H - 1)
        ms = masks_at(s)
        ok = inside.copy()
        if ms is not None:
            ix = np.clip(np.round(qx).astype(int), 0, W - 1)
            iy = np.clip(np.round(qy).astype(int), 0, H - 1)
            ok &= ~ms[iy, ix]
        if not (ok & need).any():
            continue
        mx = qx.reshape(bh, bw).astype(np.float32)
        my = qy.reshape(bh, bw).astype(np.float32)
        warped = cv2.remap(np.ascontiguousarray(frames[s]), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        wv = warped.reshape(-1, 3)
        r = ring & ok
        if r.sum() > 50 and np.abs(wv[r].astype(np.float32) - tgt[r]).mean() > 12:
            continue
        samples.append((wv, ok))
        if len(samples) >= want and all_covered(samples, need, 3):
            break
    out = im[y0:y1, x0:x1].reshape(-1, 3).copy()
    hole = need.copy()
    if samples:
        st = np.stack([s for s, _ in samples]).astype(np.float32)
        okm = np.stack([o for _, o in samples])
        st[~okm] = np.nan
        med = np.nanmedian(st, axis=0)
        good = need & okm.any(0)
        out[good] = np.clip(med[good], 0, 255).astype(np.uint8)
        hole = need & ~okm.any(0)
    patch = out.reshape(bh, bw, 3)
    if hole.any():
        patch = cv2.inpaint(patch, hole.reshape(bh, bw).astype(np.uint8), 5, cv2.INPAINT_TELEA)
    im[y0:y1, x0:x1] = patch
    return im


def all_covered(samples, need, k):
    cnt = np.zeros(need.shape, np.int32)
    for _, o in samples:
        cnt += o
    return bool((cnt[need] >= k).all())
