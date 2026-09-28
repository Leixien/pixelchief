'''ADB capture and input, shared by the bot and device diagnostics.'''
from __future__ import annotations

import argparse
import atexit
import math
import re
import shutil
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
from functools import cache
from pathlib import Path

GAME_SOURCE_GPG = 'gpg'
GAME_SOURCE_BLUESTACKS = 'bluestacks'
_BLUESTACKS_DEFAULT_PORT = 5555


def _game_source_path() -> Path:
    from app.utils.common import get_user_app_data_dir
    return get_user_app_data_dir() / 'game_source.json'


@cache
def saved_game_source() -> str:
    '''Where the game runs, as chosen in Settings. Read once: a change needs a restart.'''
    try:
        import json
        source = json.loads(_game_source_path().read_text(encoding='utf-8')).get('source')
    except (OSError, ValueError, AttributeError):
        return GAME_SOURCE_GPG
    return source if source in (GAME_SOURCE_GPG, GAME_SOURCE_BLUESTACKS) else GAME_SOURCE_GPG


def save_game_source(source: str) -> None:
    import json
    path = _game_source_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'source': source}), encoding='utf-8')


def adb_options() -> tuple[bool, str | None]:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument('--adb', action='store_true')
    parser.add_argument('--serial')
    options, _ = parser.parse_known_args()
    use = options.adb or options.serial is not None or sys.platform != 'win32'
    return use or saved_game_source() == GAME_SOURCE_BLUESTACKS, options.serial


def _bluestacks_dirs() -> tuple[Path, Path]:
    '''``(install dir, data dir)`` of BlueStacks 5, from the registry or the default paths.'''
    install = Path(r'C:\Program Files\BlueStacks_nxt')
    data = Path(r'C:\ProgramData\BlueStacks_nxt')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\BlueStacks_nxt') as key:
            install = Path(winreg.QueryValueEx(key, 'InstallDir')[0])
            data = Path(winreg.QueryValueEx(key, 'UserDefinedDir')[0])
    except (ImportError, OSError):
        pass
    return install, data


def bluestacks_adb() -> str | None:
    '''BlueStacks' own adb (HD-Adb.exe): no separate Platform Tools install needed.'''
    exe = _bluestacks_dirs()[0] / 'HD-Adb.exe'
    return str(exe) if exe.is_file() else None


def bluestacks_adb_ports(conf_text: str) -> list[int]:
    '''ADB ports of the instances in ``bluestacks.conf``, default instance first.'''
    ports = [int(p) for p in re.findall(r'^bst\.instance\.[^.]+\.status\.adb_port="(\d+)"', conf_text, re.M)]
    return sorted(set(ports)) or [_BLUESTACKS_DEFAULT_PORT]


def bluestacks_adb_disabled(conf_text: str) -> bool:
    return re.search(r'^bst\.enable_adb_access="0"', conf_text, re.M) is not None


def connect_bluestacks(adb: str) -> str:
    '''``adb connect`` to the running BlueStacks instance; returns its serial.
    BlueStacks also lists itself as ``emulator-5554``, so the explicit TCP serial is what
    keeps "exactly one device" true.'''
    conf = _bluestacks_dirs()[1] / 'bluestacks.conf'
    try:
        text = conf.read_text(encoding='utf-8', errors='replace')
    except OSError:
        text = ''
    if bluestacks_adb_disabled(text):
        raise RuntimeError('BlueStacks: turn on Settings -> Advanced -> Android Debug Bridge (ADB), then restart BasePilot.')
    # ponytail: first instance that answers; add an instance picker if people run several at once.
    for port in bluestacks_adb_ports(text):
        serial = f'127.0.0.1:{port}'
        subprocess.run([adb, 'connect', serial], capture_output=True, timeout=10)
        out = subprocess.run([adb, 'devices'], capture_output=True, timeout=10).stdout.decode(errors='replace')
        if f'{serial}\tdevice' in out:
            return serial
    raise RuntimeError('BlueStacks not found over ADB: open BlueStacks with Clash of Clans, and check Settings -> Advanced -> Android Debug Bridge is on.')


_session: AdbService | None = None
_session_lock = threading.Lock()


