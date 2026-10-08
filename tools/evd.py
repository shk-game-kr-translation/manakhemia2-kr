"""EVD event script container (Mana Khemia 2).

Layout (all u32 LE):
  nmsg, nmsg * { a, b, c, idx, d, len, bytes[len] + pad }
  n1, code1 words[n1]           (walkable with opcode length table at ELF va 0xa13478)
  n2, code2 words[n2]
  ngroups, ngroups * { nsel, nsel * { len, bytes[len] + pad } }
String len includes the terminating NUL. Stored size is (len & ~3) + 4
(always at least one pad byte position after rounding; verified on all 1226 files).
Code refers to messages by index, so string lengths may change freely.
"""
import struct


def _ssize(n):
    return (n & ~3) + 4


def _str(d, o):
    n = struct.unpack_from('<I', d, o)[0]
    o += 4
    sz = _ssize(n)
    return d[o:o + n], d[o + n:o + sz], o + sz


def parse(d):
    o = 0
    nmsg = struct.unpack_from('<I', d, o)[0]; o += 4
    msgs = []
    for _ in range(nmsg):
        hdr = struct.unpack_from('<5I', d, o); o += 20
        raw, pad, o = _str(d, o)
        msgs.append({'hdr': hdr, 'raw': raw, 'pad': pad})
    n1 = struct.unpack_from('<I', d, o)[0]
    code1 = d[o + 4:o + 4 + 4 * n1]; o += 4 + 4 * n1
    n2 = struct.unpack_from('<I', d, o)[0]
    code2 = d[o + 4:o + 4 + 4 * n2]; o += 4 + 4 * n2
    ng = struct.unpack_from('<I', d, o)[0]; o += 4
    groups = []
    for _ in range(ng):
        ns = struct.unpack_from('<I', d, o)[0]; o += 4
        g = []
        for _ in range(ns):
            raw, pad, o = _str(d, o)
            g.append({'raw': raw, 'pad': pad})
        groups.append(g)
    if o != len(d):
        raise ValueError(f'trailing bytes: parsed {o} of {len(d)}')
    return {'msgs': msgs, 'code1': code1, 'code2': code2, 'groups': groups}


def _pstr(raw, pad):
    sz = _ssize(len(raw))
    if pad is None or len(pad) != sz - len(raw):
        pad = b'\0' * (sz - len(raw))
    return struct.pack('<I', len(raw)) + raw + pad


def build(e):
    out = bytearray(struct.pack('<I', len(e['msgs'])))
    for m in e['msgs']:
        out += struct.pack('<5I', *m['hdr'])
        out += _pstr(m['raw'], m.get('pad'))
    out += struct.pack('<I', len(e['code1']) // 4) + e['code1']
    out += struct.pack('<I', len(e['code2']) // 4) + e['code2']
    out += struct.pack('<I', len(e['groups']))
    for g in e['groups']:
        out += struct.pack('<I', len(g))
        for s in g:
            out += _pstr(s['raw'], s.get('pad'))
    return bytes(out)
