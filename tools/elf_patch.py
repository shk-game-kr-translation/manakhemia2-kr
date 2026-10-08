"""Write translated ELF strings (trans/elf/elf.json) into the ELF image.

Policy per entry with 'ko' (entries with 'skip' are left untouched):
  * encoded bytes fit the original slot (string length rounded up to its 8-byte alignment,
    capped by the zero run that follows) -> written in place, rest zero-filled.
  * otherwise -> appended to the free pool and every recorded reference is redirected:
      data ref : aligned u32 pointer rewritten
      code ref : lui/addiu pair rewritten, only when the lui is used by exactly this addiu and
                 the addiu writes the lui's register (so the high half has no other consumer)
    A reference that cannot be redirected is an error (the build fails in release mode).
Pool: [glyph end (aligned), hooks.HOOK_BASE) -- the freed tail of the original glyph area.
"""
import struct, collections
import paths
import textfmt

V = 0xFF000


def slot_size(e):
    """bytes usable in place, including the terminating NUL"""
    n = len(e['_orig'])  # original byte length without NUL
    al = (n + 1 + 7) & ~7
    return min(al, e['room'] + 1)


import json as _json, os as _os, math as _math, re as _re
_WRAP = None


def _cfg(name):
    global _WRAP
    if _WRAP is None:
        p = _os.path.join(paths.CONFIG, 'elf_wrap.json')
        d = _json.load(open(p, encoding='utf-8'))
        _WRAP = {k: [(int(a, 16), int(b, 16), n) for a, b, n, *_ in d.get(k, [])] for k in ('ranges', 'list_width', 'max_lines')}
    return _WRAP[name]


def _lookup(name, key):
    k = int(key, 16)
    for a, b, n in _cfg(name):
        if a <= k < b:
            return n
    return None


_PAT = None


def _pattern(key, ja):
    """(N, max_lines) from config 'patterns' for this string, or None"""
    global _PAT
    if _PAT is None:
        p = _os.path.join(paths.CONFIG, 'elf_wrap.json')
        _PAT = [(int(a, 16), int(b, 16), _re.compile(rx), n, l)
                for a, b, rx, n, l, *_ in _json.load(open(p, encoding='utf-8')).get('patterns', [])]
    if ja is None:
        return None
    k = int(key, 16)
    for a, b, rx, n, l in _PAT:
        if a <= k < b and rx.match(ja):
            return n, l
    return None


def wrap_cols(key, ja=None):
    """engine wrap column count of the window showing this string (None = unknown)"""
    p = _pattern(key, ja)
    return p[0] if p else _lookup('ranges', key)


def max_lines(key, ja=None):
    p = _pattern(key, ja)
    return p[1] if p else _lookup('max_lines', key)


def list_width(key):
    """max width allowed for an entry of a list window (None = unknown)"""
    return _lookup('list_width', key)


def layout(ja, ko, key=None):
    """Korean lines for an ELF string.
    Multi-line Japanese: re-wrapped to the widest Japanese line (explicit newlines in the
    translation are kept as paragraph breaks). Single-line Japanese wider than the window's
    engine column count N (config/elf_wrap.json): pre-wrapped at N cells.
    Returns (lines, allowed line count, width limit)."""
    jl = ja.split(chr(10))
    jw = max(textfmt.width(textfmt.text_to_units(l, korean=False)) for l in jl)
    units = textfmt.text_to_units(ko)
    n = wrap_cols(key, ja) if key else None
    if len(jl) > 1 and n:
        # window width known: wrap at it; Japanese lines longer than n were engine-wrapped too
        jn = sum(max(1, _math.ceil(textfmt.width(textfmt.text_to_units(l, korean=False)) / n)) for l in jl)
        return textfmt.wrap(units, n, n), max(jn, max_lines(key, ja) or 0), n
    if len(jl) > 1:
        return textfmt.wrap(units, jw, int(jw)), len(jl), jw
    if n and (jw > n or chr(10) in ko or textfmt.width(units) > n):
        return textfmt.wrap(units, n, n), max(_math.ceil(jw / n), max_lines(key, ja) or 0), n
    return textfmt.wrap(units, 10 ** 6), 1, jw


def encode(ja, ko, codec, key=None):
    lines, _, _ = layout(ja, ko, key)
    return textfmt.units_to_bytes(textfmt.join_lines(lines), codec)


def patch(elf, entries, codec, pool_lo, pool_hi, rep):
    # how many addiu use each lui (over all recorded code refs)
    lui_users = collections.Counter(r[2] for e in entries for r in e['refs'] if r[0] == 'code')
    pool = (pool_lo + 7) & ~7
    stats = collections.Counter()
    for e in entries:
        if e.get('skip') or not e.get('ko'):
            continue
        off = int(e['key'], 16)
        n0 = elf.index(b'\0', off) - off
        e['_orig'] = elf[off:off + n0]
        try:
            b = encode(e['ja'], e['ko'], codec, e['key'])
        except KeyError as ex:
            rep.err(f'elf:{e["key"]} {ex}')
            continue
        size = slot_size(e)
        if len(b) + 1 <= size:
            elf[off:off + size] = b + b'\0' * (size - len(b))
            stats['inplace'] += 1
            continue
        # relocate
        need = (len(b) + 1 + 7) & ~7
        if pool + need > pool_hi:
            rep.err(f'elf:{e["key"]} pool exhausted'); continue
        bad = []
        for k, a, l in e['refs']:
            if k == 'code':
                w = struct.unpack_from('<I', elf, a - V)[0]
                wl = struct.unpack_from('<I', elf, l - V)[0]
                rs, rt = (w >> 21) & 31, (w >> 16) & 31
                if lui_users[l] != 1 or ((wl >> 16) & 31) != rs or rt != rs:
                    bad.append(hex(a))
        if bad:
            rep.err(f'elf:{e["key"]} does not fit ({len(b)}>{size - 1}) and code refs {bad} not relocatable: {e["ko"]!r}')
            continue
        fo = pool  # pool is in file offsets
        elf[fo:fo + need] = b + b'\0' * (need - len(b))
        va = fo + V
        for k, a, l in e['refs']:
            if k == 'data':
                struct.pack_into('<I', elf, a - V, va)
            else:
                w = struct.unpack_from('<I', elf, a - V)[0]
                wl = struct.unpack_from('<I', elf, l - V)[0]
                lo = va & 0xffff
                hi = (va >> 16) + (1 if lo & 0x8000 and (w >> 26) != 0x0d else 0)
                struct.pack_into('<I', elf, l - V, (wl & 0xffff0000) | (hi & 0xffff))
                struct.pack_into('<I', elf, a - V, (w & 0xffff0000) | lo)
        # old slot: keep a NUL-terminated copy of as much as fits (for unrecorded readers)
        elf[off:off + size] = b'\0' * size
        pool += need
        stats['relocated'] += 1
    rep.stats['elf'] = dict(stats, pool_used=pool - pool_lo)
