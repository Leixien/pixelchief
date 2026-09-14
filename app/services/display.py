'''Primary-display mode switching.

Google Play Games locks a game's aspect ratio to the display it launches on, so on an
ultrawide (21:9) monitor the game renders 21:9 and the bot (which needs 16:9 / 16:10)
can't read it. The workaround: switch the primary display to a 16:9 mode, relaunch the
game (it picks up 16:9), then switch the display back — the running game keeps 16:9.

The original mode is saved to disk on switch so it can be restored exactly, and
:meth:`restore_if_pending` at startup puts the display back if the app was closed while
still switched (so the user can never get stuck in 16:9).
'''
from __future__ import annotations
import ctypes
from ctypes import wintypes
from app.utils.common import ensure_dir, get_user_app_data_dir
from app.utils.logger import setup_logger
logger = setup_logger('DisplayService')

_CCHDEVICENAME = 32
_CCHFORMNAME = 32


class DEVMODE(ctypes.Structure):
    _fields_ = [
        ('dmDeviceName', ctypes.c_wchar * _CCHDEVICENAME),
        ('dmSpecVersion', ctypes.c_ushort),
        ('dmDriverVersion', ctypes.c_ushort),
        ('dmSize', ctypes.c_ushort),
        ('dmDriverExtra', ctypes.c_ushort),
        ('dmFields', ctypes.c_ulong),
        ('dmPositionX', ctypes.c_long),
        ('dmPositionY', ctypes.c_long),
        ('dmDisplayOrientation', ctypes.c_ulong),
        ('dmDisplayFixedOutput', ctypes.c_ulong),
        ('dmColor', ctypes.c_short),
        ('dmDuplex', ctypes.c_short),
        ('dmYResolution', ctypes.c_short),
        ('dmTTOption', ctypes.c_short),
        ('dmCollate', ctypes.c_short),
        ('dmFormName', ctypes.c_wchar * _CCHFORMNAME),
        ('dmLogPixels', ctypes.c_ushort),
        ('dmBitsPerPel', ctypes.c_ulong),
        ('dmPelsWidth', ctypes.c_ulong),
        ('dmPelsHeight', ctypes.c_ulong),
        ('dmDisplayFlags', ctypes.c_ulong),
        ('dmDisplayFrequency', ctypes.c_ulong),
        ('dmICMMethod', ctypes.c_ulong),
        ('dmICMIntent', ctypes.c_ulong),
        ('dmMediaType', ctypes.c_ulong),
        ('dmDitherType', ctypes.c_ulong),
        ('dmReserved1', ctypes.c_ulong),
        ('dmReserved2', ctypes.c_ulong),
        ('dmPanningWidth', ctypes.c_ulong),
        ('dmPanningHeight', ctypes.c_ulong)]


_ENUM_CURRENT_SETTINGS = -1
_DM_PELSWIDTH = 0x80000
_DM_PELSHEIGHT = 0x100000
_CDS_UPDATEREGISTRY = 0x01
_CDS_TEST = 0x02
_DISP_CHANGE_SUCCESSFUL = 0
_RESTORE_FILE = 'display_restore.devmode'


class DisplayService:
    '''Switch the primary display between the user's mode and a 16:9 mode.'''

    def __init__(self):
        self._u = ctypes.windll.user32
        self._u.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODE)]
        self._u.ChangeDisplaySettingsExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(DEVMODE), wintypes.HWND, wintypes.DWORD, ctypes.c_void_p]

    def _restore_path(self):
        return get_user_app_data_dir() / _RESTORE_FILE

    def _current(self):
        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        if self._u.EnumDisplaySettingsW(None, _ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
            return dm
        return None

    def current_size(self):
        dm = self._current()
        return (int(dm.dmPelsWidth), int(dm.dmPelsHeight)) if dm else None

    def _all_modes(self):
        out = set()
        i = 0
        while True:
            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(DEVMODE)
            if not self._u.EnumDisplaySettingsW(None, i, ctypes.byref(dm)):
                break
            out.add((int(dm.dmPelsWidth), int(dm.dmPelsHeight)))
            i += 1
        return out

    def best_16_9_mode(self):
        '''Largest available 16:9 display mode, or None.'''
        nine = [m for m in self._all_modes() if m[1] and abs(m[0] / m[1] - 16 / 9) < 0.02]
        return max(nine, key = lambda m: m[0] * m[1]) if nine else None

    def is_16_9(self):
        s = self.current_size()
        return bool(s and s[1] and abs(s[0] / s[1] - 16 / 9) < 0.02)

    def switch_to_16_9(self):
        '''Switch the primary display to the largest available 16:9 mode, saving the current
        mode for restore. Returns ``(ok, (w, h) | None, reason)``.'''
        if self.is_16_9():
            return (True, self.current_size(), 'already_16_9')
        target = self.best_16_9_mode()
        if target is None:
            return (False, None, 'no_16_9_mode')
        cur = self._current()
        if cur is None:
            return (False, None, 'read_failed')

        try:
            ensure_dir(self._restore_path().parent)
            self._restore_path().write_bytes(bytes(cur))
        except Exception:
            logger.warning('Could not persist display-restore marker')
        dm = DEVMODE()
        ctypes.memmove(ctypes.byref(dm), ctypes.byref(cur), ctypes.sizeof(DEVMODE))
        dm.dmPelsWidth = target[0]
        dm.dmPelsHeight = target[1]
        dm.dmFields = _DM_PELSWIDTH | _DM_PELSHEIGHT
        if self._u.ChangeDisplaySettingsExW(None, ctypes.byref(dm), None, _CDS_TEST, None) != _DISP_CHANGE_SUCCESSFUL:
            return (False, None, 'not_supported')
        if self._u.ChangeDisplaySettingsExW(None, ctypes.byref(dm), None, _CDS_UPDATEREGISTRY, None) != _DISP_CHANGE_SUCCESSFUL:
            return (False, None, 'change_failed')
        return (True, target, 'ok')

    def restore(self):
        '''Restore the display mode saved by :meth:`switch_to_16_9`.
        Returns ``(ok, (w, h) | None, reason)``.'''
        path = self._restore_path()
        if not path.is_file():
            return (False, None, 'nothing_to_restore')

        try:
            data = path.read_bytes()
            if len(data) < ctypes.sizeof(DEVMODE):
                return (False, None, 'bad_marker')
            saved = DEVMODE()
            ctypes.memmove(ctypes.byref(saved), data, ctypes.sizeof(DEVMODE))
        except Exception:
            return (False, None, 'bad_marker')
        res = self._u.ChangeDisplaySettingsExW(None, ctypes.byref(saved), None, _CDS_UPDATEREGISTRY, None)
        if res != _DISP_CHANGE_SUCCESSFUL:
            return (False, (int(saved.dmPelsWidth), int(saved.dmPelsHeight)), 'change_failed')

        try:
            path.unlink()
        except Exception:
            pass
        return (True, (int(saved.dmPelsWidth), int(saved.dmPelsHeight)), 'ok')

    def has_pending_restore(self):
        return self._restore_path().is_file()

    def restore_if_pending(self):
        '''Startup safety: if a switch was left un-restored (app closed while in 16:9),
        put the display back. Returns True if it restored something.'''
        if not self._restore_path().is_file():
            return False
        (ok, _, _) = self.restore()
        return ok
