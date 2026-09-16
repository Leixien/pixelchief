'''Self-checks for logic recovered from the decompiled vision.py.

Run from the project root with the normal requirements installed:

    python test_vision_recovered.py
'''
import math
import types

import numpy as np

from app.services import vision
from app.services.vision import VisionService

match = VisionService._ocr_query_matches


def _glyph_confidence(tokens, expected_char):
    '''Call the psm10 helper with a fake Tesseract returning ``tokens`` (text, conf).'''
    fake = types.SimpleNamespace(
        Output = vision.pytesseract.Output,
        TesseractNotFoundError = vision.pytesseract.TesseractNotFoundError,
        image_to_data = lambda pil, output_type = None, config = None: {
            'level': [5] * len(tokens),
            'text': [t for t, _ in tokens],
            'conf': [c for _, c in tokens] })
    mono = np.zeros((40, 40), dtype = np.uint8)  # crop stays big enough to skip the resize
    real = vision.pytesseract
    vision.pytesseract = fake
    try:
        return VisionService._tesseract_single_glyph_confidence_psm10(mono, 5, 5, 35, 35, expected_char = expected_char)
    finally:
        vision.pytesseract = real


def test_glyph_confidence():
    # The token matching the expected glyph wins over a more confident wrong read
    # (before the fix every token scored pri 0, so '8' at 95 won).
    # (the trailing distractor matters: the pre-fix code simply kept the last token.)
    assert _glyph_confidence([('8', 95), ('B', 60), ('9', 30)], 'B') == 60.0
    # Multi-char expected token: a last-char match outranks a non-match.
    assert _glyph_confidence([('x', 99), ('i', 40), ('z', 10)], 'fi') == 40.0
    # Within one tier the strongest confidence wins (before the fix the comparison
    # was inverted and the first/weakest reading stuck).
    assert _glyph_confidence([('a', 30), ('b', 80), ('c', 50)], '') == 80.0
    # Negative confidences are not candidates; nothing eligible -> NaN.
    assert math.isnan(_glyph_confidence([('a', -1)], 'a'))
    assert math.isnan(_glyph_confidence([], 'a'))
    print('glyph confidence check passed.')


def test():
    # Case-sensitive fuzzy: raw and query keep their case, so a near-miss on a
    # mixed-case name still matches (before the fix `cr` was lowercased against a
    # case-sensitive query, so every capital counted as a difference).
    assert match('ClashFan', 'ClashFam', case_sensitive = True, match_alnum_only = False, fuzzy_min_ratio = 0.8)
    # ...and case still matters when it is asked for.
    assert not match('clashfan', 'CLASHFAN', case_sensitive = True, match_alnum_only = False, fuzzy_min_ratio = 0.95)

    # Case-insensitive fuzzy: caller lowercases the query, norm_text lowercases raw.
    assert match('clashfan', 'clashfam', case_sensitive = False, match_alnum_only = False, fuzzy_min_ratio = 0.8)

    # Alnum mode strips BOTH sides (before the fix only the query was stripped, so
    # punctuation in the OCR text dragged the ratio down).
    assert match('.C l a s h F a n!', 'clashfan', case_sensitive = False, match_alnum_only = True, fuzzy_min_ratio = 0.95)

    # Guards still hold.
    assert not match('clashfan', '', case_sensitive = False, match_alnum_only = False, fuzzy_min_ratio = 0.5)
    assert not match('clashfan', 'ab', case_sensitive = False, match_alnum_only = False, fuzzy_min_ratio = 0.1)  # query < 3 chars
    assert not match('clashfanatic-the-third', 'cfa', case_sensitive = False, match_alnum_only = False, fuzzy_min_ratio = 0.1)  # length ratio < 0.5
    assert not match('zzzzzzzz', 'clashfan', case_sensitive = False, match_alnum_only = False, fuzzy_min_ratio = 0.6)

    # Exact substring path is unaffected by the fuzzy block.
    assert match('the clashfan here', 'clashfan', case_sensitive = False, match_alnum_only = False, fuzzy_min_ratio = None)
    print('OCR query match check passed.')


if __name__ == '__main__':
    test()
    test_glyph_confidence()
