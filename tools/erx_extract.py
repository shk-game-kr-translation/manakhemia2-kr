"""Extract the text strings of an ERX module (RPK entry) into trans/erx/<name>.json.

Only strings that are targets of R_MIPS_32 relocations in .rel.data are taken (the module's
real string table entries). Entry: key = string address (module VA, hex), ja (textfmt),
ko (merged from an existing file), room = byte length + following zero run,
refs = [file offsets of the 32-bit data words that point at the string].
usage: erx_extract.py <rpk entry name> <out json>
"""
import sys, os, json, struct
import paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erx, rpk, textfmt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_module(name):
    elf = bytearray(open(paths.game('SLPM_550.05'), 'rb').read())
    for n, o, sz in rpk.read_table(elf):
        if n == name:
            with open(paths.game('RPK.BIN'), 'rb') as f:
                f.seek(o * 2048)
                return erx.Erx(f.read(sz))
    raise KeyError(name)


def va2off(e, a):
    for s in e.sections:
        if s['type'] == 1 and s['addr'] and s['addr'] <= a < s['addr'] + s['size']:
            return s['off'] + a - s['addr']
    return None


def strings(e):
    """{va: (bytes without NUL, room, [ref word file offsets], [reloc entry file offsets])}"""
    d = e.d
    refs = {}
    for tgt, ro, ty, sy, reo in e.relocs():
        if ty != 2:
            continue
        wo = va2off(e, ro)
        if wo is None:
            continue
        v = struct.unpack_from('<I', d, wo)[0]
        refs.setdefault(v, []).append((wo, reo))
    out = {}
    for v, rl in refs.items():
        so = va2off(e, v)
        if so is None:
            continue
        m = erx.SJIS.match(bytes(d[so:so + 4096]))
        if not m:
            continue
        b = m.group()[:-1]
        try:
            u = b.decode('cp932')
        except UnicodeDecodeError:
            continue
        if not any(ord(c) >= 0x80 for c in u):
            continue
        z = so + len(b)
        while z < len(d) and d[z] == 0:
            z += 1
        out[v] = (b, z - so - 1, [w for w, _ in rl], [r for _, r in rl])
    return out


def main():
    name, outp = sys.argv[1], sys.argv[2]
    e = load_module(name)
    old = {}
    if os.path.exists(outp):
        old = {x['key']: x for x in json.load(open(outp, encoding='utf-8'))['entries']}
    ents = []
    for v, (b, room, words, rels) in sorted(strings(e).items()):
        k = '%06x' % v
        x = dict(key=k, ja=textfmt.game_to_text(b), ko='', room=room, refs=words)
        if k in old:
            x['ko'] = old[k].get('ko', '')
            if old[k].get('skip'):
                x['skip'] = old[k]['skip']
        ents.append(x)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(dict(module=name, entries=ents), open(outp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(len(ents), 'strings', sum(len(x['ja']) for x in ents), 'chars')


if __name__ == '__main__':
    main()
