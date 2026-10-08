"""fpack/*.fp: a sequence of LZR-compressed chunks, each starting on a 2048-byte boundary
(zero padding between). Chunks are typically TIM2 textures (sometimes PS1 TIM or other data).

  chunks(raw) -> [dict(off, slot, data)]   slot = bytes available up to the next chunk / file end
  rebuild(raw, {index: new_data}) -> bytes  re-compress replaced chunks in place (must fit the slot)
"""
import struct
import lzr


def chunks(raw):
    out = []
    p = 0
    while p < len(raw):
        if raw[p:p + 4] != b'LZR\0':
            p += 2048
            continue
        nbits, ndata, nout = struct.unpack_from('<3I', raw, p + 4)
        ln = 16 + (nbits + 7) // 8 + ndata
        out.append(dict(off=p, len=ln, data=lzr.decompress(raw[p:p + ln])))
        p = (p + ln + 2047) & ~2047
    for i, c in enumerate(out):
        nxt = out[i + 1]['off'] if i + 1 < len(out) else len(raw)
        c['slot'] = nxt - c['off']
    return out


def rebuild(raw, repl):
    """repl: {chunk index: decompressed bytes}. Raises ValueError if a chunk no longer fits."""
    raw = bytearray(raw)
    cs = chunks(bytes(raw))
    for i, data in repl.items():
        c = cs[i]
        comp = lzr.compress(data)
        if len(comp) > c['slot']:
            raise ValueError(f'chunk {i}: {len(comp)} > slot {c["slot"]}')
        raw[c['off']:c['off'] + c['slot']] = comp + b'\0' * (c['slot'] - len(comp))
    return bytes(raw)
