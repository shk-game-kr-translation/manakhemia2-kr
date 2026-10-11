"""Survey a movie for burned-in text without dumping all frames to disk.

  py -X utf8 tools/movie_survey.py ED_EXT [--every 60]

Streams the decoded frames, scores each with movie_subs.text_pixels (outlined white text,
whole frame), prints the intervals where text shows, and writes contact sheets
(every N-th frame, frame number stamped) to 90_test/movie/<NAME>_sheet_<k>.png.
"""
import sys, os, argparse, subprocess
import numpy as np
import cv2
sys.path.insert(0, os.path.dirname(__file__))
import paths
import movie_subs as ms
from movie_encode import FFMPEG


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--every', type=int, default=60)
    ap.add_argument('--thr', type=int, default=300)
    a = ap.parse_args()
    src = os.path.join(paths.EXTRACTED, 'movie', a.name + '.SFD')
    out = os.path.join(paths.TEST, 'movie')
    os.makedirs(out, exist_ok=True)
    p = subprocess.Popen([FFMPEG, '-hide_banner', '-loglevel', 'error', '-i', src, '-an',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    fs = ms.W * ms.H * 3
    scores, thumbs = [], []
    t = 0
    while True:
        b = p.stdout.read(fs)
        if len(b) < fs:
            break
        im = np.frombuffer(b, np.uint8).reshape(ms.H, ms.W, 3)
        scores.append(int(ms.text_pixels(im, False).sum()))
        if t % a.every == 0:
            th = cv2.resize(im, (320, 224), interpolation=cv2.INTER_AREA).copy()
            cv2.putText(th, '%d s%d' % (t, scores[-1]), (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            thumbs.append(th)
        t += 1
    p.wait()
    sc = np.array(scores)
    np.save(os.path.join(paths.BUILD, 'movie', a.name + '_survey.npy'), sc)
    print('%s: %d frames (%.1f s)' % (a.name, len(sc), len(sc) / 29.97))
    on = None
    for i, s in enumerate(list(sc) + [0]):
        if s > a.thr and on is None:
            on = i
        elif s <= a.thr and on is not None:
            if i - on >= 20:
                print('  text %5d-%5d (%4d fr) peak %d' % (on, i - 1, i - on, sc[on:i].max()))
            on = None
    per = 48
    for k in range(0, len(thumbs), per):
        g = thumbs[k:k + per]
        g += [np.zeros_like(thumbs[0])] * (per - len(g))
        rows = [np.concatenate(g[r:r + 6], 1) for r in range(0, per, 6)]
        path = os.path.join(out, '%s_sheet_%d.png' % (a.name, k // per))
        cv2.imwrite(path, cv2.cvtColor(np.concatenate(rows, 0), cv2.COLOR_RGB2BGR))
        print(path)


if __name__ == '__main__':
    main()
