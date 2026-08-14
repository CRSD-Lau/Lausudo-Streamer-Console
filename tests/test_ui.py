from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QStyleOptionViewItem

from streamer_console.models import (
    ChatListModel,
    ChatPreferences,
    ConnectionState,
    MessageRoles,
    Platform,
)
from streamer_console.config import ChatSettings
from streamer_console.config import WindowSettings
from streamer_console.ui import MainWindow, ensure_application_theme


def pump_events(rounds: int = 3) -> None:
    application = ensure_application_theme()
    for _ in range(rounds):
        application.processEvents()


class ChatListModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensure_application_theme()

    def test_model_is_bounded_and_keeps_receipt_order(self) -> None:
        model = ChatListModel(preferences=ChatPreferences(max_messages=100))
        added = model.append_messages(
            {
                "sequence": index,
                "platform": "twitch" if index % 2 else "tiktok",
                "username": f"viewer-{index}",
                "text": f"message {index}",
            }
            for index in range(350)
        )

        self.assertEqual(added, 350)
        self.assertEqual(model.rowCount(), 100)
        self.assertEqual(model.message_at(0).sequence, 250)
        self.assertEqual(model.message_at(99).sequence, 349)

    def test_unicode_emoji_and_highlight_terms_are_preserved(self) -> None:
        model = ChatListModel()
        text = "@Lausudo — great pull 🔥 漢字 👨‍👩‍👧‍👦"
        self.assertTrue(
            model.append_message(
                {"platform": "tiktok", "username": "Sára", "text": text}
            )
        )
        index = model.index(0, 0)

        self.assertEqual(index.data(int(MessageRoles.TextRole)), text)
        self.assertEqual(index.data(int(MessageRoles.PlatformRole)), "tiktok")
        self.assertTrue(index.data(int(MessageRoles.HighlightRole)))

    def test_non_chat_system_rows_are_hidden_by_default(self) -> None:
        model = ChatListModel()
        model.append_messages(
            [
                {"platform": "twitch", "username": "GearBot", "text": "!gear", "is_bot": True},
                {"platform": "twitch", "username": "GearBot", "text": "!gear", "is_bot": True},
                {"platform": "system", "username": "System", "text": "collector ready", "kind": "system"},
            ]
        )

        self.assertEqual(model.rowCount(), 2)
        self.assertTrue(
            all(message.platform is not Platform.SYSTEM for message in model.messages)
        )

    def test_backend_chat_settings_dataclass_is_accepted(self) -> None:
        settings = ChatSettings(font_size=32, message_spacing=20, max_messages=500)
        preferences = ChatPreferences.from_mapping(settings)

        self.assertEqual(preferences.font_size, 32)
        self.assertEqual(preferences.message_spacing, 20)
        self.assertEqual(preferences.max_messages, 500)
        self.assertFalse(preferences.filters.show_system_messages)


class PortraitWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensure_application_theme()

    def setUp(self) -> None:
        self.window = MainWindow(persist_settings=False, restore_geometry=False)

    def tearDown(self) -> None:
        self.window.close()
        pump_events()

    def test_default_window_uses_native_resizable_frame(self) -> None:
        flags = self.window.windowFlags()

        self.assertFalse(bool(flags & Qt.WindowType.FramelessWindowHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowTitleHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowSystemMenuHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowMinimizeButtonHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowMaximizeButtonHint))

    def test_borderless_round_trip_restores_native_frame_controls(self) -> None:
        self.window.show()
        pump_events()
        self.window.setGeometry(40, 50, 700, 700)
        pump_events()
        normal_geometry = QRect(self.window.normalGeometry())

        self.window.set_window_options(borderless=True, always_on_top=False)
        pump_events()
        self.assertTrue(
            bool(self.window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        )

        self.window.set_window_options(borderless=False, always_on_top=False)
        pump_events()
        flags = self.window.windowFlags()
        self.assertFalse(bool(flags & Qt.WindowType.FramelessWindowHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowMinimizeButtonHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowMaximizeButtonHint))
        QTest.qWait(150)
        pump_events()
        self.assertFalse(self.window._frame_fit_timer.isActive())
        self.assertEqual(self.window.normalGeometry(), normal_geometry)
        self.assertTrue(self.window._native_frame_matches_client())

    def test_transitional_frame_origin_does_not_add_insets_to_client(self) -> None:
        client = QRect(40, 50, 500, 640)
        self.window.setGeometry(client)
        self.window.show()
        pump_events()
        self.window._frame_fit_timer.stop()

        # A newly recreated HWND can briefly report frame origin == client
        # origin even though the non-client margins are already non-zero.
        with (
            patch.object(MainWindow, "frameGeometry", return_value=QRect(client)),
            patch.object(
                self.window,
                "_refresh_native_frame_geometry",
                wraps=self.window._refresh_native_frame_geometry,
            ) as refresh,
        ):
            self.window._fit_native_frame_to_available_screen((2, 2, 2, 2))

        refresh.assert_called_once_with(client)
        self.assertEqual(self.window.geometry(), client)

    def test_native_frame_settles_consistently_after_borderless_round_trip(self) -> None:
        if self.application.platformName().casefold() != "windows":
            self.skipTest("requires the native Windows Qt platform")
        area = self.application.primaryScreen().availableGeometry()
        if area.width() < 1100 or area.height() < 1150:
            self.skipTest("native test screen is too small for the regression rectangle")
        expected = QRect(area.x() + 300, area.y() + 200, 700, 900)
        self.window.setGeometry(expected)
        self.window.show()
        QTest.qWait(250)

        self.window.set_window_options(borderless=True, always_on_top=False)
        QTest.qWait(100)
        self.window.set_window_options(borderless=False, always_on_top=False)
        immediate = QRect(self.window.normalGeometry())
        QTest.qWait(350)
        pump_events()

        left, top, right, bottom = self.window._native_frame_insets()
        expected_frame = QRect(
            expected.x() - left,
            expected.y() - top,
            expected.width() + left + right,
            expected.height() + top + bottom,
        )
        self.assertEqual(immediate, expected)
        self.assertEqual(self.window.geometry(), expected)
        self.assertEqual(self.window.normalGeometry(), expected)
        self.assertEqual(self.window.frameGeometry(), expected_frame)
        self.assertFalse(self.window._frame_fit_timer.isActive())

    def test_flag_recreation_preserves_maximized_state_and_restore_geometry(self) -> None:
        self.window.setGeometry(45, 55, 700, 700)
        self.window.show()
        pump_events()
        normal_geometry = QRect(self.window.normalGeometry())
        self.window.showMaximized()
        pump_events()
        self.assertTrue(self.window.isMaximized())

        self.window.set_window_options(borderless=False, always_on_top=True)
        pump_events()
        self.assertTrue(self.window.isMaximized())
        self.assertEqual(self.window.normalGeometry(), normal_geometry)

        self.window.set_window_options(borderless=True, always_on_top=True)
        pump_events()
        self.assertTrue(self.window.isMaximized())
        self.assertEqual(self.window.normalGeometry(), normal_geometry)

        self.window.set_window_options(borderless=False, always_on_top=False)
        pump_events()
        self.assertTrue(self.window.isMaximized())
        self.assertEqual(self.window.normalGeometry(), normal_geometry)

        self.window.showNormal()
        QTest.qWait(150)
        pump_events()
        self.assertFalse(self.window._frame_fit_timer.isActive())
        self.assertEqual(self.window.geometry(), normal_geometry)

    def test_oversized_minimum_keeps_frame_top_left_reachable(self) -> None:
        area = QRect(100, 200, 400, 500)
        insets = (8, 31, 8, 8)
        fitted = self.window._fitted_client_geometry(
            QRect(60, 140, 500, 640),
            QRect(52, 109, 516, 679),
            area,
            insets,
            QSize(500, 640),
        )
        outer = QRect(
            fitted.x() - insets[0],
            fitted.y() - insets[1],
            fitted.width() + insets[0] + insets[2],
            fitted.height() + insets[1] + insets[3],
        )

        self.assertEqual(outer.topLeft(), area.topLeft())
        self.assertGreater(outer.width(), area.width())
        self.assertGreater(outer.height(), area.height())

    def test_snap_sized_layout_remains_usable_at_half_portrait_width(self) -> None:
        self.window.show()
        central = self.window.centralWidget()

        for height in (640, 696):
            with self.subTest(height=height):
                self.window.resize(500, height)
                pump_events()

                self.assertEqual(self.window.size().width(), 500)
                self.assertEqual(self.window.size().height(), height)
                self.assertTrue(self.window._compact_layout)
                self.assertGreaterEqual(self.window.chat_view.height(), 120)
                for widget in (
                    self.window.chat_view,
                    self.window.brb_button,
                    self.window.discord_button,
                    self.window.obs_metric,
                    self.window.vertical_metric,
                ):
                    top_left = widget.mapTo(central, QPoint(0, 0))
                    widget_rect = QRect(top_left, widget.size())
                    self.assertTrue(
                        central.rect().contains(widget_rect),
                        f"{widget.objectName() or type(widget).__name__} escaped the window",
                    )
                for metric in self.window._status_metrics:
                    self.assertLessEqual(metric.minimumSizeHint().width(), metric.width())
                self.assertLessEqual(
                    self.window.brb_button.minimumSizeHint().width(),
                    self.window.brb_button.width(),
                )
                self.assertLessEqual(
                    self.window.discord_button.minimumSizeHint().width(),
                    self.window.discord_button.width(),
                )

    def test_restore_keeps_native_frame_inside_available_work_area(self) -> None:
        self.window.show()
        pump_events()
        screen = self.window.screen()
        self.assertIsNotNone(screen)
        area = screen.availableGeometry()

        self.window.restore_window_preferences(
            WindowSettings(
                width=area.width(),
                height=area.height(),
                x=area.x(),
                y=area.y(),
                monitor_name=screen.name(),
                borderless=False,
                always_on_top=False,
            )
        )
        pump_events()
        self.assertFalse(self.window._frame_fit_applied)
        QTest.qWait(150)
        pump_events()

        self.assertTrue(self.window._frame_fit_applied)
        self.assertFalse(self.window._frame_fit_timer.isActive())
        self.assertTrue(
            area.contains(self.window.frameGeometry()),
            f"frame {self.window.frameGeometry()} escaped work area {area}",
        )

    def test_portrait_layout_devotes_about_three_quarters_to_chat(self) -> None:
        self.window.resize(1080, 1920)
        self.window.show()
        pump_events()

        ratio = self.window.chat_view.height() / self.window.centralWidget().height()
        self.assertGreaterEqual(ratio, 0.70)
        self.assertLessEqual(ratio, 0.80)
        self.assertFalse(self.window._compact_layout)
        for metric in self.window._status_metrics:
            self.assertLessEqual(metric.minimumSizeHint().width(), metric.width())
        self.assertIn("F1", self.window.brb_button.text())
        self.assertIn("F2", self.window.discord_button.text())
        self.assertIn("STATE UNAVAILABLE", self.window.discord_button.text())

    def test_manual_scrollback_pauses_then_resume_follows_live_chat(self) -> None:
        self.window.resize(640, 900)
        self.window.show()
        self.window.add_messages(
            {
                "sequence": index,
                "platform": "twitch" if index % 2 else "tiktok",
                "username": "Viewer",
                "text": "A wrapped message with enough content to occupy visible space " * 2,
            }
            for index in range(80)
        )
        pump_events(6)
        bar = self.window.chat_view.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)

        bar.setValue(0)
        self.window.chat_view.note_manual_scroll()
        self.assertFalse(self.window.chat_view.auto_scroll_enabled)

        self.window.add_message(
            {"platform": "tiktok", "username": "Sarah", "text": "what server is this?"}
        )
        pump_events()
        self.assertEqual(self.window.chat_view.unread_count, 1)
        self.assertTrue(self.window.resume_button.isVisible())
        self.assertIn("1 NEW", self.window.resume_button.text())

        self.window.chat_view.resume_auto_scroll()
        pump_events()
        self.assertTrue(self.window.chat_view.auto_scroll_enabled)
        self.assertEqual(self.window.chat_view.unread_count, 0)
        self.assertEqual(bar.value(), bar.maximum())

    def test_rapid_batch_is_bounded_and_delegate_wraps_long_unicode(self) -> None:
        messages = [
            {
                "sequence": index,
                "platform": "tiktok" if index % 3 == 0 else "twitch",
                "username": f"Viewer {index}",
                "text": f"rapid {index} 😄",
            }
            for index in range(1200)
        ]
        messages[-1]["text"] = "Long emoji message 🎉 " * 60
        self.window.add_messages(messages)
        pump_events()

        self.assertEqual(self.window.model.rowCount(), 750)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 700, 100)
        final_index = self.window.model.index(self.window.model.rowCount() - 1, 0)
        size = self.window.delegate.sizeHint(option, final_index)
        self.assertGreater(size.height(), 250)

    def test_delegate_height_cache_remains_bounded_across_long_stream(self) -> None:
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 700, 100)

        for batch_start in range(0, 2300, 100):
            self.window.add_messages(
                {
                    "sequence": index,
                    "platform": "twitch" if index % 2 else "tiktok",
                    "username": f"Viewer {index}",
                    "text": f"unique long-session message {index}",
                }
                for index in range(batch_start, batch_start + 100)
            )
            pump_events()
            first = max(0, self.window.model.rowCount() - 100)
            for row in range(first, self.window.model.rowCount()):
                size = self.window.delegate.sizeHint(
                    option, self.window.model.index(row, 0)
                )
                self.assertGreaterEqual(size.height(), 96)

        self.assertLessEqual(len(self.window.delegate._height_cache), 2200)

    def test_status_updates_derive_actual_brb_and_mixed_states(self) -> None:
        self.window.update_connection(Platform.TWITCH, ConnectionState.CONNECTED)
        self.window.update_connection(Platform.TIKTOK, ConnectionState.RECONNECTING)
        self.window.update_obs_status(
            {
                "connected": True,
                "streaming": True,
                "recording": True,
                "vertical_active": True,
                "main_scene": "BRB - Main",
                "vertical_scene": "WoW Raid TikTok",
            }
        )
        pump_events()

        self.assertEqual(self.window.brb_button.property("state"), "mixed")
        self.assertIn("MIXED", self.window.brb_button.text())
        self.assertEqual(self.window.live_tally.property("state"), "live")
        self.assertEqual(self.window.twitch_connection.dot.property("state"), "connected")
        self.assertEqual(self.window.tiktok_connection.dot.property("state"), "reconnecting")
        self.assertEqual(self.window.twitch_connection.name.text(), "TWITCH")
        self.assertGreaterEqual(self.window.twitch_connection.name.minimumWidth(), 72)

        self.window.update_obs_status(
            {"connected": True, "main_scene": "BRB - Main", "vertical_scene": "BRB - Vertical"}
        )
        pump_events()
        self.assertEqual(self.window.brb_button.property("state"), "brb")
        self.assertIn("BRB ACTIVE", self.window.brb_button.text())

    def test_buttons_emit_shared_control_requests_without_optimistic_state(self) -> None:
        events: list[str] = []
        self.window.brb_requested.connect(lambda: events.append("brb"))
        self.window.discord_toggle_requested.connect(lambda: events.append("discord"))
        original_brb_state = self.window.brb_button.property("state")

        self.window.brb_button.click()
        self.window.discord_button.click()
        pump_events()

        self.assertEqual(events, ["brb", "discord"])
        self.assertEqual(self.window.brb_button.property("state"), original_brb_state)

    def test_backend_window_settings_round_trip_hooks(self) -> None:
        self.window.restore_window_preferences(
            WindowSettings(width=700, height=700, borderless=True, always_on_top=False)
        )
        pump_events()
        captured = self.window.capture_window_preferences()

        self.assertEqual(captured["width"], 700)
        self.assertEqual(captured["height"], 700)
        self.assertTrue(captured["borderless"])


if __name__ == "__main__":
    unittest.main()
