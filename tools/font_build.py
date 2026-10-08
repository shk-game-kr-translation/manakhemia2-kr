"""Build the unified Korean font for the ELF.

The game has two glyph fonts (list of SJIS codes + 24x24 4bpp glyphs):
  font0 list @0x8aa030 (2190), glyphs @0x8ac058; font1 list @0x8ab150 (1911), glyphs @0x946018.
Lists and glyph arrays are contiguous, so both are merged into one font of up to
TOTAL = 4101 glyphs; the font pointer tables (@0x7dc7c0 lists, @0x7dc7e8 glyphs) are
pointed at the merged font for both font ids.

Output: charmap.json {char: sjis_code_int}, plus binary blobs (list bytes, glyph bytes).
"""
import json, os, sys, struct
import paths
from PIL import Image, ImageDraw, ImageFont

V = 0xFF000
LIST0, LIST1 = 0x8aa030, 0x8ab150
GLY0, GLY1 = 0x8ac058, 0x946018
N0, N1 = 2190, 1911
TOTAL = N0 + N1
GB = 288
GLY_END = GLY1 + N1 * GB  # 0x9cc5f8
assert LIST0 + 2 * TOTAL + 1 <= GLY0
MAX_GLYPH_END = 0x9a0000  # glyphs must end before this; space after is free for code/data

HERE = os.path.dirname(os.path.abspath(__file__))


def ks_hangul():
    out = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            try:
                out.append(bytes([hi, lo]).decode('euc-kr'))
            except UnicodeDecodeError:
                pass
    assert len(out) == 2350
    return out


def sjis_kanji_codes():
    """Valid double-byte SJIS codes usable as private slots (level-2 kanji area first)."""
    codes = []
    for lead in list(range(0xE0, 0xEB)) + list(range(0x98, 0xA0)) + list(range(0x89, 0x98)):
        for tr in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            c = bytes([lead, tr])
            try:
                ch = c.decode('cp932')
            except UnicodeDecodeError:
                continue
            if len(ch) == 1:
                codes.append((lead << 8) | tr)
    return codes


def cat(ch):
    o = ord(ch)
    if 0x3040 <= o <= 0x30ff:
        return 'kana'
    if 0x4e00 <= o <= 0x9fff or ch in '々〆〇仝':
        return 'kanji'
    return 'sym'


# The engine never shows the first 3 columns of a 24x24 cell (original glyph ink always lies in
# columns 3..20), so ink is placed inside [INK_L, INK_R): full-width glyphs are centred in
# columns 3..20, narrow (half-advance, 12 px) glyphs in columns 3..14.
INK_L = 3
FULL_R, NARROW_R = 21, 15


