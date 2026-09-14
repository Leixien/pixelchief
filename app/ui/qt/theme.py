'''BasePilot mission-control theme: OLED-dark instrument-panel QSS for the PySide6 UI.

Design system (ui-ux-pro-max "Dark Mode (OLED)" + Fira dashboard pairing): near-black
background, slate instrument surfaces, GREEN as the "autopilot engaged" accent (red is
reserved for Stop/destructive), monospace figures for data readouts, uppercase
letter-spaced micro-labels for panel sections. Fonts resolve at runtime with Windows
fallbacks (Fira Code/Sans → Cascadia → Consolas/Segoe UI).
'''
from __future__ import annotations
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

TOKENS = {
    'bg': '#020617',           # near-black canvas (OLED)
    'sidebar': '#0B1220',      # sidebar column, one step lighter than canvas
    'surface': '#0F172A',      # instrument panel / card
    'surface_hi': '#1E293B',   # raised surface, inputs
    'border': '#1E293B',
    'border_hi': '#334155',
    'text': '#F8FAFC',
    'text_muted': '#94A3B8',
    'text_faint': '#64748B',   # disabled / de-emphasized
    'primary': '#22C55E',      # autopilot-engaged green
    'primary_hov': '#16A34A',
    'primary_dim': '#0E3A22',  # green-tinted disabled fill
    'on_primary': '#04120A',   # near-black text on the green CTA
    'danger': '#EF4444',
    'danger_hov': '#DC2626',
    'success': '#22C55E',
    'warning': '#F59E0B',      # holding / idling amber
    'neutral': '#334155',
    'neutral_hov': '#3E4C63',
    'neutral_dark': '#1B2436',
    'neutral_dark_hov': '#28354A' }
SPACING = {
    'xs': 4,
    'sm': 8,
    'md': 12,
    'lg': 16,
    'xl': 24 }
RADIUS = 10
SIDEBAR_WIDTH = 184
WINDOW_DEFAULT = (900, 640)
WINDOW_MIN = (720, 520)

_SANS_CANDIDATES = ('Fira Sans', 'Segoe UI')
_MONO_CANDIDATES = ('Fira Code', 'Cascadia Code', 'Cascadia Mono', 'Consolas')
SANS_FONT = 'Segoe UI'
MONO_FONT = 'Consolas'


def _resolve_fonts():
    global SANS_FONT, MONO_FONT
    try:
        families = set(QFontDatabase.families())
    except Exception:
        return
    for name in _SANS_CANDIDATES:
        if name in families:
            SANS_FONT = name
            break
    for name in _MONO_CANDIDATES:
        if name in families:
            MONO_FONT = name
            break


