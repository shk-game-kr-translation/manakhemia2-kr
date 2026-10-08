# Mana Khemia 2 (SLPM-55005, JP v1.01) Korean patch — current state

Source ISO sha1 `d0e1ef687547cc91b43f99c226968dedd36f708a` (never modified; build copies it).

Folder layout (2026-10-08, see README.md; all paths in code come from tools/paths.py):
00_original (원본 ISO) · 10_extracted (ELF/RPK/ERX + unpacked, analysis dumps) · 20_source (trans/, config/,
batches/ — tracked) · 30_build (font, caches, upgrade backups) · 40_release (patched ISOs) · 50_patch (patch
files) · 60_review (review page, tables, incoming/) · 90_test (pcsx2data, screenshots, ref).
Paths below written as trans/, config/ mean 20_source/trans/, 20_source/config/.

## Established facts (verified in PCSX2 2.8.2 unless noted)
- Files are found by name (sceCdSearchFile); RPK.BIN read as LBA(base)+sector offset.
- RPK.BIN table: ELF file off 0x597f10, 4596 entries {name_ptr, sector_off, size}; covers whole RPK.
- LZR codec: tools/lzr.py (decoder @0x103c4c); all 2346 LZR files decode; round trip ok.
- EVD event scripts (1226): tools/evd.py; msgs referenced by index -> strings resizable. Pad rule (len&~3)+4.
- Text: SJIS-like 2-byte units; ASCII = control codes (table @va 0x7dc840). Text fmt: tools/textfmt.py.
- Fonts: 2 lists+24x24 4bpp glyph arrays contiguous in ELF -> merged into one font (tools/font_build.py,
  elf_font_patch.py). Kanji dropped; Hangul = KS X 1001 2350 + narrow ASCII (lead 0xEB) + kana + symbols.
  Glyph area ends ~0x96d000; free ELF RAM 0x9a0000..0x9cc3f8 (and 0x970000..) for code/data.
- Hooks (tools/hooks.py @0x9cc3f8): half-width units (space pair 0x20 0x20, lead 0xEB) advance half
  and do not count toward column limit in renderer, layout and line counter. Verified in event 1.
- Event window: 13 columns/line auto wrap, 3 lines. Build wraps Korean at 13 cells (space/ASCII = 0.5).
- Glyph cell: the renderer never shows columns 0..2 of a 24x24 cell (original ink always in 3..20).
  font_build places Hangul ink centred in columns 3..20 and narrow ASCII in 3..14 (size 21.5).
- ELF strings (tools/elf_patch.py): in place if they fit, else relocated to the freed glyph tail with
  data pointers / exclusive lui+addiu rewritten. Engine wraps ELF text by counting full-width units
  only, so Korean is pre-wrapped per window: 20_source/config/elf_wrap.json (ranges / patterns / max_lines /
  list_width). Verified windows: char-select description 20 cols x3; item memo 11 cols x5 (item menu);
  item effect field ~20 cols x2; skill description 13 cols x4 (skill menu); handbook memo 13 cols (many lines);
  trait popup 12 cols (auto-sized); assignment board wide. Others (books, monster book 20x5, help 21x5,
  diaries 18, growbook titles 16) follow the Japanese line breaks but are not yet seen in game.
- Item stat blocks ('{F1}対象：…') are generated from 20_source/config/statblock_fields.json (tools/statblock.py).
- Event name box uses the name table at 0xae6b40.. (12-byte records), not the model-name table.
- ISO rebuild (tools/iso_tool.py): ELF in place; RPK.BIN relocated to image end; ISO9660 + UDF FE,
  PD, LVID, AVDP updated; verified readable via ISO9660 and UDF (pycdlib) and in PCSX2.

- ERX (tools/erx.py, erx_extract.py, erx_patch.py, erx_tr.py): QvDataE .rodata [0x300,0xb670) holds only
  strings reached via R_MIPS_32-relocated .data words (0xb670.. used by .erx.lib, kept). Build repacks all
  strings there and rewrites the pointers (44048/45936 bytes used). Module is loaded once at boot:
  savestates keep the old text, so check field text after a fresh boot (or an in-game memory-card save).
- QsDataE.erx / QAData.erx / test.erx: no text.

- Graphics text (tools/gfxtext.py): per-label boxes in 20_source/config/gfx/<pack>.json; text rendered with
  Noto Sans/Serif KR, quantised into the texture's own palette (no CLUT change), chunks re-LZR'd in
  place (pack size unchanged, RPK.BIN overwritten in place). Options: weight/ow/outline/outline2/
  shadow/grad/fill/th/cx/cy/rot/vertical/inpaint/engrave/ring/bg; "joins" for text spanning textures.
  Default fill = one flat colour sampled from the original (per-row colours made stripes; use
  "rowfill" for real gradients), crisp mask edges when outlined; align "orig" centres on the original
  label (used for list menus / name plates).
  `gfxtext.py seg <pack> <chunk>` and `preview <spec> <dir>` for authoring.

- Font (2026-10-08): Noto Sans KR Medium (was Bold; original JP font is regular weight), auto_y.
  font_build fits each glyph's real ink into columns 3..20 (was spilling into col 21 -> slight
  right-edge clipping). Candidates compared: Noto Regular/Medium, Nanum Gothic, Gothic A1 (third_party/fonts).
