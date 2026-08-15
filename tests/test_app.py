from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from streamer_console.app import (
    APP_USER_MODEL_ID,
    StreamerConsoleRuntime,
    obs_status_payload,
    set_windows_app_user_model_id,
)
from streamer_console.config import AppConfig, ConfigStore
from streamer_console.controls import ControlResult
from streamer_console.models import ChatPreferences, FilterSettings
from streamer_console.normalizer import NormalizedMessage
from streamer_console.obs_client import ObsStatus
from streamer_console.ui import MainWindow, ensure_application_theme
from streamer_console.session import SessionTracker
from streamer_console.twitch import TwitchUpdate


class FakeIngest:
    def __init__(self, messages=None, telemetry=None) -> None:
        self.messages = list(messages or [])
        self.telemetry = list(telemetry or [])
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1
        return "127.0.0.1", 17840

    def drain(self, max_items=200):
        batch = self.messages[:max_items]
        del self.messages[:max_items]
        return batch

    def drain_telemetry(self, max_items=256):
        batch = self.telemetry[:max_items]
        del self.telemetry[:max_items]
        return batch

    def stop(self):
        self.stopped += 1

    def health_snapshot(self):
        return {"listener_running": bool(self.started and not self.stopped), "platforms": {"twitch": {}, "tiktok": {}}}


class FakeTwitch:
    def __init__(self) -> None:
        self.updates = []
        self.started = self.stopped = 0
        self.markers = []

    def start(self): self.started += 1
    def stop(self): self.stopped += 1
    def drain(self, max_items=100):
        batch = self.updates[:max_items]; del self.updates[:max_items]; return batch
    def connect(self, client_id): pass
    def refresh_info(self): pass
    def search_categories(self, query): pass
    def update_info(self, title, category): pass
    def create_marker(self, description): self.markers.append(description)


class FakeSpotify:
    def __init__(self) -> None:
        self.updates = []
        self.started = self.stopped = 0
    def start(self): self.started += 1
    def stop(self): self.stopped += 1
    def drain(self, max_items=16):
        batch = self.updates[:max_items]; del self.updates[:max_items]; return batch
    def previous(self): pass
    def play_pause(self): pass
    def next(self): pass


class FakeObsMonitor:
    def __init__(self, statuses=None) -> None:
        self.statuses = list(statuses or [])
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def drain(self, max_items=16):
        batch = self.statuses[:max_items]
        del self.statuses[:max_items]
        return batch

    def stop(self):
        self.stopped += 1


class FakeControls:
    def __init__(self) -> None:
        self.brb_calls = 0
        self.discord_calls = 0

    def toggle_brb_privacy(self):
        self.brb_calls += 1
        return ControlResult(
            "brb_privacy", "F1", True, "sent", "F1 sent", {"obs": True}
        )

    def toggle_discord_mute(self):
        self.discord_calls += 1
        return ControlResult(
            "discord_mute", "F2", True, "sent", "F2 sent", {"discord": True}
        )


def message(sequence: int, platform: str, text: str) -> NormalizedMessage:
    return NormalizedMessage(
        sequence=sequence,
        received_at="2026-08-14T18:00:00.000Z",
        platform=platform,
        username=f"Viewer {sequence}",
        text=text,
    )


def event_message(sequence: int, source_id: str) -> NormalizedMessage:
    return NormalizedMessage(
        sequence=sequence,
        received_at="2026-08-14T18:00:00.000Z",
        platform="TWITCH",
        username="Supporter",
        text="followed the stream",
        kind="event",
        event_type="follow",
        source_id=source_id,
    )


class StreamerConsoleRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensure_application_theme()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = ConfigStore(Path(self.temp.name) / "config.json")
        self.ingest = FakeIngest()
        self.obs = FakeObsMonitor()
        self.controls = FakeControls()
        self.window = MainWindow(persist_settings=False, restore_geometry=False)
        self.twitch = FakeTwitch()
        self.spotify = FakeSpotify()
        self.runtime = StreamerConsoleRuntime(
            self.application,
            config=AppConfig(),
            config_store=self.store,
            window=self.window,
            ingest_server=self.ingest,
            obs_monitor=self.obs,
            control_bridge=self.controls,
            twitch_service=self.twitch,
            spotify_service=self.spotify,
            session_tracker=SessionTracker(Path(self.temp.name) / "sessions"),
        )

    def tearDown(self) -> None:
        self.runtime.shutdown()
        self.window.close()
        self.application.processEvents()
        self.temp.cleanup()

    def test_starts_services_and_drains_combined_receipt_order(self) -> None:
        self.ingest.messages.extend(
            [
                message(1, "TWITCH", "first"),
                message(2, "TIKTOK", "second"),
                message(3, "TWITCH", "third"),
            ]
        )

        self.runtime.start()
        self.runtime._drain_messages()
        self.application.processEvents()

        self.assertEqual(self.ingest.started, 1)
        self.assertEqual(self.obs.started, 1)
        self.assertEqual(
            [item.text for item in self.window.model.messages],
            ["first", "second", "third"],
        )
        self.assertEqual(self.window.twitch_connection.detail.text(), "RECEIVING")
        self.assertEqual(self.window.tiktok_connection.detail.text(), "RECEIVING")

    def test_official_eventsub_alert_suppresses_duplicate_browser_alert(self) -> None:
        self.runtime._official_twitch_event_types = {"follow"}
        self.ingest.messages.extend(
            [event_message(1, "browser-event"), event_message(2, "eventsub:official")]
        )

        self.runtime._drain_messages()
        self.application.processEvents()

        self.assertEqual(
            [item.source_id for item in self.window.model.messages],
            ["eventsub:official"],
        )

    def test_native_twitch_chat_suppresses_browser_copy_and_falls_back_on_disconnect(self) -> None:
        self.runtime._native_twitch_chat_ready = True
        self.ingest.messages.extend(
            [
                message(1, "TWITCH", "browser copy"),
                NormalizedMessage(2, "2026-08-15T00:00:00Z", "TWITCH", "Viewer", "native", source_id="eventsub:native"),
            ]
        )
        self.runtime._drain_messages()
        self.assertEqual([item.text for item in self.window.model.messages], ["native"])

        self.twitch.updates.append(TwitchUpdate("eventsub_status", {"connected": False, "state": "reconnecting"}))
        self.runtime._drain_twitch()
        self.assertFalse(self.runtime._native_twitch_chat_ready)

    def test_marker_is_recorded_locally_and_sent_to_same_twitch_service(self) -> None:
        self.runtime._on_marker_requested("Sindragosa kill")
        self.assertEqual(self.twitch.markers, ["Sindragosa kill"])
        self.assertEqual(self.runtime.session_tracker.snapshot()["markers"][0]["description"], "Sindragosa kill")

    def test_tiktok_telemetry_updates_running_counts_without_chat_rows(self) -> None:
        from streamer_console.telemetry import TelemetryUpdate

        self.ingest.telemetry.extend(
            [
                TelemetryUpdate("tiktok_viewers", 31),
                TelemetryUpdate("tiktok_follow", 1),
                TelemetryUpdate("tiktok_like", 5),
                TelemetryUpdate("tiktok_like", 1),
            ]
        )

        self.runtime._drain_messages()
        self.application.processEvents()

        self.assertEqual(self.window.model.rowCount(), 0)
        self.assertEqual(self.window.tiktok_viewers_metric.value.text(), "31")
        self.assertEqual(self.window.tiktok_follows_metric.value.text(), "1")
        self.assertEqual(self.window.tiktok_likes_metric.value.text(), "6")

    def test_obs_snapshot_is_authoritative_for_brb_and_vertical_output(self) -> None:
        self.obs.statuses.append(
            ObsStatus(
                connected=True,
                connection_state="connected",
                streaming=True,
                recording=True,
                main_scene="BRB - Main",
                vertical_scene="BRB - Vertical",
                vertical_outputs=(
                    {"name": "Virtual Camera", "type": "virtual_cam", "active": True},
                ),
                brb_state="brb",
            )
        )

        self.runtime._drain_obs()
        self.application.processEvents()

        self.assertEqual(self.window._brb_state, "brb")
        self.assertEqual(self.window.vertical_metric.value.text(), "ON")
        self.assertEqual(self.window.main_scene.text(), "BRB - Main")

    def test_new_obs_stream_session_resets_running_activity_totals(self) -> None:
        self.runtime._live_metrics["tiktok_follows"] = 7
        self.runtime._live_metrics["tiktok_likes"] = 250
        self.obs.statuses.append(
            ObsStatus(connected=True, connection_state="connected", streaming=False)
        )
        self.runtime._drain_obs()
        self.obs.statuses.append(
            ObsStatus(connected=True, connection_state="connected", streaming=True)
        )
        self.runtime._drain_obs()
        self.application.processEvents()

        self.assertEqual(self.window.tiktok_follows_metric.value.text(), "0")
        self.assertEqual(self.window.tiktok_likes_metric.value.text(), "0")

    def test_f1_invokes_bridge_without_optimistically_changing_brb_state(self) -> None:
        self.window.set_brb_state("live")
        self.application.processEvents()

        self.runtime._on_brb_requested()
        self.application.processEvents()

        self.assertEqual(self.controls.brb_calls, 1)
        self.assertEqual(self.window._brb_state, "live")
        self.assertIn("LIVE", self.window.brb_button.text())

    def test_f2_invokes_bridge_without_fabricating_discord_mute_state(self) -> None:
        self.runtime._on_discord_requested()
        self.application.processEvents()

        self.assertEqual(self.controls.discord_calls, 1)
        self.assertIn("TOGGLE MUTE", self.window.discord_button.text())
        self.assertNotIn("UNAVAILABLE", self.window.discord_button.text())

    def test_preferences_and_window_state_are_saved_to_local_config(self) -> None:
        self.runtime.config.chat.filters.bot_names = ["Nightbot"]
        self.runtime.config.chat.filters.repeated_spam_threshold = 7
        self.runtime.config.chat.filters.repeated_spam_window_seconds = 45.0
        self.window.set_preferences(
            ChatPreferences(
                font_size=36,
                message_spacing=24,
                max_messages=500,
                highlight_terms=("Lausudo", "Tank"),
                filters=FilterSettings(hide_commands=True),
            )
        )
        self.window.resize(700, 1200)
        self.runtime._persist_now()

        saved = self.store.load()
        self.assertEqual(saved.chat.font_size, 36)
        self.assertEqual(saved.chat.message_spacing, 24)
        self.assertEqual(saved.chat.max_messages, 500)
        self.assertEqual(saved.chat.highlight_terms, ["Lausudo", "Tank"])
        self.assertTrue(saved.chat.filters.hide_commands)
        self.assertEqual(saved.chat.filters.bot_names, ["Nightbot"])
        self.assertEqual(saved.chat.filters.repeated_spam_threshold, 7)
        self.assertEqual(saved.chat.filters.repeated_spam_window_seconds, 45.0)
        self.assertEqual(saved.window.width, 700)
        self.assertEqual(saved.window.height, 1200)
        self.assertFalse(saved.start_with_windows)

    def test_fire_and_forget_connection_status_ages_to_no_recent_data(self) -> None:
        self.ingest.messages.extend(
            [message(1, "TWITCH", "hello"), message(2, "TIKTOK", "hi")]
        )
        self.runtime._drain_messages()
        self.application.processEvents()
        self.assertEqual(self.window.twitch_connection.detail.text(), "RECEIVING")
        self.assertEqual(self.window.tiktok_connection.detail.text(), "RECEIVING")

        old = time.monotonic() - self.runtime._connection_stale_seconds - 1.0
        self.runtime._platform_last_seen = {"twitch": old, "tiktok": old}
        self.runtime._age_connection_statuses()
        self.application.processEvents()

        self.assertEqual(
            self.window.twitch_connection.detail.text(), "NO RECENT DATA"
        )
        self.assertEqual(
            self.window.tiktok_connection.detail.text(), "NO RECENT DATA"
        )

    def test_shutdown_stops_each_service_once(self) -> None:
        self.runtime.start()

        self.runtime.shutdown()
        self.runtime.shutdown()

        self.assertEqual(self.ingest.stopped, 1)
        self.assertEqual(self.obs.stopped, 1)
        self.assertTrue(self.store.path.exists())


class SimulationAndMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensure_application_theme()

    def test_simulation_uses_local_messages_and_never_starts_services_or_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ingest = FakeIngest()
            obs = FakeObsMonitor()
            controls = FakeControls()
            window = MainWindow(persist_settings=False, restore_geometry=False)
            runtime = StreamerConsoleRuntime(
                self.application,
                config=AppConfig(),
                config_store=ConfigStore(Path(directory) / "config.json"),
                window=window,
                ingest_server=ingest,
                obs_monitor=obs,
                control_bridge=controls,
                simulate=True,
            )
            runtime.start()
            runtime._on_brb_requested()
            runtime._on_discord_requested()
            self.application.processEvents()

            self.assertEqual(ingest.started, 0)
            self.assertEqual(obs.started, 0)
            self.assertEqual(controls.brb_calls, 0)
            self.assertEqual(controls.discord_calls, 0)
            self.assertGreaterEqual(window.model.rowCount(), 1)
            self.assertFalse(window.brb_button.isEnabled())
            self.assertFalse(window.discord_button.isEnabled())

            runtime.shutdown()
            window.close()

    def test_obs_mapping_prefers_virtual_or_stream_outputs(self) -> None:
        payload = obs_status_payload(
            {
                "vertical_outputs": [
                    {"type": "preview", "active": True},
                    {"type": "virtual_cam", "active": False},
                ]
            }
        )

        self.assertFalse(payload["vertical_active"])

    def test_obs_mapping_keeps_vertical_unknown_without_output_data(self) -> None:
        payload = obs_status_payload(
            {"connected": False, "connection_state": "reconnecting"}
        )

        self.assertIsNone(payload["vertical_active"])

    def test_windows_app_identity_uses_stable_streamer_console_id(self) -> None:
        class FakeShell32:
            def __init__(self) -> None:
                self.value = ""

            def SetCurrentProcessExplicitAppUserModelID(self, value: str) -> int:
                self.value = value
                return 0

        shell32 = FakeShell32()
        self.assertTrue(
            set_windows_app_user_model_id(shell32, platform_name="win32")
        )
        self.assertEqual(shell32.value, APP_USER_MODEL_ID)


if __name__ == "__main__":
    unittest.main()
