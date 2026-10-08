"""Code hooks for the Korean patch (ELF, fixed revision SLPM_550.05 v1.01).

Half-width units: the space pair b'  ' (0x20 0x20, undrawn) and narrow glyphs with lead byte 0xEB. The engine already
treats a 2-byte unit whose first byte is 0x20 as an undrawn space. Hooks make it
 (a) advance half the glyph width and (b) not count toward the per-line column
limit, in the renderer, the layout/measure pass and the line counter, so that box
sizes and wraps stay consistent.
"""
import struct
from mips import assemble

V = 0xFF000
HOOK_BASE = 0x9cc3f8          # inside the (freed) glyph area tail; font must end before this
HOOK_END = 0x9cc5f8

# (site va, expected original word, hook label)
SITES = [
    (0x1357a0, None, 'h_rcount'),   # lw t7,0x34(s0)        renderer column count
    (0x135844, None, 'h_radv'),     # addiu t4,zero,0x64    renderer advance (delay: lhu t5,0x16(s2))
    (0x136234, None, 'h_lcount'),   # lw t7,0x34(sp)        layout column count
    (0x136270, None, 'h_ladv'),     # lhu t6,0x16(s0)       layout advance A
    (0x13636c, None, 'h_ladv'),     # lhu t6,0x16(s0)       layout advance B
    (0x1360c0, None, 'h_ncount'),   # lhu t7,0x1e(s4)       line counter
]
ORIG = {
    0x1357a0: 'lw t7, 0x34(s0)',
    0x135844: 'addiu t4, zero, 0x64',
    0x136234: 'lw t7, 0x34(sp)',
    0x136270: 'lhu t6, 0x16(s0)',
    0x13636c: 'lhu t6, 0x16(s0)',
    0x1360c0: 'lhu t7, 0x1e(s4)',
}

HOOK_ASM = """
h_rcount:
    lw t7, 0x34(s0)
    lw t3, 0x24(s0)
    lbu t3, 0(t3)
    addiu t4, zero, 0x20
    beq t3, t4, H1
    addiu t4, zero, 0xeb
    bne t3, t4, L1
    nop
H1: addiu t7, t7, -1
L1: jr ra
    nop
h_radv:
    addiu t4, zero, 0x64
    lw t3, 0x24(s0)
    lbu t3, 0(t3)
    addiu t7, zero, 0x20
    beq t3, t7, H2
    addiu t7, zero, 0xeb
    bne t3, t7, L2
    nop
H2: srl t5, t5, 1
L2: jr ra
    nop
h_lcount:
    lw t7, 0x34(sp)
    lw t3, 0x24(sp)
    lbu t3, 0(t3)
    addiu t4, zero, 0x20
    beq t3, t4, H3
    addiu t4, zero, 0xeb
    bne t3, t4, L3
    nop
H3: addiu t7, t7, -1
L3: jr ra
    nop
h_ladv:
    lw t7, 0x24(sp)
    lbu t7, 0(t7)
    addiu t6, t7, -0x20
    beqz t6, H4
    addiu t6, t7, -0xeb
    bnez t6, L4
    nop
H4: lhu t6, 0x16(s0)
    srl t6, t6, 1
    jr ra
    addiu t7, zero, 0x64
L4: lhu t6, 0x16(s0)
    jr ra
    addiu t7, zero, 0x64
h_ncount:
    lhu t7, 0x1e(s4)
    lbu t6, 0(s2)
    addiu t6, t6, -0x20
    beqz t6, H5
    lbu t6, 0(s2)
    addiu t6, t6, -0xeb
    bnez t6, L5
    nop
H5: addiu s1, s1, -1
L5: jr ra
    nop
"""

def apply(elf):
    code, lab = assemble(HOOK_ASM, HOOK_BASE)
    assert HOOK_BASE + len(code) <= HOOK_END
    elf[HOOK_BASE - V:HOOK_BASE - V + len(code)] = code
    for va, _, name in SITES:
        orig, _ = assemble(ORIG[va], va)
        cur = bytes(elf[va - V:va - V + 4])
        assert cur == orig, (hex(va), cur.hex(), orig.hex())
        j, _ = assemble('jal 0x%x' % lab[name], va)
        elf[va - V:va - V + 4] = j
    return lab
