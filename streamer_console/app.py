"""Application coordinator for the Lausudo Streamer Console.

Qt owns the presentation thread.  Social Stream ingestion and OBS polling run
in their existing bounded background workers; short timers drain their queues
onto the GUI thread.  The two control buttons deliberately call
``ControlBridge`` so they emit the same F1/F2 keys as the physical keyboard.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import ctypes
from dataclasses import asdict, is_dataclass
import logging
from pathlib import Path
import sys
import time
from typing import Any

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication

from .config import (
    AppConfig,
    ChatSettings,
    ConfigStore,
    FilterSettings as ConfigFilterSettings,
    WindowSettings,
)
from .controls import ControlBridge, ControlResult
from .ingest import SocialStreamIngestServer
from .logging_setup import configure_logging
from .models import ChatPreferences, ConnectionState, Platform
from .normalizer import MessageNormalizer
from .obs_client import ObsMonitor, ObsStatus
from .ui import MainWindow, ensure_application_theme
from .twitch import TwitchService, TwitchUpdate


LOGGER = logging.getLogger("streamer_console.app")
APP_USER_MODEL_ID = "NeilMitchell.StreamerConsole"


def set_windows_app_user_model_id(
    shell32: Any | None = None,
    *,
    platform_name: str | None = None,
) -> bool:
    """Give Windows a stable identity for taskbar grouping and pinning."""

    if (platform_name or sys.platform) != "win32":
        return False
    try:
        if shell32 is None:
            setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
            setter.argtypes = [ctypes.c_wchar_p]
            setter.restype = ctypes.c_long
        else:
            setter = shell32.SetCurrentProcessExplicitAppUserModelID
        return int(setter(APP_USER_MODEL_ID)) == 0
    except (AttributeError, OSError, TypeError, ValueError):
        return False


_SIMULATED_MESSAGES: tuple[dict[str, Any], ...] = (
    {
        "type": "twitch",
        "chatname": "PizzaGuy",
        "chatmessage": "nice pull 🔥",
        "id": "sim-twitch-1",
    },
    {
        "type": "tiktok",
        "chatname": "Sarah",
        "chatmessage": "what server is this?",
        "id": "sim-tiktok-1",
    },
    {
        "type": "twitch",
        "chatname": "RaidFriend",
        "chatmessage": "@Lausudo that recovery was clean",
        "id": "sim-twitch-2",
    },
    {
        "type": "tiktok",
        "chatname": "John",
        "chatmessage": "what addon is that? 👀",
        "id": "sim-tiktok-2",
    },
    {
        "type": "twitch",
        "chatname": "GuildMate",
        "chatmessage": "Raid: 12 viewers joined",
        "event": "raid",
        "id": "sim-twitch-event-1",
    },
)


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        return dict(converted) if isinstance(converted, Mapping) else {}
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return {}


def obs_status_payload(status: ObsStatus | Mapping[str, Any] | Any) -> dict[str, Any]:
    """Return the UI status shape, including Aitum output activity."""

    payload = _as_mapping(status)
    outputs = payload.get("vertical_outputs") or ()
    active_relevant: list[bool] = []
    active_fallback: list[bool] = []
    for output in outputs if isinstance(outputs, (list, tuple)) else ():
        item = _as_mapping(output)
        active = bool(item.get("active", item.get("output_active", False)))
        active_fallback.append(active)
        output_type = str(item.get("type", "")).casefold().replace("_", "")
        if "virtual" in output_type or "stream" in output_type:
            active_relevant.append(active)
    if active_relevant:
        payload["vertical_active"] = any(active_relevant)
    elif active_fallback:
        payload["vertical_active"] = any(active_fallback)
    else:
        payload["vertical_active"] = None
    return payload


class StreamerConsoleRuntime(QObject):
    """Own application services and bridge them to a :class:`MainWindow`."""

    def __init__(
        self,
        application: QApplication,
        *,
        config: AppConfig | None = None,
        config_store: ConfigStore | None = None,
        window: MainWindow | None = None,
        normalizer: MessageNormalizer | None = None,
        ingest_server: SocialStreamIngestServer | None = None,
        obs_monitor: ObsMonitor | None = None,
        control_bridge: ControlBridge | None = None,
        twitch_service: TwitchService | None = None,
        simulate: bool = False,
    ) -> None:
        super().__init__()
        self.application = application
        self.config_store = config_store or ConfigStore()
        self.config = config or self.config_store.load()
        self.simulate = bool(simulate)
        self.normalizer = normalizer or MessageNormalizer(
            highlight_terms=self.config.chat.highlight_terms,
            filters=self.config.chat.filters,
            max_messages=self.config.chat.max_messages,
        )
        self.ingest_server = ingest_server or SocialStreamIngestServer(
            self.normalizer, self.config.ingest
        )
        self.obs_monitor = obs_monitor or ObsMonitor(self.config.obs)
        self.control_bridge = control_bridge or ControlBridge()
        self.twitch_service = twitch_service or TwitchService(
            self.config.twitch, event_sink=getattr(self.ingest_server, "submit", None)
        )
        self.window = window or MainWindow(
            preferences=self.config.chat,
            persist_settings=False,
            restore_geometry=False,
        )
        self.window.set_twitch_client_id(self.config.twitch.client_id)

        self._started = False
        self._stopped = False
        self._simulation_index = 0
        self._platform_last_seen: dict[str, float] = {}
        self._official_twitch_event_types: set[str] = set()
        self._connection_stale_seconds = 30.0

        self._ingest_timer = QTimer(self)
        self._ingest_timer.setInterval(75)
        self._ingest_timer.timeout.connect(self._drain_messages)
        self._obs_timer = QTimer(self)
        self._obs_timer.setInterval(250)
        self._obs_timer.timeout.connect(self._drain_obs)
        self._twitch_timer = QTimer(self)
        self._twitch_timer.setInterval(100)
        self._twitch_timer.timeout.connect(self._drain_twitch)
        self._connection_timer = QTimer(self)
        self._connection_timer.setInterval(5_000)
        self._connection_timer.timeout.connect(self._age_connection_statuses)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._persist_now)
        self._simulation_timer = QTimer(self)
        self._simulation_timer.setInterval(650)
        self._simulation_timer.timeout.connect(self._emit_simulated_message)

        self.window.brb_requested.connect(self._on_brb_requested)
        self.window.discord_toggle_requested.connect(self._on_discord_requested)
        self.window.preferences_changed.connect(self._on_preferences_changed)
        self.window.window_preferences_changed.connect(
            self._on_window_preferences_changed
        )
        self.window.twitch_connect_requested.connect(self._on_twitch_connect)
        self.window.twitch_refresh_requested.connect(self.twitch_service.refresh_info)
        self.window.twitch_update_requested.connect(self.twitch_service.update_info)
        self.window.twitch_category_search_requested.connect(
            self.twitch_service.search_categories
        )
        self.window.installEventFilter(self)
        self.application.aboutToQuit.connect(self.shutdown)

        self.window.restore_window_preferences(self.config.window)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        LOGGER.info("Streamer Console starting simulation=%s", self.simulate)

        if self.simulate:
            self.window.update_connection(Platform.TWITCH, "connected", "SIMULATED")
            self.window.update_connection(Platform.TIKTOK, "connected", "SIMULATED")
            self.window.update_obs_status(
                {
                    "connected": True,
                    "streaming": True,
                    "recording": True,
                    "vertical_active": True,
                    "main_scene": "WoW Raid (simulation)",
                    "vertical_scene": "WoW Raid TikTok (simulation)",
                    "brb_state": "live",
                }
            )
            self.window.brb_button.setEnabled(False)
            self.window.discord_button.setEnabled(False)
            self.window.stream_info_button.setEnabled(False)
            self.window.statusBar().showMessage(
                "SIMULATION MODE — local messages only; controls disabled"
            )
            self._simulation_timer.start()
            self._emit_simulated_message()
            return

        if self.config.twitch.enabled:
            self.twitch_service.start()
            self._twitch_timer.start()

        try:
            self.ingest_server.start()
        except Exception as exc:
            LOGGER.error(
                "Social Stream listener failed type=%s", type(exc).__name__
            )
            for platform in (Platform.TWITCH, Platform.TIKTOK):
                self.window.update_connection(
                    platform, ConnectionState.DISCONNECTED, "LISTENER ERROR"
                )
        else:
            for platform in (Platform.TWITCH, Platform.TIKTOK):
                self.window.update_connection(
                    platform, ConnectionState.UNKNOWN, "WAITING FOR CHAT"
                )
            self._ingest_timer.start()
            self._connection_timer.start()

        if self.config.obs.enabled:
            try:
                self.obs_monitor.start()
            except Exception as exc:
                LOGGER.error("OBS monitor failed type=%s", type(exc).__name__)
                self.window.update_obs_status(
                    {"connected": False, "connection_state": "disconnected"}
                )
            else:
                self._obs_timer.start()
        else:
            self.window.update_obs_status(
                {"connected": False, "connection_state": "disabled"}
            )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.window and event.type() in {
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
        }:
            self._schedule_save()
        return super().eventFilter(watched, event)

    def _drain_messages(self) -> None:
        try:
            messages = self.ingest_server.drain(250)
        except Exception as exc:
            LOGGER.error("Chat queue drain failed type=%s", type(exc).__name__)
            return
        if not messages:
            return
        visible_messages = [
            message
            for message in messages
            if not (
                str(getattr(message, "platform", "")).casefold() == "twitch"
                and str(getattr(message, "kind", "")).casefold() == "event"
                and str(getattr(message, "event_type", "")).casefold()
                in self._official_twitch_event_types
                and not str(getattr(message, "source_id", "")).startswith("eventsub:")
            )
        ]
        if visible_messages:
            self.window.add_messages(visible_messages)
        received_platforms = {
            str(getattr(message, "platform", "")).strip().casefold()
            for message in messages
        }
        if "twitch" in received_platforms:
            self._platform_last_seen["twitch"] = time.monotonic()
            self.window.update_connection(
                Platform.TWITCH, ConnectionState.CONNECTED, "RECEIVING"
            )
        if "tiktok" in received_platforms:
            self._platform_last_seen["tiktok"] = time.monotonic()
            self.window.update_connection(
                Platform.TIKTOK, ConnectionState.CONNECTED, "RECEIVING"
            )

    def _age_connection_statuses(self) -> None:
        """Avoid claiming a fire-and-forget collector is connected forever."""

        now = time.monotonic()
        for key, platform in (
            ("twitch", Platform.TWITCH),
            ("tiktok", Platform.TIKTOK),
        ):
            last_seen = self._platform_last_seen.get(key)
            if last_seen is None:
                continue
            if now - last_seen >= self._connection_stale_seconds:
                self.window.update_connection(
                    platform, ConnectionState.UNKNOWN, "NO RECENT DATA"
                )
                del self._platform_last_seen[key]

    def _drain_obs(self) -> None:
        try:
            statuses = self.obs_monitor.drain(16)
        except Exception as exc:
            LOGGER.error("OBS status drain failed type=%s", type(exc).__name__)
            return
        if statuses:
            # Only the newest snapshot matters; this also prevents UI lag after
            # a temporarily blocked event loop.
            self.window.update_obs_status(obs_status_payload(statuses[-1]))

    def _drain_twitch(self) -> None:
        try:
            updates = self.twitch_service.drain(100)
        except Exception as exc:
            LOGGER.error("Twitch update drain failed type=%s", type(exc).__name__)
            return
        for update in updates:
            if update.kind == "event":
                raw = update.payload.get("message", {})
                if isinstance(raw, Mapping):
                    message = self.normalizer.normalize(raw)
                    if message is not None:
                        self.window.add_message(message)
                        self._platform_last_seen["twitch"] = time.monotonic()
                        self.window.update_connection(
                            Platform.TWITCH, ConnectionState.CONNECTED, "RECEIVING"
                        )
            else:
                self.window.update_twitch(update)
                if update.kind == "eventsub_status" and update.payload.get("connected"):
                    event_types = update.payload.get("event_types", ())
                    if isinstance(event_types, (list, tuple, set)):
                        self._official_twitch_event_types = {
                            str(value).casefold() for value in event_types
                        }
                    self.window.update_connection(
                        Platform.TWITCH, ConnectionState.CONNECTED, "ALERTS READY"
                    )

    def _on_twitch_connect(self, client_id: str) -> None:
        normalized = client_id.strip()
        if not normalized:
            self.window.update_twitch(
                TwitchUpdate("error", {"message": "Enter the Twitch Client ID first"})
            )
            return
        self.config.twitch.client_id = normalized
        self.window.set_twitch_client_id(normalized)
        self._schedule_save()
        self.twitch_service.connect(normalized)

    def _emit_simulated_message(self) -> None:
        payload = dict(
            _SIMULATED_MESSAGES[self._simulation_index % len(_SIMULATED_MESSAGES)]
        )
        payload["id"] = f"{payload['id']}-{self._simulation_index}"
        self._simulation_index += 1
        message = self.normalizer.normalize(payload)
        if message is not None:
            self.window.add_message(message)

    def _on_brb_requested(self) -> None:
        if self.simulate:
            return
        result = self.control_bridge.toggle_brb_privacy()
        self._report_control_result(result, self.window.brb_button)
        # Never set BRB optimistically.  The next OBS snapshot owns the state.

    def _on_discord_requested(self) -> None:
        if self.simulate:
            return
        result = self.control_bridge.toggle_discord_mute()
        self._report_control_result(result, self.window.discord_button)
        # Discord has no supported local mute-state API here, so keep UNKNOWN.
        self.window.set_discord_state(None)

    def _report_control_result(self, result: ControlResult, button: Any) -> None:
        level = logging.INFO if result.success else logging.WARNING
        LOGGER.log(
            level,
            "Control result control=%s code=%s success=%s",
            result.control,
            result.code,
            result.success,
        )
        button.setToolTip(result.message)
        self.window.statusBar().showMessage(result.message, 5_000)
        if not result.success:
            QApplication.beep()

    def _on_preferences_changed(self, values: Mapping[str, Any] | Any) -> None:
        preferences = ChatPreferences.from_mapping(values)
        filters = preferences.filters
        existing_filters = self.config.chat.filters
        self.config.chat = ChatSettings(
            font_size=preferences.font_size,
            message_spacing=preferences.message_spacing,
            max_messages=preferences.max_messages,
            show_timestamps=preferences.show_timestamps,
            highlight_terms=list(preferences.highlight_terms),
            filters=ConfigFilterSettings(
                hide_bots=filters.hide_bot_messages,
                bot_names=list(existing_filters.bot_names),
                hide_commands=filters.hide_commands,
                hide_duplicates=filters.collapse_duplicates,
                hide_repeated_spam=filters.suppress_repeated_spam,
                repeated_spam_threshold=existing_filters.repeated_spam_threshold,
                repeated_spam_window_seconds=(
                    existing_filters.repeated_spam_window_seconds
                ),
                # Events and system notices never enter the chat model. Keep
                # the persisted compatibility flag aligned with that contract.
                hide_system_messages=True,
            ),
        )
        # Ingestion applies changes to subsequent messages while the Qt model
        # handles its own retention and existing presentation immediately.
        self.normalizer.highlight_terms = tuple(
            term.casefold().strip()
            for term in self.config.chat.highlight_terms
            if term.strip()
        )
        self.normalizer.filters = self.config.chat.filters
        self.normalizer.max_messages = self.config.chat.max_messages
        self._schedule_save()

    def _on_window_preferences_changed(self, values: Mapping[str, Any] | Any) -> None:
        mapping = _as_mapping(values)
        self.config.window.borderless = bool(mapping.get("borderless", False))
        self.config.window.always_on_top = bool(
            mapping.get("always_on_top", False)
        )
        self._schedule_save()

    def _capture_window_settings(self) -> None:
        captured = self.window.capture_window_preferences()
        geometry = self.window.normalGeometry() if self.window.isMaximized() else self.window.geometry()
        self.config.window = WindowSettings(
            width=geometry.width(),
            height=geometry.height(),
            x=geometry.x(),
            y=geometry.y(),
            monitor_name=str(captured.get("screen", "")),
            borderless=bool(captured.get("borderless", False)),
            always_on_top=bool(captured.get("always_on_top", False)),
            maximized=self.window.isMaximized(),
        )

    def _schedule_save(self) -> None:
        if not self._stopped:
            self._save_timer.start()

    def _persist_now(self) -> None:
        if self._stopped:
            return
        try:
            self._capture_window_settings()
            self.config_store.save(self.config)
        except Exception as exc:
            LOGGER.error("Configuration save failed type=%s", type(exc).__name__)

    def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        LOGGER.info("Streamer Console shutting down")
        for timer in (
            self._ingest_timer,
            self._obs_timer,
            self._connection_timer,
            self._save_timer,
            self._simulation_timer,
            self._twitch_timer,
        ):
            timer.stop()
        try:
            self._capture_window_settings()
            self.config_store.save(self.config)
        except Exception as exc:
            LOGGER.error("Final configuration save failed type=%s", type(exc).__name__)
        if not self.simulate:
            try:
                self.ingest_server.stop()
            except Exception as exc:
                LOGGER.error("Ingest shutdown failed type=%s", type(exc).__name__)
            try:
                self.obs_monitor.stop()
            except Exception as exc:
                LOGGER.error("OBS shutdown failed type=%s", type(exc).__name__)
            try:
                self.twitch_service.stop()
            except Exception as exc:
                LOGGER.error("Twitch shutdown failed type=%s", type(exc).__name__)
        LOGGER.info("Streamer Console stopped")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch Lausudo Streamer Console")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Use only local simulated chat/status data and disable controls.",
    )
    parser.add_argument(
        "--run-seconds",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="Close automatically after SECONDS (useful with --simulate).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Use an alternate local configuration file.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    windows_identity_ready = set_windows_app_user_model_id()
    arguments = build_argument_parser().parse_args(
        list(argv) if argv is not None else sys.argv[1:]
    )
    if arguments.run_seconds < 0:
        raise SystemExit("--run-seconds must be zero or greater")

    store = ConfigStore(arguments.config)
    config = store.load()
    configure_logging(config.logging)
    LOGGER.info("Application startup")
    if sys.platform == "win32" and not windows_identity_ready:
        LOGGER.warning("Windows taskbar application identity was unavailable")

    application = ensure_application_theme()
    application.setApplicationName("Streamer Console")
    application.setOrganizationName("Neil Mitchell")
    application.setQuitOnLastWindowClosed(True)
    runtime = StreamerConsoleRuntime(
        application,
        config=config,
        config_store=store,
        simulate=arguments.simulate,
    )
    runtime.start()
    runtime.window.show()

    if arguments.run_seconds > 0:
        QTimer.singleShot(
            max(1, int(arguments.run_seconds * 1_000)), application.quit
        )
    return application.exec()


if __name__ == "__main__":  # pragma: no cover - exercised by launch smoke tests
    raise SystemExit(main())
