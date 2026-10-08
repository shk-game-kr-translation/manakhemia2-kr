"""Apply the unified font to an ELF image (bytearray) — used by the product build."""
import struct
from font_build import V, LIST0, LIST1, GLY0, GLY1, TOTAL, GB, GLY_END

FONT_LIST_PTRS = 0x7dc7c0   # u32[2]: list per font id
FONT_GLY_PTRS = 0x7dc7e8    # u32[2]: glyphs per font id


def patch(elf, list_bytes, glyph_bytes):
    n = len(list_bytes) // 2
    assert len(glyph_bytes) == n * GB and n <= TOTAL
    # verify expected original pointers
    assert struct.unpack_from('<2I', elf, FONT_LIST_PTRS - V) == (LIST0, LIST1), 'list ptrs'
    assert struct.unpack_from('<2I', elf, FONT_GLY_PTRS - V) == (GLY0, GLY1), 'glyph ptrs'
    region = bytearray(GLY0 - LIST0)
    region[:len(list_bytes)] = list_bytes
    elf[LIST0 - V:GLY0 - V] = region
    gl = bytearray(GLY_END - GLY0)
    gl[:len(glyph_bytes)] = glyph_bytes
    elf[GLY0 - V:GLY_END - V] = gl
    struct.pack_into('<2I', elf, FONT_LIST_PTRS - V, LIST0, LIST0)
    struct.pack_into('<2I', elf, FONT_GLY_PTRS - V, GLY0, GLY0)
