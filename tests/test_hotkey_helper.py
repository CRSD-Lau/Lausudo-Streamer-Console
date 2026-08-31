from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from streamer_console.hotkey_helper import HotkeyHelperManager


class FakeProcess:
    def __init__(self, *, timeout_on_first_wait: bool = False) -> None:
        self.pid = 421
        self.returncode = None
        self.terminated = 0
        self.killed = 0
        self.waits: list[float | None] = []
        self.timeout_on_first_wait = timeout_on_first_wait

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated += 1

    def kill(self):
        self.killed += 1
        self.returncode = -9

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.timeout_on_first_wait and len(self.waits) == 1:
            raise subprocess.TimeoutExpired("AutoHotkey64.exe", timeout)
        self.returncode = 0
        return self.returncode


class HotkeyHelperManagerTests(unittest.TestCase):
    def make_manager(self, *, running=False, process=None, platform="win32"):
        launched = []
        checked = []
        fake_process = process or FakeProcess()

        def launch(executable, script):
            launched.append((executable, script))
            return fake_process

        manager = HotkeyHelperManager(
            executable_path=Path(r"C:\AutoHotkey\AutoHotkey64.exe"),
            script_path=Path(r"C:\Controls\PrivacyToggle.ahk"),
            platform_name=platform,
            script_checker=lambda path: checked.append(path) or running,
            process_launcher=launch,
            path_checker=lambda _path: True,
        )
        return manager, fake_process, launched, checked

    def test_launches_and_stops_the_owned_helper_with_the_app(self):
        manager, process, launched, checked = self.make_manager()

        self.assertTrue(manager.start())
        self.assertTrue(manager.owns_process)
        self.assertEqual(checked, [Path(r"C:\Controls\PrivacyToggle.ahk")])
        self.assertEqual(len(launched), 1)

        manager.stop()
        manager.stop()
        self.assertFalse(manager.owns_process)
        self.assertEqual(process.terminated, 1)
        self.assertEqual(process.killed, 0)

    def test_existing_exact_helper_is_used_but_not_stopped(self):
        manager, process, launched, _checked = self.make_manager(running=True)

        self.assertTrue(manager.start())
        self.assertFalse(manager.owns_process)
        self.assertEqual(launched, [])

        manager.stop()
        self.assertEqual(process.terminated, 0)
        self.assertEqual(process.killed, 0)

    def test_unresponsive_owned_helper_is_force_stopped_after_timeout(self):
        process = FakeProcess(timeout_on_first_wait=True)
        manager, _, _, _ = self.make_manager(process=process)

        self.assertTrue(manager.start())
        manager.stop()

        self.assertEqual(process.terminated, 1)
        self.assertEqual(process.killed, 1)
        self.assertEqual(process.waits, [2.0, 1.0])

    def test_missing_files_fail_without_launching(self):
        launched = []
        manager = HotkeyHelperManager(
            executable_path=Path(r"C:\Missing\AutoHotkey64.exe"),
            script_path=Path(r"C:\Missing\PrivacyToggle.ahk"),
            platform_name="win32",
            script_checker=lambda _path: False,
            process_launcher=lambda *_args: launched.append(True),
            path_checker=lambda _path: False,
        )

        self.assertFalse(manager.start())
        self.assertEqual(launched, [])

    def test_non_windows_does_not_inspect_or_launch(self):
        manager, _process, launched, checked = self.make_manager(platform="linux")

        self.assertFalse(manager.start())
        self.assertEqual(checked, [])
        self.assertEqual(launched, [])


if __name__ == "__main__":
    unittest.main()
