"""Replace the video stream of a Sofdec .SFD file, keeping everything else in place.

The pack layout (2048-byte packs, SCRs), the audio (ADX) packets and the Sofdec header packets stay
byte-identical; only the payload of the video PES packets (stream E0) is refilled, in order, with a new
MPEG-1 video elementary stream. Each video packet's PTS/DTS is recomputed for the first picture that
starts in it (frame timing is taken from the original stream). Leftover capacity is filled with zero
bytes before the sequence end code (legal MPEG stuffing). The new stream must have the same frame
count and frame rate as the original.

  replace(orig_sfd_bytes, new_es_bytes) -> (new_sfd_bytes, report dict)
  CLI: sfd_video.py <orig.SFD> <new.m1v> <out.SFD>
"""
import sys, struct
import sfd

FRAME = 3003            # 90 kHz ticks per frame at 29.97 fps


def read_ts(b, p):
    return (((b[p] >> 1) & 7) << 30) | (b[p + 1] << 22) | ((b[p + 2] >> 1) << 15) | (b[p + 3] << 7) | (b[p + 4] >> 1)


def write_ts(prefix, t):
    return bytes([(prefix << 4) | (((t >> 30) & 7) << 1) | 1, (t >> 22) & 0xFF, (((t >> 15) & 0x7F) << 1) | 1,
                  (t >> 7) & 0xFF, ((t & 0x7F) << 1) | 1])


def pes_fields(d, p):
    """(std bytes, pts, dts) of the MPEG-1 PES header starting at packet offset p."""
    q = p + 6
    while d[q] == 0xFF:
        q += 1
    std = b''
    if d[q] & 0xC0 == 0x40:
        std = bytes(d[q:q + 2]); q += 2
    f = d[q] >> 4
    if f == 2:
        return std, read_ts(d, q), None
    if f == 3:
        return std, read_ts(d, q), read_ts(d, q + 5)
    return std, None, None


def pictures(es):
    """[(offset, decode index, temporal_reference, type)] of picture start codes, GOP sizes in frames"""
    pics = []
    gops = []
    p = es.find(b'\x00\x00\x01')
    k = 0
    while p >= 0:
        c = es[p + 3]
        if c == 0xB8:
            gops.append(k)
        elif c == 0x00:
            tr = (es[p + 4] << 2) | (es[p + 5] >> 6)
            ty = (es[p + 5] >> 3) & 7
            pics.append((p, k, tr, ty)); k += 1
        p = es.find(b'\x00\x00\x01', p + 4)
    return pics, gops


def timing(pics, gops):
    """display index of each picture (decode order): frames before its GOP + temporal_reference"""
    disp = []
    gi = 0
    for (_, k, tr, _) in pics:
        while gi + 1 < len(gops) and gops[gi + 1] <= k:
            gi += 1
        disp.append(gops[gi] + tr)
    return disp


def payload_ratio(ps, orig):
    """original payload bytes / packet capacity without timestamps (new headers are a bit smaller)"""
    return 1.0


def align_gops(es, npics, ngops, opics, _ratio):
    """Insert zero stuffing before each GOP (and its sequence header) so that the GOP starting at
    decode index k begins no earlier than the original picture k did: the new data then reaches the
    player at the same pace as the original (no read-ahead build-up, no trailing gap)."""
    starts = []
    for k in ngops:
        p = npics[k][0]
        g = es.rfind(b'\x00\x00\x01\xb8', 0, p)
        s = es.rfind(b'\x00\x00\x01\xb3', 0, g)
        if s >= 0 and g - s < 200:       # sequence header right before the GOP header
            g = s
        starts.append((g, opics[k][0] - (p - g)))
    out = bytearray()
    prev = 0
    for g, target in starts:
        out += es[prev:g]
        if len(out) < target:
            out += b'\x00' * (target - len(out))
        prev = g
    out += es[prev:]
    return bytes(out)


