import ctypes
import time
import random
import math
from typing import Tuple
from app.services.window import WindowService, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEMOVE, MK_LBUTTON, WM_MOUSEWHEEL, WHEEL_DELTA
from app.utils.logger import setup_logger
logger = setup_logger('InputService')

class InputService:
    '''Handles mouse and keyboard injection.'''
    
    def __init__(self, window_service, stop_event = None):
        self.window_service = window_service
        self.stop_event = stop_event
        self.user32 = None if window_service.use_adb else ctypes.windll.user32
        self._adb_touch: tuple[int, int] | None = None

    def _check_adb_stop(self) -> None:
        if self.stop_event and self.stop_event.is_set():
            self.release_touch()
            raise InterruptedError('ADB input stopped')

    def release_touch(self) -> None:
        if self._adb_touch is not None:
            try:
                self.window_service.adb.motion('UP', *self._adb_touch)
            except RuntimeError:
                logger.warning('Could not release ADB touch', exc_info=True)
            finally:
                self._adb_touch = None

    def _adb_motion(self, action: str, x: int | float, y: int | float) -> None:
        if action != 'UP':
            self._check_adb_stop()
        point = self._clamp_to_capture(x, y)
        self._adb_touch = point
        try:
            self.window_service.adb.motion(action, *point)
        except Exception:
            self.release_touch()
            raise
        if action == 'UP':
            self._adb_touch = None

    
    def _clamp_to_capture(self, x, y):
        '''
Clamp client-style coordinates into the current captured window rectangle
(:meth:`WindowService.get_outer_pixel_size`, same outer size as screenshots).
'''
        sz = self.window_service.get_outer_pixel_size()
        if not sz:
            return (int(x), int(y))
        (w, h) = sz
        if w <= 1 or h <= 1:
            return (int(x), int(y))
        cx = max(0, min(w - 1, int(x)))
        cy = max(0, min(h - 1, int(y)))
        return (cx, cy)

    
    def _make_lparam(self, x, y):
        (xc, yc) = self._clamp_to_capture(x, y)
        return yc << 16 | xc & 65535

    
    def _client_to_screen(self, x, y):
        '''Map capture/client coords to screen coords for ``WM_MOUSEWHEEL``.'''
        hwnd = self.window_service.hwnd
        if not hwnd:
            return self._clamp_to_capture(x, y)
        (xc, yc) = self._clamp_to_capture(x, y)
        
        class POINT(ctypes.Structure):
            _fields_ = [
                ('x', ctypes.c_long),
                ('y', ctypes.c_long)]

        pt = POINT(xc, yc)
        if not self.user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return (xc, yc)
        return (int(pt.x), int(pt.y))

    
    def _make_wheel_lparam(self, screen_x, screen_y):
        '''``WM_MOUSEWHEEL`` lParam uses signed screen coordinates.'''
        sx = int(screen_x) & 65535
        sy = int(screen_y) & 65535
        return sy << 16 | sx

    
    def click(self, x, y, pause = 1, rand = True):
        '''Performs a click with optional randomization and delay.'''
        if rand:
            x += random.randint(-15, 15)
            y += random.randint(-15, 15)
        self._inject_click(x, y)
        sleep_time = random.uniform(pause - pause * 0.2, pause + pause * 0.2)
        time.sleep(max(0.1, sleep_time))

    
    def _inject_click(self, x, y):
        if self.window_service.use_adb:
            self._check_adb_stop()
            self.window_service.adb.tap(*self._clamp_to_capture(x, y))
            return
        hwnd = self.window_service.hwnd
        if not hwnd:
            return None
        lparam = self._make_lparam(int(x), int(y))
        self.user32.SendMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        self.user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)

    
    def click_at(self, x, y, rand = False):
        '''Single mouse down/up at (x, y) with no delay (for chained clicks with custom timing).'''
        if rand:
            x += random.randint(-15, 15)
            y += random.randint(-15, 15)
        self._inject_click(int(x), int(y))

    
    def mouse_down(self, x, y):
        if self.window_service.use_adb:
            return self._adb_motion('DOWN', x, y)
        hwnd = self.window_service.hwnd
        if not hwnd:
            return None
        self.user32.SendMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, self._make_lparam(x, y))

    
    def mouse_up(self, x, y):
        if self.window_service.use_adb:
            if self._adb_touch is not None:
                self._adb_motion('UP', x, y)
            return
        hwnd = self.window_service.hwnd
        if not hwnd:
            return None
        self.user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, self._make_lparam(x, y))

    
    def move(self, x, y, wparam = 0):
        '''WM_MOUSEMOVE. Use ``wparam=MK_LBUTTON`` only while simulating a held drag (see ``human_move``).'''
        if self.window_service.use_adb:
            # ponytail: one ADB process per move; use a persistent input channel if latency limits deployment.
            if self._adb_touch is not None:
                self._adb_motion('MOVE', x, y)
            return
        hwnd = self.window_service.hwnd
        if not hwnd:
            return None
        self.user32.SendMessageW(hwnd, WM_MOUSEMOVE, wparam, self._make_lparam(x, y))

    
    def human_move(self, x1, y1, x2, y2, duration = 0.5):
        '''Simulates human-like mouse movement using a Bezier curve and easing.'''
        hwnd = self.window_service.hwnd
        if not hwnd and not self.window_service.use_adb:
            return None
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        offset = dist * random.uniform(0.02, 0.15)
        cx = mx + random.uniform(-offset, offset)
        cy = my + random.uniform(-offset, offset)
        start_time = time.perf_counter()
        while True:  # [recovered: decompiler collapsed this while-loop into an `if`, so the drag sent only ~2 move events -> troops never spread]
            if self.stop_event and self.stop_event.is_set():
                break
            current_time = time.perf_counter()
            elapsed = current_time - start_time
            if elapsed >= duration:
                break
            t = elapsed / duration
            ease = -(math.cos(math.pi * t) - 1) / 2
            u = 1 - ease
            x = u ** 2 * x1 + 2 * u * ease * cx + ease ** 2 * x2
            y = u ** 2 * y1 + 2 * u * ease * cy + ease ** 2 * y2
            self.move(int(x), int(y), MK_LBUTTON)
            if self.stop_event:
                self.stop_event.wait(0.005)
            else:
                time.sleep(0.005)
        self.move(x2, y2, MK_LBUTTON)

    
    def scroll(self, x, y, amount, *, upward = False):
        if self.window_service.use_adb:
            x1, y1 = self._clamp_to_capture(x, y)
            _, height = self.window_service.get_outer_pixel_size()
            x2, y2 = self._clamp_to_capture(x, y1 + int(height * (0.12 if upward else -0.12)))
            for _ in range(amount):
                self._check_adb_stop()
                self.window_service.adb.swipe(x1, y1, x2, y2, duration_ms=200)
            return
        hwnd = self.window_service.hwnd
        if not hwnd:
            return None
        delta = int(WHEEL_DELTA if upward else -WHEEL_DELTA)
        wparam = delta << 16
        (sx, sy) = self._client_to_screen(x, y)
        lparam = self._make_wheel_lparam(sx, sy)
        for _ in range(amount):
            self.user32.SendMessageW(hwnd, WM_MOUSEWHEEL, wparam, lparam)
            time.sleep(random.uniform(0.05, 0.2))
