import ctypes
import json
import time
from ctypes import wintypes
from dataclasses import dataclass
import numpy as np
import cv2
from PIL import Image
from typing import List, Optional, Tuple
from app.utils.common import get_user_app_data_dir
from app.utils.logger import setup_logger
from app.utils.window_settings_store import WindowSelection, load_window_selection
from app.services.adb import AdbService, adb_options, get_adb_service
logger = setup_logger('WindowService')
WM_LBUTTONDOWN = 513
WM_LBUTTONUP = 514
WM_MOUSEMOVE = 512
MK_LBUTTON = 1
WM_MOUSEWHEEL = 522
WHEEL_DELTA = 120
_CHILD_CLASS_PREFIX = 'CROSVM'
_SWP_NOZORDER = 0x4
_SWP_NOACTIVATE = 0x10
_SW_RESTORE = 9
_GA_ROOT = 2
_MONITOR_DEFAULTTONEAREST = 2
_RESIZE_ATTEMPTS = 3  # the surface can settle a few px off (title bar, DPI rounding): re-measure and correct
_RESIZE_SETTLE_SECONDS = 0.6
_SWP_NOSIZE = 0x1
_SM_XVIRTUALSCREEN = 76
_OFFSCREEN_GAP = 200  # px left of the leftmost monitor, so no edge of the window shows
MINIMIZED_MESSAGE = ('Clash of Clans is minimized: the bot cannot see a minimized Google Play Games window. '
                     'Restore it (it can stay behind other windows), use Settings -> Hide game window, or play in BlueStacks.')


class _MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def _hidden_marker():
    return get_user_app_data_dir() / 'hidden_window.json'


def fit_16_9(surface, outer, work):
    '''Outer window rect ``(x, y, w, h)`` whose game surface is the largest 16:9 that fits
    ``work`` (``(left, top, right, bottom)``). ``surface`` is ``(w, h)``, ``outer`` is
    ``(left, top, right, bottom)``; the difference between them is the window chrome
    (title bar, borders), which stays the same size after the resize.'''
    (dw, dh) = (outer[2] - outer[0] - surface[0], outer[3] - outer[1] - surface[1])
    (work_w, work_h) = (work[2] - work[0], work[3] - work[1])
    w = int(min(work_w - dw, (work_h - dh) * 16 / 9))
    h = round(w * 9 / 16)
    (ow, oh) = (w + dw, h + dh)
    x = max(work[0], min(outer[0], work[2] - ow))
    y = max(work[1], min(outer[1], work[3] - oh))
    return (x, y, ow, oh)


@dataclass
class WindowCandidate:
    '''A visible top-level window plus its resolved Google Play Games game surface (if any).'''
    # [recovered from bytecode: decompiler collapsed these fields into the docstring]
    top_hwnd: int = 0
    title: str = ''
    top_class: str = ''
    child_hwnd: int = 0
    child_class: str = ''

    @property
    def is_game(self):
        '''True when this window exposes a CROSVM game surface we can capture.'''
        return self.child_hwnd != 0

    
    def to_selection(self):
        return WindowSelection(title = self.title, top_class = self.top_class, child_class = self.child_class)

    
    def display_label(self):
        title = self.title or '(no title)'
        if self.is_game:
            return f'''{title}  —  surface: {self.child_class}'''
        return f'''{title}  —  no game surface ({self.top_class})'''



@dataclass
class DescendantInfo:
    '''A single descendant window under a top-level window (for the Info diagnostics view).'''
    # [recovered from bytecode: decompiler collapsed these fields into the docstring]
    hwnd: int
    cls: str
    title: str
    width: int
    height: int
    depth: int
    is_surface: bool

    def display_label(self):
        indent = '    ' * self.depth
        marker = '[surface] ' if self.is_surface else ''
        size = f'''{self.width}x{self.height}''' if self.width and self.height else '—'
        title = f'''  "{self.title}"''' if self.title else ''
        return f'''{indent}{marker}{self.cls}  ({size})  hwnd={self.hwnd}{title}'''



