"""Extract event text to trans/events/<n>.json (keeps existing 'ko' if source unchanged)."""
import sys, os, json, glob
import paths
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evd, textfmt

ROOT = os.path.dirname(HERE)
src_dir = sys.argv[1]
out_dir = os.path.join(paths.TRANS, 'events')
os.makedirs(out_dir, exist_ok=True)
for p in sorted(glob.glob(os.path.join(src_dir, '*.evd')), key=lambda x: int(os.path.basename(x)[:-4])):
    n = os.path.basename(p)[:-4]
    e = evd.parse(open(p, 'rb').read())
    ents = []
    for i, m in enumerate(e['msgs']):
        a, b, c, idx, d = m['hdr']
        ents.append({'key': f'm{i}', 'kind': a, 'chr': b if b != 0xffffffff else -1, 'ja': textfmt.game_to_text(m['raw'][:-1]), 'ko': ''})
    for gi, g in enumerate(e['groups']):
        for si, s in enumerate(g):
            ents.append({'key': f'g{gi}s{si}', 'kind': 'sel', 'ja': textfmt.game_to_text(s['raw'][:-1]), 'ko': ''})
    op = os.path.join(out_dir, n + '.json')
    if os.path.exists(op):
        old = {x['key']: x for x in json.load(open(op, encoding='utf-8'))}
        for x in ents:
            o = old.get(x['key'])
            if o and o['ja'] == x['ja']:
                x['ko'] = o.get('ko', '')
    json.dump(ents, open(op, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('done')
