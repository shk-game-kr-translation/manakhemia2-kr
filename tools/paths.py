"""Project folder layout (single place to change paths). See README.md.

00_original   원본: Japanese ISO as obtained (+ archive, sha1). Never modified.
10_extracted  압축해제본: files pulled out of the original (ELF, RPK.BIN, ERX, unpacked RPK/LZR), analysis dumps
20_source     수정본: translation + config sources (edited by people / review tool; tracked in git)
30_build      빌드 중간물: font, caches, upgrade backups (regenerated automatically)
40_release    수정완료본: patched ISOs (mk2_kr_v<ver>.iso, -dev.iso)
50_patch      패치파일: patches to apply to the original ISO
60_review     검수 자료: review page, translation tables, received review files (incoming/)
90_test       테스트: PCSX2 data, screenshots, references
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG = os.path.join(ROOT, '00_original')
ORIG_ISO = os.path.join(ORIG, 'Mana-Khemia 2 - Ochita Gakuen to Renkinjutsushi-tachi (Japan).iso')
EXTRACTED = os.path.join(ROOT, '10_extracted')
GAME = os.path.join(EXTRACTED, 'game')          # SLPM_550.05, RPK.BIN, *.ERX, SYSTEM.CNF
SOURCE = os.path.join(ROOT, '20_source')
TRANS = os.path.join(SOURCE, 'trans')
CONFIG = os.path.join(SOURCE, 'config')
BATCHES = os.path.join(SOURCE, 'batches')
BUILD = os.path.join(ROOT, '30_build')
RELEASE = os.path.join(ROOT, '40_release')
PATCH = os.path.join(ROOT, '50_patch')
REVIEW = os.path.join(ROOT, '60_review')
TEST = os.path.join(ROOT, '90_test')
FONTS = os.path.join(ROOT, 'third_party', 'fonts')    # Noto Sans/Serif KR (OFL), bundled for reproducible builds


def game(name):
    return os.path.join(GAME, name)


def font(name):
    """font file name (optionally 'file#Variation') -> path; bare names live in third_party/fonts"""
    return name if os.path.isabs(name.split('#')[0]) else os.path.join(FONTS, name)


def version():
    return open(os.path.join(ROOT, 'VERSION'), encoding='utf-8').read().strip()
