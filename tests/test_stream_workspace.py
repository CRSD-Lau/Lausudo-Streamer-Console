from __future__ import annotations

from pathlib import Path
import unittest

from streamer_console.stream_workspace import (
    AppSpec,
    Monitor,
    Rect,
    Window,
    apply_workspace,
    build_zones,
    default_apps,
    identify_roles,
)


def monitor_topology() -> list[Monitor]:
    return [
        Monitor("DISPLAY2", Rect(0, -1440, 2560, 0), Rect(0, -1440, 2560, -48), False),
        Monitor("DISPLAY3", Rect(0, 0, 2560, 1440), Rect(0, 0, 2560, 1392), True),
        Monitor("DISPLAY1", Rect(-1080, -480, 0, 1440), Rect(-1080, -480, 0, 1392), False),
    ]


class FakePlatform:
    def __init__(self, *, monitors=None, windows=None):
        self._monitors = monitor_topology() if monitors is None else monitors
        self._windows = list(windows or [])
        self.launched: list[tuple[str, ...]] = []
        self.placed: list[tuple[int, Rect]] = []
        self.minimized: list[int] = []
        self.focused: list[int] = []

    def monitors(self):
        return self._monitors

    def windows(self):
        return self._windows

    def foreground_window(self):
        return 99

    def launch(self, command):
        self.launched.append(tuple(command))

    def place(self, handle, rect):
        self.placed.append((handle, rect))
        return True

    def minimize(self, handle):
        self.minimized.append(handle)
        return True

    def restore_focus(self, handle):
        self.focused.append(handle)
        return True


class WorkspaceTests(unittest.TestCase):
    def test_roles_and_zones_match_approved_layout(self):
        roles = identify_roles(monitor_topology())
        self.assertEqual(set(roles), {"gaming", "production", "portrait"})
        zones = build_zones(roles)
        self.assertEqual(zones["production_left"], Rect(0, -1440, 1536, -48))
        self.assertEqual(zones["production_right"], Rect(1536, -1440, 2560, -48))
        self.assertEqual(zones["portrait_top"], Rect(-1080, -480, 0, 231))
        self.assertEqual(zones["portrait_bottom"], Rect(-1080, 231, 0, 1392))

    def test_missing_monitor_aborts_before_launch(self):
        platform = FakePlatform(monitors=monitor_topology()[:2])
        app = AppSpec("safe", ("safe.exe",), (), ("safe.exe",), "production_left")
        success, actions = apply_workspace(platform, [app])
        self.assertFalse(success)
        self.assertEqual(platform.launched, [])
        self.assertEqual(actions[0]["action"], "aborted_missing_monitors")

    def test_existing_windows_are_reused_and_foreground_restored(self):
        window = Window(5, 10, r"C:\Apps\OBS64.exe", "Qt", "OBS Studio")
        platform = FakePlatform(windows=[window])
        app = AppSpec("obs", ("obs64.exe",), ("OBS",), ("missing.exe",), "production_left")
        success, actions = apply_workspace(platform, [app])
        self.assertTrue(success)
        self.assertEqual(platform.launched, [])
        self.assertEqual(platform.placed[0][0], 5)
        self.assertEqual(platform.focused, [99])
        self.assertIn({"app": "obs", "action": "reuse"}, actions)

    def test_optional_voicemeeter_is_never_launched(self):
        platform = FakePlatform()
        app = AppSpec(
            "voicemeeter",
            ("voicemeeterpro.exe",),
            ("Voicemeeter",),
            None,
            "production_right",
            launch=False,
            minimize=True,
        )
        success, actions = apply_workspace(platform, [app])
        self.assertTrue(success)
        self.assertEqual(platform.launched, [])
        self.assertIn({"app": "voicemeeter", "action": "not_running_skipped"}, actions)

    def test_plan_is_non_mutating(self):
        window = Window(7, 10, r"C:\Apps\Discord.exe", "Chrome", "Discord")
        platform = FakePlatform(windows=[window])
        app = AppSpec("discord", ("Discord.exe",), ("Discord",), None, "portrait_bottom", minimize=True)
        success, actions = apply_workspace(platform, [app], dry_run=True)
        self.assertTrue(success)
        self.assertEqual(platform.placed, [])
        self.assertEqual(platform.minimized, [])
        self.assertEqual(platform.focused, [])
        self.assertIn({"app": "discord", "action": "place_portrait_bottom"}, actions)

    def test_f3_listener_owns_only_f3(self):
        script = Path(__file__).parents[1] / "tools/stream_workspace/StreamWorkspace.ahk"
        content = script.read_text(encoding="utf-8")
        self.assertIn("F3::{", content)
        self.assertNotIn("F1::{", content)
        self.assertNotIn("F2::{", content)

    def test_social_stream_uses_normal_chrome_default_profile(self):
        app = next(item for item in default_apps() if item.key == "social_stream_ninja")
        self.assertIn("--profile-directory=Default", app.command)
        self.assertTrue(
            any(part.startswith("--app=chrome-extension://") for part in app.command)
        )


if __name__ == "__main__":
    unittest.main()
