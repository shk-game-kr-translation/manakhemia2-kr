"""RPK.BIN archive: file table lives in the ELF (u32 name_ptr, u32 sector_offset, u32 size)."""
import struct

V = 0xFF000
TABLE = 0x597f10 + V      # va of first entry (file offset 0x597f10)
COUNT = 4596              # top-level entries covering RPK.BIN
SEC = 2048


def read_table(elf):
    ents = []
    for i in range(COUNT):
        np_, off, size = struct.unpack_from('<3I', elf, TABLE - V + 12 * i)
        o = np_ - V
        name = bytes(elf[o:elf.index(b'\0', o)]).decode('ascii')
        ents.append([name, off, size])
    return ents


def rebuild(elf, rpk, changed):
    """Append changed files to the end of RPK; update the ELF table in place.
    changed: {name: bytes}. Returns new RPK bytes."""
    ents = read_table(elf)
    names = {e[0]: i for i, e in enumerate(ents)}
    out = bytearray(rpk)
    assert len(out) % SEC == 0
    for name, data in sorted(changed.items()):
        i = names[name]
        off = len(out) // SEC
        out += data + b'\0' * ((-len(data)) % SEC)
        struct.pack_into('<II', elf, TABLE - V + 12 * i + 4, off, len(data))
    return bytes(out)
