"""Korean subtitles for the burned-in movie captions.

usage: movie_build.py <NAME> [--detect] [--preview T ...] [--frames A-B]
  --detect     print the detected caption cards (to fill 20_source/config/movies/<NAME>.json)
  --preview T  write before/after PNGs of frames T to 90_test/movie/ (no encode)
  (default)    full run: 30_build/movie/<NAME>.SFD (same size as the original, game-ready)

Spec 20_source/config/movies/<NAME>.json:
  {"cards": [{"frames": [a, b], "text": "ev:<event>:<key>" | "ko": "...", "lines": n?}, ...],
   "style": {...optional overrides}}
Per card: the static Japanese caption mask is found in frames [a, b] and extended over the
fades; every frame of the extended range is rebuilt under the mask from the rest of the shot
(movie_subs.clean), then the Korean caption is drawn with the original's fade curve.
"""
import sys, os, json, argparse, hashlib, subprocess
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import paths
import movie_subs as ms
import movie_encode, sfd, sfd_video, textfmt

FF = movie_encode.FFMPEG
STYLE = dict(font='NotoSansKR-Bold.otf', size=24, pitch=36, spacing=1, fill=[236, 236, 234],
             stroke=2, stroke_rgba=[0, 0, 0, 230], shadow_blur=2.0, shadow_alpha=0.55, max_width=560)


def spec_path(name):
    return os.path.join(paths.CONFIG, 'movies', name + '.json')


def raw_frames(name):
    src = os.path.join(paths.EXTRACTED, 'movie', name + '.SFD')
    if not os.path.exists(src):
        subprocess.run([sys.executable, '-X', 'utf8', os.path.join(os.path.dirname(__file__), 'extract_movies.py'),
                        name], check=True)
    raw = os.path.join(paths.BUILD, 'movie', name + '.rgb')
    if not os.path.exists(raw):
        os.makedirs(os.path.dirname(raw), exist_ok=True)
        d = open(src, 'rb').read()
        ves = b''.join(d[x['data_off']:x['data_off'] + x['data_len']] for x in sfd.packets(d) if x['sid'] == 0xE0)
        n = len(sfd_video.pictures(ves)[0])
        subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-y', '-i', src, '-an', '-frames:v', str(n),
                        '-f', 'rawvideo', '-pix_fmt', 'rgb24', raw], check=True)
    return src, ms.load(raw)


def korean(card):
    if 'ko' in card:
        return card['ko']
    _, ev, key = card['text'].split(':')
    for e in json.load(open(os.path.join(paths.TRANS, 'events', ev + '.json'), encoding='utf-8')):
        if e['key'] == key:
            return e['ko']
    raise KeyError(card['text'])


def break_lines(text, n, font, st):
    """split at spaces into n lines with the most even widths (explicit \\n kept)"""
    if '\n' in text:
        return text.split('\n')
    words = text.split(' ')
    if n <= 1 or len(words) == 1:
        return [text]
    best = None
    import itertools
    for cuts in itertools.combinations(range(1, len(words)), min(n, len(words)) - 1):
        ls = [' '.join(words[i:j]) for i, j in zip((0,) + cuts, cuts + (len(words),))]
        w = max(width(l, font, st) for l in ls)
        if best is None or w < best[0]:
            best = (w, ls)
    return best[1]


def width(s, font, st):
    return font.getlength(s) + st['spacing'] * max(0, len(s) - 1)


