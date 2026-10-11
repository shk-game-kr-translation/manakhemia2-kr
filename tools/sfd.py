"""CRI Sofdec (.SFD) = MPEG-1 program stream: packs (0x000001BA) holding PES packets
(0xE0 video MPEG-1, 0xC0 ADX audio, 0xBF private/Sofdec header, 0xBE padding).

  packets(d)         -> [dict(off, pack, sid, hdr, plen, data_off, data_len)]
  summary(path)      CLI: pack layout and per-stream byte totals
"""
import sys, struct, collections

PACK = b'\x00\x00\x01\xba'


def _pes_hdr_len(d, p):
    """MPEG-1 PES header length after the 6-byte start/len (stuffing, STD buffer, PTS/DTS)."""
    q = p
    while d[q] == 0xFF:
        q += 1
    if d[q] & 0xC0 == 0x40:
        q += 2
    f = d[q] >> 4
    if f == 2:
        q += 5
    elif f == 3:
        q += 10
    else:
        q += 1
    return q - p


def packets(d):
    out = []
    p = 0
    pack = -1
    n = len(d)
    while p + 4 <= n:
        if d[p:p + 3] != b'\x00\x00\x01':
            if not any(d[p:]):     # zero fill up to the sector end
                break
            raise ValueError('lost sync at %#x' % p)
        sid = d[p + 3]
        if sid == 0xBA:            # MPEG-1 pack header: 12 bytes
            pack = p
            p += 12 if (d[p + 4] & 0xF0) == 0x20 else 14 + (d[p + 13] & 7)
            continue
        if sid == 0xB9:            # end code
            out.append(dict(off=p, pack=pack, sid=sid, hdr=4, plen=0, data_off=p + 4, data_len=0))
            break                  # rest of the file is 0xFF fill
        plen = struct.unpack_from('>H', d, p + 4)[0]
        if sid in (0xBB, 0xBE, 0xBF):
            h = 0
        else:
            h = _pes_hdr_len(d, p + 6)
        out.append(dict(off=p, pack=pack, sid=sid, hdr=6 + h, plen=plen, data_off=p + 6 + h, data_len=plen - h))
        p += 6 + plen
    return out


def summary(path):
    d = open(path, 'rb').read()
    ps = packets(d)
    tot = collections.Counter(); cnt = collections.Counter()
    packs = sorted({x['pack'] for x in ps})
    sizes = collections.Counter(b - a for a, b in zip(packs, packs[1:]))
    for x in ps:
        tot[x['sid']] += x['data_len']; cnt[x['sid']] += 1
    print(path, len(d), 'bytes, packs', len(packs), 'pack spacing', sizes.most_common(4))
    for s in sorted(tot):
        print('  stream %02X: %6d packets, %10d payload bytes' % (s, cnt[s], tot[s]))
    print('  first packets:', [(hex(x['off']), '%02X' % x['sid'], x['plen']) for x in ps[:8]])


if __name__ == '__main__':
    summary(sys.argv[1])
