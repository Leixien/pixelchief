import os
import sys
from pathlib import Path

def get_resource_path(relative_path):
    '''Get absolute path to resource, works for dev and for PyInstaller.'''
    
    try:
        base_path = Path(sys._MEIPASS)
        return base_path / relative_path
    except Exception:
        base_path = Path(__file__).resolve().parent.parent.parent
        return base_path / relative_path



APP_NAME = 'BasePilot'
_LEGACY_DATA_DIR_NAME = 'ClashAutoLoot'  # pre-rebrand data dir; migrated on first use
_migration_checked = False


def _legacy_data_dir():
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA')
        if local:
            return Path(local) / _LEGACY_DATA_DIR_NAME
    return Path.home() / '.local' / 'share' / _LEGACY_DATA_DIR_NAME


def _maybe_migrate_legacy_data(new_dir):
    '''One-time settings migration from the pre-rebrand data dir: copy the small
    user-state files (settings, player list, window pin, display restore) — never
    logs or debug frames. Idempotent: skipped once the new dir holds settings.'''
    global _migration_checked
    if _migration_checked:
        return
    _migration_checked = True
    old_dir = _legacy_data_dir()
    if not old_dir.is_dir() or (new_dir / 'settings.json').exists():
        return
    import shutil
    ensure_dir(new_dir)
    for item in old_dir.glob('*.json'):
        try:
            shutil.copy2(item, new_dir / item.name)
        except OSError:
            pass
    for item in old_dir.glob('*.devmode'):
        try:
            shutil.copy2(item, new_dir / item.name)
        except OSError:
            pass


def get_user_app_data_dir():
    '''Per-user writable data (Windows: LOCALAPPDATA\\BasePilot).'''
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA')
        if local:
            path = Path(local) / APP_NAME
        else:
            path = Path.home() / '.local' / 'share' / APP_NAME
    else:
        path = Path.home() / '.local' / 'share' / APP_NAME
    _maybe_migrate_legacy_data(path)
    return path


def get_log_path():
    '''Path to the rotating ``basepilot.log`` in the per-user data dir.'''
    ensure_dir(get_user_app_data_dir())
    return get_user_app_data_dir() / 'basepilot.log'


# Back-compat alias (old name used across the decompiled tree).
get_autoloot_log_path = get_log_path


def get_template_path(template_name):
    '''
Return ``templates/<16_10|16_9>/…`` for the active aspect (see :class:`app.config.Config`).
``template_name`` should be a filename like ``attack.png`` (not a subpath with ``..``).
'''
    from app.config import Config
    sub = Config().aspect_key
    return get_resource_path(f'''templates/{sub}/{template_name}''')


def ensure_dir(path):
    '''Ensure a directory exists.'''
    path.mkdir(parents = True, exist_ok = True)