def get_adb_service() -> AdbService:
    '''Pin the first selected device for this process, including after disconnects.'''
    global _session
    with _session_lock:
        if _session is None:
            serial = adb_options()[1]
            if saved_game_source() == GAME_SOURCE_BLUESTACKS:
                adb = shutil.which('adb') or bluestacks_adb()
                if adb is None:
                    raise RuntimeError('ADB not found: install BlueStacks 5 or Android SDK Platform Tools.')
                _session = AdbService(serial or connect_bluestacks(adb), adb=adb)
            else:
                _session = AdbService(serial)
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
        self._original_size: str | None = None
        self._display_lock = threading.RLock()

    def restore_display(self) -> None:
        '''Restore only a display override owned by this session.'''
        with self._display_lock:
            if self._original_size is None:
                return
            result = self._run('-s', self.serial, 'shell', 'wm', 'size', self._original_size)
            if result.strip():
                raise RuntimeError(f'Android display restore failed: {result.decode(errors="replace")}')
            self._original_size = None
            atexit.unregister(self.restore_display)

    def prepare_display(self) -> None:
        '''Temporarily use 16:9 when the landscape capture is unsupported.'''
        from app.config import resolve_aspect_key

        with self._display_lock:
            height, width = self.screenshot().shape[:2]
            if resolve_aspect_key(width, height) is not None:
                return
            if width <= height:
                raise RuntimeError('Open the game in landscape before starting the bot.')
            sizes = self._run('-s', self.serial, 'shell', 'wm', 'size').decode()
            physical = re.search(r'Physical size:\s*(\d+)x(\d+)', sizes)
            override = re.search(r'Override size:\s*(\d+)x(\d+)', sizes)
            if physical is None or min(map(int, physical.groups())) <= 0:
                raise RuntimeError('Cannot determine the original Android display size.')
            unit = min(width // 16, height // 9)
            if unit < 1:
                raise RuntimeError('Android capture is too small for 16:9.')
            target_width, target_height = 16 * unit, 9 * unit
            if int(physical[1]) < int(physical[2]):
                target_width, target_height = target_height, target_width
            if self._original_size is None:
                self._original_size = f'{override[1]}x{override[2]}' if override else 'reset'
                atexit.register(self.restore_display)
            try:
                result = self._run(
                    '-s', self.serial, 'shell', 'wm', 'size', f'{target_width}x{target_height}',
                )
                if result.strip():
                    raise RuntimeError(f'Android display resize failed: {result.decode(errors="replace")}')
                deadline = time.monotonic() + self._timeout
                while time.monotonic() < deadline:
                    height, width = self.screenshot().shape[:2]
                    if resolve_aspect_key(width, height) is not None:
                        return
                    time.sleep(0.2)
                raise RuntimeError('Android display did not switch to landscape 16:9 in time.')
            except Exception:
                self.restore_display()
                raise

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
        with patch('app.utils.logger.setup_logger'):
            from app.config import resolve_aspect_key
        wide = np.zeros((108, 240, 3), dtype=np.uint8)
        supported = np.zeros((108, 192, 3), dtype=np.uint8)
        assert resolve_aspect_key(192, 108) is not None
        for previous in (None, '108x220'):
            sizes = b'Physical size: 108x240\n'
            if previous:
                sizes += f'Override size: {previous}\n'.encode()
            with patch.object(service, 'screenshot', side_effect=[wide, supported]), patch.object(
                service, '_run', side_effect=[sizes, b'', b''],
            ) as command:
                service.prepare_display()
                assert command.call_args.args == (
                    '-s', 'phone', 'shell', 'wm', 'size', '108x192',
                )
                service.restore_display()
                assert command.call_args.args[-1] == (previous or 'reset')
                service.restore_display()
                assert command.call_count == 3
        with patch.object(service, 'screenshot', return_value=supported), patch.object(
            service, '_run',
        ) as command:
            service.prepare_display()
            command.assert_not_called()
        with patch.object(service, 'screenshot', return_value=wide), patch.object(
            service, '_run', side_effect=[b'Physical size: 108x240\n', RuntimeError('resize failed'), b''],
        ) as command:
            expect_error(RuntimeError, service.prepare_display)
            assert command.call_args.args[-1] == 'reset'
            assert service._original_size is None
        with patch.object(service, 'screenshot', return_value=wide), patch.object(
            service, '_run', side_effect=[b'Physical size: 240x108\n', b'', b''],
        ) as command, patch.object(time, 'monotonic', side_effect=[0.0, service._timeout]):
            expect_error(RuntimeError, service.prepare_display)
            assert command.call_args_list[1].args[-1] == '192x108'
            assert command.call_args.args[-1] == 'reset'
        with patch.object(service, 'screenshot', side_effect=[wide, supported]), patch.object(
            service, '_run', side_effect=[b'Physical size: 108x240\n', b'', RuntimeError('offline'), b''],
        ):
            service.prepare_display()
            expect_error(RuntimeError, service.restore_display)
            assert service._original_size == 'reset'
            service.restore_display()
            assert service._original_size is None
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
