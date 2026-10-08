"""Write translated ERX strings (trans/erx/*.json) into an ERX module by repacking its string table.

QvDataE.erx: .rodata [0x300, 0xb670) holds only strings, reached solely through R_MIPS_32
relocated words in .data (0xb670.. is a constant used by .erx.lib and is kept). All strings
(translated or original, plus the empty string and any other referenced address) are laid out
again from the start of the region, 8-byte aligned, and every relocated .data word that points
into the region is rewritten. A pointer into the region whose target is unknown is an error.
Lines are laid out with elf_patch.layout (no window config: Japanese line widths/counts).
"""
import struct
import elf_patch, textfmt

REGION = {'erxs/QvDataE.erx': (0x300, 0xb670)}


def string_at(d, o):
    return bytes(d[o:d.index(b'\0', o)])


def is_news(ja):
    """school newspaper items: body + full-width space padding to cell 52 + attribution,
    i.e. a 13-column window with the body on lines 1-4 and the source on line 5"""
    return '　　' in ja and '\n' not in ja


def layout(e):
    """(lines, allowed line count, width limit)"""
    if is_news(e['ja']):
        return textfmt.wrap(textfmt.text_to_units(e['ko']), 13, 13), 5, 13
    return elf_patch.layout(e['ja'], e['ko'])


def encode(e, codec):
    lines, _, _ = layout(e)
    return textfmt.units_to_bytes(textfmt.join_lines(lines), codec)


def patch(mod, name, entries, codec, rep, align=8):
    """mod: erx.Erx (modified in place). Returns stats dict."""
    import erx_extract
    lo, hi = REGION[name]
    d = mod.d
    ro_off = erx_extract.va2off(mod, lo)
    by_key = {int(x['key'], 16): x for x in entries}
    # every relocated .data word pointing into the region
    words = []
    for tgt, r_off, ty, sy, reo in mod.relocs():
        if ty != 2:
            continue
        wo = erx_extract.va2off(mod, r_off)
        if wo is None:
            continue
        v = struct.unpack_from('<I', d, wo)[0]
        if lo <= v < hi:
            words.append((wo, v))
    targets = sorted(set(v for _, v in words))
    blobs = {}
    stats = dict(translated=0, original=0)
    for v in targets:
        x = by_key.get(v)
        if x is not None and x.get('ko') and not x.get('skip'):
            try:
                blobs[v] = encode(x, codec)
            except KeyError as ex:
                rep.err(f'erx:{name}:{x["key"]} {ex}')
                blobs[v] = string_at(d, erx_extract.va2off(mod, v))
            stats['translated'] += 1
        else:
            if x is None and d[erx_extract.va2off(mod, v)] != 0:
                rep.err(f'erx:{name}: pointer to unknown string {v:#x}')
            blobs[v] = string_at(d, erx_extract.va2off(mod, v))
            stats['original'] += 1
    # identical byte strings share one copy
    new_addr, placed = {}, {}
    pos = lo
    out = bytearray(hi - lo)
    for v in targets:
        b = blobs[v]
        if b in placed:
            new_addr[v] = placed[b]; continue
        if pos + len(b) + 1 > hi:
            rep.err(f'erx:{name}: string region full at {v:#x} ({pos - lo + len(b) + 1} > {hi - lo})')
            return stats
        out[pos - lo:pos - lo + len(b)] = b
        new_addr[v] = placed[b] = pos
        pos = (pos + len(b) + 1 + align - 1) & ~(align - 1)
    d[ro_off:ro_off + hi - lo] = out
    for wo, v in words:
        struct.pack_into('<I', d, wo, new_addr[v])
    stats.update(used=pos - lo, size=hi - lo, pointers=len(words))
    return stats
