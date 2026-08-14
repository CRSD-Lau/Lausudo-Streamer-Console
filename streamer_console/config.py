"""Local, secret-free configuration for Streamer Console.

The console's user preferences live below ``%LOCALAPPDATA%``.  OBS WebSocket
credentials deliberately do not: :mod:`streamer_console.obs_client` reads
OBS's own configuration only when it connects.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, TypeVar


APP_VENDOR = "NeilMitchell"
APP_NAME = "StreamerConsole"
CONFIG_FILENAME = "config.json"


@dataclass(slots=True)
class WindowSettings:
    width: int = 1080
    height: int = 1920
    x: int | None = None
    y: int | None = None
    monitor_name: str = ""
    borderless: bool = False
    always_on_top: bool = False
    maximized: bool = False


@dataclass(slots=True)
class FilterSettings:
    """Conservative defaults: only incontrovertible source-ID duplicates drop."""

    hide_bots: bool = False
    bot_names: list[str] = field(default_factory=list)
    hide_commands: bool = False
    hide_duplicates: bool = False
    hide_repeated_spam: bool = False
    repeated_spam_threshold: int = 3
    repeated_spam_window_seconds: float = 20.0
    hide_system_messages: bool = False


@dataclass(slots=True)
class ChatSettings:
    font_size: int = 28
    message_spacing: int = 18
    max_messages: int = 750
    show_timestamps: bool = False
    highlight_terms: list[str] = field(
        default_factory=lambda: ["Lausudo", "@Lausudo"]
    )
    filters: FilterSettings = field(default_factory=FilterSettings)


@dataclass(slots=True)
class IngestSettings:
    host: str = "127.0.0.1"
    port: int = 17840
    path: str = "/ingest/socialstream"
    max_body_bytes: int = 262_144
    queue_size: int = 1_000


@dataclass(slots=True)
class ObsSettings:
    enabled: bool = True
    host: str = "127.0.0.1"
    # A value of 0 means "use the port from OBS's own configuration".
    port: int = 0
    poll_interval_seconds: float = 1.5
    reconnect_initial_seconds: float = 1.0
    reconnect_max_seconds: float = 20.0
    mic_input: str = "Mic/Aux"
    brb_main_scene: str = "BRB - Main"
    brb_vertical_scene: str = "BRB - Vertical"
    aitum_vendor_name: str = "aitum-stream-suite"
    aitum_vertical_canvas: str = "Vertical"


@dataclass(slots=True)
class LoggingSettings:
    level: str = "INFO"
    max_bytes: int = 1_048_576
    backup_count: int = 3


@dataclass(slots=True)
class AppConfig:
    version: int = 1
    window: WindowSettings = field(default_factory=WindowSettings)
    chat: ChatSettings = field(default_factory=ChatSettings)
    ingest: IngestSettings = field(default_factory=IngestSettings)
    obs: ObsSettings = field(default_factory=ObsSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    start_with_windows: bool = False


def app_data_dir(local_app_data: str | Path | None = None) -> Path:
    """Return the application data directory without creating it."""

    if local_app_data is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / APP_VENDOR / APP_NAME


def config_path(local_app_data: str | Path | None = None) -> Path:
    return app_data_dir(local_app_data) / CONFIG_FILENAME


def log_dir(local_app_data: str | Path | None = None) -> Path:
    return app_data_dir(local_app_data) / "logs"


T = TypeVar("T")


def _coerce_dataclass(cls: type[T], value: Any) -> T:
    """Create a dataclass from a mapping while ignoring forward-version keys."""

    if not isinstance(value, Mapping):
        return cls()  # type: ignore[call-arg]

    known = {item.name: item for item in fields(cls)}
    kwargs: dict[str, Any] = {}
    for name, item in known.items():
        if name not in value:
            continue
        raw = value[name]
        if cls is AppConfig:
            nested: dict[str, type[Any]] = {
                "window": WindowSettings,
                "chat": ChatSettings,
                "ingest": IngestSettings,
                "obs": ObsSettings,
                "logging": LoggingSettings,
            }
            if name in nested:
                raw = _coerce_dataclass(nested[name], raw)
        elif cls is ChatSettings and name == "filters":
            raw = _coerce_dataclass(FilterSettings, raw)
        kwargs[name] = raw
    try:
        return cls(**kwargs)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        # A hand-edited or old file must not prevent the console from starting.
        return cls()  # type: ignore[call-arg]


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(parsed, maximum))


def _safe_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(minimum, min(parsed, maximum))


def _safe_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0"}:
            return False
    return default


def _safe_text(value: Any, default: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str):
        return default
    return value[:max_length]


def _safe_text_list(
    value: Any,
    default: list[str],
    *,
    max_items: int = 100,
    max_item_length: int = 128,
) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    return [
        item[:max_item_length]
        for item in value[:max_items]
        if isinstance(item, str) and item
    ]


def _safe_optional_int(
    value: Any, default: int | None, minimum: int, maximum: int
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(parsed, maximum))


def _clamp_config(config: AppConfig) -> AppConfig:
    """Keep user-editable values within safe operational bounds."""

    defaults = AppConfig()
    if not isinstance(config.window, WindowSettings):
        config.window = WindowSettings()
    if not isinstance(config.chat, ChatSettings):
        config.chat = ChatSettings()
    if not isinstance(config.chat.filters, FilterSettings):
        config.chat.filters = FilterSettings()
    if not isinstance(config.ingest, IngestSettings):
        config.ingest = IngestSettings()
    if not isinstance(config.obs, ObsSettings):
        config.obs = ObsSettings()
    if not isinstance(config.logging, LoggingSettings):
        config.logging = LoggingSettings()

    config.version = _safe_int(config.version, defaults.version, 1, 1_000)
    config.window.width = _safe_int(
        config.window.width, defaults.window.width, 480, 7_680
    )
    config.window.height = _safe_int(
        config.window.height, defaults.window.height, 640, 7_680
    )
    config.window.x = _safe_optional_int(config.window.x, None, -100_000, 100_000)
    config.window.y = _safe_optional_int(config.window.y, None, -100_000, 100_000)
    config.window.monitor_name = _safe_text(
        config.window.monitor_name, defaults.window.monitor_name, max_length=512
    )
    config.window.borderless = _safe_bool(
        config.window.borderless, defaults.window.borderless
    )
    config.window.always_on_top = _safe_bool(
        config.window.always_on_top, defaults.window.always_on_top
    )
    config.window.maximized = _safe_bool(
        config.window.maximized, defaults.window.maximized
    )

    config.chat.font_size = _safe_int(
        config.chat.font_size, defaults.chat.font_size, 14, 72
    )
    config.chat.message_spacing = _safe_int(
        config.chat.message_spacing, defaults.chat.message_spacing, 0, 80
    )
    config.chat.max_messages = _safe_int(
        config.chat.max_messages, defaults.chat.max_messages, 100, 5_000
    )
    config.chat.show_timestamps = _safe_bool(
        config.chat.show_timestamps, defaults.chat.show_timestamps
    )
    config.chat.highlight_terms = _safe_text_list(
        config.chat.highlight_terms, defaults.chat.highlight_terms
    )

    config.ingest.host = _safe_text(
        config.ingest.host, defaults.ingest.host, max_length=64
    ).strip().lower()
    if config.ingest.host not in {"127.0.0.1", "localhost", "::1"}:
        config.ingest.host = defaults.ingest.host
    config.ingest.port = _safe_int(
        config.ingest.port, defaults.ingest.port, 0, 65_535
    )
    config.ingest.path = _safe_text(
        config.ingest.path, defaults.ingest.path, max_length=256
    )
    if not config.ingest.path.startswith("/"):
        config.ingest.path = defaults.ingest.path
    config.ingest.max_body_bytes = _safe_int(
        config.ingest.max_body_bytes,
        defaults.ingest.max_body_bytes,
        1_024,
        2 * 1024 * 1024,
    )
    config.ingest.queue_size = _safe_int(
        config.ingest.queue_size, defaults.ingest.queue_size, 100, 10_000
    )

    config.obs.enabled = _safe_bool(config.obs.enabled, defaults.obs.enabled)
    config.obs.host = _safe_text(config.obs.host, defaults.obs.host, max_length=256)
    config.obs.port = _safe_int(config.obs.port, defaults.obs.port, 0, 65_535)
    config.obs.poll_interval_seconds = _safe_float(
        config.obs.poll_interval_seconds,
        defaults.obs.poll_interval_seconds,
        0.5,
        60.0,
    )
    config.obs.reconnect_initial_seconds = _safe_float(
        config.obs.reconnect_initial_seconds,
        defaults.obs.reconnect_initial_seconds,
        0.25,
        60.0,
    )
    config.obs.reconnect_max_seconds = _safe_float(
        config.obs.reconnect_max_seconds,
        defaults.obs.reconnect_max_seconds,
        config.obs.reconnect_initial_seconds,
        300.0,
    )
    config.obs.mic_input = _safe_text(
        config.obs.mic_input, defaults.obs.mic_input, max_length=512
    )
    config.obs.brb_main_scene = _safe_text(
        config.obs.brb_main_scene, defaults.obs.brb_main_scene, max_length=512
    )
    config.obs.brb_vertical_scene = _safe_text(
        config.obs.brb_vertical_scene, defaults.obs.brb_vertical_scene, max_length=512
    )
    config.obs.aitum_vendor_name = _safe_text(
        config.obs.aitum_vendor_name, defaults.obs.aitum_vendor_name, max_length=256
    )
    config.obs.aitum_vertical_canvas = _safe_text(
        config.obs.aitum_vertical_canvas,
        defaults.obs.aitum_vertical_canvas,
        max_length=256,
    )

    config.logging.level = _safe_text(
        config.logging.level, defaults.logging.level, max_length=16
    ).upper()
    if config.logging.level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        config.logging.level = defaults.logging.level
    config.logging.max_bytes = _safe_int(
        config.logging.max_bytes,
        defaults.logging.max_bytes,
        64 * 1024,
        50 * 1024 * 1024,
    )
    config.logging.backup_count = _safe_int(
        config.logging.backup_count, defaults.logging.backup_count, 1, 10
    )
    filters_config = config.chat.filters
    default_filters = defaults.chat.filters
    filters_config.hide_bots = _safe_bool(
        filters_config.hide_bots, default_filters.hide_bots
    )
    filters_config.bot_names = _safe_text_list(
        filters_config.bot_names, default_filters.bot_names
    )
    filters_config.hide_commands = _safe_bool(
        filters_config.hide_commands, default_filters.hide_commands
    )
    filters_config.hide_duplicates = _safe_bool(
        filters_config.hide_duplicates, default_filters.hide_duplicates
    )
    filters_config.hide_repeated_spam = _safe_bool(
        filters_config.hide_repeated_spam, default_filters.hide_repeated_spam
    )
    filters_config.repeated_spam_threshold = _safe_int(
        filters_config.repeated_spam_threshold,
        default_filters.repeated_spam_threshold,
        2,
        20,
    )
    filters_config.repeated_spam_window_seconds = _safe_float(
        filters_config.repeated_spam_window_seconds,
        default_filters.repeated_spam_window_seconds,
        1.0,
        600.0,
    )
    filters_config.hide_system_messages = _safe_bool(
        filters_config.hide_system_messages, default_filters.hide_system_messages
    )
    config.start_with_windows = _safe_bool(
        config.start_with_windows, defaults.start_with_windows
    )
    return config


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load preferences, returning safe defaults for missing/invalid files."""

    target = Path(path) if path is not None else config_path()
    try:
        with target.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError, RecursionError):
        return AppConfig()
    return _clamp_config(_coerce_dataclass(AppConfig, raw))


def save_config(config: AppConfig, path: str | Path | None = None) -> Path:
    """Atomically persist preferences as UTF-8 JSON.

    The temporary file is created beside the destination so ``os.replace`` is
    atomic on Windows as well as POSIX filesystems.
    """

    if not is_dataclass(config):
        raise TypeError("config must be an AppConfig instance")
    target = Path(path) if path is not None else config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(_clamp_config(config))
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target


class ConfigStore:
    """Small convenience facade used by the UI."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else config_path()

    def load(self) -> AppConfig:
        return load_config(self.path)

    def save(self, config: AppConfig) -> Path:
        return save_config(config, self.path)