class WindowService:
    '''Handles window finding and screenshot capture using Windows API.'''
    _TOP_LEVEL_CLASS_PREFIX = 'HwndWrapper'
    
    def __init__(self, window_name = 'Clash of Clans', child_class = 'CROSVM_1'):
        self.window_name = window_name
        self.child_class = child_class
        self.hwnd = 0
        self.use_adb, _ = adb_options()
        self._capture_size = None
        if self.use_adb:
            return
        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32
        
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            self.find_window()
            return None
        except Exception:
            self.user32.SetProcessDPIAware()


    
    @property
    def adb(self) -> AdbService:
        return get_adb_service()

    def find_window(self):
        '''
Resolve the game-surface HWND.

Honors a user-pinned selection (Settings → Game window) first; otherwise falls back to
auto-detection (Google Play Games window with a ``CROSVM*`` child surface).
'''
        if self.use_adb:
            self.screenshot()
            return True
        selection = load_window_selection()
        self.hwnd = self._resolve_hwnd(selection)
        if self.hwnd:
            how = 'pinned selection' if selection.is_set() else 'auto-detect'
            logger.info(f'''Window found via {how} (HWND: {self.hwnd})''')
            return True
        if selection.is_set():
            logger.warning(f'''Pinned game window not found (title={selection.title!r}, child={selection.child_class!r}); falling back to auto-detect.''')
            self.hwnd = self._auto_detect_child()
            if self.hwnd:
                logger.info(f'''Window found via auto-detect fallback (HWND: {self.hwnd})''')
                return True
        logger.warning(f'''Window not found: {self.window_name} (expect a titled window with a {_CHILD_CLASS_PREFIX!r}* surface, either as the top-level window itself or a descendant — Google Play Games). Open Settings → Game window to pick it manually.''')
        return False

    
    def _get_class(self, hwnd):
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    
    def _get_title(self, hwnd):
        length = self.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ''
        buff = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value

    
    def _find_descendant(self, root_hwnd, predicate):
        '''Depth-first search for the first descendant whose class satisfies ``predicate``.'''
        EnumChildWindows = self.user32.EnumChildWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        found = {
            'hwnd': 0,
            'class': '' }
        
        def enum_child_cb(child_hwnd, lParam):
            cls = self._get_class(child_hwnd)
            if predicate(cls):
                found['hwnd'] = child_hwnd
                found['class'] = cls
                return False
            EnumChildWindows(child_hwnd, EnumWindowsProc(enum_child_cb), 0)
            return True

        EnumChildWindows(root_hwnd, EnumWindowsProc(enum_child_cb), 0)
        return (found['hwnd'], found['class'])

    
    def _find_crosvm_descendant(self, root_hwnd, preferred_class = ''):
        '''Resolve a game-surface child: exact ``preferred_class`` first, then any ``CROSVM*``.'''
        if preferred_class:
            (hwnd, cls) = self._find_descendant(root_hwnd, (lambda c: c == preferred_class))
            if hwnd:
                return (hwnd, cls)
        return self._find_descendant(root_hwnd, (lambda c: c.upper().startswith(_CHILD_CLASS_PREFIX)))

    
    def _resolve_surface(self, top_hwnd, top_class, preferred_class = ''):
        '''Resolve the game surface for a top-level window.

Google Play Games window topology varies across machines/builds:
- Some have an outer ``HwndWrapper`` shell with a ``CROSVM*`` **descendant** (capture that).
- Others expose ``CROSVM*`` as the **top-level window itself** (no wrapper); capture it directly.

Returns ``(surface_hwnd, surface_class)`` or ``(0, "")`` when no surface is present.
'''
        (hwnd, cls) = self._find_crosvm_descendant(top_hwnd, preferred_class)
        if hwnd:
            return (hwnd, cls)
        if top_class.upper().startswith(_CHILD_CLASS_PREFIX):
            return (top_hwnd, top_class)
        return (0, '')

    
    def enumerate_windows(self):
        '''List visible, titled top-level windows with their resolved game surface (if any).

Used by the Settings picker so users can choose the right window when auto-detection
fails. Candidates with a CROSVM surface are sorted first.
'''
        EnumWindows = self.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        IsWindowVisible = self.user32.IsWindowVisible
        candidates = []
        
        def enum_top_cb(hwnd, lParam):
            if IsWindowVisible(hwnd):
                title = self._get_title(hwnd)
                if title:
                    top_class = self._get_class(hwnd)
                    (child_hwnd, child_class) = self._resolve_surface(hwnd, top_class)
                    candidates.append(WindowCandidate(top_hwnd = hwnd, title = title, top_class = top_class, child_hwnd = child_hwnd, child_class = child_class))
            return True

        EnumWindows(EnumWindowsProc(enum_top_cb), 0)
        candidates.sort(key = (lambda c: (not (c.is_game), c.title.lower())))
        return candidates

    
    def enumerate_descendants(self, root_hwnd):
        '''All descendant windows of ``root_hwnd`` (class, title, size, depth) for diagnostics.'''
        EnumChildWindows = self.user32.EnumChildWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        results = []
        seen = set()
        
        def walk(parent_hwnd, depth):
            
            def cb(child_hwnd, lParam):
                if child_hwnd not in seen:
                    seen.add(child_hwnd)
                    cls = self._get_class(child_hwnd)
                    size = self.window_pixel_size(child_hwnd)
                    results.append(DescendantInfo(hwnd = child_hwnd, cls = cls, title = self._get_title(child_hwnd), width = size[0] if size else 0, height = size[1] if size else 0, depth = depth, is_surface = cls.upper().startswith(_CHILD_CLASS_PREFIX)))
                    walk(child_hwnd, depth + 1)
                return True

            EnumChildWindows(parent_hwnd, EnumWindowsProc(cb), 0)

        walk(root_hwnd, 0)
        return results

    
    def window_pixel_size(self, hwnd):
        '''Outer pixel size of any HWND via ``GetWindowRect`` (same basis as :meth:`screenshot`).'''
        if not hwnd:
            return None

        try:
            rect = wintypes.RECT()
            self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                return None
            return (int(w), int(h))
        except Exception:
            return None


    def resize_to_16_9(self):
        '''Resize the game's top-level window so its capture surface is 16:9, as large as the
monitor's work area allows. Returns ``(ok, (w, h) | None, reason)``; reason is ``ok``,
``already_16_9``, ``adb``, ``not_found``, ``minimized``, ``fullscreen`` or ``not_16_9_after_resize``.'''
        from app.config import ASPECT_16_9, resolve_aspect_key
        if self.use_adb:
            return (False, None, 'adb')
        if not self.hwnd:
            self.find_window()
        surface = self.window_pixel_size(self.hwnd)
        if surface is None:
            return (False, None, 'not_found')
        if resolve_aspect_key(*surface) == ASPECT_16_9:
            return (True, surface, 'already_16_9')
        if self.is_minimized():
            return (False, None, 'minimized')
        top = self._top()
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        self.user32.GetMonitorInfoW(self.user32.MonitorFromWindow(top, _MONITOR_DEFAULTTONEAREST), ctypes.byref(info))
        work = (info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom)
        mon = info.rcMonitor
        if self.user32.IsZoomed(top):
            self.user32.ShowWindow(top, _SW_RESTORE)
            time.sleep(_RESIZE_SETTLE_SECONDS)
        for attempt in range(_RESIZE_ATTEMPTS):
            rect = wintypes.RECT()
            self.user32.GetWindowRect(top, ctypes.byref(rect))
            outer = (rect.left, rect.top, rect.right, rect.bottom)
            if attempt == 0 and outer == (mon.left, mon.top, mon.right, mon.bottom):
                # Borderless fullscreen: no chrome to measure and SetWindowPos is ignored.
                return (False, surface, 'fullscreen')
            (x, y, w, h) = fit_16_9(surface, outer, work)
            logger.info('Resize to 16:9: surface %dx%d, window -> %dx%d at (%d,%d)', surface[0], surface[1], w, h, x, y)
            self.user32.SetWindowPos(top, 0, x, y, w, h, _SWP_NOZORDER | _SWP_NOACTIVATE)
            time.sleep(_RESIZE_SETTLE_SECONDS)
            surface = self.window_pixel_size(self.hwnd)
            if surface is None:
                return (False, None, 'not_found')
            if abs(surface[0] / surface[1] - 16 / 9) < 0.005:
                break
        if resolve_aspect_key(*surface) != ASPECT_16_9:
            logger.warning('Resize to 16:9: surface is %dx%d after resizing — the game keeps its own aspect', *surface)
            return (False, surface, 'not_16_9_after_resize')
        return (True, surface, 'ok')


    def _top(self):
        return self.user32.GetAncestor(self.hwnd, _GA_ROOT) or self.hwnd


    def is_minimized(self):
        '''A minimized window has no surface to capture: PrintWindow returns black.'''
        if self.use_adb:
            return False
        if not self.hwnd:
            self.find_window()
        return bool(self.hwnd and self.user32.IsIconic(self._top()))


    def hide_offscreen(self):
        '''Park the game window left of every monitor. Capture (PrintWindow) and input
(SendMessage) do not need it on screen, and unlike minimizing it keeps rendering.
The old position is saved so :meth:`show_back` — or the next PixelChief start — puts it
back even if PixelChief closes meanwhile. Returns ``(ok, reason)``.'''
        if self.use_adb:
            return (False, 'adb')
        if not self.hwnd and not self.find_window():
            return (False, 'not_found')
        if self.is_minimized():
            return (False, 'minimized')
        top = self._top()
        rect = wintypes.RECT()
        self.user32.GetWindowRect(top, ctypes.byref(rect))
        left_edge = self.user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)
        if rect.right <= left_edge:
            return (True, 'already_hidden')
        _hidden_marker().write_text(json.dumps({'x': rect.left, 'y': rect.top}), encoding = 'utf-8')
        x = left_edge - (rect.right - rect.left) - _OFFSCREEN_GAP
        self.user32.SetWindowPos(top, 0, x, rect.top, 0, 0, _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE)
        logger.info('Game window hidden off-screen at x=%d (was %d,%d)', x, rect.left, rect.top)
        return (True, 'ok')


    def show_back(self):
        '''Undo :meth:`hide_offscreen`. Returns ``(ok, reason)``.'''
        marker = _hidden_marker()
        if not marker.is_file():
            return (False, 'not_hidden')
        if self.use_adb or (not self.hwnd and not self.find_window()):
            return (False, 'not_found')  # marker kept: the next start with the game open retries
        try:
            pos = json.loads(marker.read_text(encoding = 'utf-8'))
            (x, y) = (int(pos['x']), int(pos['y']))
        except (OSError, ValueError, KeyError, TypeError):
            (x, y) = (0, 0)
        self.user32.SetWindowPos(self._top(), 0, x, y, 0, 0, _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE)
        marker.unlink(missing_ok = True)
        logger.info('Game window back at (%d,%d)', x, y)
        return (True, 'ok')


    def _resolve_hwnd(self, selection):
        '''Resolve the game-surface HWND from a pinned selection, or auto-detect when unset.'''
        if not selection.is_set():
            return self._auto_detect_child()
        wanted_title = selection.title.strip().lower()
        for cand in self.enumerate_windows():
            if wanted_title and cand.title.strip().lower() != wanted_title:
                continue
            if selection.top_class and cand.top_class != selection.top_class:
                continue
            (surface_hwnd, _) = self._resolve_surface(cand.top_hwnd, cand.top_class, selection.child_class)
            if not surface_hwnd:
                continue
            self.enumerate_windows()
            return surface_hwnd
        return 0

    
    def _auto_detect_child(self):
        """Default Google Play Games detection: a 'Clash of Clans' window with a CROSVM surface.

The surface may be a descendant (under an ``HwndWrapper`` shell) or the top-level window
itself. The CROSVM requirement alone excludes Chromium hosts (Discord, Chrome) that merely
share the title substring, so no outer-class gate is needed.
"""
        name = self.window_name.lower()
        for cand in self.enumerate_windows():
            if not cand.is_game:
                continue
            if name and name not in cand.title.lower():
                continue
            self.enumerate_windows()
            return cand.child_hwnd
        return 0

    
    def get_outer_pixel_size(self):
        '''
Outer window size in pixels (``GetWindowRect``), same basis as :meth:`screenshot`.
'''
        if self.use_adb:
            if self._capture_size is None:
                self.screenshot()
            return self._capture_size
        if not self.hwnd and self.find_window():
            return None
        
        try:
            rect = wintypes.RECT()
            self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                return None
            return (int(w), int(h))
        except Exception:
            return None


    
    def screenshot(self):
        '''Captures a screenshot of the window. Raises on a minimized Google Play Games window:
its capture is black, and a bot working on black frames clicks blind.'''
        if self.use_adb:
            from app.config import resolve_aspect_key
            frame = self.adb.screenshot()
            h, w = frame.shape[:2]
            if resolve_aspect_key(w, h) is None:
                raise RuntimeError(f'Android capture {w}x{h} unsupported: use landscape 16:9 or 16:10.')
            self._capture_size = (w, h)
            return frame
        if not self.hwnd and self.find_window():
            return None
        if self.is_minimized():
            raise RuntimeError(MINIMIZED_MESSAGE)
        
        try:
            rect = wintypes.RECT()
            self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 0 or height <= 0:
                return None
            hwndDC = self.user32.GetWindowDC(self.hwnd)
            mfcDC = self.gdi32.CreateCompatibleDC(hwndDC)
            hbitmap = self.gdi32.CreateCompatibleBitmap(hwndDC, width, height)
            self.gdi32.SelectObject(mfcDC, hbitmap)
            PW_RENDERFULLCONTENT = 2
            self.user32.PrintWindow(self.hwnd, mfcDC, PW_RENDERFULLCONTENT)
            
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ('biSize', wintypes.DWORD),
                    ('biWidth', ctypes.c_long),
                    ('biHeight', ctypes.c_long),
                    ('biPlanes', wintypes.WORD),
                    ('biBitCount', wintypes.WORD),
                    ('biCompression', wintypes.DWORD),
                    ('biSizeImage', wintypes.DWORD),
                    ('biXPelsPerMeter', ctypes.c_long),
                    ('biYPelsPerMeter', ctypes.c_long),
                    ('biClrUsed', wintypes.DWORD),
                    ('biClrImportant', wintypes.DWORD)]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = width
            bmi.biHeight = -height
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0
            buf_size = width * height * 4
            buffer = (ctypes.c_byte * buf_size)()  # [recovered: decompiler dropped the array-type parens; caused every capture to fail]
            self.gdi32.GetDIBits(hwndDC, hbitmap, 0, height, ctypes.byref(buffer), ctypes.byref(bmi), 0)
            img = Image.frombuffer('RGBA', (width, height), bytes(buffer), 'raw', 'BGRA', 0, 1)
            frame = np.array(img)
            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            else:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            self.gdi32.DeleteObject(hbitmap)
            self.gdi32.DeleteDC(mfcDC)
            self.user32.ReleaseDC(self.hwnd, hwndDC)
            return frame
        except Exception as e:
            logger.error(f'''Screenshot failed: {e}''')
            return None
            e = None
            del e