def render_caption(lines, cx, cy, st):
    """RGBA layer (H, W, 4) float32 0..1 with the Korean caption centred at (cx, cy)"""
    font = ImageFont.truetype(paths.font(st['font']), st['size'])
    scale = 4  # supersample for clean outlines
    big = ImageFont.truetype(paths.font(st['font']), st['size'] * scale)
    Wb, Hb = ms.W * scale, ms.H * scale
    text = Image.new('L', (Wb, Hb), 0)
    edge = Image.new('L', (Wb, Hb), 0)
    dt, de = ImageDraw.Draw(text), ImageDraw.Draw(edge)
    top = cy - st['pitch'] * (len(lines) - 1) / 2.0
    asc, desc = font.getmetrics()
    for i, ln in enumerate(lines):
        y = (top + i * st['pitch']) * scale
        w = width(ln, big, dict(st, spacing=st['spacing'] * scale))
        x = cx * scale - w / 2
        for ch in ln:
            box = big.getbbox('가')
            yy = y - (box[1] + box[3]) / 2
            de.text((x, yy), ch, font=big, fill=255, stroke_width=st['stroke'] * scale, stroke_fill=255)
            dt.text((x, yy), ch, font=big, fill=255)
            x += big.getlength(ch) + st['spacing'] * scale
    text = np.asarray(text.resize((ms.W, ms.H), Image.LANCZOS), np.float32) / 255
    edge_i = edge.resize((ms.W, ms.H), Image.LANCZOS)
    shadow = np.asarray(edge_i.filter(ImageFilter.GaussianBlur(st['shadow_blur'])), np.float32) / 255
    edge = np.asarray(edge_i, np.float32) / 255
    # layers bottom->top: soft shadow (or glow), outline, fill
    a_sh = shadow * st['shadow_alpha']
    a_ol = edge * st['stroke_rgba'][3] / 255
    rgb = np.zeros((ms.H, ms.W, 3), np.float32)
    alpha = np.zeros((ms.H, ms.W), np.float32)
    sh_col = np.array(st.get('shadow_rgb', [0, 0, 0]), np.float32) / 255
    for col, a in ((sh_col, a_sh), (np.array(st['stroke_rgba'][:3], np.float32) / 255, a_ol),
                   (np.array(st['fill'], np.float32) / 255, text)):
        rgb = rgb * (1 - a[..., None]) + col * a[..., None]
        alpha = alpha + a * (1 - alpha)
    # un-premultiply: rgb above is premultiplied over black
    rgb = np.where(alpha[..., None] > 1e-4, rgb / np.maximum(alpha[..., None], 1e-4), 0)
    return np.dstack([rgb, alpha])


