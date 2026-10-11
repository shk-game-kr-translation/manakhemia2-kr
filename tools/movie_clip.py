"""Render frames A..B of a movie with its Korean captions straight to an MP4 (quick review, no SFD).

  py -X utf8 tools/movie_clip.py NAME A B [--side]     -> 90_test/movie/<NAME>_<A>-<B>.mp4
  --side: original | Korean side by side
"""
import sys, os, time, subprocess
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import paths
import movie_build as mb
import movie_subs as ms


def main():
    name, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    side = '--side' in sys.argv
    m = mb.Movie(name)
    m.analyse()
    out = os.path.join(paths.TEST, 'movie', '%s_%d-%d.mp4' % (name, a, b))
    w = ms.W * (2 if side else 1)
    p = subprocess.Popen([mb.FF, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                          '-s', '%dx%d' % (w, ms.H), '-r', '30000/1001', '-i', '-', '-c:v', 'libx264', '-crf', '18',
                          '-pix_fmt', 'yuv420p', out], stdin=subprocess.PIPE)
    t0 = time.time()
    for t in range(a, b):
        im = m.frame(t)
        if side:
            im = np.concatenate([np.asarray(m.f[t]), im], 1)
        p.stdin.write(np.ascontiguousarray(im).tobytes())
    p.stdin.close()
    p.wait()
    print(out, '%.2f s/frame' % ((time.time() - t0) / max(1, b - a)))


if __name__ == '__main__':
    main()
