"""Extract translatable ELF strings -> trans/elf/elf.json (one entry per unique string offset).

Population: strings in file range [0xa60000, 0xb90000) whose characters are all displayable
(font charset or ASCII) and that have at least one reference (data pointer or code lui/addiu).
Entries keep refs so the build can relocate. Existing 'ko' is preserved when 'ja' is unchanged.
"""
import sys, os, json
import paths
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import elf_strings, dumpfont, textfmt

ROOT = os.path.dirname(HERE)
V = 0xFF000
LO, HI = 0xa60000, 0xb90000
CODE_END = 0x597000


def main(elf_path):
    d = open(elf_path, 'rb').read()
    _, c0 = dumpfont.load(elf_path, 0)
    _, c1 = dumpfont.load(elf_path, 1)
    cs = set(c0) | set(c1)
    inv = elf_strings.inventory(elf_path)
    ents = []
    for x in inv:
        t = x['text']
        if not (LO <= x['off'] < HI):
            continue
        if not all((0x20 <= ord(c) < 0x7f) or c in cs for c in t):
            continue
        if not any(c in cs and ord(c) >= 0x3000 for c in t):
            continue
        refs = []
        for k, a, l in x['refs']:
            fo = a - V
            if k == 'data' and (fo < CODE_END or LO <= fo < HI):
                continue  # unverified location (code area / inside string pool)
            refs.append([k, a, l])
        if not refs:
            continue
        # allocated room: up to next non-zero byte (strings are packed with NUL padding)
        e = x['off'] + x['len']
        room = e
        while room < len(d) and d[room] == 0:
            room += 1
        ents.append({'key': '%06x' % x['off'], 'ja': textfmt.game_to_text(d[x['off']:e]),
                     'room': room - x['off'] - 1, 'refs': refs, 'ko': ''})
    out = os.path.join(paths.TRANS, 'elf', 'elf.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        old = {e['key']: e for e in json.load(open(out, encoding='utf-8'))}
        for e in ents:
            o = old.get(e['key'])
            if o and o['ja'] == e['ja']:
                e['ko'] = o.get('ko', '')
        # manual entries (strings reached through tables the reference scan misses; in place only)
        keys = {e['key'] for e in ents}
        ents += [o for o in old.values() if o.get('manual') and o['key'] not in keys]
        ents.sort(key=lambda e: e['key'])
    json.dump(ents, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('entries', len(ents), 'unique ja', len(set(e['ja'] for e in ents)),
          'chars', sum(len(e['ja']) for e in ents))


if __name__ == '__main__':
    main(sys.argv[1])
