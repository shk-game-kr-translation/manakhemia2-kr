"""MP4 previews of the built (Korean) movies for review: 30_build/movie/<NAME>.SFD -> 90_test/preview/.

  py -X utf8 tools/movie_preview.py NAME [NAME ...] [--mail]
  --mail: also a small copy (<= 9.5 MB, for mail attachments) next to it, *_mail.mp4
"""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import paths
from movie_encode import FFMPEG

PROBE = os.path.join(os.path.dirname(FFMPEG), 'ffprobe.exe')


def main():
    names = [a for a in sys.argv[1:] if not a.startswith('--')]
    out_dir = os.path.join(paths.TEST, 'preview')
    os.makedirs(out_dir, exist_ok=True)
    for n in names:
        src = os.path.join(paths.BUILD, 'movie', n + '.SFD')
        dst = os.path.join(out_dir, 'mk2_kr_v%s_%s.mp4' % (paths.version(), n))
        subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', src, '-c:v', 'libx264',
                        '-crf', '21', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                        '-movflags', '+faststart', dst], check=True)
        print(dst, os.path.getsize(dst))
        if '--mail' in sys.argv:
            dur = float(subprocess.run([PROBE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                        dst], capture_output=True, text=True).stdout)
            kbps = int(9.3 * 8 * 1024 / dur) - 64
            small = dst[:-4] + '_mail.mp4'
            log = os.path.join(os.environ.get('TEMP', '.'), 'mk2prev')
            for p in (1, 2):
                cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', src, '-c:v', 'libx264',
                       '-b:v', '%dk' % kbps, '-pass', str(p), '-passlogfile', log, '-preset', 'slow',
                       '-pix_fmt', 'yuv420p']
                cmd += ['-an', '-f', 'mp4', 'NUL'] if p == 1 else ['-c:a', 'aac', '-b:a', '64k', '-movflags',
                                                                  '+faststart', small]
                subprocess.run(cmd, check=True)
            print(small, os.path.getsize(small))


if __name__ == '__main__':
    main()
