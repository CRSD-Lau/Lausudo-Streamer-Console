from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import uuid

from streamer_console.stream_workspace import (
    AppSpec,
    Monitor,
    Rect,
    Window,
    apply_workspace,
    build_zones,
    default_apps,
    identify_roles,
    SOCIAL_STREAM_EXTENSION_ID,
    TIKTOK_LIVE_URL,
    TIKTOK_PLACEMENT_TASK,
    TWITCH_CHAT_URL,
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
        self.elevated_placements: list[tuple[str, float]] = []
        self.minimized: list[int] = []
        self.focused: list[int] = []
        self.rects = {
            window.handle: Rect(10, 10, 810, 610) for window in self._windows
        }

    def monitors(self):
        return self._monitors

    def windows(self):
        return self._windows

    def launch(self, command, *, working_directory=None, shell_execute=False):
        self.launched.append(tuple(command))
        self.launch_options.append((working_directory, shell_execute))

    def place(self, handle, rect):
        self.placed.append((handle, rect))
        self.rects[handle] = rect
        return True

    def window_rect(self, handle):
        return self.rects.get(handle)

    def place_elevated(self, task_name, timeout):
        self.elevated_placements.append((task_name, timeout))
        return True

    def minimize(self, handle):
        self.minimized.append(handle)
        return True

class WorkspaceTests(unittest.TestCase):
    def test_roles_and_zones_match_approved_layout(self):
        roles = identify_roles(monitor_topology())
        self.assertEqual(set(roles), {"gaming", "production", "portrait"})
        zones = build_zones(roles)
        self.assertEqual(zones["production_left"], Rect(0, -1440, 1360, -48))
        self.assertEqual(zones["production_right"], Rect(1360, -1440, 2560, -48))
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
        self.assertEqual(tiktok.zone, "production_right")
        self.assertEqual(tiktok.elevated_placement_task, TIKTOK_PLACEMENT_TASK)

    def test_social_stream_uses_installed_default_profile_and_exact_extension_id(self):
        app = next(item for item in default_apps() if item.key == "social_stream_ninja")
        self.assertTrue(app.launch)
        self.assertTrue(app.minimize)
        self.assertIn("--profile-directory=Default", app.command)
        self.assertIn(
            f"--app=chrome-extension://{SOCIAL_STREAM_EXTENSION_ID}/background.html",
            app.command,
        )
        self.assertEqual(SOCIAL_STREAM_EXTENSION_ID, "cppibjhfemifednoimlblfcmjgfhfjeg")

    def test_f3_opens_required_tiktok_page_and_twitch_fallback_in_default_profile(self):
        apps = {item.key: item for item in default_apps()}
        expectations = {
            "tiktok_live_page": TIKTOK_LIVE_URL,
            "twitch_chat_fallback": TWITCH_CHAT_URL,
        }

        for key, url in expectations.items():
            app = apps[key]
            self.assertEqual(app.executable_names, ("chrome.exe",))
            self.assertIn("--profile-directory=Default", app.command)
            self.assertIn(f"--app={url}", app.command)
            self.assertTrue(app.minimize)
            self.assertIsNone(app.zone)

        self.assertEqual(TIKTOK_LIVE_URL, "https://www.tiktok.com/@lausudo/live")
        self.assertEqual(
            TWITCH_CHAT_URL,
            "https://www.twitch.tv/popout/lausudo/chat?popout=",
        )

    def test_tiktok_placement_routes_only_through_fixed_elevated_broker(self):
        window = Window(
            14,
            22,
            r"C:\Apps\TikTok LIVE Studio.exe",
            "Chrome",
            "TikTok LIVE Studio",
        )
        app = next(item for item in default_apps() if item.key == "tiktok_live_studio")
        platform = FakePlatform(windows=[window])
        success, actions = apply_workspace(platform, [app])
        self.assertTrue(success)
        self.assertEqual(platform.placed, [])
        self.assertEqual(platform.elevated_placements[0][0], TIKTOK_PLACEMENT_TASK)
        self.assertIn(
            {"app": "tiktok_live_studio", "action": "place_production_right_elevated"},
            actions,
        )

    def test_discord_saved_bounds_restore_is_overridden_until_target_sticks(self):
        window = Window(19, 31, r"C:\Apps\Discord.exe", "Chrome", "Discord")
        target = Rect(-1080, 231, 0, 1392)

        class RestoringPlatform(FakePlatform):
            def place(self, handle, rect):
                self.placed.append((handle, rect))
                self.rects[handle] = (
                    Rect(-1087, -480, 7, 775)
                    if len(self.placed) == 1
                    else rect
                )
                return True

        platform = RestoringPlatform(windows=[window])
        app = AppSpec(
            "discord",
            ("Discord.exe",),
            ("Discord",),
            None,
            "portrait_bottom",
            settle_before_place=True,
        )
        ticks = [index * 0.25 for index in range(100)]
        with patch("streamer_console.stream_workspace.time.monotonic", side_effect=ticks), patch(
            "streamer_console.stream_workspace.time.sleep"
        ):
            success, _actions = apply_workspace(platform, [app])
        self.assertTrue(success)
        self.assertGreaterEqual(len(platform.placed), 2)
        self.assertEqual(platform.rects[window.handle], target)

    def test_broker_is_fixed_scope_and_installed_from_protected_location(self):
        root = Path(__file__).parents[1]
        broker = (root / "tools/stream_workspace/TikTokPlacementBroker.ps1").read_text(
            encoding="utf-8"
        )
        installer = (root / "tools/stream_workspace/Install-StreamWorkspace.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('process.ProcessName,\n                    "TikTok LIVE Studio"', broker)
        self.assertIn("$ValidateOnly", broker)
        self.assertIn("tiktok_window_found = $TikTokWindow -ne [IntPtr]::Zero", broker)
        self.assertIn("$Target.Bottom = $Target.Top + 740", broker)
        self.assertNotIn("Start-Process", broker)
        self.assertNotIn("Invoke-Expression", broker)
        self.assertIn("$env:ProgramFiles", installer)
        self.assertIn("-RunLevel Highest", installer)
        self.assertIn("unsafe writable ACL", installer)
        self.assertIn("TikTokPlacementBroker.ps1", installer)
        self.assertIn("UTF8Encoding]::new($false)", broker)
        self.assertIn("-and -not $IsAdministrator", installer)
        self.assertNotIn("$UnsafeRights", installer)
        self.assertIn("$MutationRights", installer)
        self.assertIn("FileSystemRights]::WriteData", installer)
        self.assertIn("FileSystemRights]::ChangePermissions", installer)
        self.assertIn("FileSystemRights]::TakeOwnership", installer)
        self.assertIn("@($BrokerDirectory, $BrokerInstalledPath)", installer)

    def test_elevated_placement_correlates_result_to_fixed_task_request(self):
        platform = object.__new__(WindowsPlatform)
        request_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_directory = Path(temporary_directory)

            def run_task(command, **_kwargs):
                self.assertEqual(
                    command,
                    ["schtasks.exe", "/Run", "/TN", TIKTOK_PLACEMENT_TASK],
                )
                (state_directory / "tiktok-placement-result.json").write_text(
                    '{"request_id":"11111111-2222-3333-4444-555555555555",'
                    '"status":"placed"}',
                    encoding="utf-8",
                )
                return type("Completed", (), {"returncode": 0})()

            with patch(
                "streamer_console.stream_workspace._local_root",
                return_value=state_directory,
            ), patch(
                "streamer_console.stream_workspace.uuid.uuid4",
                return_value=request_id,
            ), patch(
                "streamer_console.stream_workspace.subprocess.run",
                side_effect=run_task,
            ):
                self.assertTrue(
                    platform.place_elevated(TIKTOK_PLACEMENT_TASK, timeout=1.0)
                )
            request_text = (
                state_directory / "tiktok-placement-request.txt"
            ).read_text(encoding="ascii")
        self.assertEqual(request_text, str(request_id))

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
