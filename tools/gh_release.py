"""Create/update a GitHub Release of the public repo and upload the patch files.

usage: gh_release.py [--ver X.Y.Z]
Uses the GitHub login that git already stored (git credential helper); the token is never printed.
Uploads 50_patch/mk2_kr_v<ver>.xdelta and the how-to text (ASCII asset name; GitHub mangles Hangul names).
"""
import sys, os, json, subprocess, argparse, urllib.request, urllib.error, urllib.parse
import paths

REPO = 'shk-game-kr-translation/manakhemia2-kr'
API = 'https://api.github.com/repos/' + REPO

BODY = """## 마나케미아 2 한글 패치 v{ver}

### 필요한 것
- 일본판 원본 ISO: **SLPM-55005** 「マナケミア2 ～おちた学園と錬金術士たち～」
- 원본 sha1 `{src}`
  (다른 버전·다른 덤프에는 적용되지 않습니다)

### 적용 방법 (GUI)
1. [Delta Patcher](https://github.com/marco-calautti/DeltaPatcher/releases) 를 받습니다.
2. **Original file** 에 원본 ISO, **XDelta patch** 에 `mk2_kr_v{ver}.xdelta` 를 지정합니다.
3. **Apply patch** — 원본을 남기려면 *Backup original file* 옵션을 켜 두세요.
4. 만들어진 ISO 를 PCSX2 등에서 실행합니다.

### 적용 방법 (명령줄)
```
xdelta3 -d -s "원본.iso" mk2_kr_v{ver}.xdelta mk2_kr_v{ver}.iso
```

### 확인
결과 ISO 의 sha1 이 `{dst}` 이면 정상입니다.
(PowerShell: `Get-FileHash 결과.iso -Algorithm SHA1`)

### 변경 내역
{changes}

---
원본 게임의 저작권은 권리자에게 있습니다. 이 패치에는 게임 데이터가 들어 있지 않으며, 정품에서 직접 만든 ISO 에만 사용하세요. 패치된 ISO 를 배포하지 마세요.
"""


def token():
    r = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                       capture_output=True, text=True, check=True)
    for ln in r.stdout.splitlines():
        if ln.startswith('password='):
            return ln[9:]
    raise SystemExit('no stored GitHub login (push once with git first)')


def call(method, url, tok, data=None, ctype='application/json'):
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': 'Bearer ' + tok, 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': ctype, 'User-Agent': 'mk2-kr-release'})
    try:
        with urllib.request.urlopen(req) as r:
            b = r.read()
            return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'null')


def changes(ver):
    s = open(os.path.join(paths.ROOT, 'CHANGELOG.md'), encoding='utf-8').read()
    i = s.find('## v%s' % ver)
    if i < 0:
        return '-'
    j = s.find('\n## ', i + 1)
    # '~' pairs render as strikethrough in GitHub markdown
    return s[s.index('\n', i) + 1: j if j > 0 else len(s)].strip().replace('~', '\\~')


def sha1_from_guide(guide):
    for ln in open(guide, encoding='utf-8'):
        if '결과 sha1' in ln:
            return ln.split()[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ver', default=paths.version())
    a = ap.parse_args()
    ver = a.ver
    patch = os.path.join(paths.PATCH, 'mk2_kr_v%s.xdelta' % ver)
    guide = os.path.join(paths.PATCH, 'mk2_kr_v%s_적용방법.txt' % ver)
    for f in (patch, guide):
        if not os.path.exists(f):
            raise SystemExit('missing ' + f + ' (run tools/make_patch.py)')
    tok = token()
    body = BODY.format(ver=ver, src='d0e1ef687547cc91b43f99c226968dedd36f708a', dst=sha1_from_guide(guide),
                       changes=changes(ver))
    st, rel = call('GET', API + '/releases/tags/v' + ver, tok)
    if st == 200:
        st, rel = call('PATCH', API + '/releases/%d' % rel['id'], tok, {'name': 'v' + ver, 'body': body})
    else:
        st, rel = call('POST', API + '/releases', tok, {'tag_name': 'v' + ver, 'name': 'v' + ver, 'body': body,
                                                        'draft': False, 'prerelease': False})
    if st not in (200, 201):
        raise SystemExit('release failed: HTTP %d %s' % (st, rel and rel.get('message')))
    print('release', rel['html_url'])
    uploads = [(patch, 'mk2_kr_v%s.xdelta' % ver), (guide, 'mk2_kr_v%s_how-to-patch_ko.txt' % ver)]
    for asset in rel.get('assets', []):
        if asset['name'] in [n for _, n in uploads]:
            call('DELETE', API + '/releases/assets/%d' % asset['id'], tok)
    up = rel['upload_url'].split('{')[0]
    for path, name in uploads:
        st, r = call('POST', up + '?name=' + urllib.parse.quote(name), tok, open(path, 'rb').read(),
                     'application/octet-stream')
        if st != 201:
            raise SystemExit('upload %s failed: HTTP %d %s' % (name, st, r and r.get('message')))
        print('uploaded %s (%d bytes)' % (r['name'], r['size']))


if __name__ == '__main__':
    main()
