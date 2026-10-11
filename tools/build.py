"""Product build: original ISO + translations -> Korean ISO.

usage: build.py [--out PATH] [--dev]
  --dev : development policy; untranslated entries keep Japanese (kana-only font => kanji
          become blank). Never produces a release candidate.
"""
import sys, os, json, hashlib, struct, glob, argparse, subprocess
import paths
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pycdlib
import font_build, elf_font_patch, hooks, rpk, evd, textfmt, iso_tool, elf_patch, erx, erx_patch, gfxtext, jasource
ERX_TRANS = {'erxs/QvDataE.erx': 'qvdata.json'}
from textcodec import Codec

ROOT = os.path.dirname(HERE)
SRC_ISO = paths.ORIG_ISO
SRC_SHA1 = 'd0e1ef687547cc91b43f99c226968dedd36f708a'
V = 0xFF000


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def read_iso_file(iso, p):
    import io
    b = io.BytesIO(); iso.get_file_from_iso_fp(b, iso_path=p); return b.getvalue()


def load_trans(kind):
    """trans/<kind>/*.json -> {file: {key: entry}}"""
    out = {}
    for p in sorted(glob.glob(os.path.join(paths.TRANS, kind, '*.json'))):
        data = json.load(open(p, encoding='utf-8'))
        out[os.path.splitext(os.path.basename(p))[0]] = {e['key']: e for e in data}
    return out


class Report:
    def __init__(self):
        self.errors = []; self.warnings = []; self.stats = {}

    def err(self, m): self.errors.append(m)

    def warn(self, m): self.warnings.append(m)


# width budget per event message kind (cells per visual line, max visual lines)
EVD_WIDTH = 13          # engine column limit (full-width units)
EVD_FULL = 13
EVD_PIX = 14.5          # window holds ~16 cells; keep a margin


