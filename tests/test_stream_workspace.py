from __future__ import annotations

from pathlib import Path
import os
import unittest
from unittest.mock import patch

from streamer_console.stream_workspace import (
    AppSpec,
    Monitor,
    Rect,
    Window,
    apply_workspace,
    build_zones,
    default_apps,
    identify_roles,
    WindowsPlatform,
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
        self.launch_options: list[tuple[str | None, bool]] = []
        self.placed: list[tuple[int, Rect]] = []
        self.minimized: list[int] = []
        self.focused: list[int] = []

    def monitors(self):
        return self._monitors

    def windows(self):
        return self._windows

    def launch(self, command, *, working_directory=None, shell_execute=False):
        self.launched.append(tuple(command))
        self.launch_options.append((working_directory, shell_execute))

    def place(self, handle, rect):
        self.placed.append((handle, rect))
        return True

    def minimize(self, handle):
        self.minimized.append(handle)
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

    def test_existing_windows_are_reused_without_child_focus_manipulation(self):
        window = Window(5, 10, r"C:\Apps\OBS64.exe", "Qt", "OBS Studio")
        platform = FakePlatform(windows=[window])
        app = AppSpec("obs", ("obs64.exe",), ("OBS",), ("missing.exe",), "production_left")
        success, actions = apply_workspace(platform, [app])
        self.assertTrue(success)
        self.assertEqual(platform.launched, [])
        self.assertEqual(platform.placed[0][0], 5)
        self.assertEqual(platform.focused, [])
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
        self.assertIn('previousWindow := WinExist("A")', content)
        self.assertIn('WinActivate "ahk_id " previousWindow', content)

    def test_real_gui_launch_contracts_match_installed_shortcuts(self):
        apps = {item.key: item for item in default_apps()}
        obs = apps["obs"]
        tiktok = apps["tiktok_live_studio"]
        self.assertEqual(Path(obs.working_directory), Path(obs.command[0]).parent)
        self.assertFalse(obs.shell_execute)
        self.assertEqual(Path(tiktok.working_directory), Path(tiktok.command[0]).parent)
        self.assertTrue(tiktok.shell_execute)
        self.assertEqual(tiktok.executable_names, ("TikTok LIVE Studio.exe",))
        self.assertIsNone(tiktok.zone)

    def test_social_stream_is_an_external_prerequisite_not_a_chrome_launch(self):
        app = next(item for item in default_apps() if item.key == "social_stream_ninja")
        self.assertFalse(app.launch)
        self.assertIsNone(app.command)
        self.assertFalse(app.minimize)

    def test_missing_external_social_stream_context_is_not_an_f3_failure(self):
        app = next(item for item in default_apps() if item.key == "social_stream_ninja")
        platform = FakePlatform()
        success, actions = apply_workspace(platform, [app])
        self.assertTrue(success)
        self.assertEqual(platform.launched, [])
        self.assertEqual(
            actions,
            [{"app": "social_stream_ninja", "action": "not_running_skipped"}],
        )

    def test_launch_options_are_forwarded_to_platform(self):
        executable = Path(__file__)
        app = AppSpec(
            "launch",
            ("launched.exe",),
            (),
            (str(executable),),
            None,
            working_directory=str(executable.parent),
            shell_execute=True,
        )

        class ReadyPlatform(FakePlatform):
            def launch(self, command, *, working_directory=None, shell_execute=False):
                super().launch(
                    command,
                    working_directory=working_directory,
                    shell_execute=shell_execute,
                )
                self._windows.append(
                    Window(12, 4, r"C:\Apps\launched.exe", "Window", "Ready")
                )

        platform = ReadyPlatform()
        success, _actions = apply_workspace(platform, [app])
        self.assertTrue(success)
        self.assertEqual(platform.launch_options, [(str(executable.parent), True)])

    def test_shell_execute_launch_preserves_working_directory(self):
        platform = WindowsPlatform.__new__(WindowsPlatform)
        with patch.object(os, "startfile", create=True) as startfile:
            platform.launch(
                (r"C:\Apps\TikTok.exe", "--safe-argument"),
                working_directory=r"C:\Apps",
                shell_execute=True,
            )
        startfile.assert_called_once_with(
            r"C:\Apps\TikTok.exe",
            "open",
            "--safe-argument",
            r"C:\Apps",
            WindowsPlatform.SW_RESTORE,
        )

    @patch("streamer_console.stream_workspace.subprocess.Popen")
    def test_standard_gui_launch_preserves_working_directory(self, popen):
        platform = WindowsPlatform.__new__(WindowsPlatform)
        platform.launch(
            (r"C:\Apps\OBS\obs64.exe",),
            working_directory=r"C:\Apps\OBS",
        )
        popen.assert_called_once_with(
            [r"C:\Apps\OBS\obs64.exe"],
            close_fds=True,
            creationflags=0x08000000,
            cwd=r"C:\Apps\OBS",
        )


if __name__ == "__main__":
    unittest.main()
