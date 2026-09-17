'''Self-checks for logic recovered from the decompiled vision.py.

Run from the project root with the normal requirements installed:

    python -m unittest discover -s tests -v
'''
import math
import types
import unittest

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


class RandomSessionLengthTests(unittest.TestCase):

    def test_range_normalization(self):
        from app.utils.profile_settings_store import _normalize_random_range as norm

        # A zero minimum switches the feature off and never drags the max along.
        assert norm(0, 180) == (0, 180)
        assert norm(0, 0) == (0, 0)
        # A max below the min would make random.randint raise, so it is pulled up.
        assert norm(120, 60) == (120, 120)
        assert norm(120, 180) == (120, 180)
        # Clamped to the Run page's own 1..999 spinbox range.
        assert norm(-5, 5000) == (0, 999)
        assert norm(5000, 5000) == (999, 999)
        # Junk in the JSON must not crash the loader.
        assert norm('abc', None) == (0, 0)
        assert norm(None, 'x') == (0, 0)

    def test_every_roll_lands_inside_the_range(self):
        import random
        from app.utils.profile_settings_store import _normalize_random_range as norm

        low, high = norm(60, 180)
        for _ in range(200):
            assert low <= random.randint(low, high) <= high


class AutoRestartLoopTests(unittest.TestCase):
    '''Drive BotController's worker with a fake Bot: no Qt event loop, no game.'''

    def _controller(self, *, pause_min, pause_max, run_minutes = 30, fail_times = 0):
        import threading
        from app.ui.qt import bot_controller as bc
        from app.utils.profile_settings_store import ProfileSettings

        runs = []
        state = {'left': fail_times}

        class FakeBot:
            def __init__(self):
                self.stop_event = threading.Event()

            def start(self, method, minutes, **kw):
                runs.append(minutes)
                if state['left'] > 0:
                    state['left'] -= 1
                    raise RuntimeError('boom')
                cb = kw.get('loot_callback')
                if cb:  # one session earns a fixed amount, counting up from zero
                    cb(100, 200, 5, 60.0)

            def stop(self):
                self.stop_event.set()

        ctl = bc.BotController.__new__(bc.BotController)
        # QObject.__init__ is needed before touching signals; the fakes replace them.
        import PySide6.QtCore as qtcore
        qtcore.QObject.__init__(ctl)
        ctl._bot_version = 'test'
        ctl._bot = FakeBot()
        ctl._bot_thread = None
        ctl._stop_requested = threading.Event()
        real_load = bc.load_profile_settings
        bc.load_profile_settings = lambda: ProfileSettings(
            repeat_pause_min = pause_min, repeat_pause_max = pause_max)
        self.addCleanup(lambda: setattr(bc, 'load_profile_settings', real_load))
        return ctl, runs, run_minutes

    def test_single_session_when_pause_is_zero(self):
        ctl, runs, mins = self._controller(pause_min = 0, pause_max = 0)
        ctl.start(method = 'm', minutes = mins, star_bonus = False, ranked_fill = False,
                  upgrade_walls = False, multi_run_players = None)
        ctl._bot_thread.join(5)
        assert runs == [mins], runs

    def test_loop_repeats_until_stop(self):
        # A pause of 0 minutes is not selectable in the UI, so use the smallest range
        # and stop the loop from outside after a few cycles.
        ctl, runs, mins = self._controller(pause_min = 1, pause_max = 1)
        real_wait = ctl._stop_requested.wait
        def fast_wait(timeout = None):
            # Collapse the pause, and end the loop once we have seen enough cycles.
            if len(runs) >= 3:
                ctl._stop_requested.set()
            return real_wait(0)
        ctl._stop_requested.wait = fast_wait
        ctl.start(method = 'm', minutes = mins, star_bonus = False, ranked_fill = False,
                  upgrade_walls = False, multi_run_players = None)
        ctl._bot_thread.join(5)
        assert len(runs) == 3, runs

    def test_gives_up_after_consecutive_failures(self):
        from app.utils.profile_settings_store import REPEAT_MAX_CONSECUTIVE_FAILURES as cap
        ctl, runs, mins = self._controller(pause_min = 1, pause_max = 1, fail_times = 99)
        ctl._stop_requested.wait = lambda timeout = None: False  # skip the pause
        ctl.start(method = 'm', minutes = mins, star_bonus = False, ranked_fill = False,
                  upgrade_walls = False, multi_run_players = None)
        ctl._bot_thread.join(5)
        assert len(runs) == cap, f'expected to stop after {cap} failures, ran {len(runs)}'

    def test_loot_totals_accumulate_across_sessions(self):
        ctl, runs, mins = self._controller(pause_min = 1, pause_max = 1)
        seen = []
        ctl.lootChanged = type('S', (), {'emit': lambda _s, *a: seen.append(a)})()
        real_wait = ctl._stop_requested.wait
        def fast_wait(timeout = None):
            if len(runs) >= 3:
                ctl._stop_requested.set()
            return real_wait(0)
        ctl._stop_requested.wait = fast_wait
        ctl.start(method = 'm', minutes = mins, star_bonus = False, ranked_fill = False,
                  upgrade_walls = False, multi_run_players = None)
        ctl._bot_thread.join(5)
        # Three sessions of 100/200/5 each -> the totals climb instead of resetting.
        assert seen == [(100, 200, 5, 60.0), (200, 400, 10, 120.0), (300, 600, 15, 180.0)], seen

    def test_run_until_maxed_never_loops(self):
        ctl, runs, _ = self._controller(pause_min = 1, pause_max = 1, run_minutes = 0)
        ctl.start(method = 'm', minutes = 0, star_bonus = False, ranked_fill = False,
                  upgrade_walls = False, multi_run_players = None)
        ctl._bot_thread.join(5)
        assert runs == [0], runs


