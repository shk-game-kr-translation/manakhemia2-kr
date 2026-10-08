"""Generate config/gfx/help.json (res/HELP captions) from detected caption boxes + translations.

usage: helpgen.py <detect.json> <help_ko.txt>
detect.json: {"005": [{"box": [x, y, w, h], "kind": "B"|"R"}, ...]}  (scratch tool helpdet.py)
help_ko.txt: lines "NNN idx 한국어" (idx = detected line index; '#' comments). Optional per-line
overrides after a tab as JSON, e.g. 005 0 붉어지면 기절 직전!\t{"th": 12}
Kinds: B = white text with blue outline, R = red text with white outline.
"""
import sys, os, json
import paths

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLE = {'B': dict(fill=[255, 255, 255], outline=[8, 0, 248]),
         'R': dict(fill=[235, 20, 20], outline=[255, 255, 255]),
         'O': dict(fill=[255, 120, 0], outline=[255, 255, 255])}


def main():
    det = json.load(open(sys.argv[1], encoding='utf-8'))
    files = {}
    n = 0
    for ln in open(sys.argv[2], encoding='utf-8'):
        ln = ln.rstrip('\n')
        if not ln.strip() or ln.startswith('#'):
            continue
        extra = {}
        if '\t' in ln:
            ln, ex = ln.split('\t', 1)
            extra = json.loads(ex)
        img, idx, ko = ln.split(' ', 2)
        if idx == 'm':  # manual box (extra must give box, kind defaults to B)
            d = dict(box=extra.pop('box'), kind=extra.pop('kind', 'B'))
        else:
            d = det[img][int(idx)]
            if 'box' in extra:
                d = dict(d, box=extra.pop('box'))
        x, y, w, h = d['box']
        x2, y2 = min(384, x + w + 8), min(256, y + h)
        y, y2 = y - 1, min(256, y2 + 1)
        x, y = max(0, x), max(0, y)
        w, h = x2 - x, y2 - y
        lab = dict(STYLE[d['kind']], box=[x, y, w, h], ko=ko, caption=True, weight='Black', ow=2, fit=True,
                   th=max(9, h - 6), valign='center', noanalyse=True)
        lab.update(extra)
        files.setdefault('res/HELP/HELP_%s.tim.lzr' % img, {'labels': []})['labels'].append(lab)
        n += 1
    out = os.path.join(paths.CONFIG, 'gfx', 'help.json')
    json.dump({'files': files}, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(n, 'captions in', len(files), 'images')


if __name__ == '__main__':
    main()
