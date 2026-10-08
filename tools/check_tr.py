"""Validate event translations: control-token parity, unmapped chars, wrapped line count."""
import sys, os, json, glob, re, collections
import paths
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import textfmt, elf_patch
from textcodec import Codec

ROOT = os.path.dirname(HERE)
TOK = re.compile(r'\{[^{}]*\}')
EVD_FULL = 13
EVD_PIX = 14.5


def tokens(t):
    return collections.Counter(x for x in TOK.findall(t))


def main(maxw=13):
    cc = Codec(os.path.join(paths.BUILD, 'font', 'charmap.json'))
    issues = collections.defaultdict(list)
    seen = set()
    for p in sorted(glob.glob(os.path.join(paths.TRANS, 'events', '*.json')), key=lambda p: int(os.path.basename(p)[:-5])):
        f = os.path.basename(p)[:-5]
        for e in json.load(open(p, encoding='utf-8')):
            if not e['ko'] or (e['ja'], e['ko']) in seen:
                continue
            seen.add((e['ja'], e['ko']))
            ko, ja = e['ko'], e['ja']
            if tokens(ko) != tokens(ja):
                issues['token'].append((f, e['key'], ja, ko))
            u = textfmt.text_to_units(ko)
            try:
                textfmt.units_to_bytes(u, cc)
            except KeyError as ex:
                issues['char'].append((f, e['key'], str(ex), ko))
            if e['kind'] == 'sel':
                if textfmt.width(u) > max(13, len(ja)):
                    issues['sel_width'].append((f, e['key'], ja, ko))
                continue
            lines = textfmt.wrap(u, EVD_PIX, EVD_FULL)
            ol = sum(max(1, -(-len(TOK.sub('', l)) // maxw)) for l in ja.split('\n'))
            if len(lines) > max(3, ol):
                issues['lines'].append((f, e['key'], len(lines), ko))
    for k, v in issues.items():
        print(f'== {k}: {len(v)}')
        for x in v[:int(sys.argv[1]) if len(sys.argv) > 1 else 20]:
            print('  ', x)


if __name__ == '__main__' and not (len(sys.argv) > 2 and sys.argv[2] == 'elf'):
    main()


def check_elf(nshow=20):
    """ELF strings: token parity, unmapped chars, per-line width vs the Japanese original."""
    cc = Codec(os.path.join(paths.BUILD, 'font', 'charmap.json'))
    d = json.load(open(os.path.join(paths.TRANS, 'elf', 'elf.json'), encoding='utf-8'))
    issues = collections.defaultdict(list)
    seen = set()
    for e in d:
        ko, ja = e.get('ko'), e['ja']
        if not ko or e.get('skip') or (ja, ko) in seen:
            continue
        seen.add((ja, ko))
        if tokens(ko) != tokens(ja):
            issues['token'].append((e['key'], ja, ko))
        try:
            textfmt.units_to_bytes(textfmt.text_to_units(ko), cc)
        except KeyError as ex:
            issues['char'].append((e['key'], str(ex), ko))
        lines, njl, lim = elf_patch.layout(ja, ko, e['key'])
        kl = [textfmt.width(l) for l in lines]
        if len(lines) > njl:
            issues['nlines'].append((e['key'], len(lines), njl, ko))
        if njl == 1 and lim <= 24:
            lim = max(lim + 1, lim * 1.08)   # short UI labels: small slack
        lw = elf_patch.list_width(e['key'])
        n = elf_patch.wrap_cols(e['key'], ja)
        if njl == 1 and n and not (lw and ja.startswith('{F1}')):
            lim = n                          # text window: engine width
        elif njl == 1 and lw:
            lim = max(lim, lw)
        if max(kl) > lim:
            issues['width'].append((e['key'], max(kl), lim, ja, ko))
    for k, v in issues.items():
        print(f'== elf {k}: {len(v)}')
        for x in v[:nshow]:
            print('  ', x)


if __name__ == '__main__' and len(sys.argv) > 2 and sys.argv[2] == 'elf':
    check_elf(int(sys.argv[1]))