- ELF manual entries ('manual': true in elf.json, kept by extract_elf): strings reached via tables the
  ref scan misses, e.g. help category {F1}戦闘 @b875c0 (was blank), はい/いいえ, 調合する/量産する, なし.
- Verified in game: help pages (battle/quest/explore/other incl. grown HELP_086/088/124), student ID
  card (sideways text), battle commands, map/menu titles.

## Text populations
| population | location | volume | status |
|---|---|---|---|
| event dialogue | RPK Event/*.evd | 21964 msgs + 2522 choices, ~512k chars (exact) | TRANSLATED (24475/24486 entries, all unique lines; batches 20_source/batches/ev_0001..0027) — needs in-game QA |
| ELF UI/DB strings | SLPM_550.05 0xa6..0xb8 | 11146 entries, 251k ja chars | TRANSLATED (7621 + 3494 skipped debug/model/flag names); build ok, relocation pool 120 KB. Batches 20_source/batches/el_0001..0052 (+ .manual/.manual2) |
| field text | erxs/QvDataE.erx (also identical /ERXS/QVDATAE.ERX on disc) | 821 strings ~21k chars | TRANSLATED (20_source/trans/erx/qvdata.json, batches 20_source/batches/erx_0001..0004*). Seen in game: map list names, NPC bubbles (auto-sized). Newspaper items (13 cols x4 + source line) not yet seen |
| graphics text | fpack/*.fp textures (LZR chunks, TIM2/TIM) | 18 packs specced | IN PROGRESS: tools/gfxtext.py + 20_source/config/gfx/*.json (menu, font, common, battle, subject, kadai_moji, maptime, schedule, phase, note, atlas, board, compound, handbook, sugoroku, bazaar, field, title). Seen in game: title logo, 주인공 선택, 학원 지도, main menu, item/equip/status screens. res/HELP: 170 captions in 109 images done (20_source/trans/help_ko.txt + 20_source/config/help_boxes.json -> tools/helpgen.py -> 20_source/config/gfx/help.json; caption pixels removed by colour + vertical interpolation). HELP files are re-LZR'd and appended to RPK (17 grew, max +1001 B) - in-game display of a HELP page not yet seen (appear at first tutorials). Student ID card seen in game OK. Left: loading.fp logo, item.fp badges, field.fp 10, temp.fp (MK1 debug, skipped), movies |

## Runtime test harness
tools/pcsx2ctl.ps1 (start/keys/shot/stop), datapath D:/Game/ps2/mk2-kr/90_test/pcsx2data, window-targeted
PostMessage input only (never global keystrokes).

## Next steps (2026-10-07)
- ELF strings done. Still to see in game: recipe book descriptions, monster book, help pages, diaries, growbook.
- QvDataE.erx translated + verified in classroom building (Roze route day 1). In-game memory-card save
  not yet made (save point = atelier; main menu via triangle has no save). Savestate slot 1 = dev.iso
  build of 2026-10-08 on the classroom-building rooftop.
- Verify in game: book (recipe) description window (b02e60..b07000, ja 72..92 chars), trait window
  (12 cols assumed), quest/help windows (22 assumed). Event titles b097c0..b14fa8 were marked skip as
  debug (dev tags) - confirm no in-game event list uses them.
- Graphics text seen: title logo subtitle, main menu items, 主人公選択 header, character name plates,
  所持金, 固有スキル/コモンスキル labels, opening movie burned-in subtitles, student ID card (生徒手帳),
  equip labels (武器/防具/アクセサリ, エーテル効果, stat names), item screen メモ/標準レシピ/効果, 日直 board label.
- QvDataE.erx, graphics text survey, final non-dev ISO build + PCSX2 QA.

## Release build (2026-10-08)
- `py -X utf8 tools/build.py (-> 40_release/mk2_kr_v<ver>.iso)` passes with no errors (untranslated check on):
  31 short ELF names/labels filled (name table ae6bc0.., はい/いいえ, ゼーレ/キュア/スロウ/カース...);
  event 848:m10 has an empty source (skip). Release ISO boots and plays into the first event.
- Graphics: 20 packs + 109 HELP images. Added item.fp shop badges (한정/이득/재고처분/품절; 4th badge
  reading 在庫処分 is a guess from a tiny sprite), loading.fp logo subtitle, field.fp 보너스/슬롯.
- Labels are limited to the original label width (game crops to it); long ones scale down uniformly.
  전갈자리->전갈, 물고기자리->물고기 (slot too narrow).
- Remaining: in-game check of later-story screens (bazaar, fishing, sugoroku, grade stamps, later help
  pages, books/diaries) - only reachable by progressing the story.

## Versioning / review (2026-10-08)
- VERSION file (1.0.0), CHANGELOG.md, git repo (local, tag v1.0.0). Only tools/ 20_source/ docs/ are tracked.
- Outputs: 40_release/mk2_kr_v<ver>.iso (release) + -dev.iso; 60_review/mk2_kr_v<ver>_검수.html,
  60_review/mk2_kr_v<ver>_번역.csv/.json. build.py names outputs from VERSION when --out is omitted.
- Review loop: tools/review_html.py builds the page (rows carry the build's layout limits; checker in the page
  reports 0 issues on the current translation = same verdict as the build); reviewers save a 'mk2-review'
  JSON; tools/review_apply.py <file> [--dry] [--force] re-validates and writes 20_source/trans/ + 20_source/config/gfx/.
