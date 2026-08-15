from __future__ import annotations

from pathlib import Path
import unittest

from streamer_console.app import APP_USER_MODEL_ID


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ShortcutIdentityTests(unittest.TestCase):
    def test_installer_stamps_same_identity_as_running_application(self) -> None:
        script = (PROJECT_ROOT / "Install-StreamerConsoleShortcut.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn(f"$AppUserModelId = '{APP_USER_MODEL_ID}'", script)
        self.assertIn("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3", script)
        self.assertIn("Microsoft\\Windows\\Start Menu\\Programs", script)
        self.assertIn("User Pinned\\TaskBar", script)
        self.assertIn("Shortcut identity verification failed", script)

    def test_background_launcher_uses_windowed_python_without_console(self) -> None:
        script = (PROJECT_ROOT / "Start-StreamerConsole.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("pythonw.exe", script)
        self.assertIn("-WindowStyle Hidden", script)


if __name__ == "__main__":
    unittest.main()
