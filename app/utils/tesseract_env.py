'''Resolve Tesseract OCR for development and for PyInstaller one-file builds.'''
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path
from app.utils.logger import setup_logger
logger = setup_logger('TesseractEnv')

def _patch_pytesseract_hidden_console():
    '''Hide the console window when ``tesseract.exe`` is spawned from a GUI / windowed process.'''
    if sys.platform != 'win32':
        return None
    flag = getattr(subprocess, 'CREATE_NO_WINDOW', None)
    if flag is None:
        return None
    
    try:
        import pytesseract.pytesseract
        pt = pytesseract.pytesseract
        _orig = pt.subprocess_args
        
        def subprocess_args(include_stdout = True):
            kwargs = _orig(include_stdout)
            prev = int(kwargs.get('creationflags', 0))
            kwargs['creationflags'] = prev | flag
            return kwargs

        pt.subprocess_args = subprocess_args
        return None
    except ImportError:
        return None



def _tessdata_dir(install_root):
    '''Directory that contains ``*.traineddata`` (Tesseract expects TESSDATA_PREFIX to point here on Windows).'''
    return install_root / 'tessdata'


def _configure_tessdata(install_root: Path) -> None:
    td = _tessdata_dir(install_root)
    if td.is_dir():
        os.environ.setdefault('TESSDATA_PREFIX', str(td.resolve()) + os.sep)


def configure_tesseract():
    '''
Point pytesseract at tesseract.exe and set TESSDATA_PREFIX to the ``tessdata`` folder
(where ``eng.traineddata`` lives), not the install root.

Resolution order:
1. ``TESSERACT_CMD`` env var (full path to tesseract.exe)
2. Frozen app: ``sys._MEIPASS/tesseract.exe`` and ``sys._MEIPASS/tessdata/``
3. Dev default: ``C:\\Program Files\\Tesseract-OCR\\tesseract.exe``
4. System ``tesseract`` executable on PATH (all platforms)
'''
    
    try:
        import pytesseract
        _patch_pytesseract_hidden_console()
        if os.environ.get('TESSERACT_CMD'):
            cmd = Path(shutil.which(os.environ['TESSERACT_CMD']) or os.environ['TESSERACT_CMD'])
            pytesseract.pytesseract.tesseract_cmd = str(cmd)
            td = _tessdata_dir(cmd.parent)
            _configure_tessdata(cmd.parent)
            logger.debug('Tesseract from TESSERACT_CMD: %s, tessdata=%s', cmd, td)
            return None
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base = Path(sys._MEIPASS)
            bundled = base / 'tesseract.exe'
            if bundled.is_file():
                pytesseract.pytesseract.tesseract_cmd = str(bundled)
                td = _tessdata_dir(base)
                _configure_tessdata(base)
                logger.debug('Tesseract bundled at %s, tessdata=%s', bundled, td)
                return None
        win = Path('C:\\Program Files\\Tesseract-OCR\\tesseract.exe')
        if win.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(win)
            td = _tessdata_dir(win.parent)
            _configure_tessdata(win.parent)
            logger.debug('Tesseract dev install: %s, tessdata=%s', win, td)
            return None
        system = shutil.which('tesseract')
        if system:
            pytesseract.pytesseract.tesseract_cmd = system
            return None
        logger.error('Tesseract not found. Install Tesseract OCR with English language data and add it to PATH, or set TESSERACT_CMD.')
        return None
    except ImportError:
        return None

