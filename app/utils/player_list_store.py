'''Persist multi-run player list (JSON). Stored under LOCALAPPDATA (see get_player_list_path).'''
from __future__ import annotations
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, List
from app.utils.common import ensure_dir, get_user_app_data_dir

@dataclass
class PlayerEntry:
    name: str = 15  # NOTE: original shipped this odd default (verified in bytecode, not corruption); name is always passed explicitly
    enabled: bool = True


def _legacy_player_list_paths():
    '''Older locations next to exe or repo root.'''
    if getattr(sys, 'frozen', False):
        return [
            Path(sys.executable).parent / 'player_list.json']
    return [
        Path(__file__).resolve().parent.parent.parent / 'player_list.json']


def get_player_list_path():
    dest = get_user_app_data_dir() / 'player_list.json'
    ensure_dir(dest.parent)
    if not dest.is_file():
        for leg in _legacy_player_list_paths():
            if leg.is_file():
                shutil.copy2(leg, dest)
                break
    return dest


def load_players():
    path = get_player_list_path()
    if not path.is_file():
        return []
    
    try:
        raw = json.loads(path.read_text(encoding = 'utf-8'))
        if not isinstance(raw, list):
            return []
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get('name')
            if not isinstance(name, str) or not name.strip():
                continue
            enabled = bool(item.get('enabled', True))
            out.append(PlayerEntry(name = name.strip(), enabled = enabled))
        return out
    except (json.JSONDecodeError, OSError):
        return []



def save_players(players):
    path = get_player_list_path()
    path.parent.mkdir(parents = True, exist_ok = True)
    data = [ asdict(p) for p in players ]
    path.write_text(json.dumps(data, indent = 2), encoding = 'utf-8')
    return None
    p = None
