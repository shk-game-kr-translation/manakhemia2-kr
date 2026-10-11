"""Copy the movie files (/MOVIE/*.SFD) out of the original ISO into 10_extracted/movie/.
usage: extract_movies.py [name ...]     (default: all top-level movies, not MOVIE/EFF)"""
import sys, os
import paths
import pycdlib

NAMES = ['OP', 'ABAN01', 'ABAN02', 'ED_URU', 'ED_ROZE', 'ED_EXT']


def main():
    names = sys.argv[1:] or NAMES
    out = os.path.join(paths.EXTRACTED, 'movie')
    os.makedirs(out, exist_ok=True)
    iso = pycdlib.PyCdlib()
    iso.open(paths.ORIG_ISO)
    for n in names:
        dst = os.path.join(out, n + '.SFD')
        if os.path.exists(dst):
            print('have', dst); continue
        with open(dst, 'wb') as f:
            iso.get_file_from_iso_fp(f, iso_path='/MOVIE/%s.SFD;1' % n)
        print('wrote', dst, os.path.getsize(dst))
    iso.close()


if __name__ == '__main__':
    main()
