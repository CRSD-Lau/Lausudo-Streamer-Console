"""Presentation models for the Streamer Console.

The ingestion layer deliberately remains independent of Qt.  ``ChatMessage``
can therefore coerce dictionaries as well as the backend's dataclass objects,
while ``ChatListModel`` gives the UI a bounded, receipt-ordered model.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum, IntEnum
import re
from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Signal


class Platform(str, Enum):
    TWITCH = "twitch"
    TIKTOK = "tiktok"
    SYSTEM = "system"

    @classmethod
    def coerce(cls, value: Any) -> "Platform":
        raw = str(getattr(value, "value", value) or "system").strip().lower()
        aliases = {
            "tt": cls.TIKTOK,
            "tik tok": cls.TIKTOK,
            "tiktok live": cls.TIKTOK,
            "socialstream": cls.SYSTEM,
            "social stream": cls.SYSTEM,
        }
        if raw in aliases:
            return aliases[raw]
        try:
            return cls(raw)
        except ValueError:
            return cls.SYSTEM


class MessageKind(str, Enum):
    CHAT = "chat"
    EVENT = "event"
    SYSTEM = "system"

    @classmethod
    def coerce(cls, value: Any) -> "MessageKind":
        raw = str(getattr(value, "value", value) or "chat").strip().lower()
        if raw in {"follow", "subscription", "sub", "resub", "gift", "raid", "bits"}:
            return cls.EVENT
        try:
            return cls(raw)
        except ValueError:
            return cls.CHAT


class ConnectionState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    UNKNOWN = "unknown"

    @classmethod
    def coerce(cls, value: Any) -> "ConnectionState":
        if isinstance(value, bool):
            return cls.CONNECTED if value else cls.DISCONNECTED
        raw = str(getattr(value, "value", value) or "unknown").strip().lower()
        aliases = {
            "online": cls.CONNECTED,
            "live": cls.CONNECTED,
            "ready": cls.CONNECTED,
            "offline": cls.DISCONNECTED,
            "retrying": cls.RECONNECTING,
            "connecting": cls.RECONNECTING,
        }
        if raw in aliases:
            return aliases[raw]
        try:
            return cls(raw)
        except ValueError:
            return cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class FilterSettings:
    """Optional filters applied after the mandatory chat-only boundary."""

    hide_bot_messages: bool = False
    hide_commands: bool = False
    collapse_duplicates: bool = False
    suppress_repeated_spam: bool = False
    show_system_messages: bool = False


@dataclass(frozen=True, slots=True)
class ChatPreferences:
    font_size: int = 29
    message_spacing: int = 16
    show_timestamps: bool = False
    max_messages: int = 750
    highlight_terms: tuple[str, ...] = ("Lausudo", "@Lausudo")
    filters: FilterSettings = field(default_factory=FilterSettings)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | Any | None) -> "ChatPreferences":
        if not values:
            return cls()
        defaults = cls()
        if not isinstance(values, Mapping):
            if is_dataclass(values) and not isinstance(values, type):
                values = asdict(values)
            else:
                values = {
                    name: getattr(values, name)
                    for name in (
                        "font_size",
                        "message_spacing",
                        "show_timestamps",
                        "max_messages",
                        "highlight_terms",
                        "filters",
                    )
                    if hasattr(values, name)
                }
        raw_filters = values.get("filters", {})
        if isinstance(raw_filters, FilterSettings):
            filters = raw_filters
        elif isinstance(raw_filters, Mapping):
            show_system = (
                _coerce_bool(raw_filters["show_system_messages"])
                if "show_system_messages" in raw_filters
                else not _coerce_bool(raw_filters.get("hide_system_messages", False))
            )
            filters = FilterSettings(
                hide_bot_messages=_coerce_bool(
                    raw_filters.get("hide_bot_messages", raw_filters.get("hide_bots", False))
                ),
                hide_commands=_coerce_bool(raw_filters.get("hide_commands", False)),
                collapse_duplicates=_coerce_bool(
                    raw_filters.get("collapse_duplicates", raw_filters.get("hide_duplicates", False))
                ),
                suppress_repeated_spam=_coerce_bool(
                    raw_filters.get(
                        "suppress_repeated_spam", raw_filters.get("hide_repeated_spam", False)
                    )
                ),
                show_system_messages=show_system,
            )
        else:
            filters = FilterSettings()

        terms = values.get("highlight_terms", defaults.highlight_terms)
        if isinstance(terms, str):
            terms = tuple(part.strip() for part in terms.split(",") if part.strip())
        else:
            terms = tuple(str(part).strip() for part in terms if str(part).strip())
        return cls(
            font_size=max(18, min(48, int(values.get("font_size", defaults.font_size)))),
            message_spacing=max(4, min(36, int(values.get("message_spacing", defaults.message_spacing)))),
            show_timestamps=_coerce_bool(values.get("show_timestamps", defaults.show_timestamps)),
            max_messages=max(100, min(5000, int(values.get("max_messages", defaults.max_messages)))),
            highlight_terms=terms or defaults.highlight_terms,
            filters=filters,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    sequence: int
    received_at: datetime
    platform: Platform
    username: str
    text: str
    kind: MessageKind = MessageKind.CHAT
    event_type: str = ""
    highlight: bool = False
    source_id: str = ""
    is_bot: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def coerce(cls, value: Any, sequence_fallback: int = 0) -> "ChatMessage":
        if isinstance(value, cls):
            return value
        getter = value.get if isinstance(value, Mapping) else lambda key, default=None: getattr(value, key, default)
        event_type = str(getter("event_type", "") or "")
        kind = MessageKind.coerce(getter("kind", "event" if event_type else "chat"))
        return cls(
            sequence=int(getter("sequence", sequence_fallback) or sequence_fallback),
            received_at=_coerce_datetime(getter("received_at", None)),
            platform=Platform.coerce(getter("platform", "system")),
            # Viewer identity is part of the chat-only contract. Do not invent
            # one for platform notices that bypass the normalizer.
            username=str(getter("username", getter("name", "")) or "").strip(),
            text=str(getter("text", getter("message", getter("content", ""))) or ""),
            kind=kind,
            event_type=event_type.strip(),
            highlight=_coerce_bool(getter("highlight", False)),
            source_id=str(getter("source_id", getter("id", "")) or ""),
            is_bot=_coerce_bool(getter("is_bot", getter("bot", False))),
            metadata=getter("metadata", {}) or {},
        )

    @property
    def timestamp_text(self) -> str:
        return self.received_at.astimezone().strftime("%H:%M")


class MessageRoles(IntEnum):
    MessageRole = Qt.ItemDataRole.UserRole + 1
    SequenceRole = Qt.ItemDataRole.UserRole + 2
    PlatformRole = Qt.ItemDataRole.UserRole + 3
    UsernameRole = Qt.ItemDataRole.UserRole + 4
    TextRole = Qt.ItemDataRole.UserRole + 5
    TimestampRole = Qt.ItemDataRole.UserRole + 6
    KindRole = Qt.ItemDataRole.UserRole + 7
    EventTypeRole = Qt.ItemDataRole.UserRole + 8
    HighlightRole = Qt.ItemDataRole.UserRole + 9


class ChatListModel(QAbstractListModel):
    """A bounded chronological stream of normalized messages."""

    messages_added = Signal(int)
    messages_trimmed = Signal(int)
    preferences_changed = Signal(object)

    def __init__(
        self,
        messages: Iterable[Any] | None = None,
        preferences: ChatPreferences | Mapping[str, Any] | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._preferences = (
            preferences
            if isinstance(preferences, ChatPreferences)
            else ChatPreferences.from_mapping(preferences)
        )
        self._messages: list[ChatMessage] = []
        self._next_sequence = 1
        if messages:
            self.append_messages(messages)

    @property
    def preferences(self) -> ChatPreferences:
        return self._preferences

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        return tuple(self._messages)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._messages)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._messages):
            return None
        message = self._messages[index.row()]
        role_map = {
            Qt.ItemDataRole.DisplayRole: message.text,
            Qt.ItemDataRole.ToolTipRole: f"{message.platform.value.upper()} · {message.username}\n{message.text}",
            Qt.ItemDataRole.AccessibleTextRole: (
                f"{message.platform.value}, {message.username}: {message.text}"
            ),
            MessageRoles.MessageRole: message,
            MessageRoles.SequenceRole: message.sequence,
            MessageRoles.PlatformRole: message.platform.value,
            MessageRoles.UsernameRole: message.username,
            MessageRoles.TextRole: message.text,
            MessageRoles.TimestampRole: message.timestamp_text,
            MessageRoles.KindRole: message.kind.value,
            MessageRoles.EventTypeRole: message.event_type,
            MessageRoles.HighlightRole: message.highlight,
        }
        return role_map.get(role)

    def roleNames(self) -> dict[int, bytes]:  # noqa: N802 - Qt API
        return {
            int(MessageRoles.MessageRole): b"message",
            int(MessageRoles.SequenceRole): b"sequence",
            int(MessageRoles.PlatformRole): b"platform",
            int(MessageRoles.UsernameRole): b"username",
            int(MessageRoles.TextRole): b"text",
            int(MessageRoles.TimestampRole): b"timestamp",
            int(MessageRoles.KindRole): b"kind",
            int(MessageRoles.EventTypeRole): b"eventType",
            int(MessageRoles.HighlightRole): b"highlight",
        }

    def message_at(self, row: int) -> ChatMessage:
        return self._messages[row]

    def append_message(self, value: Any) -> bool:
        message = self._prepare_message(value)
        if message is None:
            return False
        if len(self._messages) >= self._preferences.max_messages:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            del self._messages[0]
            self.endRemoveRows()
            self.messages_trimmed.emit(1)
        row = len(self._messages)
        self.beginInsertRows(QModelIndex(), row, row)
        self._messages.append(message)
        self.endInsertRows()
        self.messages_added.emit(1)
        return True

    def append_messages(self, values: Iterable[Any]) -> int:
        prepared = [message for value in values if (message := self._prepare_message(value)) is not None]
        if not prepared:
            return 0
        combined = self._messages + prepared
        trimmed = max(0, len(combined) - self._preferences.max_messages)
        self.beginResetModel()
        self._messages = combined[-self._preferences.max_messages :]
        self.endResetModel()
        if trimmed:
            self.messages_trimmed.emit(trimmed)
        self.messages_added.emit(len(prepared))
        return len(prepared)

    def clear(self) -> None:
        if not self._messages:
            return
        self.beginResetModel()
        self._messages.clear()
        self.endResetModel()

    def set_preferences(self, preferences: ChatPreferences | Mapping[str, Any]) -> None:
        next_preferences = (
            preferences
            if isinstance(preferences, ChatPreferences)
            else ChatPreferences.from_mapping(preferences)
        )
        old_count = len(self._messages)
        self._preferences = next_preferences
        if old_count > next_preferences.max_messages:
            trim = old_count - next_preferences.max_messages
            self.beginRemoveRows(QModelIndex(), 0, trim - 1)
            del self._messages[:trim]
            self.endRemoveRows()
            self.messages_trimmed.emit(trim)
        if self._messages:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._messages) - 1, 0),
                [int(MessageRoles.HighlightRole)],
            )
        self.preferences_changed.emit(next_preferences)

    def _prepare_message(self, value: Any) -> ChatMessage | None:
        message = ChatMessage.coerce(value, self._next_sequence)
        self._next_sequence = max(self._next_sequence + 1, message.sequence + 1)
        if not message.text.strip() and message.kind is MessageKind.CHAT:
            return None
        if not message.highlight and self._matches_highlight(message.text):
            message = replace(message, highlight=True)
        if not self._accepts(message):
            return None
        return message

    def _matches_highlight(self, text: str) -> bool:
        folded = text.casefold()
        return any(term.casefold() in folded for term in self._preferences.highlight_terms if term)

    def _accepts(self, message: ChatMessage) -> bool:
        filters = self._preferences.filters
        if (
            message.kind is not MessageKind.CHAT
            or message.platform is Platform.SYSTEM
            or not message.username.strip()
        ):
            return False
        if filters.hide_bot_messages and message.is_bot:
            return False
        if filters.hide_commands and message.text.lstrip().startswith("!"):
            return False
        signature = self._signature(message)
        if filters.collapse_duplicates and self._messages:
            previous = self._messages[-1]
            if message.source_id and previous.source_id == message.source_id:
                return False
            if signature == self._signature(previous):
                return False
        if filters.suppress_repeated_spam:
            repetitions = sum(self._signature(candidate) == signature for candidate in self._messages[-12:])
            if repetitions >= 2:
                return False
        return True

    @staticmethod
    def _signature(message: ChatMessage) -> tuple[str, str, str]:
        normalized = re.sub(r"\s+", " ", message.text.strip()).casefold()
        return message.platform.value, message.username.casefold(), normalized


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