def replace(orig, es, align=True):
    ps = [x for x in sfd.packets(orig) if x['sid'] == 0xE0]
    # timing reference from the original: PTS of display frame 0, DTS of decode frame 0
    ovid = b''.join(orig[x['data_off']:x['data_off'] + x['data_len']] for x in ps)
    opics, ogops = pictures(ovid)
    odisp = timing(opics, ogops)
    pts0 = dts0 = None
    pi = 0
    pos = 0
    for x in ps:
        std, pts, dts = pes_fields(orig, x['off'])
        while pi + 1 < len(opics) and opics[pi + 1][0] < pos:
            pi += 1
        if pts is not None and pts0 is None:
            # first picture starting in this packet
            j = next(i for i, pc in enumerate(opics) if pc[0] >= pos)
            pts0 = pts - odisp[j] * FRAME
            dts0 = (dts if dts is not None else pts) - j * FRAME
        pos += x['data_len']
    npics, ngops = pictures(es)
    if len(npics) != len(opics):
        raise ValueError('frame count %d != original %d' % (len(npics), len(opics)))
    if align:
        es = align_gops(es, npics, ngops, opics, payload_ratio(ps, orig))
        npics, ngops = pictures(es)
    ndisp = timing(npics, ngops)
    # strip a trailing sequence end code; it is re-added after the stuffing
    if es.endswith(b'\x00\x00\x01\xb7'):
        es = es[:-4]
    out = bytearray(orig)
    src = 0
    pic_i = 0
    spans = []
    padded = 0
    for n, x in enumerate(ps):
        std, _, _ = pes_fields(orig, x['off'])
        total = x['plen']                                  # bytes after the 6-byte start+length
        # which picture starts first in the payload we are about to place? (header size depends on it)
        def first_pic(cap):
            j = pic_i
            while j < len(npics) and npics[j][0] < src:
                j += 1
            return j if j < len(npics) and npics[j][0] < src + cap else None
        hdr_none = len(std) + 1
        j = first_pic(total - hdr_none)
        if j is not None:
            pts = pts0 + ndisp[j] * FRAME
            dts = dts0 + j * FRAME
            ts = write_ts(3, pts) + write_ts(1, dts) if dts != pts else write_ts(2, pts)
            cap = total - len(std) - len(ts)
            if first_pic(cap) != j:          # the picture moved out of the smaller payload
                j = first_pic(cap)
                if j is None:
                    ts = b'\x0f'; cap = total - hdr_none
                else:
                    pts = pts0 + ndisp[j] * FRAME; dts = dts0 + j * FRAME
                    ts = write_ts(3, pts) + write_ts(1, dts) if dts != pts else write_ts(2, pts)
                    cap = total - len(std) - len(ts)
        else:
            ts = b'\x0f'; cap = total - hdr_none
        chunk = es[src:src + cap]
        last = n == len(ps) - 1
        if last:
            chunk = chunk + b'\x00' * (cap - 4 - len(chunk)) + b'\x00\x00\x01\xb7'
        elif len(chunk) < cap:
            chunk = chunk + b'\x00' * (cap - len(chunk))
        body = std + ts + chunk
        assert len(body) == total
        if not last and ts == b'\x0f' and not any(chunk):
            # nothing but stuffing: make it a padding packet (stream BE, 0xFF fill) so the player never
            # sees the zeros; long zero runs inside the video stream hung the PS2 player (ABAN02)
            out[x['off'] + 3] = 0xBE
            body = b'\xff' * total
            padded += 1
        out[x['off'] + 6:x['off'] + 6 + total] = body
        spans.append((src, src + cap, pack_scr(orig, x['pack'])))
        while pic_i < len(npics) and npics[pic_i][0] < src + cap:
            pic_i += 1
        src += cap
    if src < len(es):
        raise ValueError('new video is %d bytes too large for the original packets' % (len(es) - src))
    # arrival check against the original: SCR of the pack that completes each picture, new vs original.
    # (Sofdec reads far ahead, so SCR is no hard deadline; a picture should just not arrive much later
    # than it did in the original stream.)
    ospans = []
    o = 0
    for x in ps:
        ospans.append((o, o + x['data_len'], pack_scr(orig, x['pack']))); o += x['data_len']
    a_new = arrival(spans, npics, len(es))
    a_old = arrival(ospans, opics, len(ovid))
    delay = [(a - b) / 90000.0 for a, b in zip(a_new, a_old)]
    worst = max(range(len(delay)), key=delay.__getitem__)
    rep = dict(capacity=src, used=len(es), spare=src - len(es), frames=len(npics),
               max_delay_vs_orig_s=round(delay[worst], 3), worst_frame=worst, padding_packets=padded)
    return bytes(out), rep


def arrival(spans, pics, n):
    """SCR of the packet holding the last byte of each picture"""
    ends = [pics[i + 1][0] for i in range(len(pics) - 1)] + [n]
    out = []
    si = 0
    for e in ends:
        while spans[si][1] < e:
            si += 1
        out.append(spans[si][2])
    return out


def pack_scr(d, p):
    b = d[p + 4:p + 9]
    return (((b[0] >> 1) & 7) << 30) | (b[1] << 22) | ((b[2] >> 1) << 15) | (b[3] << 7) | (b[4] >> 1)


def main():
    orig = open(sys.argv[1], 'rb').read()
    es = open(sys.argv[2], 'rb').read()
    out, rep = replace(orig, es)
    open(sys.argv[3], 'wb').write(out)
    print(rep)


if __name__ == '__main__':
    main()
