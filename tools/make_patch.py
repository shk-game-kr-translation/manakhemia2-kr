"""Make the distributable patch: 50_patch/mk2_kr_v<ver>.xdelta (original ISO -> release ISO).

usage: make_patch.py [--ver X.Y.Z] [--iso ORIGINAL] [--xdelta EXE]
Also writes mk2_kr_v<ver>_적용방법.txt with the sha1 of the input and the expected output,
and checks the patch by applying it to a temporary file.
"""
import sys, os, shutil, subprocess, hashlib, argparse, tempfile
import paths

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_SHA1 = 'd0e1ef687547cc91b43f99c226968dedd36f708a'


def sha1(p):
    h = hashlib.sha1()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def xdelta_exe(given=None):
    for c in (given, os.path.join(paths.ROOT, 'third_party', 'xdelta', 'xdelta3.exe'),
              shutil.which('xdelta3'), shutil.which('xdelta')):
        if c and os.path.exists(c):
            return c
    raise SystemExit('xdelta3 not found: put xdelta3.exe in third_party/xdelta/ '
                     '(https://github.com/jmacd/xdelta-gpl/releases) or on PATH')


GUIDE = """마나케미아 2 ～오치타 학원과 연금술사들～ 한글 패치 v{ver}

[필요한 것]
  일본판 ISO: SLPM-55005 「マナケミア2 ～おちた学園と錬金術士たち～」
  원본 sha1  {src}
  (다른 버전·다른 덤프에는 적용되지 않습니다)

[적용 방법]
  1) Delta Patcher (GUI) 또는 xdelta3 를 준비합니다.
  2) 원본 ISO 에 {patch} 를 적용합니다.
     명령줄: xdelta3 -d -s "원본.iso" {patch} mk2_kr_v{ver}.iso
  3) 결과 ISO sha1 이 아래와 같으면 정상입니다.
     결과 sha1  {dst}

원본 게임의 저작권은 권리자에게 있습니다. 이 패치에는 게임 데이터가 들어 있지 않으며,
정품 디스크에서 직접 만든 ISO 에만 사용하세요.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ver', default=paths.version())
    ap.add_argument('--iso', default=paths.ORIG_ISO)
    ap.add_argument('--xdelta', default=None)
    a = ap.parse_args()
    exe = xdelta_exe(a.xdelta)
    rel = os.path.join(paths.RELEASE, 'mk2_kr_v%s.iso' % a.ver)
    if not os.path.exists(rel):
        raise SystemExit('release ISO missing: %s (run tools/build.py first)' % rel)
    if sha1(a.iso) != SRC_SHA1:
        raise SystemExit('original ISO sha1 mismatch')
    os.makedirs(paths.PATCH, exist_ok=True)
    name = 'mk2_kr_v%s.xdelta' % a.ver
    out = os.path.join(paths.PATCH, name)
    # source window spans the whole RPK so rebuilt files match their originals (124 MB -> 2 MB)
    subprocess.run([exe, '-e', '-9', '-f', '-S', 'djw', '-B', str(1 << 31), '-s', a.iso, rel, out], check=True)
    dst = sha1(rel)
    # self-check: apply to a temp file next to the release ISO (same drive, avoids filling C:)
    tmp = os.path.join(paths.BUILD, 'patch_check.iso')
    os.makedirs(paths.BUILD, exist_ok=True)
    try:
        subprocess.run([exe, '-d', '-f', '-s', a.iso, out, tmp], check=True)
        ok = sha1(tmp) == dst
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if not ok:
        os.remove(out)
        raise SystemExit('patch self-check failed')
    open(os.path.join(paths.PATCH, 'mk2_kr_v%s_적용방법.txt' % a.ver), 'w', encoding='utf-8').write(
        GUIDE.format(ver=a.ver, src=SRC_SHA1, dst=dst, patch=name))
    print('%s  %.1f MB  (verified: applies to the original and gives sha1 %s)'
          % (out, os.path.getsize(out) / 1048576, dst))


if __name__ == '__main__':
    main()
