"""Disassemble the game ELF. usage: elfdis.py ELF find-imm <hex> | dis <vaddr> <count> | xref <vaddr>"""
import sys, struct
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
ELF = sys.argv[1]
d = open(ELF, 'rb').read()
V = 0xFF000
TEXT_END = 0x597000  # rough; code before data tables
md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)
md.skipdata = True

R = ['zero','at','v0','v1','a0','a1','a2','a3','t0','t1','t2','t3','t4','t5','t6','t7',
     's0','s1','s2','s3','s4','s5','s6','s7','t8','t9','k0','k1','gp','sp','fp','ra']
def ee(w):
    op = w >> 26; rs = (w >> 21) & 31; rt = (w >> 16) & 31; rd = (w >> 11) & 31; imm = w & 0xffff
    simm = imm - 0x10000 if imm & 0x8000 else imm
    if op == 0x3f: return 'sd', f'${R[rt]}, {simm:#x}(${R[rs]})'
    if op == 0x37: return 'ld', f'${R[rt]}, {simm:#x}(${R[rs]})'
    if op == 0x1f: return 'sq', f'${R[rt]}, {simm:#x}(${R[rs]})'
    if op == 0x1e: return 'lq', f'${R[rt]}, {simm:#x}(${R[rs]})'
    if op == 0 and (w & 0x3f) == 0x2d: return 'daddu', f'${R[rd]}, ${R[rs]}, ${R[rt]}'
    if op == 0 and (w & 0x3f) == 0x2f: return 'dsubu', f'${R[rd]}, ${R[rs]}, ${R[rt]}'
    if op == 0 and (w & 0x3f) == 0x14: return 'dsllv', f'${R[rd]}, ${R[rt]}, ${R[rs]}'
    if op == 0 and (w & 0x3f) == 0x38: return 'dsll', f'${R[rd]}, ${R[rt]}, {(w>>6)&31}'
    if op == 0 and (w & 0x3f) == 0x3c: return 'dsll32', f'${R[rd]}, ${R[rt]}, {(w>>6)&31}'
    if op == 0 and (w & 0x3f) == 0x3a: return 'dsrl', f'${R[rd]}, ${R[rt]}, {(w>>6)&31}'
    if op == 0 and (w & 0x3f) == 0x3e: return 'dsrl32', f'${R[rd]}, ${R[rt]}, {(w>>6)&31}'
    if op == 0 and (w & 0x3f) == 0x3f: return 'dsra32', f'${R[rd]}, ${R[rt]}, {(w>>6)&31}'
    if op == 0x19: return 'daddiu', f'${R[rt]}, ${R[rs]}, {simm:#x}'
    return None
def dis(va, n):
    off = va - V
    for k in range(n):
        a = va + 4 * k; w = struct.unpack_from('<I', d, off + 4 * k)[0]
        r = ee(w)
        if r is None:
            ins = list(md.disasm(d[off + 4 * k:off + 4 * k + 4], a))
            r = (ins[0].mnemonic, ins[0].op_str) if ins else ('.word', hex(w))
        print(f'{a:08x}: {r[0]:8s} {r[1]}')

cmd = sys.argv[2]
if cmd == 'dis':
    dis(int(sys.argv[3], 16), int(sys.argv[4]))
elif cmd == 'find-imm':
    imm = int(sys.argv[3], 16)
    for off in range(0x1000, TEXT_END, 4):
        w = struct.unpack_from('<I', d, off)[0]
        if (w & 0xffff) == imm and (w >> 26) in (0x0d, 0x0f, 0x09, 0x08, 0x0a, 0x0b, 0x0c, 0x04, 0x05):
            print(hex(off + V), hex(w))
elif cmd == 'xref':
    # find lui/addiu pairs building an address
    tgt = int(sys.argv[3], 16)
    hi = (tgt + 0x8000) >> 16; lo = tgt & 0xffff
    for off in range(0x1000, TEXT_END, 4):
        w = struct.unpack_from('<I', d, off)[0]
        if (w >> 26) in (0x09, 0x0d, 0x23, 0x2b, 0x21, 0x25, 0x20, 0x24, 0x28, 0x29) and (w & 0xffff) == lo:
            # look back for lui with hi
            for k in range(1, 12):
                w2 = struct.unpack_from('<I', d, off - 4 * k)[0]
                if (w2 >> 26) == 0x0f and (w2 & 0xffff) == (hi if (w >> 26) != 0x0d else tgt >> 16):
                    print(hex(off + V)); break
elif cmd == 'jal':
    tgt = int(sys.argv[3], 16)
    w0 = (3 << 26) | ((tgt >> 2) & 0x3ffffff)
    for off in range(0x1000, TEXT_END, 4):
        if struct.unpack_from('<I', d, off)[0] == w0: print(hex(off + V))