def _quantize(im, cfg):
    im = im.resize((24, 24), Image.LANCZOS)
    return [min(15, (min(255, int(v * cfg.get('gain', 1.0))) + 8) // 17) for v in im.get_flattened_data()]


def _place(font, ch, cfg, left, right, anchor='center'):
    """draw ch at 4x so its ink box sits inside columns [left, right) of the 24 px cell"""
    bb = font.getbbox(ch)
    w = bb[2] - bb[0]
    L, R = left * 4, right * 4
    if anchor == 'left':
        x = L
    elif anchor == 'right':
        x = R - w
    else:
        x = L + (R - L - w) / 2
    x = max(x, L) if w <= R - L else L + (R - L - w) / 2
    im = Image.new('L', (24 * 4, 24 * 4), 0)
    y = cfg['y'] * 4
    if cfg.get('auto_y'):  # put the top of full-height Hangul at the cell top (like the original)
        y = 1 - font.getbbox('한글')[1]
    ImageDraw.Draw(im).text((x - bb[0], y), ch, fill=255, font=font)
    # keep the real ink (after downsampling) inside columns [left, right): the engine hides
    # columns outside 3..20, so antialiasing spill into column 21 / 2 shows as clipped edges.
    ink = im.getbbox()
    if ink:
        lo, hi = L + 3, R - 3  # 3/4 px margin for the LANCZOS kernel
        x0, x1 = ink[0], ink[2]
        if x1 - x0 > hi - lo:  # too wide: squeeze horizontally
            band = im.crop((x0, 0, x1, 96)).resize((hi - lo, 96), Image.LANCZOS)
            im = Image.new('L', (96, 96), 0); im.paste(band, (lo, 0))
        elif x0 < lo or x1 > hi:
            dx = lo - x0 if x0 < lo else hi - x1
            im = im.transform(im.size, Image.AFFINE, (1, 0, -dx, 0, 1, 0))
    return _quantize(im, cfg)


def render_glyph(font, ch, cfg):
    """24x24 4bpp glyph values (list of 576 ints 0..15)."""
    return _place(font, ch, cfg, INK_L, FULL_R)


def render_narrow(font, ch, cfg):
    """ASCII glyph in columns 3..14 (advance is halved by hooks)."""
    anchor = 'left' if ch in '.,!?;:)]}' else 'right' if ch in '([{' else 'center'
    return _place(font, ch, cfg, INK_L, NARROW_R, anchor)


def pack(vals):
    out = bytearray()
    for i in range(0, len(vals), 2):
        out.append(vals[i] | (vals[i + 1] << 4))
    return bytes(out)


def scan_trans():
    import glob
    chars = set()
    for p in glob.glob(os.path.join(paths.TRANS, '**', '*.json'), recursive=True):
        d = json.load(open(p, encoding='utf-8'))
        for e in (d['entries'] if isinstance(d, dict) else d):
            chars.update(e.get('ko', ''))
    return chars


def build(elf_path, used_chars, out_dir, font_path, cfg):
    d = open(elf_path, 'rb').read()
    used_chars = set(used_chars) | scan_trans()

    def lst(va, n):
        o = va - V
        return d[o:o + 2 * n].decode('cp932')

    c0, c1 = lst(LIST0, N0), lst(LIST1, N1)
    gly = {}
    for chars, base in ((c0, GLY0), (c1, GLY1)):
        for i, ch in enumerate(chars):
            if ch not in gly:
                o = base - V + i * GB
                gly[ch] = d[o:o + GB]
    syms = []
    for ch in c0 + c1:
        if cat(ch) == 'sym' and ch not in syms and not (0xF000 <= ord(ch) < 0xF100):
            syms.append(ch)
    hangul = ks_hangul()
    extra = sorted(ch for ch in used_chars if 0xAC00 <= ord(ch) <= 0xD7A3 and ch not in hangul)
    hangul += extra
    # Japanese fallback: font0 order is roughly by frequency; keep kana first then kanji
    jp = [ch for ch in c0 + c1 if cat(ch) != 'sym']
    seen = set(); jp2 = []
    for ch in sorted(jp, key=lambda c: (cat(c) != 'kana',)):
        if ch not in seen:
            seen.add(ch); jp2.append(ch)
    # Japanese fallback: kana only (kanji are dropped; any leftover kanji in product text
    # fails the build as an unmapped character). The freed tail holds hooks/relocated data.
    jp_keep = [ch for ch in jp2 if cat(ch) == 'kana']
    cap = (MAX_GLYPH_END - GLY0) // GB
    if len(syms) + len(hangul) + len(jp_keep) > cap:
        raise SystemExit(f'font overflow: {len(syms)}+{len(hangul)}+{len(jp_keep)} > {cap}')
    # assign codes
    cmap = {}
    for ch in syms + jp_keep:
        cmap[ch] = int.from_bytes(ch.encode('cp932'), 'big')
    # Hangul take SJIS codes absent from the original fonts, so leftover Japanese kanji render
    # blank (and fail the build check) instead of as unrelated Hangul.
    used_codes = set(cmap.values()) | {int.from_bytes(ch.encode('cp932'), 'big') for ch in c0 + c1}
    free = [c for c in sjis_kanji_codes() if c not in used_codes]
    for ch, code in zip(hangul, free):
        cmap[ch] = code
    assert all(ch in cmap for ch in hangul)
    # narrow (half-advance) glyphs for ASCII 0x21..0x7e: Unicode PUA U+F021.. -> codes 0xEB40..
    narrow = [chr(0xF000 + c) for c in range(0x21, 0x7f)]
    for i, ch in enumerate(narrow):
        tr = 0x40 + i
        if tr >= 0x7f:
            tr += 1
        cmap[ch] = 0xEB00 | tr
    order = syms + hangul + narrow + jp_keep
    font = ImageFont.truetype(font_path, int(cfg['size'] * 4))
    list_bytes = bytearray()
    glyph_bytes = bytearray()
    for ch in order:
        list_bytes += cmap[ch].to_bytes(2, 'big')
        if ch in gly:
            glyph_bytes += gly[ch]
        elif 0xF000 <= ord(ch) < 0xF100:
            glyph_bytes += pack(render_narrow(font, chr(ord(ch) - 0xF000), cfg))
        else:
            glyph_bytes += pack(render_glyph(font, ch, cfg))
    assert len(order) <= TOTAL
    os.makedirs(out_dir, exist_ok=True)
    json.dump({ch: cmap[ch] for ch in order}, open(os.path.join(out_dir, 'charmap.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=0)
    open(os.path.join(out_dir, 'font_list.bin'), 'wb').write(bytes(list_bytes))
    open(os.path.join(out_dir, 'font_glyphs.bin'), 'wb').write(bytes(glyph_bytes))
    return order, cmap


if __name__ == '__main__':
    elf, out_dir = sys.argv[1:3]
    cfg = json.load(open(os.path.join(paths.CONFIG, 'font.json'), encoding='utf-8'))
    order, cmap = build(elf, set(), out_dir, paths.font(cfg['ttf']), cfg)
    print('glyphs', len(order))
