'''Profile preferences (JSON) under LOCALAPPDATA\\BasePilot, next to ``player_list.json``.'''
from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from app.utils.common import ensure_dir, get_user_app_data_dir
EARTHQUAKE_METHOD_CURVE = 'Curve Placement'
EARTHQUAKE_METHOD_RANDOM = 'Random Placement'
EARTHQUAKE_METHOD_OPTIONS = (EARTHQUAKE_METHOD_CURVE, EARTHQUAKE_METHOD_RANDOM)
SETTINGS_FILENAME = 'settings.json'
WALL_UPGRADE_THRESHOLD_M_DEFAULT = 3
WALL_UPGRADE_THRESHOLD_M_MAX = 20
RESERVE_BUILDERS_DEFAULT = 1
RESERVE_BUILDERS_MAX = 5
UPGRADE_ORDER_PRICIEST = 'priciest'
UPGRADE_ORDER_CHEAPEST = 'cheapest'
UPGRADE_ORDER_OPTIONS = (UPGRADE_ORDER_PRICIEST, UPGRADE_ORDER_CHEAPEST)
# Random session length. Matches the Run page spinbox range; 0 as the minimum means
# off, the same "0 = disabled" idiom the wall threshold uses.
RANDOM_MINUTES_CAP = 999
RANDOM_MINUTES_MIN_DEFAULT = 0
RANDOM_MINUTES_MAX_DEFAULT = 0
# Pause between automatic restarts; 0 as the minimum means the bot stops after one
# session, as it always did. Shares the range rules with the random session length.
REPEAT_PAUSE_MIN_DEFAULT = 0
REPEAT_PAUSE_MAX_DEFAULT = 0
# An unattended loop that keeps failing must not spin: give up after this many
# consecutive failed sessions.
REPEAT_MAX_CONSECUTIVE_FAILURES = 3

@dataclass
class ProfileSettings:
    earthquake_method: 'str' = EARTHQUAKE_METHOD_CURVE
    wall_upgrade_threshold_m: 'int' = WALL_UPGRADE_THRESHOLD_M_DEFAULT
    reserve_builders: 'int' = RESERVE_BUILDERS_DEFAULT
    upgrade_order: 'str' = UPGRADE_ORDER_PRICIEST
    random_minutes_min: 'int' = RANDOM_MINUTES_MIN_DEFAULT
    random_minutes_max: 'int' = RANDOM_MINUTES_MAX_DEFAULT
    repeat_pause_min: 'int' = REPEAT_PAUSE_MIN_DEFAULT
    repeat_pause_max: 'int' = REPEAT_PAUSE_MAX_DEFAULT


def get_settings_path():
    dest = get_user_app_data_dir() / SETTINGS_FILENAME
    ensure_dir(dest.parent)
    return dest


def _normalize_earthquake_method(raw):
    if raw == EARTHQUAKE_METHOD_RANDOM or raw == EARTHQUAKE_METHOD_CURVE:
        return str(raw)
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s == 'random placement':
            return EARTHQUAKE_METHOD_RANDOM
        if s == 'curve placement':
            return EARTHQUAKE_METHOD_CURVE
    return EARTHQUAKE_METHOD_CURVE


def _normalize_wall_threshold_m(raw):
    '''Millions of gold/elixir that trigger wall upgrades; 0 = only when storages are full.'''
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return WALL_UPGRADE_THRESHOLD_M_DEFAULT
    return max(0, min(WALL_UPGRADE_THRESHOLD_M_MAX, value))


def _normalize_upgrade_order(raw):
    if isinstance(raw, str) and raw.strip().lower() in UPGRADE_ORDER_OPTIONS:
        return raw.strip().lower()
    return UPGRADE_ORDER_PRICIEST


def _normalize_reserve_builders(raw):
    '''Builders the auto-upgrader must leave free (the wall flow spends through them).
    0 = every free builder may be used; walls-maxed accounts want 0.'''
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return RESERVE_BUILDERS_DEFAULT
    return max(0, min(RESERVE_BUILDERS_MAX, value))


def _normalize_random_range(min_raw, max_raw):
    '''``(min, max)`` clamped to 0..RANDOM_MINUTES_CAP, with max never below a live min.'''
    def clamp(raw):
        try:
            return max(0, min(RANDOM_MINUTES_CAP, int(raw)))
        except (TypeError, ValueError):
            return 0

    low, high = clamp(min_raw), clamp(max_raw)
    if low <= 0:
        return (0, high)
    return (low, max(low, high))


def load_profile_settings():
    path = get_settings_path()
    if not path.is_file():
        return ProfileSettings()

    try:
        raw = json.loads(path.read_text(encoding = 'utf-8'))
        if not isinstance(raw, dict):
            return ProfileSettings()
        rand_min, rand_max = _normalize_random_range(
            raw.get('random_minutes_min', RANDOM_MINUTES_MIN_DEFAULT),
            raw.get('random_minutes_max', RANDOM_MINUTES_MAX_DEFAULT))
        pause_min, pause_max = _normalize_random_range(
            raw.get('repeat_pause_min', REPEAT_PAUSE_MIN_DEFAULT),
            raw.get('repeat_pause_max', REPEAT_PAUSE_MAX_DEFAULT))
        return ProfileSettings(
            earthquake_method = _normalize_earthquake_method(raw.get('earthquake_method')),
            wall_upgrade_threshold_m = _normalize_wall_threshold_m(raw.get('wall_upgrade_threshold_m', WALL_UPGRADE_THRESHOLD_M_DEFAULT)),
            reserve_builders = _normalize_reserve_builders(raw.get('reserve_builders', RESERVE_BUILDERS_DEFAULT)),
            upgrade_order = _normalize_upgrade_order(raw.get('upgrade_order', UPGRADE_ORDER_PRICIEST)),
            random_minutes_min = rand_min,
            random_minutes_max = rand_max,
            repeat_pause_min = pause_min,
            repeat_pause_max = pause_max)
    except (json.JSONDecodeError, OSError):
        return ProfileSettings()  # [recovered: decompiler turned this into `return None`, crashing every caller on a corrupt settings.json]



def save_profile_settings(settings):
    path = get_settings_path()
    path.parent.mkdir(parents = True, exist_ok = True)
    rand_min, rand_max = _normalize_random_range(
        getattr(settings, 'random_minutes_min', RANDOM_MINUTES_MIN_DEFAULT),
        getattr(settings, 'random_minutes_max', RANDOM_MINUTES_MAX_DEFAULT))
    pause_min, pause_max = _normalize_random_range(
        getattr(settings, 'repeat_pause_min', REPEAT_PAUSE_MIN_DEFAULT),
        getattr(settings, 'repeat_pause_max', REPEAT_PAUSE_MAX_DEFAULT))
    normalized = ProfileSettings(
        earthquake_method = _normalize_earthquake_method(settings.earthquake_method),
        wall_upgrade_threshold_m = _normalize_wall_threshold_m(getattr(settings, 'wall_upgrade_threshold_m', WALL_UPGRADE_THRESHOLD_M_DEFAULT)),
        reserve_builders = _normalize_reserve_builders(getattr(settings, 'reserve_builders', RESERVE_BUILDERS_DEFAULT)),
        upgrade_order = _normalize_upgrade_order(getattr(settings, 'upgrade_order', UPGRADE_ORDER_PRICIEST)),
        random_minutes_min = rand_min,
        random_minutes_max = rand_max,
        repeat_pause_min = pause_min,
        repeat_pause_max = pause_max)
    payload = asdict(normalized)
    path.write_text(json.dumps(payload, indent = 2), encoding = 'utf-8')
