"""ISO rebuild for Mana Khemia 2 (ISO9660 + UDF 1.02 bridge).

build(src_iso, out_iso, replace_inplace={iso_path: bytes}, relocate={iso_path: bytes})
 - in-place replacements must keep the original size (checked).
 - relocated files are appended at the end of the image; ISO9660 directory record,
   UDF File Entry, PVD volume size, UDF partition length, LVID size and the trailing
   AVDP are updated. Original data stays untouched (unreferenced).
"""
import os, shutil, struct
import pycdlib

SEC = 2048


def crc_itu(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xffff
    return crc


def fix_tag(buf):
    """Recompute UDF descriptor tag CRC and checksum in a sector buffer (bytearray)."""
    crclen = struct.unpack_from('<H', buf, 10)[0]
    struct.pack_into('<H', buf, 8, crc_itu(bytes(buf[16:16 + crclen])))
    s = sum(buf[0:4]) + sum(buf[5:16])
    buf[4] = s & 0xff


def check_tag(buf):
    crclen = struct.unpack_from('<H', buf, 10)[0]
    ok_crc = struct.unpack_from('<H', buf, 8)[0] == crc_itu(bytes(buf[16:16 + crclen]))
    ok_sum = buf[4] == (sum(buf[0:4]) + sum(buf[5:16])) & 0xff
    return ok_crc and ok_sum


class Iso:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'r+b')

    def read(self, lba, n=1):
        self.f.seek(lba * SEC); return bytearray(self.f.read(n * SEC))

    def write(self, lba, data):
        self.f.seek(lba * SEC); self.f.write(data)

    def close(self):
        self.f.close()


def locate(src_iso):
    """Return {iso9660_path: (lba, size, dirrec_lba, dirrec_offset)} for all files."""
    iso = pycdlib.PyCdlib(); iso.open(src_iso)
    out = {}
    for path, dirs, files in iso.walk(iso_path='/'):
        for fn in files:
            p = path.rstrip('/') + '/' + fn
            rec = iso.get_record(iso_path=p)
            out[p] = rec
    res = {}
    for p, rec in out.items():
        # directory record location: parent extent + offset
        parent = rec.parent
        lba = parent.extent_location()
        res[p] = (rec.extent_location(), rec.get_data_length(), lba, p.split('/')[-1])
    iso.close()
    return res


def find_dirrec(img, dir_lba, name):
    name_b = name.encode('ascii')
    for k in range(8):
        sec = img.read(dir_lba + k)
        o = 0
        while o < SEC:
            ln = sec[o]
            if ln == 0:
                break
            nl = sec[o + 32]
            if sec[o + 33:o + 33 + nl] == name_b:
                return dir_lba + k, o
            o += ln
    raise KeyError(name)


def find_udf_fe(img, file_lba, part_start, search=(271, 2000)):
    rel = file_lba - part_start
    for n in range(*search):
        b = img.read(n)
        if struct.unpack_from('<H', b, 0)[0] != 261:
            continue
        l_ea, l_ad = struct.unpack_from('<II', b, 168)
        if l_ad != 8:
            continue
        ln, pos = struct.unpack_from('<II', b, 176 + l_ea)
        if pos == rel:
            return n
    raise KeyError('UDF FE not found')


def build(src_iso, out_iso, inplace, relocate, copy=True):
    files = locate(src_iso)
    if copy or not os.path.exists(out_iso):
        shutil.copyfile(src_iso, out_iso)
    img = Iso(out_iso)
    pvd = img.read(16)
    assert pvd[1:6] == b'CD001'
    vol = struct.unpack_from('<I', pvd, 80)[0]
    assert vol * SEC == os.path.getsize(src_iso)
    # UDF anchors / descriptors
    avdp = img.read(256)
    assert struct.unpack_from('<H', avdp, 0)[0] == 2 and check_tag(avdp)
    mlen, mloc = struct.unpack_from('<II', avdp, 16)
    rlen, rloc = struct.unpack_from('<II', avdp, 24)
    pds, lvds = [], []
    for base in (mloc, rloc):
        for k in range(mlen // SEC):
            b = img.read(base + k)
            t = struct.unpack_from('<H', b, 0)[0]
            if t == 5: pds.append(base + k)
            if t == 6: lvds.append(base + k)
            if t == 8: break
    pdb = img.read(pds[0])
    part_start, part_len = struct.unpack_from('<II', pdb, 188)
    assert part_start + part_len + 1 == vol, (part_start, part_len, vol)
    lvd = img.read(lvds[0])
    _, lvid_loc = struct.unpack_from('<II', lvd, 432)

    for p, data in inplace.items():
        lba, size, _, _ = files[p]
        assert len(data) == size, (p, len(data), size)
        img.write(lba, data)

    end = vol - 1  # overwrite trailing AVDP sector position (re-written at new end)
    for p, data in relocate.items():
        lba, size, dir_lba, name = files[p]
        new_lba = end
        nsec = (len(data) + SEC - 1) // SEC
        img.write(new_lba, data + b'\0' * (nsec * SEC - len(data)))
        end = new_lba + nsec
        # ISO9660 record
        rl, ro = find_dirrec(img, dir_lba, name)
        sec = img.read(rl)
        struct.pack_into('<I', sec, ro + 2, new_lba); struct.pack_into('>I', sec, ro + 6, new_lba)
        struct.pack_into('<I', sec, ro + 10, len(data)); struct.pack_into('>I', sec, ro + 14, len(data))
        img.write(rl, sec)
        # UDF FE
        fe_lba = find_udf_fe(img, lba, part_start)
        fe = img.read(fe_lba)
        l_ea = struct.unpack_from('<I', fe, 168)[0]
        struct.pack_into('<Q', fe, 56, len(data))
        struct.pack_into('<Q', fe, 64, nsec)
        struct.pack_into('<II', fe, 176 + l_ea, len(data), new_lba - part_start)
        fix_tag(fe)
        img.write(fe_lba, fe)
    new_vol = end + 1
    # trailing AVDP
    av = bytearray(avdp)
    struct.pack_into('<I', av, 12, new_vol - 1)
    fix_tag(av)
    img.write(new_vol - 1, av)
    # PVD volume size
    struct.pack_into('<I', pvd, 80, new_vol); struct.pack_into('>I', pvd, 84, new_vol)
    img.write(16, pvd)
    # UDF partition length
    for n in pds:
        b = img.read(n)
        struct.pack_into('<I', b, 192, new_vol - 1 - part_start)
        fix_tag(b); img.write(n, b)
    b = img.read(lvid_loc)
    if struct.unpack_from('<H', b, 0)[0] == 9:
        npart = struct.unpack_from('<I', b, 72)[0]
        struct.pack_into('<I', b, 80 + 4 * npart, new_vol - 1 - part_start)
        fix_tag(b); img.write(lvid_loc, b)
    img.f.truncate(new_vol * SEC)
    img.close()
    return new_vol
