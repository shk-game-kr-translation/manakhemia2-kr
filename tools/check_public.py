"""Guard for the public repository: fail if game data or Japanese script slipped in.

usage: check_public.py <repo dir>     (exit 1 on any violation)
Checks every file except .git/ and the ignored work folders:
  - translation entries must not carry 'ja' (only the hash 'jh')
  - no game binaries (ELF, TIM2, LZR packs, ISO, ...) and no large files except bundled fonts
  - no file with a long run of Japanese text (short terms in configs/glossary are fine)
  - markdown: no bare '~' (GitHub renders ~text~ as strikethrough)
"""
import os, sys, re, json

SKIP_DIRS = {'.git', '00_original', '10_extracted', '30_build', '40_release', '50_patch', '60_review', '90_test',
             '__pycache__'}
FONT_DIR = os.path.join('third_party', 'fonts')
BAD_EXT = {'.iso', '.bin', '.erx', '.evd', '.fp', '.tm2', '.tim', '.p2s', '.ps2', '.xdelta', '.png', '.jpg', '.bmp'}
MAGIC = [b'\x7fELF', b'TIM2', b'CD001']
JP = re.compile(r'[぀-ヿ㐀-鿿]')
MAX_JP_CHARS = 2500      # per file; the glossary / configs hold short terms only
MAX_SIZE = 2 << 20


def md_tildes(rel, s):
    """bare ASCII '~' in markdown prose turns into strikethrough on GitHub (use ～, \\~ or `code`)"""
    out, fence = [], False
    for n, ln in enumerate(s.splitlines(), 1):
        if ln.lstrip().startswith('```'):
            fence = not fence; continue
        if fence:
            continue
        prose = re.sub(r'`[^`]*`', '', ln).replace('\\~', '')
        if '~' in prose:
            out.append('%s:%d: unescaped "~" (renders as strikethrough): %s' % (rel, n, ln.strip()[:60]))
    return out


def main(root):
    bad = []
    report = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root)
            ext = os.path.splitext(f)[1].lower()
            size = os.path.getsize(p)
            in_fonts = rel.startswith(FONT_DIR)
            if ext in BAD_EXT:
                bad.append('%s: file type not allowed' % rel); continue
            if size > MAX_SIZE and not in_fonts:
                bad.append('%s: %d bytes (large files are not allowed)' % (rel, size)); continue
            if in_fonts:
                continue
            head = open(p, 'rb').read(4)
            if any(head.startswith(m) for m in MAGIC):
                bad.append('%s: looks like game data' % rel); continue
            try:
                s = open(p, encoding='utf-8').read()
            except UnicodeDecodeError:
                bad.append('%s: binary file' % rel); continue
            if rel.startswith(os.path.join('20_source', 'trans')) and ext == '.json':
                d = json.loads(s)
                ents = d['entries'] if isinstance(d, dict) else d
                n = sum(1 for e in ents if 'ja' in e)
                if n:
                    bad.append('%s: %d entries carry Japanese source text (ja)' % (rel, n))
            if ext == '.md':
                bad += md_tildes(rel, s)
            j = len(JP.findall(s))
            if j:
                report.append((j, rel))
            if j > MAX_JP_CHARS:
                bad.append('%s: %d Japanese characters' % (rel, j))
    report.sort(reverse=True)
    print('Japanese characters per file (top 8):')
    for j, rel in report[:8]:
        print('  %6d  %s' % (j, rel))
    if bad:
        print('FAIL')
        for b in bad:
            print('  ' + b)
        sys.exit(1)
    print('OK: no game data found')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