class WallUpgradeSafetyTests(unittest.TestCase):

    def test_confirm_refuses_without_the_gem_dialog_guard(self):
        '''No gem-dialog template for the active aspect -> confirm nothing at all.

        templates/16_10/needgold_x.png does not ship, and get_template_path() has no
        cross-aspect fallback, so on 16:10 the guard used to evaluate to "absent ->
        skip the check" and the Okay click went in unprotected.
        '''
        import pathlib  # imported here: app.core.bot pulls in OpenCV/Tesseract at module level
        from app.core import bot as bot_module

        touched = []
        fake_bot = types.SimpleNamespace(
            _wall_debug_save = lambda *a, **k: None,
            _wall_debug_click = lambda *a, **k: touched.append(('click',) + a),
            vision = types.SimpleNamespace(
                find_template = lambda *a, **k: (touched.append(('match',) + a), (None, None))[1]))

        real = bot_module.get_template_path
        bot_module.get_template_path = lambda name: pathlib.Path('no-such-dir') / name
        try:
            assert bot_module.Bot._confirm_wall_upgrade(fake_bot, None) is False
        finally:
            bot_module.get_template_path = real
        assert not touched, f'nothing may be matched or clicked without the guard, got {touched}'


class VisionRecoveredTests(unittest.TestCase):

    def test_glyph_confidence(self):
        # The token matching the expected glyph wins over a more confident wrong read
        # (before the fix every token scored pri 0, so '8' at 95 won). The trailing
        # distractor matters: the pre-fix code simply kept the last token.
        assert _glyph_confidence([('8', 95), ('B', 60), ('9', 30)], 'B') == 60.0
        # Multi-char expected token: a last-char match outranks a non-match.
        assert _glyph_confidence([('x', 99), ('i', 40), ('z', 10)], 'fi') == 40.0
        # Within one tier the strongest confidence wins (before the fix the comparison
        # was inverted and the first/weakest reading stuck).
        assert _glyph_confidence([('a', 30), ('b', 80), ('c', 50)], '') == 80.0
        # Negative confidences are not candidates; nothing eligible -> NaN.
        assert math.isnan(_glyph_confidence([('a', -1)], 'a'))
        assert math.isnan(_glyph_confidence([], 'a'))

    def test_ocr_query_matches(self):
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


if __name__ == '__main__':
    unittest.main()
