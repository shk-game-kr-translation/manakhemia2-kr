"""Item stat blocks ('{F1}対象：…'): rows of 10-column fields.

Japanese rows are split into 10-column fields (full-width counting, {=%s} counts as the
value inserted at runtime and is kept with its label). Each field is translated through
config/statblock_fields.json and the row is rebuilt with full-width/half-width spaces so the
second field starts at column 10 again.
"""
import os, re, json, sys
import paths
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import textfmt

ROOT = os.path.dirname(HERE)
FIELDS = os.path.join(paths.CONFIG, 'statblock_fields.json')
TOK = re.compile(r'\{[^{}]*\}')


def is_statblock(ja):
    return ja.startswith('{F1}対象：')


def fields(ja):
    """[[field, ...] per row]; trailing padding stripped"""
    rows = []
    for line in ja[4:].split('\n'):
        out, cur, w = [], '', 0
        parts = TOK.split(line)
        toks = TOK.findall(line)
        seq = []
        for i, p in enumerate(parts):
            seq += list(p)
            if i < len(toks):
                seq.append(toks[i])
        for c in seq:
            cw = 0 if c.startswith('{') else 1
            if w + cw > 10 and cur:
                out.append(cur); cur, w = '', 0
            cur += c; w += cw
        if cur:
            out.append(cur)
        rows.append([f.rstrip('　') for f in out if f.strip('　')])
    return rows


def width(s):
    return textfmt.width(textfmt.text_to_units(s))


def pad(s, cells):
    w = width(s)
    if w > cells:
        raise ValueError(f'field too wide ({w}>{cells}): {s}')
    full = int(cells - w)
    half = (cells - w) - full
    return s + '　' * full + (' ' if half else '')


def build(ja, table):
    rows = []
    for r in fields(ja):
        ko = [table[f] for f in r]
        rows.append(''.join(pad(f, 10) for f in ko[:-1]) + ko[-1])
    return '{F1}' + '\n'.join(rows)


def load_table():
    return json.load(open(FIELDS, encoding='utf-8')) if os.path.exists(FIELDS) else {}


if __name__ == '__main__':
    elf = json.load(open(os.path.join(paths.TRANS, 'elf', 'elf.json'), encoding='utf-8'))
    tab = load_table()
    seen = {}
    for e in elf:
        if is_statblock(e['ja']):
            for r in fields(e['ja']):
                for f in r:
                    seen[f] = seen.get(f, 0) + 1
    miss = [f for f in seen if f not in tab]
    print(len(seen), 'fields;', len(miss), 'untranslated')
    print(' | '.join(sorted(miss)))
