'''ADB capture and input, shared by the bot and device diagnostics.'''
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import threading

import cv2
import numpy as np


def adb_options() -> tuple[bool, str | None]:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument('--adb', action='store_true')
    parser.add_argument('--serial')
    options, _ = parser.parse_known_args()
    return options.adb or options.serial is not None or sys.platform != 'win32', options.serial


_session: AdbService | None = None
_session_lock = threading.Lock()


def get_adb_service() -> AdbService:
    '''Pin the first selected device for this process, including after disconnects.'''
    global _session
    with _session_lock:
        if _session is None:
            _session = AdbService(adb_options()[1])
        return _session


class AdbService:
    '''Address one Android device explicitly, without automatic failover.'''

    def __init__(
        self, serial: str | None = None, *, adb: str = 'adb', timeout: float = 10.0
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('ADB timeout must be finite and positive.')
        executable = shutil.which(adb)
        if executable is None:
            raise RuntimeError('ADB not found. Install Android SDK Platform Tools.')
        self._adb = executable
        self._timeout = timeout
        devices = self.list_devices()
        if serial is None:
            if len(devices) != 1:
                raise RuntimeError('Expected one ADB device; specify a serial explicitly.')
            serial = next(iter(devices))
        if not serial or serial.startswith('-') or any(c.isspace() for c in serial):
            raise ValueError('Invalid ADB serial.')
        state = devices.get(serial)
        if state != 'device':
            raise RuntimeError(f'ADB device {serial!r}: {state or "not connected"}.')
        self.serial = serial
        self._motion_supported = False

    def _run(self, *args: str) -> bytes:
        try:
            result = subprocess.run(
                [self._adb, *args], capture_output=True, check=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('ADB command timed out.') from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b'').decode('utf-8', errors='replace').strip()
            raise RuntimeError(f'ADB command failed: {detail or exc.returncode}') from exc
        except OSError as exc:
            raise RuntimeError(f'Cannot execute ADB: {exc}') from exc
        return result.stdout

    def list_devices(self) -> dict[str, str]:
        '''Return serial -> state, including offline and unauthorized devices.'''
        devices: dict[str, str] = {}
        for line in self._run('devices').decode('utf-8', errors='replace').splitlines():
            if '\t' not in line:
                continue
            serial, state = line.split('\t', 1)
            if serial and state.strip():
                devices[serial] = state.strip()
        return devices

    def screenshot(self) -> np.ndarray:
        '''Return a BGR frame in device-screen coordinates; raise on failure.'''
        data = self._run('-s', self.serial, 'exec-out', 'screencap', '-p')
        if not data:
            raise RuntimeError('ADB returned an empty screenshot.')
        try:
            frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        except cv2.error as exc:
            raise RuntimeError('ADB returned an invalid screenshot.') from exc
        if frame is None:
            raise RuntimeError('ADB returned an invalid screenshot.')
        return frame

    @staticmethod
    def _coordinate(value: int) -> str:
        if type(value) is not int or value < 0:
            raise ValueError('Coordinates must be non-negative integers.')
        return str(value)

    def tap(self, x: int, y: int) -> None:
        '''Tap at device-screen pixel coordinates.'''
        self._run(
            '-s', self.serial, 'shell', 'input', 'tap',
            self._coordinate(x), self._coordinate(y),
        )

    def back(self) -> None:
        '''Press the Android Back button.'''
        self._run('-s', self.serial, 'shell', 'input', 'keyevent', 'BACK')

    def require_motion_support(self) -> None:
        if not self._motion_supported:
            help_text = self._run('-s', self.serial, 'shell', 'input', 'help')
            if b'motionevent' not in help_text:
                raise RuntimeError('Android input motionevent is required for held drags.')
            self._motion_supported = True

    def motion(self, action: str, x: int, y: int) -> None:
        if action not in ('DOWN', 'MOVE', 'UP'):
            raise ValueError('Motion action must be DOWN, MOVE, or UP.')
        points = [self._coordinate(x), self._coordinate(y)]
        self.require_motion_support()
        self._run('-s', self.serial, 'shell', 'input', 'motionevent', action, *points)

    def swipe(
        self, x1: int, y1: int, x2: int, y2: int, *, duration_ms: int = 500
    ) -> None:
        '''Send one complete swipe, including touch down and release.'''
        if type(duration_ms) is not int or duration_ms <= 0:
            raise ValueError('Swipe duration must be a positive integer in milliseconds.')
        points = [self._coordinate(value) for value in (x1, y1, x2, y2)]
        self._run(
            '-s', self.serial, 'shell', 'input', 'swipe', *points, str(duration_ms),
        )


def _self_check() -> None:
    '''Check command routing and failures with simulated ADB; never use a device.'''
    from collections.abc import Callable
    from unittest.mock import Mock, patch

    def reply(stdout: bytes = b'') -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=b'')

    def expect_error(
        error: type[Exception], action: Callable[..., object],
        *args: object, **kwargs: object,
    ) -> None:
        try:
            action(*args, **kwargs)
        except error:
            return
        raise AssertionError(f'Expected {error.__name__}')

    with patch.object(shutil, 'which', return_value='adb'), patch.object(
        subprocess, 'run'
    ) as run:
        run.return_value = reply(b'List of devices attached\nphone\tdevice\n')
        service = AdbService()
        assert service.serial == 'phone'
        frame = np.full((2, 3, 3), (10, 20, 30), dtype=np.uint8)
        encoded, png = cv2.imencode('.png', frame)
        assert encoded
        run.return_value = reply(png.tobytes())
        assert np.array_equal(service.screenshot(), frame)
        assert run.call_args.args[0] == ['adb', '-s', 'phone', 'exec-out', 'screencap', '-p']
        service.tap(1, 2)
        assert run.call_args.args[0] == ['adb', '-s', 'phone', 'shell', 'input', 'tap', '1', '2']
        service.swipe(1, 2, 3, 4, duration_ms=250)
        assert run.call_args.args[0] == [
            'adb', '-s', 'phone', 'shell', 'input', 'swipe', '1', '2', '3', '4', '250',
        ]
        assert run.call_args.kwargs == {'capture_output': True, 'check': True, 'timeout': 10.0}
        run.return_value = reply(b'motionevent <DOWN|UP|MOVE>')
        for action in ('DOWN', 'MOVE', 'UP'):
            service.motion(action, 1, 2)
            assert run.call_args.args[0] == [
                'adb', '-s', 'phone', 'shell', 'input', 'motionevent', action, '1', '2',
            ]
        expect_error(ValueError, service.motion, 'INVALID', 1, 2)
        service._motion_supported = False
        run.return_value = reply(b'tap swipe')
        expect_error(RuntimeError, service.require_motion_support)
        count = run.call_count
        for invalid in (-1, 1.5, True, '1; reboot'):
            expect_error(ValueError, service.tap, invalid, 0)
            expect_error(ValueError, service.swipe, 0, 0, 1, 1, duration_ms=invalid)
        expect_error(ValueError, service.swipe, 0, 0, 1, 1, duration_ms=0)
        assert run.call_count == count
        for data in (b'', b'not a PNG'):
            run.return_value = reply(data)
            expect_error(RuntimeError, service.screenshot)
        for state in ('offline', 'unauthorized'):
            run.return_value = reply(f'phone\t{state}\n'.encode())
            expect_error(RuntimeError, AdbService, 'phone')
        run.return_value = reply(b'phone\tdevice\nother\tdevice\n')
        expect_error(RuntimeError, AdbService)
        assert AdbService('phone').serial == 'phone'
        expect_error(RuntimeError, AdbService, 'missing')
        run.return_value = reply(b'')
        expect_error(RuntimeError, AdbService)
        for failure in (
            subprocess.TimeoutExpired('adb', 10),
            subprocess.CalledProcessError(1, 'adb', stderr=b'device disconnected'),
            FileNotFoundError('adb'),
        ):
            run.side_effect = failure
            count = run.call_count
            expect_error(RuntimeError, service.tap, 0, 0)
            assert run.call_count == count + 1
            assert run.call_args.args[0][1:3] == ['-s', 'phone']
    with patch.object(shutil, 'which', return_value=None):
        expect_error(RuntimeError, AdbService)
    with patch('app.utils.logger.setup_logger'):
        from app.services.input import InputService
    window = Mock(use_adb=True, hwnd=0)
    window.get_outer_pixel_size.return_value = (100, 100)
    stop = threading.Event()
    inputs = InputService(window, stop)
    inputs.mouse_down(-1, 100)
    inputs.move(5, 6)
    inputs.mouse_up(5, 6)
    assert [c.args for c in window.adb.motion.call_args_list] == [
        ('DOWN', 0, 99), ('MOVE', 5, 6), ('UP', 5, 6),
    ]
    inputs.mouse_down(10, 20)
    stop.set()
    expect_error(InterruptedError, inputs.move, 30, 40)
    assert window.adb.motion.call_args.args == ('UP', 10, 20)
    assert inputs._adb_touch is None
    stop.clear()
    window.adb.motion.side_effect = [RuntimeError('connection lost'), None]
    expect_error(RuntimeError, inputs.mouse_down, 1, 2)
    assert window.adb.motion.call_args.args == ('UP', 1, 2)
    assert inputs._adb_touch is None
    print('ADB simulated check passed.')


if __name__ == '__main__':
    import sys

    if sys.argv[1:] != ['--check']:
        raise SystemExit('Usage: python -m app.services.adb --check')
    _self_check()
