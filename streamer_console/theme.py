"""Visual language for the Lausudo broadcast console."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


@dataclass(frozen=True, slots=True)
class ConsoleColors:
    ink: str = "#0B0F14"
    panel: str = "#101820"
    raised: str = "#15222B"
    deep_blue: str = "#102A36"
    line: str = "#25343D"
    text: str = "#F2FAF8"
    mist: str = "#D9F1EE"
    muted: str = "#8DA39F"
    teal: str = "#2FB7B0"
    teal_dark: str = "#176B69"
    amber: str = "#D9A441"
    danger: str = "#E06464"
    twitch: str = "#A970FF"
    tiktok: str = "#25F4EE"


COLORS = ConsoleColors()

DISPLAY_FONT = "Bahnschrift SemiBold"
BODY_FONT = "Segoe UI Variable Text"
MONO_FONT = "Cascadia Mono"


def apply_theme(application: QApplication) -> None:
    """Install the console palette and widget stylesheet."""

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS.ink))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS.ink))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS.panel))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS.panel))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS.text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS.teal_dark))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS.text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLORS.muted))
    application.setPalette(palette)
    application.setStyleSheet(STYLESHEET)


def repolish(widget: QWidget) -> None:
    """Refresh selectors after a dynamic Qt property changes."""

    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


STYLESHEET = f"""
* {{
    font-family: "{BODY_FONT}", "Segoe UI", sans-serif;
    color: {COLORS.text};
}}
QMainWindow, QWidget#consoleRoot {{
    background: {COLORS.ink};
}}
QLabel#brandName {{
    font-family: "{DISPLAY_FONT}";
    font-size: 31px;
    font-weight: 700;
    letter-spacing: 3px;
    color: {COLORS.mist};
}}
QLabel#brandKicker, QLabel#sectionKicker, QLabel#statusLabel,
QLabel#sceneCaption, QLabel#settingSection {{
    font-family: "{DISPLAY_FONT}";
    font-weight: 600;
    letter-spacing: 1px;
    color: {COLORS.muted};
}}
QLabel#brandKicker {{ font-size: 11px; }}
QLabel#sectionTitle {{
    font-family: "{DISPLAY_FONT}";
    font-size: 20px;
    font-weight: 650;
}}
QFrame#hairline {{ background: {COLORS.line}; max-height: 1px; }}
QFrame#connectionStrip, QFrame#streamStatusStrip, QFrame#audienceStrip {{
    background: {COLORS.panel};
    border: 1px solid {COLORS.line};
    border-radius: 9px;
}}
QWidget#audienceMetric {{ background: transparent; }}
QFrame#audienceDivider {{ color: {COLORS.line}; }}
QLabel#audienceCaption {{
    font-family: "{DISPLAY_FONT}";
    font-size: 10px;
    font-weight: 650;
    letter-spacing: 1px;
    color: {COLORS.muted};
}}
QLabel#audienceValue {{
    font-family: "{DISPLAY_FONT}";
    font-size: 19px;
    font-weight: 700;
    color: {COLORS.muted};
}}
QLabel#audienceValue[state="active"] {{ color: {COLORS.teal}; }}
QWidget#connectionBadge {{ background: transparent; }}
QLabel#connectionName {{
    font-family: "{DISPLAY_FONT}";
    font-size: 14px;
    font-weight: 650;
}}
QLabel#connectionDetail {{
    font-size: 12px;
    font-weight: 600;
    color: {COLORS.muted};
}}
QLabel#connectionDot {{ font-size: 18px; color: {COLORS.muted}; }}
QLabel#connectionDot[state="ready"],
QLabel#connectionDot[state="connected"] {{ color: {COLORS.teal}; }}
QLabel#connectionDot[state="reconnecting"] {{ color: {COLORS.amber}; }}
QLabel#connectionDot[state="disconnected"] {{ color: {COLORS.danger}; }}
QFrame#liveTally {{
    border: 1px solid {COLORS.line};
    border-radius: 7px;
    background: {COLORS.panel};
}}
QLabel#liveTallyDot {{
    font-size: 18px;
    color: {COLORS.muted};
}}
QLabel#liveTallyDot[state="ready"],
QLabel#liveTallyDot[state="live"] {{ color: {COLORS.teal}; }}
QLabel#liveTallyText {{
    font-family: "{DISPLAY_FONT}";
    font-size: 14px;
    font-weight: 700;
    color: {COLORS.muted};
}}
QLabel#liveTallyText[state="ready"],
QLabel#liveTallyText[state="live"] {{
    color: {COLORS.mist};
}}
QFrame#liveTally[state="live"] {{
    border-color: {COLORS.teal_dark};
    background: {COLORS.deep_blue};
}}
QListView#chatFeed {{
    background: {COLORS.ink};
    border: none;
    outline: none;
    padding: 0;
}}
QScrollBar:vertical {{
    width: 12px;
    margin: 0;
    border: none;
    background: {COLORS.ink};
}}
QScrollBar::handle:vertical {{
    min-height: 54px;
    border-radius: 5px;
    background: {COLORS.line};
}}
QScrollBar::handle:vertical:hover {{ background: {COLORS.teal_dark}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolButton#readerTool {{
    min-width: 42px;
    min-height: 38px;
    border: 1px solid {COLORS.line};
    border-radius: 6px;
    background: {COLORS.panel};
    color: {COLORS.mist};
    font-family: "{DISPLAY_FONT}";
    font-size: 14px;
    font-weight: 650;
}}
QToolButton#readerTool:hover {{ border-color: {COLORS.teal}; background: {COLORS.deep_blue}; }}
QToolButton#readerTool[state="ready"] {{ color: {COLORS.teal}; border-color: {COLORS.teal_dark}; }}
QToolButton#readerTool[state="warning"] {{ color: {COLORS.amber}; }}
QFrame#spotifyPanel {{
    background: {COLORS.panel};
    border: 1px solid {COLORS.line};
    border-radius: 9px;
}}
QLabel#spotifyMark {{
    border-radius: 7px;
    background: {COLORS.deep_blue};
    color: {COLORS.teal};
    font-size: 25px;
}}
QLabel#spotifyKicker {{ color: {COLORS.teal}; font-family: "{DISPLAY_FONT}"; font-size: 10px; letter-spacing: 1px; }}
QLabel#spotifyTitle {{ font-family: "{DISPLAY_FONT}"; font-size: 15px; font-weight: 650; }}
QLabel#spotifyArtist {{ color: {COLORS.muted}; font-size: 12px; }}
QProgressBar#spotifyProgress {{ border: none; background: {COLORS.line}; }}
QProgressBar#spotifyProgress::chunk {{ background: {COLORS.teal}; }}
QToolButton#spotifyControl {{
    min-width: 42px; min-height: 42px;
    border: 1px solid {COLORS.line}; border-radius: 21px;
    background: {COLORS.ink}; color: {COLORS.mist};
    font-family: "{DISPLAY_FONT}"; font-size: 13px;
}}
QToolButton#spotifyControl:hover {{ border-color: {COLORS.teal}; background: {COLORS.deep_blue}; }}
QToolButton#spotifyControl:disabled {{ color: {COLORS.muted}; }}
QPushButton#resumeButton {{
    min-height: 43px;
    padding: 0 18px;
    border: 1px solid {COLORS.amber};
    border-radius: 7px;
    background: #2A2518;
    color: #FFE2A6;
    font-family: "{DISPLAY_FONT}";
    font-size: 14px;
    font-weight: 700;
}}
QPushButton#resumeButton:hover {{ background: #3B321C; }}
QLabel#metricValue {{
    font-family: "{DISPLAY_FONT}";
    font-size: 14px;
    font-weight: 650;
}}
QLabel#metricValue[state="on"], QLabel#metricValue[state="connected"] {{ color: {COLORS.teal}; }}
QLabel#metricValue[state="off"], QLabel#metricValue[state="disconnected"] {{ color: {COLORS.muted}; }}
QLabel#metricValue[state="warning"] {{ color: {COLORS.amber}; }}
QLabel#sceneValue {{ font-size: 13px; color: {COLORS.mist}; }}
QPushButton#controlButton {{
    min-height: 112px;
    border: 1px solid {COLORS.line};
    border-radius: 10px;
    background: {COLORS.panel};
    color: {COLORS.text};
    font-family: "{DISPLAY_FONT}";
    font-size: 20px;
    font-weight: 700;
    text-align: left;
    padding: 15px 20px;
}}
QPushButton#controlButton:hover {{ border-color: {COLORS.teal}; background: {COLORS.deep_blue}; }}
QPushButton#controlButton:pressed {{ background: #183744; }}
QPushButton#controlButton[control="brb"][state="brb"] {{
    background: #332817;
    border: 2px solid {COLORS.amber};
    color: #FFE0A0;
}}
QPushButton#controlButton[control="brb"][state="mixed"] {{
    background: #3B1E1E;
    border: 2px solid {COLORS.danger};
}}
QPushButton#controlButton[control="brb"][state="unknown"] {{ color: {COLORS.muted}; }}
QPushButton#controlButton[control="discord"][state="muted"] {{
    background: #332817;
    border-color: {COLORS.amber};
}}
QLabel#keyHint {{
    font-family: "{MONO_FONT}";
    color: {COLORS.muted};
}}
QDialog, QGroupBox {{ background: {COLORS.ink}; }}
QDialog#readerSettings, QDialog#twitchStreamInfo, QDialog#consoleListDialog {{ min-width: 540px; }}
QLabel#dialogDetail {{ color: {COLORS.muted}; }}
QListWidget#consoleDataList {{
    background: {COLORS.panel}; border: 1px solid {COLORS.line}; border-radius: 7px;
    padding: 8px; font-size: 14px;
}}
QListWidget#consoleDataList::item {{ min-height: 42px; border-bottom: 1px solid {COLORS.line}; }}
QLabel#twitchAuthStatus {{
    min-height: 36px;
    padding: 0 10px;
    border: 1px solid {COLORS.line};
    border-radius: 6px;
    background: {COLORS.panel};
    color: {COLORS.muted};
    font-family: "{DISPLAY_FONT}";
    font-weight: 650;
}}
QLabel#twitchAuthStatus[state="connected"] {{ color: {COLORS.teal}; border-color: {COLORS.teal_dark}; }}
QLabel#twitchAuthStatus[state="warning"] {{ color: {COLORS.amber}; }}
QLabel#authorizationCode {{
    padding: 12px;
    border: 1px solid {COLORS.teal_dark};
    border-radius: 6px;
    background: {COLORS.deep_blue};
    color: {COLORS.text};
    font-family: "{MONO_FONT}";
}}
QSpinBox, QLineEdit, QComboBox {{
    min-height: 38px;
    padding: 0 10px;
    border: 1px solid {COLORS.line};
    border-radius: 6px;
    background: {COLORS.panel};
    selection-background-color: {COLORS.teal_dark};
}}
QCheckBox {{ spacing: 10px; min-height: 34px; }}
QCheckBox::indicator {{ width: 20px; height: 20px; }}
QDialogButtonBox QPushButton {{
    min-height: 40px;
    min-width: 110px;
    border: 1px solid {COLORS.line};
    border-radius: 6px;
    background: {COLORS.panel};
    font-weight: 650;
}}
QDialogButtonBox QPushButton:hover {{ border-color: {COLORS.teal}; }}
QToolTip {{
    border: 1px solid {COLORS.line};
    background: {COLORS.raised};
    color: {COLORS.text};
    padding: 6px;
}}
"""
