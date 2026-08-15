"""PySide6 Widgets interface for the portrait Streamer Console."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QModelIndex,
    QPointF,
    QRect,
    QRectF,
    QSettings,
    QSize,
    QSizeF,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QFont,
    QKeyEvent,
    QPainter,
    QPen,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import (
    ChatListModel,
    ChatMessage,
    ChatPreferences,
    ConnectionState,
    FilterSettings,
    MessageKind,
    MessageRoles,
    Platform,
)
from .theme import BODY_FONT, COLORS, DISPLAY_FONT, apply_theme, repolish


def _value(source: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(source, Mapping) and name in source:
            return source[name]
        if hasattr(source, name):
            return getattr(source, name)
    return default


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"true", "1", "yes", "on", "active", "live", "connected"}:
            return True
        if raw in {"false", "0", "no", "off", "inactive", "disconnected"}:
            return False
        return None
    return bool(value)


class ConnectionBadge(QWidget):
    """Compact state readout used for the independent chat collectors."""

    def __init__(self, platform: Platform, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.platform = platform
        self.setObjectName("connectionBadge")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.dot = QLabel("●")
        self.dot.setObjectName("connectionDot")
        self.dot.setProperty("platform", platform.value)
        self.name = QLabel(platform.value.upper())
        self.name.setObjectName("connectionName")
        # Keep the platform name readable when the longer RECEIVING detail is
        # shown on a narrow portrait half-row.
        self.name.setMinimumWidth(72)
        self.name.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        self.detail = QLabel("WAITING")
        self.detail.setObjectName("connectionDetail")
        self.detail.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.dot)
        layout.addWidget(self.name)
        layout.addWidget(self.detail)
        layout.addStretch(1)
        self.set_state(ConnectionState.UNKNOWN)

    def set_state(self, state: ConnectionState | str | bool, detail: str = "") -> None:
        normalized = ConnectionState.coerce(state)
        normalized_detail = detail.strip().upper()
        display_state = normalized.value
        if normalized is ConnectionState.UNKNOWN and normalized_detail in {
            "WAITING FOR CHAT",
            "NO RECENT DATA",
        }:
            # The local collector is ready even though no fresh platform
            # message exists to prove an active upstream chat connection.
            display_state = "ready"
        self.dot.setProperty("state", display_state)
        self.dot.setAccessibleName(f"{self.platform.value} {display_state}")
        repolish(self.dot)
        self.detail.setText(normalized_detail or normalized.value.upper())


class Metric(QWidget):
    def __init__(self, caption: str, value: str = "UNKNOWN", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(7)
        self.caption = QLabel(caption.upper())
        self.caption.setObjectName("statusLabel")
        self.value = QLabel(value)
        self.value.setObjectName("metricValue")
        self._layout.addWidget(self.caption)
        self._layout.addWidget(self.value)
        self._layout.addStretch(1)

    def set_compact(self, compact: bool) -> None:
        self._layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if compact
            else QBoxLayout.Direction.LeftToRight
        )
        self._layout.setSpacing(0 if compact else 7)

    def set_value(self, text: str, state: str = "unknown") -> None:
        self.value.setText(text)
        self.value.setProperty("state", state)
        repolish(self.value)


class ChatItemDelegate(QStyledItemDelegate):
    """Paints one readable, wrapped message without per-row widgets."""

    def __init__(self, preferences: ChatPreferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preferences = preferences
        self._height_cache: dict[tuple[str, int, int, int], int] = {}

    def set_preferences(self, preferences: ChatPreferences) -> None:
        self.preferences = preferences
        self._height_cache.clear()
        parent = self.parent()
        if isinstance(parent, QListView):
            parent.doItemsLayout()
            parent.viewport().update()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        message = index.data(int(MessageRoles.MessageRole))
        if not isinstance(message, ChatMessage):
            return QSize(max(320, option.rect.width()), 96)
        width = max(300, option.rect.width() - 56)
        key = (message.text, width, self.preferences.font_size, self.preferences.message_spacing)
        cached_height = self._height_cache.get(key)
        if cached_height is None:
            body_height = self._document(message.text, width).size().height()
            height = int(34 + body_height + self.preferences.message_spacing + 17)
            cached_height = max(96, height)
            if len(self._height_cache) >= 2200:
                self._height_cache.clear()
            self._height_cache[key] = cached_height
        return QSize(max(320, option.rect.width()), cached_height)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        message = index.data(int(MessageRoles.MessageRole))
        if not isinstance(message, ChatMessage):
            return super().paint(painter, option, index)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(2, 2, -10, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if message.highlight:
            painter.fillRect(rect, QColor("#143039"))
        elif message.kind is MessageKind.EVENT:
            painter.fillRect(rect, QColor("#172128"))
        elif selected:
            painter.fillRect(rect, QColor(COLORS.deep_blue))

        platform_color = {
            Platform.TWITCH: QColor(COLORS.twitch),
            Platform.TIKTOK: QColor(COLORS.tiktok),
            Platform.SYSTEM: QColor(COLORS.amber),
        }[message.platform]
        rail_color = QColor(COLORS.amber) if message.highlight else platform_color
        painter.fillRect(QRect(rect.left(), rect.top(), 5, rect.height() - 1), rail_color)
        painter.setPen(QPen(QColor(COLORS.line), 1))
        painter.drawLine(rect.left() + 17, rect.bottom(), rect.right(), rect.bottom())

        x = rect.left() + 24
        usable_width = max(260, rect.width() - 37)
        platform_font = QFont(DISPLAY_FONT)
        platform_font.setPixelSize(13)
        platform_font.setWeight(QFont.Weight.Bold)
        painter.setFont(platform_font)
        painter.setPen(platform_color)
        event_suffix = f"  •  {message.event_type.upper()}" if message.event_type else ""
        platform_text = message.platform.value.upper() + event_suffix
        painter.drawText(QRectF(x, rect.top() + 7, usable_width, 21), platform_text)

        username_font = QFont(DISPLAY_FONT)
        username_font.setPixelSize(max(17, self.preferences.font_size - 9))
        username_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(username_font)
        painter.setPen(QColor(COLORS.mist))
        username_width = usable_width - (64 if self.preferences.show_timestamps else 0)
        painter.drawText(QRectF(x, rect.top() + 28, username_width, 28), message.username)

        if self.preferences.show_timestamps:
            timestamp_font = QFont(BODY_FONT)
            timestamp_font.setPixelSize(12)
            painter.setFont(timestamp_font)
            painter.setPen(QColor(COLORS.muted))
            painter.drawText(
                QRectF(rect.right() - 58, rect.top() + 9, 54, 20),
                Qt.AlignmentFlag.AlignRight,
                message.timestamp_text,
            )

        document = self._document(message.text, usable_width)
        painter.translate(QPointF(x, rect.top() + 59))
        document.drawContents(painter, QRectF(0, 0, usable_width, rect.height() - 60))
        painter.restore()

    def _document(self, text: str, width: int) -> QTextDocument:
        document = QTextDocument()
        document.setDocumentMargin(0)
        font = QFont(BODY_FONT)
        font.setPixelSize(self.preferences.font_size)
        font.setWeight(QFont.Weight.Medium)
        document.setDefaultFont(font)
        document.setPlainText(text)
        cursor = QTextCursor(document)
        cursor.select(QTextCursor.SelectionType.Document)
        character_format = QTextCharFormat()
        character_format.setForeground(QColor(COLORS.text))
        cursor.mergeCharFormat(character_format)
        document.setPageSize(QSizeF(width, -1))
        return document


class ChatListView(QListView):
    """List view that only follows chat while the reader remains at the bottom."""

    auto_scroll_changed = Signal(bool)
    unread_count_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatFeed")
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSpacing(0)
        self.setUniformItemSizes(False)
        self._auto_scroll = True
        self._unread_count = 0
        self.verticalScrollBar().sliderReleased.connect(self.note_manual_scroll)
        self.verticalScrollBar().actionTriggered.connect(self._scroll_action_triggered)

    @property
    def auto_scroll_enabled(self) -> bool:
        return self._auto_scroll

    @property
    def unread_count(self) -> int:
        return self._unread_count

    @Slot(int)
    def notify_new_messages(self, count: int = 1) -> None:
        if self._auto_scroll:
            QTimer.singleShot(0, self.scrollToBottom)
        else:
            self._unread_count += max(0, count)
            self.unread_count_changed.emit(self._unread_count)

    @Slot()
    def pause_auto_scroll(self) -> None:
        if self._auto_scroll:
            self._auto_scroll = False
            self.auto_scroll_changed.emit(False)

    @Slot()
    def resume_auto_scroll(self) -> None:
        was_paused = not self._auto_scroll
        self._auto_scroll = True
        self._unread_count = 0
        self.unread_count_changed.emit(0)
        if was_paused:
            self.auto_scroll_changed.emit(True)
        QTimer.singleShot(0, self.scrollToBottom)

    @Slot()
    def note_manual_scroll(self) -> None:
        bar = self.verticalScrollBar()
        at_bottom = bar.maximum() <= 0 or bar.value() >= bar.maximum() - 4
        if at_bottom:
            self.resume_auto_scroll()
        else:
            self.pause_auto_scroll()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        super().wheelEvent(event)
        QTimer.singleShot(0, self.note_manual_scroll)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        super().keyPressEvent(event)
        if event.key() in {
            Qt.Key.Key_Up,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_Home,
            Qt.Key.Key_Down,
            Qt.Key.Key_PageDown,
            Qt.Key.Key_End,
        }:
            QTimer.singleShot(0, self.note_manual_scroll)

    def _scroll_action_triggered(self, _: int) -> None:
        QTimer.singleShot(0, self.note_manual_scroll)


class ReaderSettingsDialog(QDialog):
    def __init__(
        self,
        preferences: ChatPreferences,
        *,
        borderless: bool,
        always_on_top: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("readerSettings")
        self.setWindowTitle("Reader & Window Settings")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(13)

        title = QLabel("READER SETTINGS")
        title.setObjectName("sectionTitle")
        root.addWidget(title)
        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(10)
        self.font_size = QSpinBox()
        self.font_size.setRange(18, 48)
        self.font_size.setSuffix(" px")
        self.font_size.setValue(preferences.font_size)
        self.message_spacing = QSpinBox()
        self.message_spacing.setRange(4, 36)
        self.message_spacing.setSuffix(" px")
        self.message_spacing.setValue(preferences.message_spacing)
        self.max_messages = QSpinBox()
        self.max_messages.setRange(100, 5000)
        self.max_messages.setSingleStep(100)
        self.max_messages.setValue(preferences.max_messages)
        self.timestamps = QCheckBox("Show compact timestamps")
        self.timestamps.setChecked(preferences.show_timestamps)
        self.highlights = QLineEdit(", ".join(preferences.highlight_terms))
        self.highlights.setPlaceholderText("Lausudo, @Lausudo")
        form.addRow("Chat font", self.font_size)
        form.addRow("Message spacing", self.message_spacing)
        form.addRow("Retained messages", self.max_messages)
        form.addRow("Timestamps", self.timestamps)
        form.addRow("Highlight terms", self.highlights)
        root.addLayout(form)

        filter_label = QLabel("OPTIONAL FILTERS — OFF BY DEFAULT")
        filter_label.setObjectName("settingSection")
        root.addWidget(filter_label)
        self.hide_bots = QCheckBox("Hide messages marked as bots")
        self.hide_bots.setChecked(preferences.filters.hide_bot_messages)
        self.hide_commands = QCheckBox("Hide commands beginning with !")
        self.hide_commands.setChecked(preferences.filters.hide_commands)
        self.collapse_duplicates = QCheckBox("Collapse exact consecutive duplicates")
        self.collapse_duplicates.setChecked(preferences.filters.collapse_duplicates)
        self.suppress_spam = QCheckBox("Suppress a third repeated message")
        self.suppress_spam.setChecked(preferences.filters.suppress_repeated_spam)
        for control in (
            self.hide_bots,
            self.hide_commands,
            self.collapse_duplicates,
            self.suppress_spam,
        ):
            root.addWidget(control)

        window_label = QLabel("WINDOW")
        window_label.setObjectName("settingSection")
        root.addWidget(window_label)
        self.borderless = QCheckBox(
            "Borderless window (disables native resize and Snap layouts)"
        )
        self.borderless.setChecked(borderless)
        self.always_on_top = QCheckBox("Always on top")
        self.always_on_top.setChecked(always_on_top)
        root.addWidget(self.borderless)
        root.addWidget(self.always_on_top)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        root.addWidget(buttons)

    def preferences(self) -> ChatPreferences:
        terms = tuple(part.strip() for part in self.highlights.text().split(",") if part.strip())
        return ChatPreferences(
            font_size=self.font_size.value(),
            message_spacing=self.message_spacing.value(),
            show_timestamps=self.timestamps.isChecked(),
            max_messages=self.max_messages.value(),
            highlight_terms=terms or ("Lausudo", "@Lausudo"),
            filters=FilterSettings(
                hide_bot_messages=self.hide_bots.isChecked(),
                hide_commands=self.hide_commands.isChecked(),
                collapse_duplicates=self.collapse_duplicates.isChecked(),
                suppress_repeated_spam=self.suppress_spam.isChecked(),
                show_system_messages=False,
            ),
        )


class MainWindow(QMainWindow):
    """Portrait-first console with thread-safe integration entry points."""

    _COMPACT_WIDTH = 880
    _FRAME_FIT_DELAYS_MS = (0, 25, 75, 150, 300)

    brb_requested = Signal()
    discord_toggle_requested = Signal()
    preferences_changed = Signal(object)
    window_preferences_changed = Signal(object)

    incoming_message = Signal(object)
    incoming_messages = Signal(object)
    incoming_connection_status = Signal(object, object, str)
    incoming_obs_status = Signal(object)
    incoming_brb_state = Signal(str)
    incoming_discord_state = Signal(object)

    def __init__(
        self,
        preferences: ChatPreferences | Mapping[str, Any] | None = None,
        *,
        model: ChatListModel | None = None,
        settings: QSettings | None = None,
        persist_settings: bool = True,
        restore_geometry: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lausudo Streamer Console")
        # Fits a practical half-width cell on the 1080 px portrait display.
        self.setMinimumSize(500, 640)
        self.resize(880, 1560)
        self._persist_settings = persist_settings
        self._settings = settings or QSettings("Neil Mitchell", "Streamer Console")
        self._borderless = False
        self._always_on_top = False
        self._brb_state = "unknown"
        self._discord_state: bool | None = None
        self._compact_layout: bool | None = None
        self._frame_fit_attempt = 0
        self._frame_fit_last_signature: tuple[int, int, int, int] | None = None
        self._frame_fit_applied = False
        self._frame_fit_final_verification = False
        self._frame_fit_timer = QTimer(self)
        self._frame_fit_timer.setSingleShot(True)
        self._frame_fit_timer.timeout.connect(self._run_scheduled_frame_fit)

        loaded_preferences = (
            preferences
            if isinstance(preferences, ChatPreferences)
            else ChatPreferences.from_mapping(preferences)
            if preferences is not None
            else self._load_preferences()
            if persist_settings
            else ChatPreferences()
        )
        self.model = model or ChatListModel(preferences=loaded_preferences, parent=self)
        self.delegate = ChatItemDelegate(self.model.preferences)
        self._build_ui()
        self._update_responsive_layout(self.width())
        self._connect_signals()
        self.set_brb_state("unknown")
        self.set_discord_state(None)

        if persist_settings:
            self._borderless = self._settings.value("window/borderless", False, bool)
            self._always_on_top = self._settings.value("window/always_on_top", False, bool)
            self._apply_window_flags(show_again=False)
        if restore_geometry:
            QTimer.singleShot(0, self._restore_or_place_window)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("consoleRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(9)

        header = QWidget()
        header.setFixedHeight(76)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(13)
        logo = QLabel()
        logo.setFixedSize(58, 58)
        packaged_logo = (
            Path(__file__).resolve().parent / "assets" / "lausudo-logo-600.png"
        )
        source_logo = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "lausudo-logo-600.png"
        )
        logo_path = packaged_logo if packaged_logo.exists() else source_logo
        pixmap = QPixmap(str(logo_path))
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    logo.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            logo.setText("L")
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setAccessibleName("Lausudo logo")
        brand_stack = QVBoxLayout()
        brand_stack.setSpacing(0)
        kicker = QLabel("STREAMER CONSOLE")
        kicker.setObjectName("brandKicker")
        brand = QLabel("LAUSUDO")
        brand.setObjectName("brandName")
        brand_stack.addStretch(1)
        brand_stack.addWidget(kicker)
        brand_stack.addWidget(brand)
        brand_stack.addStretch(1)
        self.live_tally_box = QFrame()
        self.live_tally_box.setObjectName("liveTally")
        tally_layout = QHBoxLayout(self.live_tally_box)
        tally_layout.setContentsMargins(13, 8, 13, 8)
        tally_layout.setSpacing(8)
        self.live_tally_dot = QLabel("●")
        self.live_tally_dot.setObjectName("liveTallyDot")
        self.live_tally = QLabel("STANDBY")
        self.live_tally.setObjectName("liveTallyText")
        self.live_tally_box.setProperty("state", "standby")
        self.live_tally_dot.setProperty("state", "standby")
        self.live_tally.setProperty("state", "standby")
        self.live_tally_dot.setAccessibleName("OBS standby")
        tally_layout.addWidget(self.live_tally_dot)
        tally_layout.addWidget(self.live_tally)
        header_layout.addWidget(logo)
        header_layout.addLayout(brand_stack)
        header_layout.addStretch(1)
        header_layout.addWidget(self.live_tally_box)
        layout.addWidget(header)

        connection_strip = QFrame()
        connection_strip.setObjectName("connectionStrip")
        connection_strip.setFixedHeight(54)
        connections = QHBoxLayout(connection_strip)
        connections.setContentsMargins(14, 6, 14, 6)
        connections.setSpacing(12)
        self.twitch_connection = ConnectionBadge(Platform.TWITCH)
        self.tiktok_connection = ConnectionBadge(Platform.TIKTOK)
        connections.addWidget(self.twitch_connection, 1)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet(f"color: {COLORS.line};")
        connections.addWidget(divider)
        connections.addWidget(self.tiktok_connection, 1)
        layout.addWidget(connection_strip)

        chat_header = QWidget()
        chat_header.setFixedHeight(42)
        chat_header_layout = QHBoxLayout(chat_header)
        chat_header_layout.setContentsMargins(0, 0, 0, 0)
        chat_header_layout.setSpacing(7)
        chat_title_stack = QVBoxLayout()
        chat_title_stack.setSpacing(0)
        chat_kicker = QLabel("ONE FEED · RECEIPT ORDER")
        chat_kicker.setObjectName("sectionKicker")
        chat_title = QLabel("STREAM CHAT")
        chat_title.setObjectName("sectionTitle")
        chat_title_stack.addWidget(chat_kicker)
        chat_title_stack.addWidget(chat_title)
        chat_header_layout.addLayout(chat_title_stack)
        chat_header_layout.addStretch(1)
        self.font_down = self._reader_tool("A−", "Decrease chat font")
        self.font_up = self._reader_tool("A+", "Increase chat font")
        self.settings_button = self._reader_tool("⚙", "Reader, filter and window settings")
        chat_header_layout.addWidget(self.font_down)
        chat_header_layout.addWidget(self.font_up)
        chat_header_layout.addWidget(self.settings_button)
        layout.addWidget(chat_header)

        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(6)
        self.chat_view = ChatListView()
        self.chat_view.setModel(self.model)
        self.chat_view.setItemDelegate(self.delegate)
        self.resume_button = QPushButton("RESUME LIVE CHAT")
        self.resume_button.setObjectName("resumeButton")
        self.resume_button.setVisible(False)
        self.resume_button.setAccessibleName("Resume automatic chat scrolling")
        chat_layout.addWidget(self.chat_view, 1)
        chat_layout.addWidget(self.resume_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(chat_container, 1)

        self.status_strip = QFrame()
        self.status_strip.setObjectName("streamStatusStrip")
        self.status_strip.setFixedHeight(105)
        status_layout = QVBoxLayout(self.status_strip)
        status_layout.setContentsMargins(14, 9, 14, 8)
        status_layout.setSpacing(5)
        self.metric_layout = QGridLayout()
        self.metric_layout.setHorizontalSpacing(13)
        self.metric_layout.setVerticalSpacing(4)
        self.obs_metric = Metric("OBS")
        self.stream_metric = Metric("TWITCH")
        self.record_metric = Metric("REC")
        self.vertical_metric = Metric("TIKTOK OUT")
        self._status_metrics = (
            self.obs_metric,
            self.stream_metric,
            self.record_metric,
            self.vertical_metric,
        )
        for column, metric in enumerate(self._status_metrics):
            self.metric_layout.addWidget(metric, 0, column)
            self.metric_layout.setColumnStretch(column, 1)
        status_layout.addLayout(self.metric_layout)
        line = QFrame()
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        status_layout.addWidget(line)
        scenes = QGridLayout()
        scenes.setContentsMargins(0, 0, 0, 0)
        scenes.setHorizontalSpacing(12)
        scenes.setVerticalSpacing(0)
        main_caption = QLabel("MAIN SCENE")
        main_caption.setObjectName("sceneCaption")
        vertical_caption = QLabel("VERTICAL SCENE")
        vertical_caption.setObjectName("sceneCaption")
        self.main_scene = QLabel("—")
        self.main_scene.setObjectName("sceneValue")
        self.vertical_scene = QLabel("—")
        self.vertical_scene.setObjectName("sceneValue")
        scenes.addWidget(main_caption, 0, 0)
        scenes.addWidget(self.main_scene, 1, 0)
        scenes.addWidget(vertical_caption, 0, 1)
        scenes.addWidget(self.vertical_scene, 1, 1)
        status_layout.addLayout(scenes)
        layout.addWidget(self.status_strip)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.brb_button = QPushButton()
        self.brb_button.setObjectName("controlButton")
        self.brb_button.setProperty("control", "brb")
        self.brb_button.setAccessibleName("Toggle BRB privacy, F1")
        self.discord_button = QPushButton()
        self.discord_button.setObjectName("controlButton")
        self.discord_button.setProperty("control", "discord")
        self.discord_button.setAccessibleName("Toggle Discord microphone mute, F2")
        controls.addWidget(self.brb_button, 1)
        controls.addWidget(self.discord_button, 1)
        layout.addLayout(controls)

    def _connect_signals(self) -> None:
        self.model.messages_added.connect(self.chat_view.notify_new_messages)
        self.model.preferences_changed.connect(self._model_preferences_changed)
        self.chat_view.unread_count_changed.connect(self._update_resume_button)
        self.resume_button.clicked.connect(self.chat_view.resume_auto_scroll)
        self.font_down.clicked.connect(lambda: self._bump_font(-2))
        self.font_up.clicked.connect(lambda: self._bump_font(2))
        self.settings_button.clicked.connect(self.open_settings)
        self.brb_button.clicked.connect(self.brb_requested)
        self.discord_button.clicked.connect(self.discord_toggle_requested)
        self.incoming_message.connect(self._append_message)
        self.incoming_messages.connect(self._append_messages)
        self.incoming_connection_status.connect(self._update_connection)
        self.incoming_obs_status.connect(self._update_obs_status)
        self.incoming_brb_state.connect(self._set_brb_state)
        self.incoming_discord_state.connect(self._set_discord_state)

    def _reader_tool(self, text: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("readerTool")
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        return button

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "metric_layout"):
            self._update_responsive_layout(event.size().width())

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._borderless and not self.isMaximized():
            self._schedule_native_frame_fit()

    def _update_responsive_layout(self, width: int) -> None:
        compact = width < self._COMPACT_WIDTH
        if compact == self._compact_layout:
            return
        self._compact_layout = compact

        for metric in self._status_metrics:
            self.metric_layout.removeWidget(metric)
            metric.set_compact(compact)
        for column in range(4):
            self.metric_layout.setColumnStretch(column, 0)
        if compact:
            for index, metric in enumerate(self._status_metrics):
                row, column = divmod(index, 2)
                self.metric_layout.addWidget(metric, row, column)
            self.metric_layout.setColumnStretch(0, 1)
            self.metric_layout.setColumnStretch(1, 1)
            self.status_strip.setFixedHeight(135)
            control_style = "font-size: 15px; padding: 8px 10px;"
        else:
            for column, metric in enumerate(self._status_metrics):
                self.metric_layout.addWidget(metric, 0, column)
                self.metric_layout.setColumnStretch(column, 1)
            self.status_strip.setFixedHeight(105)
            control_style = ""

        self.brb_button.setStyleSheet(control_style)
        self.discord_button.setStyleSheet(control_style)
        self._set_brb_state(self._brb_state)
        self._set_discord_state(self._discord_state)

    def add_message(self, message: Any) -> None:
        """Thread-safe entry point for an ingestion callback."""

        self.incoming_message.emit(message)

    def add_messages(self, messages: Iterable[Any]) -> None:
        self.incoming_messages.emit(list(messages))

    def update_connection(self, platform: Any, state: Any, detail: str = "") -> None:
        self.incoming_connection_status.emit(platform, state, detail)

    def update_obs_status(self, status: Any) -> None:
        self.incoming_obs_status.emit(status)

    def set_brb_state(self, state: str) -> None:
        self.incoming_brb_state.emit(str(state))

    def set_discord_state(self, muted: bool | None) -> None:
        self.incoming_discord_state.emit(muted)

    @Slot(object)
    def _append_message(self, message: Any) -> None:
        self.model.append_message(message)

    @Slot(object)
    def _append_messages(self, messages: Iterable[Any]) -> None:
        self.model.append_messages(messages)

    @Slot(object, object, str)
    def _update_connection(self, platform: Any, state: Any, detail: str = "") -> None:
        normalized = Platform.coerce(platform)
        if normalized is Platform.TWITCH:
            badge = self.twitch_connection
        elif normalized is Platform.TIKTOK:
            badge = self.tiktok_connection
        else:
            return
        badge.set_state(state, detail)

    @Slot(object)
    def _update_obs_status(self, status: Any) -> None:
        connected = _bool_or_none(_value(status, "connected", "obs_connected"))
        streaming = _bool_or_none(_value(status, "streaming", "stream_active", "streaming_active"))
        recording = _bool_or_none(_value(status, "recording", "record_active", "recording_active"))
        vertical_active = _bool_or_none(
            _value(status, "vertical_active", "vertical_streaming", "virtual_camera_active")
        )
        if vertical_active is None:
            vertical_outputs = _value(status, "vertical_outputs", default=()) or ()
            active_values = [
                _bool_or_none(_value(output, "active", "output_active"))
                for output in vertical_outputs
            ]
            known_values = [value for value in active_values if value is not None]
            if known_values:
                vertical_active = any(known_values)
        main_scene = str(
            _value(status, "main_scene", "current_scene", "current_program_scene_name", default="—") or "—"
        )
        vertical_scene = str(
            _value(status, "vertical_scene", "current_vertical_scene", default="—") or "—"
        )
        self._set_boolean_metric(self.obs_metric, connected, "CONNECTED", "OFFLINE")
        self._set_boolean_metric(self.stream_metric, streaming, "LIVE", "OFFLINE")
        self._set_boolean_metric(self.record_metric, recording, "ON", "OFF")
        self._set_boolean_metric(self.vertical_metric, vertical_active, "ON", "OFF")
        self.main_scene.setText(main_scene)
        self.vertical_scene.setText(vertical_scene)

        if streaming is True:
            tally_text = "LIVE"
            tally_state = "live"
        elif connected is True:
            tally_text = "READY"
            tally_state = "ready"
        else:
            tally_text = "STANDBY"
            tally_state = "standby"
        self.live_tally.setText(tally_text)
        self.live_tally_box.setProperty("state", tally_state)
        self.live_tally_dot.setProperty("state", tally_state)
        self.live_tally.setProperty("state", tally_state)
        self.live_tally_dot.setAccessibleName(f"OBS {tally_text.lower()}")
        repolish(self.live_tally_box)
        repolish(self.live_tally_dot)
        repolish(self.live_tally)

        explicit_brb = _value(status, "brb_state", default=None)
        if explicit_brb is not None:
            self._set_brb_state(str(explicit_brb))
        elif main_scene != "—" and vertical_scene != "—":
            main_is_brb = main_scene.casefold() == "brb - main"
            vertical_is_brb = vertical_scene.casefold() == "brb - vertical"
            derived = "brb" if main_is_brb and vertical_is_brb else "mixed" if main_is_brb != vertical_is_brb else "live"
            self._set_brb_state(derived)

    def _set_boolean_metric(
        self,
        metric: Metric,
        value: bool | None,
        true_label: str,
        false_label: str,
    ) -> None:
        if value is None:
            metric.set_value("UNKNOWN", "warning")
        elif value:
            metric.set_value(true_label, "on")
        else:
            metric.set_value(false_label, "off")

    @Slot(str)
    def _set_brb_state(self, state: str) -> None:
        normalized = state.strip().lower().replace("_", " ")
        compact = bool(self._compact_layout)
        if normalized in {"active", "brb active", "privacy", "brb"}:
            normalized = "brb"
            text = "BRB ACTIVE\nF1 · RETURN" if compact else "BRB ACTIVE\nF1  •  RETURN LIVE"
        elif normalized in {"live", "normal", "inactive", "ready"}:
            normalized = "live"
            text = "BRB PRIVACY\nF1 · LIVE" if compact else "BRB / PRIVACY\nF1  •  LIVE"
        elif normalized in {"mixed", "partial", "drifted"}:
            normalized = "mixed"
            text = "BRB MIXED\nF1 · FIX" if compact else "PRIVACY STATE MIXED\nF1  •  RECONCILE"
        else:
            normalized = "unknown"
            text = "BRB PRIVACY\nF1 · UNKNOWN" if compact else "BRB / PRIVACY\nF1  •  STATE UNKNOWN"
        self._brb_state = normalized
        self.brb_button.setText(text)
        self.brb_button.setProperty("state", normalized)
        repolish(self.brb_button)

    @Slot(object)
    def _set_discord_state(self, muted: bool | None) -> None:
        compact = bool(self._compact_layout)
        if muted is True:
            state = "muted"
            text = "DISCORD MUTED\nF2 · UNMUTE" if compact else "DISCORD MUTED\nF2  •  UNMUTE"
        elif muted is False:
            state = "live"
            text = "DISCORD MUTE\nF2 · LIVE" if compact else "DISCORD MUTE\nF2  •  MIC LIVE"
        else:
            state = "unknown"
            text = "DISCORD MUTE\nF2 · TOGGLE" if compact else "DISCORD MUTE\nF2  •  TOGGLE MUTE"
        self._discord_state = muted
        self.discord_button.setText(text)
        self.discord_button.setProperty("state", state)
        repolish(self.discord_button)

    @Slot(int)
    def _update_resume_button(self, unread_count: int) -> None:
        self.resume_button.setVisible(unread_count > 0)
        self.resume_button.setText(
            f"RESUME LIVE CHAT  ·  {unread_count} NEW" if unread_count else "RESUME LIVE CHAT"
        )

    def _bump_font(self, delta: int) -> None:
        current = self.model.preferences
        next_size = max(18, min(48, current.font_size + delta))
        if next_size != current.font_size:
            self.set_preferences(replace(current, font_size=next_size))

    def set_preferences(self, preferences: ChatPreferences | Mapping[str, Any]) -> None:
        normalized = (
            preferences
            if isinstance(preferences, ChatPreferences)
            else ChatPreferences.from_mapping(preferences)
        )
        self.model.set_preferences(normalized)

    @Slot(object)
    def _model_preferences_changed(self, preferences: ChatPreferences) -> None:
        self.delegate.set_preferences(preferences)
        self.chat_view.doItemsLayout()
        self.chat_view.viewport().update()
        self.preferences_changed.emit(preferences.to_dict())
        if self._persist_settings:
            self._save_preferences(preferences)

    @Slot()
    def open_settings(self) -> None:
        dialog = ReaderSettingsDialog(
            self.model.preferences,
            borderless=self._borderless,
            always_on_top=self._always_on_top,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.set_preferences(dialog.preferences())
        self.set_window_options(
            borderless=dialog.borderless.isChecked(),
            always_on_top=dialog.always_on_top.isChecked(),
        )

    def set_window_options(self, *, borderless: bool, always_on_top: bool) -> None:
        changed = borderless != self._borderless or always_on_top != self._always_on_top
        self._borderless = borderless
        self._always_on_top = always_on_top
        self._apply_window_flags(show_again=self.isVisible())
        values = {"borderless": borderless, "always_on_top": always_on_top}
        if self._persist_settings:
            self._settings.setValue("window/borderless", borderless)
            self._settings.setValue("window/always_on_top", always_on_top)
        if changed:
            self.window_preferences_changed.emit(values)

    def _apply_window_flags(self, *, show_again: bool) -> None:
        current_flags = self.windowFlags()
        desired_flags = current_flags
        if self._borderless:
            desired_flags |= Qt.WindowType.FramelessWindowHint
        else:
            desired_flags &= ~Qt.WindowType.FramelessWindowHint
        if self._always_on_top:
            desired_flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            desired_flags &= ~Qt.WindowType.WindowStaysOnTopHint

        was_visible = bool(show_again and self.isVisible())
        was_maximized = self.isMaximized()
        normal_geometry = QRect(self.normalGeometry())
        if not normal_geometry.isValid():
            normal_geometry = QRect(self.geometry())

        if desired_flags != current_flags:
            # Changing either hint recreates the HWND on Windows. Preserve the
            # user's restore rectangle and maximized state across that rebuild.
            self._frame_fit_timer.stop()
            self.setWindowFlags(desired_flags)
            self.setGeometry(normal_geometry)
            if was_visible:
                if was_maximized:
                    self.showMaximized()
                else:
                    self.show()
            elif was_maximized:
                self.setWindowState(
                    self.windowState() | Qt.WindowState.WindowMaximized
                )

        if was_visible and not self._borderless and not was_maximized:
            self._schedule_native_frame_fit()

    def capture_window_preferences(self) -> dict[str, Any]:
        screen = self.screen()
        geometry = self.geometry()
        return {
            "screen": screen.name() if screen else "",
            "x": geometry.x(),
            "y": geometry.y(),
            "width": geometry.width(),
            "height": geometry.height(),
            "borderless": self._borderless,
            "always_on_top": self._always_on_top,
        }

    def restore_window_preferences(self, preferences: Any) -> None:
        """Apply a backend ``WindowSettings`` object without forcing a missing display."""

        borderless = bool(_value(preferences, "borderless", default=False))
        always_on_top = bool(_value(preferences, "always_on_top", default=False))
        self.set_window_options(borderless=borderless, always_on_top=always_on_top)

        screens = QApplication.screens()
        monitor_name = str(
            _value(preferences, "monitor_name", "screen", default="") or ""
        )
        target = next((screen for screen in screens if screen.name() == monitor_name), None)
        if target is None:
            portrait = [
                screen
                for screen in screens
                if screen.availableGeometry().height() > screen.availableGeometry().width()
            ]
            target = (
                max(portrait, key=lambda screen: screen.availableGeometry().height())
                if portrait
                else QApplication.primaryScreen()
            )
        width = max(self.minimumWidth(), int(_value(preferences, "width", default=1080) or 1080))
        height = max(self.minimumHeight(), int(_value(preferences, "height", default=1920) or 1920))
        x = _value(preferences, "x", default=None)
        y = _value(preferences, "y", default=None)
        requested = QRect(int(x), int(y), width, height) if x is not None and y is not None else QRect()

        if not requested.isNull() and self._geometry_on_available_screen(requested):
            self.setGeometry(requested)
        elif target is not None:
            area = target.availableGeometry()
            fitted_width = min(width, area.width())
            fitted_height = min(height, area.height())
            self.setGeometry(
                area.x() + (area.width() - fitted_width) // 2,
                area.y() + (area.height() - fitted_height) // 2,
                fitted_width,
                fitted_height,
            )
        else:
            self._place_on_portrait_screen()

        if bool(_value(preferences, "maximized", default=False)):
            self.showMaximized()
        elif not borderless:
            # Runs after the event loop starts, when Windows has supplied the
            # real title-bar and resize-frame margins.
            self._schedule_native_frame_fit()

    def _load_preferences(self) -> ChatPreferences:
        values = {
            "font_size": self._settings.value("reader/font_size", 29, int),
            "message_spacing": self._settings.value("reader/message_spacing", 16, int),
            "show_timestamps": self._settings.value("reader/show_timestamps", False, bool),
            "max_messages": self._settings.value("reader/max_messages", 750, int),
            "highlight_terms": self._settings.value(
                "reader/highlight_terms", ["Lausudo", "@Lausudo"], list
            ),
            "filters": {
                "hide_bot_messages": self._settings.value("filters/hide_bots", False, bool),
                "hide_commands": self._settings.value("filters/hide_commands", False, bool),
                "collapse_duplicates": self._settings.value("filters/collapse_duplicates", False, bool),
                "suppress_repeated_spam": self._settings.value("filters/suppress_spam", False, bool),
                "show_system_messages": False,
            },
        }
        return ChatPreferences.from_mapping(values)

    def _save_preferences(self, preferences: ChatPreferences) -> None:
        self._settings.setValue("reader/font_size", preferences.font_size)
        self._settings.setValue("reader/message_spacing", preferences.message_spacing)
        self._settings.setValue("reader/show_timestamps", preferences.show_timestamps)
        self._settings.setValue("reader/max_messages", preferences.max_messages)
        self._settings.setValue("reader/highlight_terms", list(preferences.highlight_terms))
        self._settings.setValue("filters/hide_bots", preferences.filters.hide_bot_messages)
        self._settings.setValue("filters/hide_commands", preferences.filters.hide_commands)
        self._settings.setValue("filters/collapse_duplicates", preferences.filters.collapse_duplicates)
        self._settings.setValue("filters/suppress_spam", preferences.filters.suppress_repeated_spam)
        self._settings.setValue("filters/show_system", False)
        self._settings.sync()

    def _restore_or_place_window(self) -> None:
        geometry_value = self._settings.value("window/geometry") if self._persist_settings else None
        restored = False
        if geometry_value:
            if isinstance(geometry_value, QByteArray):
                restored = self.restoreGeometry(geometry_value)
            elif isinstance(geometry_value, bytes):
                restored = self.restoreGeometry(QByteArray(geometry_value))
        if restored and self._geometry_on_available_screen(self.frameGeometry()):
            self._schedule_native_frame_fit()
            return
        self._place_on_portrait_screen()
        self._schedule_native_frame_fit()

    def _place_on_portrait_screen(self) -> None:
        screens = QApplication.screens()
        preferred_name = self._settings.value("window/screen", "", str) if self._persist_settings else ""
        preferred = next((screen for screen in screens if screen.name() == preferred_name), None)
        portrait = [screen for screen in screens if screen.availableGeometry().height() > screen.availableGeometry().width()]
        target = preferred or (max(portrait, key=lambda screen: screen.availableGeometry().height()) if portrait else QApplication.primaryScreen())
        if target is None:
            return
        area = target.availableGeometry()
        width = min(1000, max(self.minimumWidth(), int(area.width() * 0.94)))
        height = min(1820, max(self.minimumHeight(), int(area.height() * 0.94)))
        x = area.x() + (area.width() - width) // 2
        y = area.y() + (area.height() - height) // 2
        self.setGeometry(x, y, width, height)

    def _schedule_native_frame_fit(self) -> None:
        """Fit only after two matching native-frame observations."""

        if self._borderless or self.isMaximized():
            self._frame_fit_timer.stop()
            return
        self._frame_fit_attempt = 0
        self._frame_fit_last_signature = None
        self._frame_fit_applied = False
        self._frame_fit_final_verification = False
        self._frame_fit_timer.start(self._FRAME_FIT_DELAYS_MS[0])

    def _run_scheduled_frame_fit(self) -> None:
        if self._borderless or self.isMaximized():
            return
        if not self.isVisible():
            self._queue_frame_fit_retry()
            return

        signature = self._native_frame_insets()
        stable = signature == self._frame_fit_last_signature
        at_last_attempt = self._frame_fit_attempt >= len(self._FRAME_FIT_DELAYS_MS) - 1

        if not self._frame_fit_applied:
            if not stable and not at_last_attempt:
                self._frame_fit_last_signature = signature
                self._queue_frame_fit_retry()
                return
            self._fit_native_frame_to_available_screen(signature)
            self._frame_fit_applied = True
            self._frame_fit_last_signature = signature
            if not self._queue_frame_fit_retry():
                self._queue_final_frame_fit_verification()
            return

        margins_changed = signature != self._frame_fit_last_signature
        frame_inconsistent = not self._native_frame_matches_client(signature)
        if (
            margins_changed
            or frame_inconsistent
            or not self._native_frame_placement_is_reachable()
        ):
            self._fit_native_frame_to_available_screen(signature)
            self._frame_fit_last_signature = signature
            if not self._queue_frame_fit_retry():
                self._queue_final_frame_fit_verification()

    def _queue_frame_fit_retry(self) -> bool:
        next_attempt = self._frame_fit_attempt + 1
        if next_attempt >= len(self._FRAME_FIT_DELAYS_MS):
            return False
        self._frame_fit_attempt = next_attempt
        self._frame_fit_timer.start(self._FRAME_FIT_DELAYS_MS[next_attempt])
        return True

    def _queue_final_frame_fit_verification(self) -> None:
        if self._frame_fit_final_verification:
            return
        self._frame_fit_final_verification = True
        self._frame_fit_timer.start(50)

    def _native_frame_insets(self) -> tuple[int, int, int, int]:
        frame = self.frameGeometry()
        client = self.geometry()
        handle = self.windowHandle()
        if handle is not None:
            margins = handle.frameMargins()
            reported = (
                max(0, margins.left()),
                max(0, margins.top()),
                max(0, margins.right()),
                max(0, margins.bottom()),
            )
            if any(reported):
                return reported
        return (
            max(0, client.x() - frame.x()),
            max(0, client.y() - frame.y()),
            max(0, frame.width() - client.width() - (client.x() - frame.x())),
            max(0, frame.height() - client.height() - (client.y() - frame.y())),
        )

    def _target_screen_for_frame(self, frame: QRect) -> Any:
        screens = QApplication.screens()
        intersecting = [
            (
                max(0, frame.intersected(screen.availableGeometry()).width())
                * max(0, frame.intersected(screen.availableGeometry()).height()),
                screen,
            )
            for screen in screens
        ]
        best_area, best_screen = max(intersecting, default=(0, None), key=lambda item: item[0])
        if best_area > 0:
            return best_screen
        return self.screen() or QApplication.primaryScreen()

    def _native_frame_placement_is_reachable(self) -> bool:
        frame = self.frameGeometry()
        screen = self._target_screen_for_frame(frame)
        if screen is None:
            return True
        area = screen.availableGeometry()
        horizontal = frame.left() >= area.left() and (
            frame.width() > area.width() or frame.right() <= area.right()
        )
        vertical = frame.top() >= area.top() and (
            frame.height() > area.height() or frame.bottom() <= area.bottom()
        )
        return horizontal and vertical

    def _native_frame_matches_client(
        self, insets: tuple[int, int, int, int] | None = None
    ) -> bool:
        client = self.geometry()
        left, top, right, bottom = insets or self._native_frame_insets()
        expected = QRect(
            client.x() - left,
            client.y() - top,
            client.width() + left + right,
            client.height() + top + bottom,
        )
        return self.frameGeometry() == expected

    def _refresh_native_frame_geometry(self, client: QRect) -> None:
        """Force Qt/Windows to recompute a stale non-client frame in place."""

        if client.width() < self.maximumWidth():
            pulse = QRect(client.x(), client.y(), client.width() + 1, client.height())
        elif client.width() > self.minimumWidth():
            pulse = QRect(client.x(), client.y(), client.width() - 1, client.height())
        elif client.height() < self.maximumHeight():
            pulse = QRect(client.x(), client.y(), client.width(), client.height() + 1)
        elif client.height() > self.minimumHeight():
            pulse = QRect(client.x(), client.y(), client.width(), client.height() - 1)
        else:
            pulse = QRect(client.x() + 1, client.y(), client.width(), client.height())
        self.setGeometry(pulse)
        self.setGeometry(client)

    def _fit_native_frame_to_available_screen(
        self, insets: tuple[int, int, int, int] | None = None
    ) -> None:
        """Keep the Windows caption reachable and fit the frame when possible."""

        if self._borderless or self.isMaximized() or not self.isVisible():
            return
        client = self.geometry()
        left, top, right, bottom = insets or self._native_frame_insets()
        # HWND recreation can briefly report the client origin as the frame
        # origin even after its margins have stabilized. Derive the candidate
        # frame from the preserved client rectangle so that transient native
        # positioning cannot introduce one extra inset on every toggle.
        frame = QRect(
            client.x() - left,
            client.y() - top,
            client.width() + left + right,
            client.height() + top + bottom,
        )
        screen = self._target_screen_for_frame(frame)
        if screen is None:
            return
        fitted = self._fitted_client_geometry(
            client,
            frame,
            screen.availableGeometry(),
            (left, top, right, bottom),
            self.minimumSize(),
        )
        if fitted != client:
            self.setGeometry(fitted)
        elif not self._native_frame_matches_client((left, top, right, bottom)):
            self._refresh_native_frame_geometry(client)

    @staticmethod
    def _fitted_client_geometry(
        client: QRect,
        frame: QRect,
        area: QRect,
        insets: tuple[int, int, int, int],
        minimum: QSize,
    ) -> QRect:
        left, top, right, bottom = (max(0, value) for value in insets)
        max_client_width = max(minimum.width(), area.width() - left - right)
        max_client_height = max(minimum.height(), area.height() - top - bottom)
        client_width = min(max(client.width(), minimum.width()), max_client_width)
        client_height = min(max(client.height(), minimum.height()), max_client_height)
        frame_width = client_width + left + right
        frame_height = client_height + top + bottom

        if frame_width > area.width():
            frame_x = area.x()
        else:
            max_frame_x = area.x() + area.width() - frame_width
            frame_x = min(max(frame.x(), area.x()), max_frame_x)
        if frame_height > area.height():
            frame_y = area.y()
        else:
            max_frame_y = area.y() + area.height() - frame_height
            frame_y = min(max(frame.y(), area.y()), max_frame_y)
        return QRect(
            frame_x + left,
            frame_y + top,
            client_width,
            client_height,
        )

    @staticmethod
    def _geometry_on_available_screen(rect: QRect) -> bool:
        return any(rect.intersects(screen.availableGeometry()) for screen in QApplication.screens())

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._persist_settings:
            self._settings.setValue("window/geometry", self.saveGeometry())
            screen = self.screen()
            if screen:
                self._settings.setValue("window/screen", screen.name())
            self._settings.sync()
        super().closeEvent(event)


StreamerConsoleWindow = MainWindow


def ensure_application_theme() -> QApplication:
    """Create/reuse a QApplication and install the branded palette."""

    application = QApplication.instance() or QApplication([])
    apply_theme(application)
    return application
