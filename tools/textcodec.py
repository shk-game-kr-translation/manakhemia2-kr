"""Encode/decode game text between Unicode (with ASCII control tokens) and game bytes.

Game text is SJIS-like: bytes >= 0x80 start a 2-byte glyph code; ASCII bytes are
control sequences recognised by the engine (table @ELF va 0x7dc840):
  CR, CLxx, RGxxxxxx, ALxx, SPxx, IMxx, ICxx, IExx, EVICxxxx, SIPSxxxx, Fd, SCxx, 4X, 2X, 1X, HX,
  VBxx, WFxx, TS, TGXYxxxxxx, TG, #d, SWxx, SHxx, Bx, SExxxx, WTxxxx
plus printf-style %s/%d in some UI strings.
"""
import json, re

CTRL = [('CR', 2), ('CL', 4), ('RG', 8), ('AL', 4), ('SP', 4), ('IM', 4), ('IC', 4), ('IE', 4),
        ('EVIC', 6), ('SIPS', 6), ('F', 2), ('SC', 4), ('4X', 2), ('2X', 2), ('1X', 2), ('HX', 2),
        ('VB', 4), ('WF', 4), ('TS', 2), ('TGXY', 10), ('TG', 2), ('#', 2), ('SW', 4), ('SH', 4),
        ('B', 3), ('SE', 6), ('WT', 6)]


class Codec:
    def __init__(self, charmap_path):
        m = json.load(open(charmap_path, encoding='utf-8'))
        self.enc = {ch: code for ch, code in m.items()}
        self.dec = {code: ch for ch, code in m.items()}

    def encode(self, text, strict=True):
        """text: Unicode with ASCII control tokens left as-is. Returns bytes (no NUL)."""
        out = bytearray()
        missing = []
        for ch in text:
            o = ord(ch)
            if o < 0x80:
                out.append(o)
            elif ch in self.enc:
                out += self.enc[ch].to_bytes(2, 'big')
            else:
                missing.append(ch)
        if missing and strict:
            raise KeyError('unmapped characters: ' + ''.join(sorted(set(missing))))
        return bytes(out)

    def decode_game(self, b):
        """Decode bytes produced by encode() back to Unicode (for verification)."""
        out = []
        i = 0
        while i < len(b):
            c = b[i]
            if c < 0x80:
                out.append(chr(c)); i += 1
            else:
                code = (c << 8) | b[i + 1]
                out.append(self.dec.get(code, '�')); i += 2
        return ''.join(out)
