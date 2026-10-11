"""Re-encode an .SFD movie's video with an ffmpeg filter and put it back into the .SFD.

usage: movie_encode.py <NAME> [--vf FILTER] [--kbps N] [--out PATH]
  NAME   movie in 10_extracted/movie (e.g. ABAN01)
  --vf   ffmpeg video filter applied to the decoded frames (subtitle overlay etc.)
Output: 30_build/movie/<NAME>.SFD (same size and pack layout as the original; see sfd_video.py).
The bitrate is chosen from the original video size (95%); 2-pass so the result fits.
"""
import sys, os, subprocess, argparse
import paths
import sfd, sfd_video

import shutil
FFMPEG = next((p for p in (os.path.join(paths.ROOT, 'third_party', 'ffmpeg', 'bin', 'ffmpeg.exe'),
                           shutil.which('ffmpeg')) if p and os.path.exists(p)), 'ffmpeg')


def encode_q(src, vf, q, nframes, out_es):
    """constant quantizer: bits follow scene complexity, like the original's allocation"""
    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', src, '-an', '-frames:v', str(nframes)]
    if vf:
        cmd += ['-vf', vf]
    cmd += ['-c:v', 'mpeg1video', '-q:v', str(q), '-g', '15', '-bf', '2', '-f', 'mpeg1video', out_es]
    subprocess.run(cmd, check=True)


def encode(src, vf, kbps, nframes, out_es, log):
    base = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', src, '-an', '-frames:v', str(nframes)]
    if vf:
        base += ['-vf', vf]
    enc = ['-c:v', 'mpeg1video', '-b:v', '%dk' % kbps, '-maxrate', '8000k', '-bufsize', '1441792',
           '-g', '15', '-bf', '2', '-passlogfile', log, '-f', 'mpeg1video']
    subprocess.run(base + enc + ['-pass', '1', os.devnull if os.name != 'nt' else 'NUL'], check=True)
    subprocess.run(base + enc + ['-pass', '2', out_es], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--vf', default='')
    ap.add_argument('--kbps', type=int, default=0)
    ap.add_argument('--q', type=int, default=0, help='constant quantizer instead of 2-pass bitrate')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    src = os.path.join(paths.EXTRACTED, 'movie', a.name + '.SFD')
    work = os.path.join(paths.BUILD, 'movie')
    os.makedirs(work, exist_ok=True)
    orig = open(src, 'rb').read()
    ves = b''.join(orig[x['data_off']:x['data_off'] + x['data_len']] for x in sfd.packets(orig) if x['sid'] == 0xE0)
    pics, _ = sfd_video.pictures(ves)
    secs = len(pics) * 1001 / 30000
    kbps = a.kbps or int(len(ves) * 8 * 0.95 / secs / 1000)
    es_path = os.path.join(work, a.name + '.m1v')
    if a.q:
        encode_q(src, a.vf, a.q, len(pics), es_path)
        out, rep = sfd_video.replace(orig, open(es_path, 'rb').read())
        dst = a.out or os.path.join(work, a.name + '.SFD')
        open(dst, 'wb').write(out)
        rep['q'] = a.q
        print(dst, rep)
        return
    for attempt in range(4):
        encode(src, a.vf, kbps, len(pics), es_path, os.path.join(work, a.name + '_pass'))
        es = open(es_path, 'rb').read()
        try:
            out, rep = sfd_video.replace(orig, es)
            break
        except ValueError as ex:
            if 'too large' not in str(ex):
                raise
            print('too large at %d kbps, retrying lower' % kbps)
            kbps = int(kbps * 0.95)
    else:
        raise SystemExit('could not fit the video')
    dst = a.out or os.path.join(work, a.name + '.SFD')
    open(dst, 'wb').write(out)
    rep['kbps'] = kbps
    print(dst, rep)


if __name__ == '__main__':
    main()
