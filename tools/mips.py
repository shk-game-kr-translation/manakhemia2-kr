"""Minimal deterministic MIPS (R5900 subset) assembler: no delay-slot reordering, no macros.

Syntax: one instruction per line, 'label:' lines, '#' comments.
Supported: lw lbu lhu lb lh sw sb sh addiu ori andi xori sll srl sra addu subu or and
           beq bne bnez beqz j jal jr nop lui slt sltu slti .word
"""
import re, struct

REG = {n: i for i, n in enumerate(
    ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3', 't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
     's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra'])}
MEM = {'lb': 0x20, 'lh': 0x21, 'lw': 0x23, 'lbu': 0x24, 'lhu': 0x25, 'sb': 0x28, 'sh': 0x29, 'sw': 0x2b}
IMM = {'addiu': 0x09, 'slti': 0x0a, 'sltiu': 0x0b, 'andi': 0x0c, 'ori': 0x0d, 'xori': 0x0e}
RRR = {'addu': 0x21, 'subu': 0x23, 'and': 0x24, 'or': 0x25, 'slt': 0x2a, 'sltu': 0x2b, 'daddu': 0x2d}
SH = {'sll': 0x00, 'srl': 0x02, 'sra': 0x03}


def r(x):
    return REG[x.strip().lstrip('$')]


def num(x, labels=None):
    x = x.strip()
    if labels is not None and x in labels:
        return labels[x]
    return int(x, 0)


def assemble(src, base):
    lines = []
    for raw in src.splitlines():
        s = raw.split('#')[0].strip()
        if s:
            lines.append(s)
    labels = {}
    addr = base
    insns = []
    for s in lines:
        m = re.match(r'^([A-Za-z_.][\w.]*):\s*(.*)$', s)
        if m:
            labels[m.group(1)] = addr
            s = m.group(2)
            if not s:
                continue
        insns.append((addr, s)); addr += 4
    out = bytearray()
    for a, s in insns:
        op, _, args = s.partition(' ')
        A = [x.strip() for x in args.split(',')] if args.strip() else []
        if op == 'nop':
            w = 0
        elif op == '.word':
            w = num(A[0], labels) & 0xffffffff
        elif op in MEM:
            m = re.match(r'^(.*)\((\$?\w+)\)$', A[1])
            off = num(m.group(1) or '0')
            w = (MEM[op] << 26) | (r(m.group(2)) << 21) | (r(A[0]) << 16) | (off & 0xffff)
        elif op in IMM:
            w = (IMM[op] << 26) | (r(A[1]) << 21) | (r(A[0]) << 16) | (num(A[2], labels) & 0xffff)
        elif op == 'lui':
            w = (0x0f << 26) | (r(A[0]) << 16) | (num(A[1], labels) & 0xffff)
        elif op in RRR:
            w = (r(A[1]) << 21) | (r(A[2]) << 16) | (r(A[0]) << 11) | RRR[op]
        elif op in SH:
            w = (r(A[1]) << 16) | (r(A[0]) << 11) | ((num(A[2]) & 31) << 6) | SH[op]
        elif op in ('beq', 'bne', 'beqz', 'bnez'):
            if op in ('beqz', 'bnez'):
                rs, rt, tgt = r(A[0]), 0, num(A[1], labels)
                code = 4 if op == 'beqz' else 5
            else:
                rs, rt, tgt = r(A[0]), r(A[1]), num(A[2], labels)
                code = 4 if op == 'beq' else 5
            off = (tgt - (a + 4)) >> 2
            assert -0x8000 <= off < 0x8000
            w = (code << 26) | (rs << 21) | (rt << 16) | (off & 0xffff)
        elif op in ('j', 'jal'):
            tgt = num(A[0], labels)
            assert (tgt & 0xf0000000) == ((a + 4) & 0xf0000000)
            w = ((2 if op == 'j' else 3) << 26) | ((tgt >> 2) & 0x3ffffff)
        elif op == 'jr':
            w = (r(A[0]) << 21) | 0x08
        else:
            raise ValueError('unsupported: ' + s)
        out += struct.pack('<I', w)
    return bytes(out), labels
