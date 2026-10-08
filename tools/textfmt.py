"""Translation text format <-> game byte strings.

Source/translation text format (Unicode):
  - newline '\\n'  <-> CR control
  - other control sequences are kept as {TOKEN}, e.g. {CLRE} {CLNR} {IM00} {F1} {#1}
  - any other ASCII run in the source (debug text, printf %s, button names) is kept
    verbatim inside {=...} so the round trip is exact.
For Korean output, plain ASCII typed by the translator is normalised:
  space -> half-width space (two 0x20 bytes); other ASCII -> narrow glyphs (PUA U+F021.., codes 0xEB40..)
  which advance half a cell (hooks.py). Full-width forms typed explicitly stay full-width.
"""
import re

CTRL = [('TGXY', 10), ('EVIC', 6), ('SIPS', 6), ('RG', 8), ('SE', 6), ('WT', 6), ('CR', 2), ('CL', 4),
        ('AL', 4), ('SP', 4), ('IM', 4), ('IC', 4), ('IE', 4), ('SC', 4), ('VB', 4), ('WF', 4), ('SW', 4),
        ('SH', 4), ('4X', 2), ('2X', 2), ('1X', 2), ('HX', 2), ('TS', 2), ('TG', 2), ('F', 2), ('#', 2),
        ('B', 3)]
# engine matching order is table order (CR, CL, RG, AL, ...); we mirror it exactly:
ENGINE_ORDER = [('CR', 2), ('CL', 4), ('RG', 8), ('AL', 4), ('SP', 4), ('IM', 4), ('IC', 4), ('IE', 4),
                ('EVIC', 6), ('SIPS', 6), ('F', 2), ('SC', 4), ('4X', 2), ('2X', 2), ('1X', 2), ('HX', 2),
                ('VB', 4), ('WF', 4), ('TS', 2), ('TGXY', 10), ('TG', 2), ('#', 2), ('SW', 4), ('SH', 4),
                ('B', 3), ('SE', 6), ('WT', 6)]


def _match_ctrl(b, i):
    for name, ln in ENGINE_ORDER:
        nb = name.encode()
        if b.startswith(nb, i) and i + ln <= len(b) and all(x < 0x80 for x in b[i:i + ln]):
            return ln
    return 0


def game_to_text(b):
    """Decode original SJIS game bytes (no NUL) to the editable text format."""
    out = []
    i = 0
    asc = bytearray()

    def flush():
        if asc:
            out.append('{=' + asc.decode('ascii') + '}')
            asc.clear()
    while i < len(b):
        c = b[i]
        if c >= 0x80:
            flush()
            out.append(b[i:i + 2].decode('cp932')); i += 2
            continue
        ln = _match_ctrl(b, i)
        if ln:
            flush()
            tok = b[i:i + ln].decode('ascii')
            out.append('\n' if tok == 'CR' else '{' + tok + '}')
            i += ln
        else:
            asc.append(c); i += 1
    flush()
    return ''.join(out)


TOKEN = re.compile(r'\{=(.*?)\}|\{([^{}]+)\}|\n|.', re.S)
FW = {chr(c): chr(c + 0xFEE0) for c in range(0x21, 0x7f)}
FW.update({'-': '－', '~': '～', "'": '’', '"': '”'})


def text_to_units(t, korean=True):
    """Split text into display units: ('ctrl', ascii) | ('ch', char) | ('sp', None)."""
    units = []
    for m in TOKEN.finditer(t):
        if m.group(1) is not None:
            units.append(('ctrl', m.group(1)))
        elif m.group(2) is not None:
            units.append(('ctrl', m.group(2)))
        else:
            ch = m.group(0)
            if ch == '\n':
                units.append(('ctrl', 'CR'))
            elif ch == ' ' and korean:
                units.append(('sp', None))
            elif ord(ch) < 0x80 and korean:
                units.append(('nch', chr(0xF000 + ord(ch))))
            else:
                units.append(('ch', ch))
    return units


def units_to_bytes(units, codec):
    out = bytearray()
    for k, v in units:
        if k == 'ctrl':
            out += v.encode('ascii')
        elif k == 'sp':
            out += b'  '
        else:  # 'ch' or 'nch'
            out += codec.encode(v)
    return bytes(out)


def width(units):
    w = 0.0
    for k, v in units:
        if k == 'sp':
            w += 0.5
        elif k == 'ch':
            w += 1
        elif k == 'nch':
            w += 0.5
    return w


def nfull(units):
    """Engine column count: full-width glyphs only (half units are not counted, see hooks.py)."""
    return sum(1 for k, v in units if k == 'ch')


def fits(units, maxw, maxfull):
    return width(units) <= maxw and nfull(units) <= maxfull


def wrap(units, maxw, maxfull=None):
    """Re-wrap Korean units: explicit CR kept; long segments broken at spaces.
    A line fits when its pixel width (cells) <= maxw and its full-width count <= maxfull.
    Returns list of lines (each a unit list)."""
    if maxfull is None:
        maxfull = int(maxw)
    lines = []
    seg = []
    segs = []
    for u in units:
        if u == ('ctrl', 'CR'):
            segs.append(seg); seg = []
        else:
            seg.append(u)
    segs.append(seg)
    for seg in segs:
        # split into words at spaces
        words, cur = [], []
        for u in seg:
            if u[0] == 'sp':
                words.append(cur); cur = []
            else:
                cur.append(u)
        words.append(cur)
        line = []
        for w in words:
            if not line:
                cand = list(w)
            else:
                cand = line + [('sp', None)] + w
            if fits(cand, maxw, maxfull) or not line:
                line = cand
            else:
                lines.append(line); line = list(w)
            # hard-break a single word longer than maxw
            while not fits(line, maxw, maxfull):
                acc, rest = [], []
                for i, u in enumerate(line):
                    if not fits(acc + [u], maxw, maxfull):
                        rest = line[i:]; break
                    acc.append(u)
                lines.append(acc); line = rest
        lines.append(line)
    return lines


def join_lines(lines):
    out = []
    for i, l in enumerate(lines):
        if i:
            out.append(('ctrl', 'CR'))
        out += l
    return out