def translate_evd(name, data, tr, codec, rep, dev):
    e = evd.parse(data)
    changed = False
    def conv(key, raw, maxlines):
        nonlocal changed
        ent = tr.get(key) if tr else None
        ja = textfmt.game_to_text(raw[:-1])
        if not ent or not ent.get('ko'):
            if not dev and not ja.strip() == '' and not (ent and ent.get('skip')):
                rep.err(f'{name}:{key} untranslated')
            return raw
        if not jasource.same(ent, ja):
            rep.err(f'{name}:{key} source mismatch'); return raw
        units = textfmt.text_to_units(ent['ko'])
        lines = textfmt.wrap(units, EVD_PIX, EVD_FULL)
        if maxlines and len(lines) > maxlines:
            rep.warn(f'{name}:{key} {len(lines)} lines > {maxlines}: {ent["ko"]!r}')
        try:
            b = textfmt.units_to_bytes(textfmt.join_lines(lines), codec)
        except KeyError as ex:
            rep.err(f'{name}:{key} {ex}'); return raw
        changed = True
        return b + b'\0'
    for i, m in enumerate(e['msgs']):
        orig_lines = sum(max(1, -(-len(l) // EVD_WIDTH)) for l in textfmt.game_to_text(m['raw'][:-1]).split('\n'))
        m['raw'] = conv(f'm{i}', m['raw'], max(3, orig_lines))
    for gi, g in enumerate(e['groups']):
        for si, s in enumerate(g):
            s['raw'] = conv(f'g{gi}s{si}', s['raw'], 1)
    return evd.build(e) if changed else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None, help='default: 40_release/mk2_kr_v<VERSION>.iso (dev: ...-dev.iso)')
    ap.add_argument('--dev', action='store_true')
    ap.add_argument('--skip-sha', action='store_true')
    ap.add_argument('--no-movies', action='store_true', help='keep the original movies (quick test builds)')
    ap.add_argument('--iso', default=SRC_ISO, help='original Japanese ISO (default: 00_original/...)')
    a = ap.parse_args()
    if a.out is None:
        a.out = os.path.join(paths.RELEASE, 'mk2_kr_v%s%s.iso' % (paths.version(), '-dev' if a.dev else ''))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    if not a.skip_sha:
        assert sha1(a.iso) == SRC_SHA1, 'original ISO sha1 mismatch: need SLPM-55005 (sha1 %s)' % SRC_SHA1
    rep = Report()
    iso = pycdlib.PyCdlib(); iso.open(a.iso)
    elf = bytearray(read_iso_file(iso, '/SLPM_550.05;1'))
    rpk_orig = read_iso_file(iso, '/RPK.BIN;1')
    iso.close()
    elf_orig = bytes(elf)
    # font
    cfg = json.load(open(os.path.join(paths.CONFIG, 'font.json'), encoding='utf-8'))
    fdir = os.path.join(paths.BUILD, 'font')
    font_build.build_from_bytes = None
    tmp_elf = os.path.join(paths.BUILD, 'orig.elf')
    os.makedirs(os.path.dirname(tmp_elf), exist_ok=True)
    open(tmp_elf, 'wb').write(elf)
    font_build.build(tmp_elf, set(), fdir, paths.font(cfg['ttf']), cfg)
    codec = Codec(os.path.join(fdir, 'charmap.json'))
    elf_font_patch.patch(elf, open(os.path.join(fdir, 'font_list.bin'), 'rb').read(),
                         open(os.path.join(fdir, 'font_glyphs.bin'), 'rb').read())
    hooks.apply(elf)
    # ELF strings
    elf_ents = json.load(open(os.path.join(paths.TRANS, 'elf', 'elf.json'), encoding='utf-8'))
    jasource.fill_elf(elf_ents, elf_orig, rep.err)   # public sources carry only hashes of the Japanese
    if not a.dev:
        for e in elf_ents:
            if not e.get('ko') and not e.get('skip') and not (e['room'] <= 3):
                rep.err(f'elf:{e["key"]} untranslated')
    glyph_len = os.path.getsize(os.path.join(fdir, 'font_glyphs.bin'))
    pool_lo = (font_build.GLY0 - V + glyph_len + 15) & ~15
    elf_patch.patch(elf, elf_ents, codec, pool_lo, hooks.HOOK_BASE - V, rep)
    # events
    tr_ev = load_trans('events')
    changed = {}
    ents = rpk.read_table(elf)
    for name, off, size in ents:
        if not name.startswith('Event/'):
            continue
        key = name[6:-4]
        data = rpk_orig[off * 2048:off * 2048 + size]
        nb = translate_evd(key, data, tr_ev.get(key), codec, rep, a.dev)
        if nb is not None:
            changed[name] = nb
    rep.stats['events_changed'] = len(changed)
    # ERX field text (RPK copy and the identical /ERXS copy on disc)
    erx_files = {}
    for name, off, size in ents:
        tp = os.path.join(paths.TRANS, 'erx', ERX_TRANS.get(name, '-'))
        if not os.path.exists(tp):
            continue
        mod = erx.Erx(rpk_orig[off * 2048:off * 2048 + size])
        tr = json.load(open(tp, encoding='utf-8'))['entries']
        jasource.fill_erx(tr, mod, rep.err)
        if not a.dev:
            for x in tr:
                if not x.get('ko') and not x.get('skip'):
                    rep.err(f'erx:{name}:{x["key"]} untranslated')
        rep.stats[name] = erx_patch.patch(mod, name, tr, codec, rep)
        changed[name] = bytes(mod.d)
        erx_files['/ERXS/' + name.split('/')[-1].upper() + ';1'] = bytes(mod.d)
    # graphics text (config/gfx/*.json)
    # (packs keep their size, so they are written in place: RPK table entries stay unchanged)
    by_name = {n: (o, s) for n, o, s in ents}
    inplace = {}
    for spec in gfxtext.specs():
        if 'files' in spec:  # single image files (may change size -> appended to RPK)
            for fname, fspec in spec['files'].items():
                o, s = by_name[fname]
                try:
                    changed[fname] = gfxtext.build_file(rpk_orig[o * 2048:o * 2048 + s], fspec)
                except ValueError as ex:
                    rep.err(f'gfx:{fname} {ex}')
            rep.stats['gfx_files'] = rep.stats.get('gfx_files', 0) + len(spec['files'])
            continue
        o, s = by_name[spec['pack']]
        try:
            nb = gfxtext.build_pack(rpk_orig[o * 2048:o * 2048 + s], spec)
            assert len(nb) == s
            inplace[o * 2048] = nb
        except ValueError as ex:
            rep.err(f'gfx:{spec["pack"]} {ex}')
    rep.stats['gfx_packs'] = len(inplace)
    new_rpk = bytearray(rpk.rebuild(elf, rpk_orig, changed))
    for off, nb in inplace.items():
        new_rpk[off:off + len(nb)] = nb
    new_rpk = bytes(new_rpk)
    for w in rep.warnings[:50]:
        print('WARN', w)
    print('warnings', len(rep.warnings))
    if rep.errors:
        for e in rep.errors[:50]:
            print('ERR', e)
        print('errors', len(rep.errors))
        if not a.dev:
            sys.exit(1)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    # movies with burned-in captions (config/movies/*.json): rebuilt only when their cache key changes
    # (spec, Korean text, movie tools); same size as the originals, written in place
    movies = {}
    if not a.no_movies:
        import movie_build
        for sp in sorted(glob.glob(os.path.join(paths.CONFIG, 'movies', '*.json'))):
            name = os.path.splitext(os.path.basename(sp))[0]
            out_p = os.path.join(paths.BUILD, 'movie', name + '.SFD')
            key_p = os.path.join(paths.BUILD, 'movie', name + '.key')
            key = movie_build.cache_key(name)
            if not (os.path.exists(out_p) and os.path.exists(key_p) and open(key_p).read() == key):
                print('movie %s: rendering Korean captions (takes a while)...' % name, flush=True)
                subprocess.run([sys.executable, '-X', 'utf8', os.path.join(HERE, 'movie_build.py'), name], check=True)
            movies['/MOVIE/%s.SFD;1' % name] = open(out_p, 'rb').read()
        rep.stats['movies'] = sorted(movies)
    vol = iso_tool.build(a.iso, a.out, dict({'/SLPM_550.05;1': bytes(elf)}, **erx_files, **movies),
                         {'/RPK.BIN;1': new_rpk})
    print('stats', rep.stats, 'volume sectors', vol)


if __name__ == '__main__':
    main()
