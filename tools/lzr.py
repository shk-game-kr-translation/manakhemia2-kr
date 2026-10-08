"""LZR codec (Mana Khemia 2, decoder at ELF 0x103c4c).

Header: 'LZR\\0', u32 nbits (2 bits per token), u32 data_len, u32 out_len.
Then ceil(nbits/8) flag bytes (2-bit codes, MSB pair first), then data stream.
Codes: 0 = 1 literal byte; 1 = n, then n literal bytes; 2 = n, b -> b repeated n;
       3 = b0 b1 -> copy (b1 & 15) bytes from out[-((b0 << 4) | (b1 >> 4))].
"""
import struct, sys


def decompress(src):
    if src[:4] != b'LZR\0':
        raise ValueError('not LZR')
    nbits, ndata, nout = struct.unpack_from('<3I', src, 4)
    fp = 16
    dp = 16 + (nbits + 7) // 8
    out = bytearray()
    ntok = nbits // 2
    for t in range(ntok):
        code = (src[fp + t // 4] >> (6 - 2 * (t % 4))) & 3
        if code == 0:
            out.append(src[dp]); dp += 1
        elif code == 1:
            n = src[dp]; out += src[dp + 1:dp + 1 + n]; dp += 1 + n
        elif code == 2:
            n, b = src[dp], src[dp + 1]; out += bytes([b]) * n; dp += 2
        else:
            b0, b1 = src[dp], src[dp + 1]; dp += 2
            dist = (b0 << 4) | (b1 >> 4); n = b1 & 15
            s = len(out) - dist
            for i in range(n):
                out.append(out[s + i])
    if len(out) != nout:
        raise ValueError(f'size mismatch {len(out)} != {nout}')
    return bytes(out)


def compress(data):
    n = len(data)
    codes = []
    stream = bytearray()
    lit = bytearray()
    # hash chains of 3-byte prefixes for LZ search
    head = {}
    prev = [-1] * n

    def flush_lit():
        nonlocal lit
        while lit:
            chunk = lit[:255]; lit = lit[255:]
            if len(chunk) == 1:
                codes.append(0); stream.append(chunk[0])
            else:
                codes.append(1); stream.append(len(chunk)); stream.extend(chunk)

    def insert(i):
        if i + 3 <= n:
            k = data[i:i + 3]
            prev[i] = head.get(k, -1)
            head[k] = i

    i = 0
    while i < n:
        # RLE
        r = 1
        while i + r < n and r < 255 and data[i + r] == data[i]:
            r += 1
        # LZ
        bl, bd = 0, 0
        if i + 3 <= n:
            j = head.get(data[i:i + 3], -1)
            tries = 0
            while j >= 0 and i - j <= 4095 and tries < 256:
                l = 0
                while l < 15 and i + l < n and data[j + l] == data[i + l]:
                    l += 1
                if l > bl:
                    bl, bd = l, i - j
                    if l == 15: break
                j = prev[j]; tries += 1
        if r >= 3 and r >= bl:
            flush_lit(); codes.append(2); stream += bytes([r, data[i]])
            adv = r
        elif bl >= 3:
            flush_lit(); codes.append(3); stream += bytes([bd >> 4, ((bd & 15) << 4) | bl])
            adv = bl
        else:
            lit.append(data[i]); adv = 1
        for k in range(adv):
            insert(i + k)
        i += adv
    flush_lit()
    flags = bytearray((len(codes) + 3) // 4)
    for t, c in enumerate(codes):
        flags[t // 4] |= c << (6 - 2 * (t % 4))
    hdr = b'LZR\0' + struct.pack('<3I', 2 * len(codes), len(stream), n)
    return hdr + bytes(flags) + bytes(stream)


if __name__ == '__main__':
    mode, a, b = sys.argv[1:4]
    src = open(a, 'rb').read()
    open(b, 'wb').write(decompress(src) if mode == 'd' else compress(src))
