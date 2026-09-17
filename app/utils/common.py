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


# Templates the code looks up through `get_template_path(...).exists()`, i.e. it carries
# on without them. That is the right call for an optional signal and the wrong one for a
# silent loss of function, so each aspect folder that lacks one gets told at load time —
# templates/16_10/needgold_x.png went missing exactly this way and disabled the gem-dialog
# guard on every 16:10 display without a word.
OPTIONAL_TEMPLATES = {
    'needgold_x.png': 'buy-with-gems dialog guard — wall upgrades stay disabled without it',
    'reload.png': 'RELOAD button — cannot recover from a dropped connection without it',
    'claim_btn.png': 'daily reward popup — cannot be dismissed without it',
    'dailyreward_x.png': 'daily reward popup — cannot be dismissed without it' }
_optional_report_done = set()


def report_missing_optional_templates(aspect_key):
    """Log once per aspect which optional templates are absent, and what each one costs."""
    if not aspect_key or aspect_key in _optional_report_done:
        return None
    # Built here, not at module scope: setup_logger imports from this module, so a
    # module-level call would run while this module is still initializing.
    from app.utils.logger import setup_logger
    logger = setup_logger('Templates')
    _optional_report_done.add(aspect_key)
    missing = [(name, why) for name, why in sorted(OPTIONAL_TEMPLATES.items())
               if not get_resource_path(f'''templates/{aspect_key}/{name}''').is_file()]
    if not missing:
        logger.info('Templates: every optional template is present for %s', aspect_key)
        return None
    for name, why in missing:
        logger.warning('Templates: %s is missing for %s — %s', name, aspect_key, why)
    return None


def ensure_dir(path):
    '''Ensure a directory exists.'''
    path.mkdir(parents = True, exist_ok = True)