def build_stylesheet():
    t = TOKENS
    return f'''
QWidget {{
    background-color: {t['bg']};
    color: {t['text']};
    font-family: '{SANS_FONT}';
    font-size: 13px;
}}
QLabel {{
    background-color: transparent;
    padding: 0;
    margin: 0;
}}
QFrame#Card {{
    background-color: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: {RADIUS}px;
}}
QFrame#Card[variant="status"] {{
    border: 1px solid #1F3D2B;
    border-left: 3px solid {t['primary']};
}}
QLabel#SectionTitle {{
    color: {t['text_muted']};
    font-weight: 600;
    font-size: 11px;
    background-color: transparent;
}}
QLabel#SectionTitle:disabled {{
    color: {t['text_faint']};
}}
QLabel#DurationUnit:disabled {{
    color: {t['text_faint']};
}}
QLabel#PageTitle {{
    font-size: 20px;
    font-weight: bold;
    color: {t['text']};
    background-color: transparent;
}}
QLabel#StatValue {{
    font-family: '{MONO_FONT}';
    font-size: 15px;
    font-weight: 600;
    color: {t['text']};
    background-color: transparent;
}}
QLabel#StatTitle {{
    color: {t['text_faint']};
    font-size: 10px;
    font-weight: 600;
    background-color: transparent;
}}
QLabel#Brand {{
    font-family: '{MONO_FONT}';
    font-size: 16px;
    font-weight: bold;
    background-color: transparent;
}}
QPushButton {{
    border: none;
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 28px;
}}
QPushButton[role="primary"] {{
    background-color: {t['primary']};
    color: {t['on_primary']};
    font-weight: bold;
}}
QPushButton[role="primary"]:hover {{
    background-color: {t['primary_hov']};
}}
QPushButton[role="primary"]:disabled {{
    background-color: {t['primary_dim']};
    color: {t['text_faint']};
}}
QPushButton[role="danger"] {{
    background-color: {t['danger']};
    color: #fff;
    font-weight: bold;
}}
QPushButton[role="danger"]:hover {{
    background-color: {t['danger_hov']};
}}
QPushButton[role="danger"]:disabled {{
    background-color: #3A1212;
    color: {t['text_faint']};
}}
QPushButton[role="neutral"] {{
    background-color: {t['neutral']};
    color: {t['text']};
}}
QPushButton[role="neutral"]:hover {{
    background-color: {t['neutral_hov']};
}}
QPushButton[role="chip"] {{
    background-color: {t['neutral_dark']};
    color: {t['text']};
    padding: 4px 10px;
    min-height: 24px;
}}
QPushButton[role="chip"]:hover {{
    background-color: {t['neutral_dark_hov']};
}}
QPushButton[role="chip"]:disabled {{
    background-color: {t['surface_hi']};
    color: {t['text_faint']};
}}
QPushButton[role="segment"] {{
    background-color: transparent;
    border: 1px solid {t['border_hi']};
    color: {t['text_muted']};
}}
QPushButton[role="segment"]:hover:!checked {{
    border-color: {t['text_muted']};
    color: {t['text']};
}}
QPushButton[role="segment"]:checked {{
    background-color: rgba(34, 197, 94, 0.16);
    color: #4ADE80;
    border-color: {t['primary']};
    font-weight: bold;
}}
QPushButton[role="segment"][underDevelopment="true"] {{
    color: {t['text_faint']};
    border-color: {t['border']};
}}
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {t['sidebar']};
    border: 1px solid {t['border_hi']};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {t['primary_hov']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {t['primary']};
}}
QComboBox QAbstractItemView {{
    background-color: {t['surface_hi']};
    border: 1px solid {t['border_hi']};
    selection-background-color: {t['neutral']};
}}
QSpinBox#DurationSpin {{
    font-family: '{MONO_FONT}';
    min-height: 28px;
    max-height: 28px;
    padding: 2px 6px;
}}
QSpinBox:disabled, QSpinBox#DurationSpin:disabled {{
    color: {t['text_faint']};
    background-color: {t['surface']};
    border-color: {t['border']};
}}
QPushButton[role="stepper"] {{
    background-color: {t['neutral_dark']};
    padding: 0;
    min-height: 13px;
    max-height: 13px;
    min-width: 22px;
    max-width: 22px;
    border-radius: 4px;
}}
QPushButton[role="stepper"]:hover {{
    background-color: {t['neutral_dark_hov']};
}}
QPushButton[role="stepper"]:pressed {{
    background-color: {t['neutral']};
}}
QPushButton[role="stepper"]:disabled {{
    background-color: {t['surface_hi']};
}}
QPushButton[role="help"] {{
    background-color: transparent;
    color: {t['text_muted']};
    padding: 0;
    min-height: 18px;
    min-width: 18px;
    max-height: 18px;
    max-width: 18px;
    border-radius: 9px;
    border: 1px solid {t['text_muted']};
    font-size: 11px;
    font-weight: bold;
}}
QPushButton[role="help"]:hover {{
    color: {t['text']};
    border-color: {t['text']};
}}
QPushButton[role="icon"] {{
    background-color: {t['neutral_dark']};
    color: {t['text']};
    padding: 0;
    min-height: 34px;
    min-width: 34px;
    max-height: 34px;
    max-width: 34px;
    border-radius: 6px;
}}
QPushButton[role="icon"]:hover {{
    background-color: {t['neutral_dark_hov']};
}}
QPushButton[role="icon"]:checked {{
    background-color: {t['neutral']};
}}
QListWidget#Sidebar {{
    background-color: {t['sidebar']};
    border: none;
    padding: 6px;
    outline: none;
}}
QListWidget#Sidebar::item {{
    padding: 10px 14px;
    border-radius: 6px;
    border-left: 3px solid transparent;
    color: {t['text_muted']};
}}
QListWidget#Sidebar::item:selected {{
    background-color: {t['surface_hi']};
    border-left: 3px solid {t['primary']};
    color: {t['text']};
    font-weight: 600;
}}
QListWidget#Sidebar::item:hover:!selected {{
    background-color: {t['surface']};
    color: {t['text']};
}}
QStatusBar {{
    background-color: {t['sidebar']};
    border-top: 1px solid {t['border']};
    font-family: '{MONO_FONT}';
    font-size: 11px;
}}
QStatusBar::item {{
    border: none;
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {t['border_hi']};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QCheckBox#ToggleSwitch {{
    spacing: 8px;
    background-color: transparent;
}}
QCheckBox#ToggleSwitch::indicator {{
    width: 0;
    height: 0;
    border: none;
}}
'''


def apply_theme(app):
    app.setStyle('Fusion')
    _resolve_fonts()
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(TOKENS['bg']))
    pal.setColor(QPalette.Base, QColor(TOKENS['sidebar']))
    pal.setColor(QPalette.AlternateBase, QColor(TOKENS['surface']))
    pal.setColor(QPalette.Text, QColor(TOKENS['text']))
    pal.setColor(QPalette.WindowText, QColor(TOKENS['text']))
    pal.setColor(QPalette.Button, QColor(TOKENS['surface']))
    pal.setColor(QPalette.ButtonText, QColor(TOKENS['text']))
    pal.setColor(QPalette.ToolTipBase, QColor(TOKENS['surface_hi']))
    pal.setColor(QPalette.ToolTipText, QColor(TOKENS['text']))
    pal.setColor(QPalette.Highlight, QColor(TOKENS['primary_hov']))
    pal.setColor(QPalette.HighlightedText, QColor('#ffffff'))
    app.setPalette(pal)
    app.setStyleSheet(build_stylesheet())


# Back-compat: some call sites import STYLESHEET directly.
STYLESHEET = build_stylesheet()