class Movie:
    def __init__(self, name):
        self.name = name
        self.src, self.f = raw_frames(name)
        self.spec = json.load(open(spec_path(name), encoding='utf-8'))
        self.st = dict(STYLE, **self.spec.get('style', {}))
        self.cards = []

    def analyse_fixed(self, c):
        """captions on a logo / static layout ('plate' or 'inpaint' mode): mask from a reference frame"""
        f = self.f
        a, b = c['frames']
        x0, y0, x1, y1 = c['box']
        st = dict(self.st, **c.get('style', {}))
        ref = np.asarray(f[c['ref']], np.float32)
        box = np.zeros((ms.H, ms.W), bool)
        box[y0:y1, x0:x1] = True
        if c['mode'] == 'plate':
            plate = np.asarray(f[c['plate']], np.float32)
            core = (np.abs(ref - plate).max(2) > c.get('thr', 40)) & box
        else:
            plate = None
            g = ref.mean(2)
            core = (np.abs(g - cv2.medianBlur(g.astype(np.uint8), 9).astype(np.float32)) > c.get('thr', 25)) & box
        full = cv2.dilate(core.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & box
        ring = cv2.dilate(full.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~full
        lines = c.get('lines') or [korean(c)]
        layer = render_caption(lines, c.get('cx', (x0 + x1) / 2.0), c.get('cy', (y0 + y1) / 2.0), st)
        self.fixed.append(dict(c, a=a, b=b, core=core, full=full, ring=ring, plate=plate, layer=layer,
                               ref_im=ref, lines=lines))

    def frame_fixed(self, t, im):
        for c in self.fixed:
            if not c['a'] <= t <= c['b']:
                continue
            cur = np.asarray(self.f[t], np.float32)
            m = c['full']
            if c['plate'] is not None:
                # clean plate + the frame's change against it (glow flashes, the sword's light),
                # measured around the caption and carried smoothly across it
                d = np.clip(cur - c['plate'], -127, 127) + 128
                d = cv2.inpaint(d.astype(np.uint8), m.astype(np.uint8), 7, cv2.INPAINT_TELEA).astype(np.float32) - 128
                bg = np.clip(c['plate'] + d, 0, 255)
                im = im.astype(np.float32)
                im[m] = bg[m]
                ref_d = np.abs(c['ref_im'] - c['plate'])[c['core']].mean()
                k = float(np.clip(np.abs(cur - bg)[c['core']].mean() / max(1.0, ref_d), 0, 1))
            else:
                im = cv2.inpaint(np.ascontiguousarray(im.astype(np.uint8)), m.astype(np.uint8), 3, cv2.INPAINT_TELEA)
                im = im.astype(np.float32)
                ref_d = np.abs(c['ref_im'] - cv2.inpaint(c['ref_im'].astype(np.uint8), m.astype(np.uint8), 3,
                                                           cv2.INPAINT_TELEA))[c['core']].mean()
                k = float(np.clip(np.abs(cur - im)[c['core']].mean() / max(1.0, ref_d), 0, 1))
            L = c['layer']
            a = L[..., 3:4] * k
            im = (im / 255 * (1 - a) + L[..., :3] * a) * 255
        return np.clip(im + 0.5, 0, 255).astype(np.uint8)

    def analyse(self):
        f = self.f
        self.fixed = []
        self.scroll = None
        if 'scroll' in self.spec:
            import movie_scroll
            self.scroll = movie_scroll.Scroll(self.name, f, self.spec)
        for c in self.spec['cards']:
            if c.get('mode') in ('plate', 'inpaint'):
                self.analyse_fixed(c)
                continue
            a, b = c['frames']
            sc = np.zeros(len(f), np.int64)
            for i in range(a, b + 1):
                sc[i] = ms.text_pixels(f[i], False).sum()
            core, full = ms.card_mask(f, a, b, sc)
            a2, b2 = ms.extend(f, a, b, core, full)
            peak = max(ms.visibility(f[i], core, full) for i in range(a, b + 1, max(1, (b - a) // 20)))
            base = min(ms.visibility(f[a2], core, full), ms.visibility(f[b2], core, full))
            ys, xs = np.nonzero(core)
            cy = (ys.min() + ys.max()) / 2.0
            rows = core.any(1)
            ko = korean(c)
            font = ImageFont.truetype(paths.font(self.st['font']), self.st['size'])
            if isinstance(c.get('lines'), list):
                # hand-made line breaks; must still spell the current translation
                lines = c['lines']
                if ' '.join(lines).replace('\n', ' ') != ko.replace('\n', ' '):
                    raise SystemExit('%s %s: lines %r no longer match the translation %r'
                                     % (self.name, c.get('text'), lines, ko))
            else:
                lines = break_lines(ko, c.get('nlines') or count_lines(core), font, self.st)
                while max(width(l, font, self.st) for l in lines) > self.st['max_width'] and len(lines) < 4:
                    lines = break_lines(ko, len(lines) + 1, font, self.st)
            if max(width(l, font, self.st) for l in lines) > self.st['max_width']:
                raise SystemExit('%s %s: caption too wide' % (self.name, c.get('text')))
            layer = render_caption(lines, ms.W / 2, cy, self.st)
            # area to clean: Japanese mask; the Korean layer covers its own area afterwards
            wide = cv2.dilate(full.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
            self.cards.append(dict(a=a2, b=b2, core=core, full=full, wide=wide, peak=peak, base=base,
                                   lines=lines, layer=layer))
        if not self.cards:
            self.motion = None
            return
        ex = np.zeros((ms.H, ms.W), bool)
        for c in self.cards:
            ex |= c['full']
        self.motion = ms.Motion(f, ex)
        lo = max(0, min(c['a'] for c in self.cards) - 450)
        hi = min(len(f), max(c['b'] for c in self.cards) + 450)
        self.motion.prepare(lo, hi)

    def cards_at(self, t):
        return [c for c in self.cards if c['a'] <= t <= c['b']]

    def masks_at(self, s):
        """area a source frame must not be sampled from (its captions, with a safety margin)"""
        cs = self.cards_at(s)
        if not cs:
            return None
        m = cs[0]['wide']
        for c in cs[1:]:
            m = m | c['wide']
        return m

    def frame(self, t):
        im = self.frame_moving(t)
        if any(c['a'] <= t <= c['b'] for c in self.fixed):
            im = self.frame_fixed(t, im)
        if self.scroll is not None:
            im = self.scroll.frame(t, np.array(im))
        return im

    def frame_moving(self, t):
        cs = self.cards_at(t)
        if not cs:
            return np.asarray(self.f[t])
        full = cs[0]['full']
        wide = cs[0]['wide']
        for c in cs[1:]:
            full = full | c['full']; wide = wide | c['wide']
        im = ms.clean(self.f, t, full, self.masks_at, self.motion)
        # second pass: leftovers of the Japanese caption (fade frames, missed antialiasing)
        left = ms.text_pixels(im, False) & wide
        if left.sum() > 3:
            extra = cv2.dilate(left.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
            im = ms.clean(self.f, t, extra, self.masks_at, self.motion, base=im)
        out = im.astype(np.float32) / 255
        for c in cs:     # cross-fading captions: each with its own fade level
            vis = ms.visibility(self.f[t], c['core'], c['full'])
            k = float(np.clip((vis - c['base']) / max(1e-3, c['peak'] - c['base']), 0, 1))
            L = c['layer']
            a = L[..., 3:4] * k
            out = out * (1 - a) + L[..., :3] * a
        return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)


def count_lines(core):
    rows = core.sum(1) > 2
    n, run = 0, 0
    for r in rows:
        if r:
            run += 1
        else:
            if run >= 6:
                n += 1
            run = 0
    return max(1, n + (1 if run >= 6 else 0))


def free_mb():
    """available physical memory (MB), Windows; None elsewhere"""
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [('len', ctypes.c_ulong), ('load', ctypes.c_ulong), ('total', ctypes.c_ulonglong),
                        ('avail', ctypes.c_ulonglong), ('tp', ctypes.c_ulonglong), ('ap', ctypes.c_ulonglong),
                        ('tv', ctypes.c_ulonglong), ('av', ctypes.c_ulonglong), ('ext', ctypes.c_ulonglong)]
        s = MS(); s.len = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
        return s.avail // (1 << 20)
    except Exception:
        return None


def wait_for_memory(need_mb=2048):
    """pause while the machine is short of memory (other programs); resume when it recovers"""
    import time
    fm = free_mb()
    if fm is None or fm >= need_mb:
        return
    print('paused: only %d MB free memory, waiting...' % fm, flush=True)
    while True:
        time.sleep(15)
        fm = free_mb()
        if fm >= need_mb + 512:
            print('resumed: %d MB free' % fm, flush=True)
            return


def changed_ranges(m):
    r = [(c['a'], c['b']) for c in m.cards] + [(c['a'], c['b']) for c in m.fixed]
    if getattr(m, 'scroll', None) is not None and m.scroll.range():
        r.append(m.scroll.range())
    return sorted(r)


ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14,
          21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60,
          61, 54, 47, 55, 62, 63]


MPEG1_INTRA = [8, 16, 19, 22, 26, 27, 29, 34, 16, 16, 22, 24, 27, 29, 34, 37, 19, 22, 26, 27, 29, 34, 34, 38,
               22, 22, 26, 27, 29, 34, 37, 40, 22, 26, 27, 29, 32, 35, 40, 48, 26, 27, 29, 32, 35, 40, 48, 58,
               26, 27, 29, 34, 38, 46, 56, 69, 27, 29, 35, 38, 46, 56, 69, 83]   # ISO 11172-2 default, raster


def seq_matrices(hdr):
    """(intra, non_intra) quantiser matrices of an MPEG-1 sequence header, raster order (None = default)"""
    v = int.from_bytes(hdr, 'big')
    n = len(hdr) * 8
    pos = 32 + 62                      # after start code: size/aspect/rate/bitrate/marker/vbv/constrained
    def take(k):
        nonlocal pos
        x = (v >> (n - pos - k)) & ((1 << k) - 1)
        pos += k
        return x
    out = []
    for _ in range(2):
        if take(1):
            m = [0] * 64
            for i in range(64):
                m[ZIGZAG[i]] = take(8)
            out.append(m)
        else:
            out.append(None)
    return out


def spread(seg, targets, limit):
    """insert zero stuffing so that picture k of seg (with the sequence/GOP headers right before it)
    starts at or after targets[k]; never grows past limit (then the rest stays compact)"""
    pics, _ = sfd_video.pictures(seg)
    units = []
    for p, k, tr, ty in pics:
        u = p
        g = seg.rfind(b'\x00\x00\x01\xb8', 0, p)
        if g >= 0 and p - g < 16:
            u = g
            s = seg.rfind(b'\x00\x00\x01\xb3', 0, g)
            if s >= 0 and g - s < 200:
                u = s
        units.append(u)
    out = bytearray(seg[:units[0]]) if units else bytearray()
    for i, u in enumerate(units):
        end = units[i + 1] if i + 1 < len(units) else len(seg)
        # picture i should fill up to where the original's next picture started; the extra bytes are
        # spread as small zero runs in front of its slice start codes (00 00 01 01..af), so every
        # packet keeps carrying video data like the original's
        nxt = targets[i + 1] if i + 1 < len(targets) else limit - (len(seg) - end)
        left_after = len(seg) - end
        extra = max(0, min(nxt, limit - left_after) - len(out) - (end - u))
        body = seg[u:end]
        cuts = [m for m in _slice_starts(body)]
        if extra and cuts:
            per, rem = divmod(extra, len(cuts))
            pieces = []
            last = 0
            for j, c in enumerate(cuts):
                pieces.append(body[last:c])
                pieces.append(b'\x00' * (per + (1 if j < rem else 0)))
                last = c
            pieces.append(body[last:])
            body = b''.join(pieces)
        elif extra:
            body = body + b'\x00' * extra
        out += body
    return bytes(out)


def _slice_starts(b):
    p = b.find(b'\x00\x00\x01')
    while p >= 0:
        if p + 3 < len(b) and 0x01 <= b[p + 3] <= 0xAF:
            yield p
        p = b.find(b'\x00\x00\x01', p + 3)


def header_end(es, p):
    """end of the header starting at p (next start code)"""
    q = es.find(b'\x00\x00\x01', p + 4)
    return len(es) if q < 0 else q


def splice_encode(name, src_sfd, ko_raw, ranges, q=4, full=False):
    """Re-encode only the GOPs that show changed frames; every other GOP keeps its original bytes
    (full=True: re-encode every GOP, for movies whose original GOPs can't be mixed with new ones).
    A GOP of decode index g displays frames gops[g] .. gops[g+1]-1 (temporal_reference counts from
    the GOP's first displayed frame), so a run of GOPs is a contiguous span of display frames.
    The new span is encoded as closed GOPs and replaces the original bytes of those GOPs."""
    orig = open(src_sfd, 'rb').read()
    ves = b''.join(orig[x['data_off']:x['data_off'] + x['data_len']] for x in sfd.packets(orig) if x['sid'] == 0xE0)
    pics, gops = sfd_video.pictures(ves)
    n = len(pics)
    bounds = gops + [n]
    # GOP byte offsets: sequence header (if right before) or GOP header
    def gop_off(g):
        if g >= len(gops):
            return len(ves)
        p = pics[gops[g]][0]
        o = ves.rfind(b'\x00\x00\x01\xb8', 0, p)
        s = ves.rfind(b'\x00\x00\x01\xb3', 0, o)
        return s if s >= 0 and o - s < 200 else o
    seq0 = ves.find(b'\x00\x00\x01\xb3')
    # the original sequence header is repeated after each segment so the original GOPs that follow get
    # their own quantiser matrices back.
    # Found on ABAN01 (custom matrices 8,1,1,..): an ffmpeg segment placed after original GOPs decodes as
    # garbage whatever its header says (own/loaded/original matrices, original stream fields), and the PS2
    # player hung there. Such movies use full=True (spec "reencode": "all"); the in-span check in verify()
    # catches this case.
    hdr = ves[seq0:header_end(ves, seq0)]
    mat = []
    if full:
        # whole movie, in chunks of 4 original GOPs: each chunk gets the bytes its GOPs had, so the
        # player reads the new data at the original pace (one big encode put frames up to 5.6 s late)
        spans = [[g, min(g + 3, len(gops) - 1)] for g in range(0, len(gops), 4)]
    else:
        touched = sorted({g for a, b in ranges for g in range(len(gops)) if bounds[g] <= b and bounds[g + 1] > a})
        spans = []
        for g in touched:
            if spans and spans[-1][1] == g - 1:
                spans[-1][1] = g
            else:
                spans.append([g, g])
    work = os.path.join(paths.BUILD, 'movie')
    fsize = ms.W * ms.H * 3
    out = bytearray()
    prev = 0
    for g0, g1 in spans:
        f0, f1 = bounds[g0], bounds[g1 + 1]          # display frames [f0, f1)
        seg_raw = os.path.join(work, '%s_seg.rgb' % name)
        with open(ko_raw, 'rb') as fi, open(seg_raw, 'wb') as fo:
            fi.seek(f0 * fsize)
            fo.write(fi.read((f1 - f0) * fsize))
        seg_es = os.path.join(work, '%s_seg.m1v' % name)
        room = gop_off(g1 + 1) - gop_off(g0)
        # best quality that still fits the original bytes of these GOPs (keeps the read pace)
        for qq in range(2, 16):
            subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                            '-s', '%dx%d' % (ms.W, ms.H), '-r', '30000/1001', '-i', seg_raw,
                            '-c:v', 'mpeg1video', '-q:v', str(qq), '-g', '15', '-bf', '2', '-flags', '+cgop',
                            '-sc_threshold', '1000000000'] + mat + ['-f', 'mpeg1video', seg_es], check=True)
            seg = open(seg_es, 'rb').read()
            if seg.endswith(b'\x00\x00\x01\xb7'):
                seg = seg[:-4]
            if len(seg) + len(hdr) <= room * 0.97:
                break
        if len(sfd_video.pictures(seg)[0]) != f1 - f0:
            raise SystemExit('%s: segment %d-%d encoded to a different frame count' % (name, f0, f1))
        # partial mode: original GOPs follow -> give them their own header (matrices) back.
        # full mode: only ffmpeg chunks follow, which must keep ffmpeg's matrices
        tail = hdr if gop_off(g1 + 1) < len(ves) and not full else b''
        if len(seg) + len(tail) > room:
            raise SystemExit('%s: frames %d-%d do not fit even at q%d' % (name, f0, f1 - 1, qq))
        # each new picture starts no earlier than the original picture with the same decode index did, so
        # the spare bytes are spread between pictures and video stays interleaved with the audio as in the
        # original (all spare bytes after the chunk left long video-less stretches; the PS2 player
        # deadlocked there on ABAN02). Zero stuffing is legal before a start code; whole packets of it
        # become padding packets in sfd_video.replace.
        base = gop_off(g0)
        targets = [pics[k][0] - base for k in range(bounds[g0], bounds[g1 + 1])]
        seg = spread(seg, targets, room - len(tail))
        # zero stuffing keeps every following original GOP at its byte offset; in partial mode the
        # original sequence header right before it restores the original quantiser matrices
        out += ves[prev:gop_off(g0)] + seg + b'\x00' * (room - len(seg) - len(tail)) + tail
        prev = gop_off(g1 + 1)
        print('  re-encoded frames %d-%d (GOPs %d-%d) at q%d: %d -> %d bytes'
              % (f0, f1 - 1, g0, g1, qq, room, len(seg)))
    out += ves[prev:]
    os.remove(seg_raw); os.remove(seg_es)
    assert len(out) == len(ves)
    new, rep = sfd_video.replace(orig, bytes(out), align=False)
    return new, rep


def verify(sfd_path, orig_frames, ranges, slack=3, ko_frames=None):
    """decode the result: frames outside the re-encoded spans must equal the original decode
    (a few frames after each span may differ: open-GOP B frames that referenced the old data);
    frames inside must be close to the intended (Korean) frames, i.e. only encoding loss"""
    n = len(orig_frames)
    fsize = ms.W * ms.H * 3
    # decode the bare video stream: exactly one frame per picture in display order (decoding the .SFD lets
    # ffmpeg's timestamp handling duplicate/drop frames, which shifts the comparison by a frame)
    d = open(sfd_path, 'rb').read()
    es_path = sfd_path + '.verify.m1v'
    open(es_path, 'wb').write(b''.join(d[x['data_off']:x['data_off'] + x['data_len']]
                                       for x in sfd.packets(d) if x['sid'] == 0xE0))
    p = subprocess.Popen([FF, '-hide_banner', '-loglevel', 'error', '-f', 'mpegvideo', '-i', es_path,
                          '-frames:v', str(n), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    worst = (0.0, -1)
    t = 0
    while t < n:
        b = p.stdout.read(fsize)
        if len(b) < fsize:
            break
        if not any(a - 1 <= t <= z + slack for a, z in ranges):
            d = float(np.abs(np.frombuffer(b, np.uint8).astype(np.int16)
                             - np.asarray(orig_frames[t]).reshape(-1).astype(np.int16)).mean())
            if d > worst[0]:
                worst = (d, t)
        elif ko_frames is not None and t % 5 == 0:
            d = float(np.abs(np.frombuffer(b, np.uint8).astype(np.int16)
                             - np.asarray(ko_frames[t]).reshape(-1).astype(np.int16)).mean())
            if d > 12:
                p.kill()
                raise SystemExit('verify: re-encoded frame %d is broken (mean diff %.1f)' % (t, d))
        t += 1
    p.wait()
    os.remove(es_path)
    if t < n:
        raise SystemExit('verify: only %d of %d frames decoded' % (t, n))
    if worst[0] > 0.5:
        raise SystemExit('verify: frame %d differs from the original outside the changed spans (mean %.2f)'
                         % (worst[1], worst[0]))
    return worst


def cache_key(name):
    """changes whenever the spec, its Korean texts or the movie tools change"""
    h = hashlib.sha1()
    spec = json.load(open(spec_path(name), encoding='utf-8'))
    h.update(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode('utf-8'))
    for c in spec['cards']:
        h.update(korean(c).encode('utf-8'))
    here = os.path.dirname(os.path.abspath(__file__))
    for t in ('movie_build.py', 'movie_subs.py', 'sfd_video.py', 'sfd.py') + (('movie_scroll.py',) if 'scroll' in spec else ()):
        h.update(open(os.path.join(here, t), 'rb').read())
    for fnt in {STYLE['font']} | {c.get('style', {}).get('font', STYLE['font']) for c in spec['cards']}:
        h.update(fnt.encode())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--detect', action='store_true')
    ap.add_argument('--preview', type=int, nargs='*')
    ap.add_argument('--q', type=int, default=4)
    ap.add_argument('--encode-only', action='store_true', help='reuse 30_build/movie/<NAME>_ko.rgb')
    ap.add_argument('--part', type=int, nargs=2, metavar=('LO', 'HI'),
                    help='render only frames LO..HI-1 into <NAME>_ko.rgb (then --encode-only)')
    a = ap.parse_args()
    if a.detect:
        _, f = raw_frames(a.name)
        cards, _ = ms.detect_cards(f)
        print(json.dumps([{'frames': c} for c in cards]))
        return
    m = Movie(a.name)
    m.analyse()
    for c in m.cards + m.fixed:
        print('card %d-%d: %s' % (c['a'], c['b'], ' / '.join(c['lines'])))
    if m.scroll is not None:
        print('scroll: %d labels, frames %s' % (len(m.scroll.items), m.scroll.range()))
    out_dir = os.path.join(paths.TEST, 'movie')
    if a.preview:
        os.makedirs(out_dir, exist_ok=True)
        rows = [np.concatenate([np.asarray(m.f[t]), m.frame(t)], 1) for t in a.preview]
        p = os.path.join(out_dir, '%s_preview.png' % a.name)
        cv2.imwrite(p, cv2.cvtColor(np.concatenate(rows, 0), cv2.COLOR_RGB2BGR))
        print(p)
        return
    raw = os.path.join(paths.BUILD, 'movie', a.name + '_ko.rgb')
    ranges = changed_ranges(m)
    if a.part:
        # render only frames [lo, hi) into the _ko.rgb (started as a copy of the original frames), so a
        # long movie can be done in several short runs
        lo, hi = a.part
        src_raw = os.path.join(paths.BUILD, 'movie', a.name + '.rgb')
        fsize = ms.W * ms.H * 3
        if not os.path.exists(raw) or os.path.getsize(raw) != os.path.getsize(src_raw):
            import shutil
            shutil.copyfile(src_raw, raw)
        with open(raw, 'r+b') as fo:
            for t in range(lo, min(hi, len(m.f))):
                if any(x <= t <= y for x, y in ranges):
                    fo.seek(t * fsize)
                    fo.write(m.frame(t).tobytes())
                if t % 100 == 0:
                    print('frame', t, 'free %s MB' % free_mb(), flush=True)
                    wait_for_memory()
        print('part %d-%d done' % (lo, hi))
        return
    if not a.encode_only:
        fsize = ms.W * ms.H * 3
        with open(raw, 'wb') as fo:
            for t in range(len(m.f)):
                inside = any(x <= t <= y for x, y in ranges)
                fo.write(m.frame(t).tobytes() if inside else np.asarray(m.f[t]).tobytes())
                if t % 250 == 0:
                    print('frame', t, 'free %s MB' % free_mb(), flush=True)
                if t % 25 == 0:
                    wait_for_memory()
    full = m.spec.get('reencode') == 'all'
    out, rep = splice_encode(a.name, m.src, raw, ranges, a.q, full)
    if full:
        ranges = [(0, len(m.f) - 1)]
    dst = os.path.join(paths.BUILD, 'movie', a.name + '.SFD')
    open(dst, 'wb').write(out)
    # spans as re-encoded (whole GOPs) are wider than the cards; compare only clearly untouched frames
    worst = verify(dst, m.f, [(x - 20, y + 20) for x, y in ranges], ko_frames=ms.load(raw))
    rep['verify_max_diff'] = round(worst[0], 3)
    open(os.path.join(paths.BUILD, 'movie', a.name + '.key'), 'w').write(cache_key(a.name))
    print(dst, rep)


if __name__ == '__main__':
    main()
