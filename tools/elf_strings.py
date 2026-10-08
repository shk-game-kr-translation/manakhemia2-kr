"""Inventory of Japanese text strings in the ELF and their references.

Candidates: NUL-terminated byte strings (previous byte NUL) in the data area whose content is
valid game text (SJIS pairs + ASCII controls) and contains Japanese.
References:
  data: aligned u32 == string va (anywhere in the ELF image)
  code: lui rX,hi ; ... addiu/ori rY,rX,lo  (register-tracked within a basic window)
"""
import struct, re, json, sys, os
V = 0xFF000
CODE_END = 0x597000          # file offset where code ends (tables start at 0x597f10)
DATA_START = 0x597000


def is_text(b):
    try:
        t = b.decode('cp932')
    except UnicodeDecodeError:
        return False
    jp = sum(1 for c in t if ord(c) >= 0x3000)
    if jp == 0:
        return False
    # reject binary-ish: control chars
    if any(ord(c) < 0x20 for c in t):
        return False
    # need mostly kana/kanji/fullwidth
    return True


def find_strings(d, lo=DATA_START, hi=None):
    hi = hi or len(d)
    out = []
    i = lo
    while i < hi:
        if d[i] == 0 or d[i - 1] != 0:
            i += 1; continue
        e = d.find(b'\0', i, hi)
        if e < 0:
            break
        b = d[i:e]
        if len(b) >= 2 and is_text(b):
            out.append((i, b))
        i = e + 1
    return out


def code_refs(d, targets):
    """targets: set of va. returns {va: [(kind, insn_va, lui_va)]}"""
    refs = {}
    last_lui = {}   # reg -> (value_hi, va)
    for off in range(0x1000, CODE_END, 4):
        w = struct.unpack_from('<I', d, off)[0]
        op = w >> 26
        va = off + V
        if op == 0x0f:
            rt = (w >> 16) & 31
            last_lui[rt] = ((w & 0xffff) << 16, va)
            continue
        if op in (0x09, 0x0d, 0x19):  # addiu, ori, daddiu
            rs = (w >> 21) & 31; rt = (w >> 16) & 31
            imm = w & 0xffff
            if rs in last_lui:
                hiv, lva = last_lui[rs]
                if va - lva <= 0x200:
                    a = (hiv + (imm - 0x10000 if (imm & 0x8000 and op != 0x0d) else imm)) & 0xffffffff
                    if a in targets:
                        refs.setdefault(a, []).append(('code', va, lva))
        # loads/stores with lui base (e.g. lw rX, lo(rHi)) are not string refs; ignore
        if op in (0x02, 0x03) or (op == 0 and (w & 0x3f) in (0x08, 0x09)):
            pass
    return refs


def data_refs(d, targets):
    refs = {}
    for off in range(0, len(d) - 3, 4):
        v = struct.unpack_from('<I', d, off)[0]
        if v in targets:
            refs.setdefault(v, []).append(('data', off + V, None))
    return refs


def inventory(elf_path):
    d = open(elf_path, 'rb').read()
    ss = find_strings(d)
    targets = {o + V for o, _ in ss}
    cr = code_refs(d, targets)
    dr = data_refs(d, targets)
    inv = []
    for o, b in ss:
        va = o + V
        r = cr.get(va, []) + dr.get(va, [])
        inv.append({'off': o, 'va': va, 'len': len(b), 'text': b.decode('cp932'),
                    'refs': [[k, a, l] for k, a, l in r]})
    return inv


if __name__ == '__main__':
    inv = inventory(sys.argv[1])
    json.dump(inv, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False)
    n = len(inv); nref = sum(1 for x in inv if x['refs'])
    nd = sum(1 for x in inv if any(r[0] == 'data' for r in x['refs']))
    nc = sum(1 for x in inv if any(r[0] == 'code' for r in x['refs']))
    print('strings', n, 'with refs', nref, 'data', nd, 'code', nc,
          'chars', sum(len(x['text']) for x in inv), 'unref chars', sum(len(x['text']) for x in inv if not x['refs']))
