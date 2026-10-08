"""ERX translation helper.
  erx_tr.py export <json> <out.txt> [from] [to]   key<TAB>ja (newlines as \\n) for entries [from, to)
  erx_tr.py import <json> <batch.txt>...          batch lines: key<TAB>ko (newlines as \\n)
  erx_tr.py check <json>                          layout / width / glyph check of every ko
"""
import sys, os, json
import paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elf_patch, erx_patch, textfmt
from textcodec import Codec

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(p):
    return json.load(open(p, encoding='utf-8'))


def save(p, d):
    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def check(entries):
    codec = Codec(os.path.join(paths.BUILD, 'font', 'charmap.json'))
    bad = 0
    for x in entries:
        if not x.get('ko') or x.get('skip'):
            continue
        lines, allowed, lim = erx_patch.layout(x)
        msg = []
        if len(lines) > allowed:
            msg.append(f'lines {len(lines)}>{allowed}')
        w = max(textfmt.width(l) for l in lines)
        if '\n' not in x['ja'] and not erx_patch.is_news(x['ja']):
            # single line: names shown in wide map lists / auto-sized bubbles (seen in game)
            lim = max(lim, 12)
        if w > lim:
            msg.append(f'width {w}>{lim}')
        try:
            textfmt.units_to_bytes(textfmt.join_lines(lines), codec)
        except KeyError as ex:
            msg.append(f'glyph {ex}')
        if msg:
            bad += 1
            print(x['key'], ' '.join(msg), repr(x['ja']), repr(x['ko']))
    done = sum(1 for x in entries if x.get('ko') or x.get('skip'))
    print('translated', done, '/', len(entries), 'problems', bad)


def main():
    cmd, p = sys.argv[1], sys.argv[2]
    d = load(p)
    ents = d['entries']
    if cmd == 'export':
        a = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        b = int(sys.argv[5]) if len(sys.argv) > 5 else len(ents)
        with open(sys.argv[3], 'w', encoding='utf-8') as f:
            for x in ents[a:b]:
                f.write(x['key'] + '\t' + x['ja'].replace('\n', '\\n') + '\n')
    elif cmd == 'import':
        by = {x['key']: x for x in ents}
        n = 0
        for bp in sys.argv[3:]:
            for ln in open(bp, encoding='utf-8'):
                ln = ln.rstrip('\n')
                if not ln.strip() or ln.startswith('#'):
                    continue
                k, ko = ln.split('\t', 1)
                if k not in by:
                    print('unknown key', k); continue
                by[k]['ko'] = ko.replace('\\n', '\n')
                n += 1
        save(p, d)
        print('imported', n)
        check(ents)
    elif cmd == 'check':
        check(ents)


if __name__ == '__main__':
    main()
