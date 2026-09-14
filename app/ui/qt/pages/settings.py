'''Settings page — profile preferences and manual game-window selection.'''
from __future__ import annotations
from threading import Thread
from typing import List, Optional
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QSpinBox, QVBoxLayout, QWidget
from app.config import resolve_aspect_key
from app.services.display import DisplayService
from app.services.adb import adb_options
from app.services.window import DescendantInfo, WindowCandidate, WindowService
from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import Card, PageTitle, SectionTitle, neutral_button, primary_button
from app.utils.logger import setup_logger
from app.utils.profile_settings_store import EARTHQUAKE_METHOD_OPTIONS, RESERVE_BUILDERS_MAX, WALL_UPGRADE_THRESHOLD_M_MAX, ProfileSettings, load_profile_settings, save_profile_settings
from app.utils.window_settings_store import clear_window_selection, load_window_selection, save_window_selection
logger = setup_logger('SettingsPage')

class WindowInfoDialog(QDialog):
    '''Read-only view of every child window/surface under a selected top-level window.'''
    
    def __init__(self, parent, candidate, descendants):
        super().__init__(parent)
        self.setWindowTitle('Window info')
        self.setModal(True)
        self.resize(640, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING['lg'], SPACING['lg'], SPACING['lg'], SPACING['lg'])
        layout.setSpacing(SPACING['sm'])
        header = QLabel(f'''Top-level: {candidate.title or '(no title)'}\nClass: {candidate.top_class}    hwnd={candidate.top_hwnd}''')
        header.setWordWrap(True)
        header.setStyleSheet(f'''color: {TOKENS['text']};''')
        layout.addWidget(header)
        count = len(descendants)
        surfaces = sum([ 1 for d in descendants if d.is_surface ])
        summary = QLabel(f'''{count} child window(s), {surfaces} game surface(s). Surfaces are marked [surface].''')
        summary.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        layout.addWidget(summary)
        listing = QListWidget()
        listing.setObjectName('WindowInfoList')
        mono = QFont('Consolas')
        mono.setStyleHint(QFont.StyleHint.Monospace)
        listing.setFont(mono)
        if descendants:
            for d in descendants:
                item = QListWidgetItem(d.display_label())
                if d.is_surface:
                    item.setForeground(QColor(TOKENS['primary']))
                listing.addItem(item)
        else:
            listing.addItem(QListWidgetItem('No child windows found under this window.'))
        layout.addWidget(listing, stretch = 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = neutral_button('Close', parent = self)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)



