"""Normalize Social Stream Ninja payloads into safe, bounded chat records."""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re
import threading
import time
from typing import Any, Callable, Iterable, Mapping

try:
    from .config import FilterSettings
except ImportError:  # pragma: no cover - useful for direct-file diagnostics
    from config import FilterSettings  # type: ignore


_WHITESPACE = re.compile(r"[ \t\f\v]+")
_EXCESS_NEWLINES = re.compile(r"\n{3,}")
_NON_CHAT_MARKER_KEYS = (
    "event",
    "eventType",
    "event_type",
    "system",
)


class _PlainTextHTMLParser(HTMLParser):
    _BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "div", "footer", "h1",
        "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "p",
        "section", "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        attributes = {name.lower(): value for name, value in attrs}
        if tag == "img":
            # SSN represents many Twitch/TikTok emotes as images whose alt text
            # is the correct accessible/plain-text representation.
            label = (
                attributes.get("alt")
                or attributes.get("data-name")
                or attributes.get("data-emote")
                or attributes.get("title")
                or ""
            )
            self.parts.append(label)
        elif tag == "br":
            self.parts.append("\n")
        elif tag in self._BLOCK_TAGS and self.parts:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "template"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if not self._ignored_depth and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def html_to_plain_text(value: Any, *, max_length: int = 4_000) -> str:
    """Convert SSN plain/HTML message fields to readable, non-markup text."""

    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    parser = _PlainTextHTMLParser()
    try:
        parser.feed(value)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        # Malformed markup should not take down ingestion.  This conservative
        # fallback removes tags without interpreting URLs or attributes.
        text = re.sub(r"<[^>]*>", "", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(_WHITESPACE.sub(" ", part).strip() for part in text.split("\n"))
    text = _EXCESS_NEWLINES.sub("\n\n", text).strip()
    # Drop C0 controls while preserving tab/newline; never alter Unicode emoji.
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
    if len(text) > max_length:
        text = text[: max(0, max_length - 1)].rstrip() + "…"
    return text


@dataclass(frozen=True, slots=True)
class NormalizedMessage:
    sequence: int
    received_at: str
    platform: str
    username: str
    text: str
    kind: str = "chat"
    event_type: str = ""
    highlight: bool = False
    source_id: str = ""
    avatar_url: str = ""
    amount: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _platform_name(value: Any) -> str:
    raw = html_to_plain_text(value, max_length=64).lower().replace("_", "").replace("-", "")
    if "tiktok" in raw:
        return "TIKTOK"
    if "twitch" in raw:
        return "TWITCH"
    return raw.upper() if raw else "UNKNOWN"


def _first(payload: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return value
    return ""


def _marker_is_truthy(value: Any) -> bool:
    """Interpret source event flags without treating string ``false`` as true."""

    if value in (None, "", False, 0):
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in {
            "",
            "0",
            "false",
            "null",
            "none",
            "no",
            "off",
        }
    return True


def _unwrap_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept direct SSN messages and common webhook wrapper objects."""

    candidate: Any = payload
    for _ in range(4):
        if not isinstance(candidate, Mapping):
            break
        wrapped: Any = None
        data_received = candidate.get("dataReceived")
        if isinstance(data_received, Mapping) and isinstance(
            data_received.get("overlayNinja"), Mapping
        ):
            wrapped = data_received["overlayNinja"]
        else:
            for key in ("data", "message", "payload", "value", "overlayNinja"):
                value = candidate.get(key)
                if isinstance(value, Mapping):
                    wrapped = value
                    break
                if isinstance(value, str) and value.lstrip().startswith("{"):
                    try:
                        decoded = json.loads(value)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(decoded, Mapping):
                        wrapped = decoded
                        break
        if not isinstance(wrapped, Mapping):
            break
        candidate = wrapped
        if "chatname" in candidate or "chatmessage" in candidate or "event" in candidate:
            break
    return candidate if isinstance(candidate, Mapping) else payload


@dataclass(slots=True)
class _RepeatRecord:
    timestamps: deque[float] = field(default_factory=deque)


class MessageNormalizer:
    """Thread-safe receipt sequencing, normalization, filtering, and retention."""

    def __init__(
        self,
        *,
        highlight_terms: Iterable[str] = ("Lausudo", "@Lausudo"),
        filters: FilterSettings | None = None,
        max_messages: int = 750,
        clock: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.highlight_terms = tuple(
            term.casefold().strip() for term in highlight_terms if term and term.strip()
        )
        self.filters = filters or FilterSettings()
        try:
            requested_max = int(max_messages)
        except (TypeError, ValueError, OverflowError):
            requested_max = 750
        self.max_messages = max(1, min(requested_max, 5_000))
        self._cache_limit = max(512, min(4_096, self.max_messages * 4))
        self._clock = clock
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._sequence = 0
        self._messages: deque[NormalizedMessage] = deque(maxlen=self.max_messages)
        self._seen_ids: OrderedDict[str, None] = OrderedDict()
        self._recent_text: OrderedDict[tuple[str, str, str], float] = OrderedDict()
        self._repeat: OrderedDict[tuple[str, str, str], _RepeatRecord] = OrderedDict()

    def normalize(
        self,
        payload: Mapping[str, Any],
        *,
        sequence: int | None = None,
        received_at: datetime | None = None,
    ) -> NormalizedMessage | None:
        if not isinstance(payload, Mapping):
            return None
        payload = _unwrap_payload(payload)
        now = received_at or self._clock()
        monotonic_now = self._monotonic()

        platform = _platform_name(_first(payload, ("type", "platform", "source")))
        username = html_to_plain_text(
            _first(payload, ("chatname", "username", "user", "author")), max_length=256
        )
        text = html_to_plain_text(
            _first(payload, ("chatmessage", "text", "comment", "content"))
        )
        is_non_chat = any(
            _marker_is_truthy(payload.get(key)) for key in _NON_CHAT_MARKER_KEYS
        )
        # The console is deliberately a conversation surface. Social Stream
        # events, platform notices, counters, and placeholder strings are not
        # viewer chat and must never enter the retained model.
        if platform not in {"TWITCH", "TIKTOK"} or is_non_chat or not username or not text:
            return None

        source_id = html_to_plain_text(
            _first(payload, ("id", "mid", "message_id", "messageId")), max_length=256
        )
        avatar_url = str(_first(payload, ("chatimg", "avatar", "avatar_url")))[:2_048]
        bot_names = {name.casefold() for name in self.filters.bot_names}
        is_bot = bool(payload.get("bot") or payload.get("isBot")) or username.casefold() in bot_names
        text_key = (platform, username.casefold(), text.casefold())

        with self._lock:
            if source_id:
                identity = f"{platform}:{source_id}"
                if identity in self._seen_ids:
                    return None
                self._seen_ids[identity] = None
                self._seen_ids.move_to_end(identity)
                while len(self._seen_ids) > self._cache_limit:
                    self._seen_ids.popitem(last=False)

            if self.filters.hide_bots and is_bot:
                return None
            if self.filters.hide_commands and text.lstrip().startswith("!"):
                return None
            if self.filters.hide_duplicates:
                duplicate_window = max(1.0, self.filters.repeated_spam_window_seconds)
                prior = self._recent_text.get(text_key)
                self._recent_text[text_key] = monotonic_now
                self._recent_text.move_to_end(text_key)
                cutoff = monotonic_now - duplicate_window
                while self._recent_text:
                    oldest_key, oldest_time = next(iter(self._recent_text.items()))
                    if oldest_time >= cutoff:
                        break
                    self._recent_text.pop(oldest_key, None)
                while len(self._recent_text) > self._cache_limit:
                    self._recent_text.popitem(last=False)
                if prior is not None and prior >= cutoff:
                    return None

            if self.filters.hide_repeated_spam:
                window = max(1.0, self.filters.repeated_spam_window_seconds)
                record = self._repeat.setdefault(text_key, _RepeatRecord())
                self._repeat.move_to_end(text_key)
                while record.timestamps and record.timestamps[0] < monotonic_now - window:
                    record.timestamps.popleft()
                record.timestamps.append(monotonic_now)
                try:
                    threshold = int(self.filters.repeated_spam_threshold)
                except (TypeError, ValueError, OverflowError):
                    threshold = 3
                threshold = max(2, min(threshold, 20))
                while len(record.timestamps) > threshold:
                    record.timestamps.popleft()
                while len(self._repeat) > self._cache_limit:
                    self._repeat.popitem(last=False)
                if len(record.timestamps) >= threshold:
                    return None

            if sequence is None:
                self._sequence += 1
                message_sequence = self._sequence
            else:
                message_sequence = int(sequence)
                self._sequence = max(self._sequence, message_sequence)
            combined = f"{username}\n{text}".casefold()
            highlighted = any(term in combined for term in self.highlight_terms)
            message = NormalizedMessage(
                sequence=message_sequence,
                received_at=_iso_utc(now),
                platform=platform,
                username=username or "System",
                text=text,
                kind="chat",
                event_type="",
                highlight=highlighted,
                source_id=source_id,
                avatar_url=avatar_url,
                amount="",
            )
            self._messages.append(message)
            return message

    def snapshot(self) -> list[NormalizedMessage]:
        with self._lock:
            return list(self._messages)

    def diagnostic_cache_sizes(self) -> dict[str, int]:
        """Return counts for bounded-cache regression tests and diagnostics."""

        with self._lock:
            return {
                "limit": self._cache_limit,
                "source_ids": len(self._seen_ids),
                "recent_text": len(self._recent_text),
                "repeat_keys": len(self._repeat),
                "repeat_timestamps": sum(
                    len(record.timestamps) for record in self._repeat.values()
                ),
            }

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
            self._seen_ids.clear()
            self._recent_text.clear()
            self._repeat.clear()


def normalize_social_stream_message(
    payload: Mapping[str, Any],
    *,
    sequence: int = 1,
    received_at: datetime | None = None,
    highlight_terms: Iterable[str] = ("Lausudo", "@Lausudo"),
) -> NormalizedMessage | None:
    """Stateless convenience wrapper for tests and one-off callers."""

    return MessageNormalizer(highlight_terms=highlight_terms).normalize(
        payload, sequence=sequence, received_at=received_at
    )
