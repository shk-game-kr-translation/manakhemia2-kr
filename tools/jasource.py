"""Japanese source text without shipping it.

The public repository stores translation entries with 'jh' (short hash of the Japanese source line)
instead of 'ja'. The build reads the Japanese text from the user's own original ISO, checks it
against 'jh', and fills 'ja' back in memory, so nothing downstream changes.

  jh(ja)                      hash used in place of the text
  strip(entries)              ja -> jh (publishing)
  fill_elf / fill_events / fill_erx   jh -> ja from game data (building)
  same(entry, ja)             source check that works with either form
"""
import hashlib
import textfmt


def jh(ja):
    return hashlib.sha1(ja.encode('utf-8')).hexdigest()[:12]


def strip(entries):
    out = []
    for e in entries:
        n = {}
        for k, v in e.items():
            if k == 'ja':
                n['jh'] = jh(v)
            else:
                n[k] = v
        out.append(n)
    return out


def same(ent, ja):
    if 'ja' in ent:
        return ent['ja'] == ja
    return ent.get('jh') == jh(ja)


def _fill(ent, ja, where, err):
    if 'ja' in ent:
        return
    if ent.get('jh') != jh(ja):
        err('%s:%s source mismatch (different game version or data?)' % (where, ent['key']))
    ent['ja'] = ja


def fill_elf(entries, elf, err):
    """ELF entries: key = file offset (hex) of a NUL-terminated string."""
    for e in entries:
        if 'ja' in e:
            continue
        off = int(e['key'], 16)
        _fill(e, textfmt.game_to_text(bytes(elf[off:elf.index(b'\0', off)])), 'elf', err)


def event_texts(evd_mod, data):
    """{key: ja} of one event script (same keys as extract_events)."""
    e = evd_mod.parse(data)
    out = {}
    for i, m in enumerate(e['msgs']):
        out['m%d' % i] = textfmt.game_to_text(m['raw'][:-1])
    for gi, g in enumerate(e['groups']):
        for si, s in enumerate(g):
            out['g%ds%d' % (gi, si)] = textfmt.game_to_text(s['raw'][:-1])
    return out


def fill_events(entries, texts, where, err):
    for e in entries:
        if e['key'] in texts:
            _fill(e, texts[e['key']], where, err)
        elif 'ja' not in e:
            err('%s:%s not in game data' % (where, e['key']))


def fill_erx(entries, mod, err):
    """ERX entries: key = module VA (hex) of a relocated string."""
    import erx_extract
    st = erx_extract.strings(mod)
    for e in entries:
        v = int(e['key'], 16)
        if v in st:
            _fill(e, textfmt.game_to_text(st[v][0]), 'erx', err)
        elif 'ja' not in e:
            err('erx:%s not in game data' % e['key'])