class SettingsPage(QWidget):
    _adb_result = Signal(str)
    
    def __init__(self, parent = None):
        super().__init__(parent)
        self._candidates = []
        self._use_adb, self._adb_serial = adb_options()
        self._display = None if self._use_adb else DisplayService()
        self._adb_result.connect(self._on_adb_result)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACING['lg'], SPACING['lg'], SPACING['lg'], SPACING['lg'])
        outer.setSpacing(SPACING['md'])
        outer.addWidget(PageTitle('Settings'))
        # The settings cards outgrew the fixed window (upgrade-order/reserve controls) —
        # scroll like the Run page instead of compressing cards into overlap.
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING['md'])
        layout.addWidget(self._build_earthquake_card())
        layout.addWidget(self._build_window_card())
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    
    def _build_earthquake_card(self):
        card = Card()
        card.card_layout.addWidget(SectionTitle('Earthquake placement'))
        self._earthquake = QComboBox()
        self._earthquake.addItems(list(EARTHQUAKE_METHOD_OPTIONS))
        card.card_layout.addWidget(self._earthquake)
        card.card_layout.addWidget(SectionTitle('Wall upgrade threshold'))
        wall_hint = QLabel('With "Upgrade walls" on, upgrade as soon as gold or elixir reaches this amount — before storages fill up and raids stop earning. 0 = only upgrade when storages are full.')
        wall_hint.setWordWrap(True)
        wall_hint.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        card.card_layout.addWidget(wall_hint)
        wall_row = QHBoxLayout()
        self._wall_threshold = QSpinBox()
        self._wall_threshold.setRange(0, WALL_UPGRADE_THRESHOLD_M_MAX)
        self._wall_threshold.setSuffix('M')
        self._wall_threshold.setFixedWidth(88)
        wall_row.addWidget(self._wall_threshold)
        wall_unit = QLabel('gold or elixir')
        wall_unit.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        wall_row.addWidget(wall_unit)
        wall_row.addStretch()
        card.card_layout.addLayout(wall_row)
        card.card_layout.addWidget(SectionTitle('Upgrade order'))
        order_hint = QLabel('Priciest first soaks full storages into the biggest jobs (best when the bot farms loot faster than builders free up). Dark elixir upgrades (heroes) always get first claim either way.')
        order_hint.setWordWrap(True)
        order_hint.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        card.card_layout.addWidget(order_hint)
        self._upgrade_order = QComboBox()
        self._upgrade_order.addItems(['Priciest first', 'Cheapest first'])
        card.card_layout.addWidget(self._upgrade_order)
        card.card_layout.addWidget(SectionTitle('Reserve builders'))
        reserve_hint = QLabel('With Auto upgrade on, keep this many builders free (the wall flow spends through them). Set 0 when your walls are maxed so every builder is used for upgrades.')
        reserve_hint.setWordWrap(True)
        reserve_hint.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        card.card_layout.addWidget(reserve_hint)
        reserve_row = QHBoxLayout()
        self._reserve_builders = QSpinBox()
        self._reserve_builders.setRange(0, RESERVE_BUILDERS_MAX)
        self._reserve_builders.setFixedWidth(88)
        reserve_row.addWidget(self._reserve_builders)
        reserve_unit = QLabel('builders kept free')
        reserve_unit.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        reserve_row.addWidget(reserve_unit)
        reserve_row.addStretch()
        card.card_layout.addLayout(reserve_row)
        btn_row = QHBoxLayout()
        self._btn_save = primary_button('Save', parent = card)
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)
        self._btn_reset = neutral_button('Reset', parent = card)
        self._btn_reset.clicked.connect(self._reload_earthquake)
        btn_row.addWidget(self._btn_reset)
        btn_row.addStretch()
        card.card_layout.addLayout(btn_row)
        return card

    
    def _build_adb_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle('Android device (ADB)'))
        self._adb_status = QLabel(
            f'Serial: {self._adb_serial or "auto-detect (one device required)"}\n'
            'Connect and authorize your Android device, then press Test capture.\n'
            'To choose another device, restart with --serial SERIAL.'
        )
        self._adb_status.setTextFormat(Qt.PlainText)
        self._adb_status.setWordWrap(True)
        card.card_layout.addWidget(self._adb_status)
        self._adb_test = neutral_button('Test capture', parent=card)
        self._adb_test.clicked.connect(self._test_adb)
        card.card_layout.addWidget(self._adb_test)
        return card

    def _test_adb(self) -> None:
        self._adb_test.setEnabled(False)
        self._adb_status.setText('Checking Android capture...')

        def worker() -> None:
            try:
                window = WindowService()
                frame = window.screenshot()
                h, w = frame.shape[:2]
                message = f'Serial: {window.adb.serial}\nCapture OK: {w}x{h} (BGR).'
            except Exception as exc:
                message = str(exc)
            self._adb_result.emit(message)

        Thread(target=worker, daemon=True, name='AdbCaptureCheck').start()

    @Slot(str)
    def _on_adb_result(self, message: str) -> None:
        self._adb_status.setText(message)
        self._adb_test.setEnabled(True)

    def _build_window_card(self):
        if self._use_adb:
            return self._build_adb_card()
        card = Card()
        card.card_layout.addWidget(SectionTitle('Game window'))
        hint = QLabel("If the bot can't find Clash of Clans, pick the Google Play Games window below and press Test. Windows with a game surface are listed first.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        card.card_layout.addWidget(hint)
        self._window_list = QListWidget()
        self._window_list.setObjectName('WindowList')
        self._window_list.setMinimumHeight(140)
        self._window_list.currentRowChanged.connect((lambda _: self._update_window_buttons()))
        card.card_layout.addWidget(self._window_list)
        self._window_status = QLabel('')
        self._window_status.setWordWrap(True)
        self._window_status.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        card.card_layout.addWidget(self._window_status)
        row = QHBoxLayout()
        self._btn_refresh = neutral_button('Refresh', parent = card)
        self._btn_refresh.clicked.connect(self._refresh_windows)
        row.addWidget(self._btn_refresh)
        self._btn_test = neutral_button('Test', parent = card)
        self._btn_test.clicked.connect(self._on_test_window)
        row.addWidget(self._btn_test)
        self._btn_info = neutral_button('Info', parent = card)
        self._btn_info.clicked.connect(self._on_window_info)
        row.addWidget(self._btn_info)
        self._btn_use = primary_button('Use this window', parent = card)
        self._btn_use.clicked.connect(self._on_use_window)
        row.addWidget(self._btn_use)
        row.addStretch()
        self._btn_auto = neutral_button('Auto-detect', parent = card)
        self._btn_auto.clicked.connect(self._on_auto_detect)
        row.addWidget(self._btn_auto)
        card.card_layout.addLayout(row)
        disp_hint = QLabel("Ultrawide / 21:9 monitor? Google Play Games locks the game to your display's aspect at launch, so it renders 21:9 (unsupported). Fix: click below to switch to 16:9, FULLY close and reopen Clash, then restore your display — the running game stays 16:9.")
        disp_hint.setWordWrap(True)
        disp_hint.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        card.card_layout.addWidget(disp_hint)
        disp_row = QHBoxLayout()
        self._btn_disp_169 = neutral_button('Switch display to 16:9', parent = card)
        self._btn_disp_169.clicked.connect(self._on_switch_display_169)
        disp_row.addWidget(self._btn_disp_169)
        self._btn_disp_restore = neutral_button('Restore my display', parent = card)
        self._btn_disp_restore.clicked.connect(self._on_restore_display)
        disp_row.addWidget(self._btn_disp_restore)
        disp_row.addStretch()
        card.card_layout.addLayout(disp_row)
        return card

    
    def showEvent(self, event):
        super().showEvent(event)
        self._reload_earthquake()
        self._refresh_windows()

    
    def _reload_earthquake(self):
        settings = load_profile_settings()
        idx = self._earthquake.findText(settings.earthquake_method)
        if idx >= 0:
            self._earthquake.setCurrentIndex(idx)
        self._wall_threshold.setValue(settings.wall_upgrade_threshold_m)
        self._reserve_builders.setValue(settings.reserve_builders)
        self._upgrade_order.setCurrentIndex(1 if settings.upgrade_order == 'cheapest' else 0)


    def _on_save(self):
        save_profile_settings(ProfileSettings(earthquake_method = self._earthquake.currentText(), wall_upgrade_threshold_m = self._wall_threshold.value(), reserve_builders = self._reserve_builders.value(), upgrade_order = 'cheapest' if self._upgrade_order.currentIndex() == 1 else 'priciest'))
        self._flash_status_bar('Saved')

    
    def _selected_candidate(self):
        row = self._window_list.currentRow()
        if 0 <= row and row < len(self._candidates):
            pass
        else:
            return None
        return self._candidates[row]

    
    def _update_window_buttons(self):
        cand = self._selected_candidate()
        has_sel = cand is not None
        self._btn_test.setEnabled(has_sel)
        self._btn_use.setEnabled(has_sel)
        self._btn_info.setEnabled(has_sel)

    
    def _refresh_windows(self):
        if self._use_adb:
            return
        
        try:
            self._candidates = WindowService().enumerate_windows()
            saved = load_window_selection()
            self._window_list.clear()
            selected_row = -1
            for i, cand in enumerate(self._candidates):
                item = QListWidgetItem(cand.display_label())
                if not cand.is_game:
                    item.setForeground(self._muted_brush())
                self._window_list.addItem(item)
                if not saved.is_set():
                    continue
                if not cand.title.strip().lower() == saved.title.strip().lower():
                    continue
                if not saved.top_class and cand.top_class == saved.top_class:
                    continue
                selected_row = i
            if selected_row >= 0:
                self._window_list.setCurrentRow(selected_row)
            if not self._candidates:
                self._window_status.setText('No visible windows found. Open the game, then Refresh.')
            elif saved.is_set():
                self._window_status.setText(f'''Pinned window: {saved.title or '(saved)'}''')
            else:
                self._window_status.setText('Using auto-detect.')
            self._update_window_buttons()
            return None
        except Exception:
            exc = None
            logger.warning(f'''Could not enumerate windows: {exc}''')
            self._candidates = []
            exc = None
            del exc

        exc = None
        del exc

    
    def _muted_brush(self):
        return QColor(TOKENS['text_muted'])

    
    @staticmethod
    def _aspect_label(w, h):
        if not w or not h:
            return 'size unavailable'
        aspect = resolve_aspect_key(w, h)
        if aspect is None:
            return f'''{w}x{h} (not ~16:9/16:10)'''
        pretty = '16:9' if aspect == '16_9' else '16:10'
        return f'''{w}x{h} ({pretty})'''

    
    def _on_test_window(self):
        cand = self._selected_candidate()
        if cand is None:
            return None
        if not cand.is_game:
            self._window_status.setText('No Google Play Games surface (CROSVM) under this window — pick the game window.')
            return None
        ws = WindowService()
        surface_size = ws.window_pixel_size(cand.child_hwnd)
        if surface_size is None:
            self._window_status.setText('Could not read the window size. Is the game minimized?')
            return None
        sub_size = None
        
        try:
            for d in ws.enumerate_descendants(cand.top_hwnd):
                if not d.cls.lower() == 'subwin':
                    continue
                sub_size = (d.width, d.height)
                ws.enumerate_descendants(cand.top_hwnd)
            (sw, sh) = surface_size
            lines = [
                f'''Capture target {cand.child_class}: {self._aspect_label(sw, sh)}''']
            if not sub_size is None:
                lines.append(f'''Inner subWin: {self._aspect_label(*sub_size)}''')
            if resolve_aspect_key(sw, sh) is None:
                lines.append('Surface aspect unsupported — try resizing the game window.')
            else:
                lines.append('Surface OK to use.')
            self._window_status.setText('\n'.join(lines))
            return None
        except Exception:
            exc = None
            logger.warning(f'''Could not inspect subWin: {exc}''')
            exc = None
            del exc

        exc = None
        del exc

    
    def _on_switch_display_169(self):
        (ok, size, reason) = self._display.switch_to_16_9()
        if ok and reason == 'already_16_9':
            self._window_status.setText('Your display is already 16:9 — just (re)launch Clash in Google Play Games and it will render 16:9.')
        elif ok:
            self._window_status.setText(f'''Display set to {size[0]}x{size[1]} (16:9). Now FULLY close and reopen Clash in Google Play Games, then click "Restore my display".''')
        elif reason == 'no_16_9_mode':
            self._window_status.setText('Your display driver offers no 16:9 mode — use a 16:9 monitor for the game instead.')
        else:
            self._window_status.setText('Could not switch the display resolution.')
        self._flash_status_bar('Display set to 16:9' if ok else 'Display switch failed')


    def _on_restore_display(self):
        (ok, size, reason) = self._display.restore()
        if ok:
            self._window_status.setText(f'''Display restored to {size[0]}x{size[1]}. If you relaunched Clash while in 16:9 it stays 16:9 — press Test to confirm, then Start.''')
        elif reason == 'nothing_to_restore':
            self._window_status.setText('Nothing to restore — you have not switched your display (or it was already restored).')
        else:
            self._window_status.setText('Could not restore the display. Use Windows Settings → Display to set it back.')
        self._flash_status_bar('Display restored' if ok else 'Restore failed')


    def _on_window_info(self):
        cand = self._selected_candidate()
        if cand is None:
            return None

        try:
            descendants = WindowService().enumerate_descendants(cand.top_hwnd)
            WindowInfoDialog(self.window(), cand, descendants).exec()
            return None
        except Exception:
            exc = None
            logger.warning(f'''Could not enumerate descendants: {exc}''')
            descendants = []
            exc = None
            del exc

        exc = None
        del exc

    
    def _on_use_window(self):
        cand = self._selected_candidate()
        if cand is None:
            return None
        save_window_selection(cand.to_selection())
        self._window_status.setText(f'''Pinned: {cand.title or '(no title)'}. Press Test to verify.''')
        self._flash_status_bar('Window saved')

    
    def _on_auto_detect(self):
        clear_window_selection()
        self._window_status.setText('Cleared — using auto-detect.')
        self._flash_status_bar('Auto-detect')
        self._refresh_windows()

    
    def _flash_status_bar(self, msg):
        win = self.window()
        if isinstance(win, QMainWindow):
            if not win.statusBar() is None:
                win.statusBar().showMessage(msg, 1500)
                return None
            return None

