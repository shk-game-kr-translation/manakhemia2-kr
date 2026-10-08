# `마나케미아 2 ~오치타 학원과 연금술사들~ 한글 패치`

PS2 「マナケミア2 ～おちた学園と錬金術士たち～」(SLPM-55005) 비공식 한글 패치입니다.

> 이 저장소에는 **게임 데이터가 들어 있지 않습니다.** ISO·게임 파일·일본어 대본·게임 이미지는 포함하지 않으며,
> 패치는 정품 디스크에서 직접 만든 ISO 에만 적용됩니다.

## 패치 적용 (일반 사용자)

1. [Releases](../../releases) 에서 `mk2_kr_v<버전>.xdelta` 와 `적용방법.txt` 를 받습니다.
2. 원본 ISO 가 아래 해시와 같은지 확인합니다.
   - 대상: SLPM-55005 (일본판)
   - sha1 `d0e1ef687547cc91b43f99c226968dedd36f708a`
3. [Delta Patcher](https://github.com/marco-calautti/DeltaPatcher) 또는 xdelta3 로 적용합니다.
   ```
   xdelta3 -d -s "원본.iso" mk2_kr_v1.0.0.xdelta mk2_kr_v1.0.0.iso
   ```
4. PCSX2 또는 실기(OPL 등)에서 실행합니다.

## 번역 범위

| 항목 | 분량 |
|---|---|
| 이벤트 대사·선택지 | 24,485행 |
| 메뉴·아이템·스킬·설명 (실행 파일 내 텍스트) | 7,675행 |
| 필드 NPC 대사·지명·신문 | 821행 |
| 그래픽 텍스트 (메뉴 제목·라벨 텍스처 476개, 도움말 이미지 109장) | 전체 |
| 오프닝 영상 자막 | 미포함 |

자세한 변경 내역은 [CHANGELOG.md](CHANGELOG.md).

## 오역·버그 제보

[Issues](../../issues) 에 남겨 주세요. 화면 위치(장면, 메뉴 이름)와 현재 문구, 제안 문구를 적어 주시면 됩니다.

## 직접 빌드하기 (개발자)

필요: Python 3.11+, `pip install pycdlib pillow`, 원본 ISO

```
00_original/Mana-Khemia 2 - Ochita Gakuen to Renkinjutsushi-tachi (Japan).iso   ← 원본 ISO 를 이 이름으로 넣기
py -X utf8 tools/build.py                   → 40_release/mk2_kr_v<버전>.iso
py -X utf8 tools/make_patch.py              → 50_patch/mk2_kr_v<버전>.xdelta   (xdelta3 필요)
```
`--iso <경로>` 로 다른 위치의 원본을 지정할 수도 있습니다.

### 번역 데이터에 일본어 원문이 없는 이유
`20_source/trans/` 의 각 항목은 한국어 번역(`ko`)과 원문 대신 **원문 해시(`jh`)** 만 가지고 있습니다.
빌드할 때 사용자의 원본 ISO 에서 일본어를 읽어 해시로 대조한 뒤 사용하므로, 저장소에 대본을 싣지 않고도
같은 결과물(바이트 단위 동일)을 만들 수 있습니다.

### 폴더
| 폴더 | 내용 | 저장소 |
|---|---|---|
| `00_original/` | 원본 ISO (직접 준비) | ✗ |
| `10_extracted/` | 원본에서 추출한 파일 (분석용) | ✗ |
| `20_source/` | `trans/` 번역, `config/` 글꼴·그래픽 텍스트·줄바꿈 설정 | ✓ |
| `30_build/` | 빌드 중간물 | ✗ |
| `40_release/` | 한글 ISO | ✗ |
| `50_patch/` | xdelta 패치 | ✗ (Releases 로 배포) |
| `tools/` | 빌드·추출 도구 | ✓ |
| `third_party/fonts/` | Noto Sans KR / Noto Serif KR (SIL OFL 1.1) | ✓ |

## 라이선스
- 도구 코드: MIT (`LICENSE`)
- 한국어 번역문·설정: CC BY-NC-SA 4.0 (`LICENSE`)
- 글꼴: SIL Open Font License 1.1 (`third_party/fonts/OFL.txt`)
- 원본 게임: 권리자 소유 — [NOTICE.md](NOTICE.md)
