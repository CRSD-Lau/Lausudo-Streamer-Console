from __future__ import annotations

import unittest
from unittest.mock import patch

from streamer_console import controls
from streamer_console.controls import ControlBridge


class ControlBridgeTests(unittest.TestCase):
    def make_bridge(self, processes, sender=None, *, platform_name="win32"):
        sent: list[int] = []

        def fake_sender(virtual_key: int) -> None:
            sent.append(virtual_key)

        bridge = ControlBridge(
            process_provider=lambda: processes,
            key_sender=sender or fake_sender,
            platform_name=platform_name,
        )
        return bridge, sent

    def test_f1_checks_obs_and_autohotkey_then_sends_once(self):
        bridge, sent = self.make_bridge(["OBS64.EXE", "AutoHotkey64.exe"])

        result = bridge.toggle_brb_privacy()

        self.assertTrue(result.success)
        self.assertEqual(result.code, "sent")
        self.assertEqual(result.key, "F1")
        self.assertEqual(sent, [ControlBridge.VK_F1])
        self.assertEqual(result.dependencies, {"autohotkey": True, "obs": True})

    def test_f1_does_not_send_when_obs_is_missing(self):
        bridge, sent = self.make_bridge(["AutoHotkey64.exe", "Discord.exe"])

        result = bridge.trigger_brb()

        self.assertFalse(result.success)
        self.assertEqual(result.code, "dependency_missing")
        self.assertEqual(result.missing, ("obs",))
        self.assertEqual(sent, [])

    def test_f2_requires_discord_and_autohotkey_but_not_obs(self):
        bridge, sent = self.make_bridge(
            [r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe", "Discord.exe"]
        )

        result = bridge.toggle_discord_mute()

        self.assertTrue(result.success)
        self.assertEqual(result.key, "F2")
        self.assertEqual(sent, [ControlBridge.VK_F2])
        self.assertNotIn("obs", result.dependencies)

    def test_f2_does_not_send_when_helper_is_missing(self):
        bridge, sent = self.make_bridge(["Discord.exe", "obs64.exe"])

        result = bridge.trigger_discord_mute()

        self.assertFalse(result.success)
        self.assertEqual(result.code, "dependency_missing")
        self.assertEqual(result.missing, ("autohotkey",))
        self.assertEqual(sent, [])

    def test_unsupported_platform_performs_no_process_check_or_keypress(self):
        touched: list[str] = []

        bridge = ControlBridge(
            process_provider=lambda: touched.append("process") or (),
            key_sender=lambda _key: touched.append("key"),
            platform_name="linux",
        )

        result = bridge.toggle_brb_privacy()

        self.assertFalse(result.success)
        self.assertEqual(result.code, "unsupported_platform")
        self.assertEqual(touched, [])

    def test_process_inspection_failure_is_structured_and_does_not_send(self):
        sent: list[int] = []

        def fail_process_check():
            raise OSError("snapshot unavailable")

        bridge = ControlBridge(
            process_provider=fail_process_check,
            key_sender=sent.append,
            platform_name="Windows",
        )

        result = bridge.toggle_brb_privacy()

        self.assertFalse(result.success)
        self.assertEqual(result.code, "process_check_failed")
        self.assertIn("snapshot unavailable", result.message)
        self.assertEqual(sent, [])

    def test_sendinput_failure_is_structured(self):
        def fail_send(_virtual_key: int) -> None:
            raise OSError("access denied")

        bridge, _sent = self.make_bridge(
            ["AutoHotkey64.exe", "Discord.exe"], sender=fail_send
        )

        result = bridge.toggle_discord_mute()

        self.assertFalse(result.success)
        self.assertEqual(result.code, "send_input_failed")
        self.assertIn("access denied", result.message)

    def test_result_can_be_serialized_for_the_ui(self):
        bridge, _sent = self.make_bridge(["AutoHotkey64.exe", "obs64.exe"])

        payload = bridge.toggle_brb_privacy().to_dict()

        self.assertEqual(payload["control"], "brb_privacy")
        self.assertEqual(payload["key"], "F1")
        self.assertTrue(payload["success"])

    def test_win32_sender_builds_key_down_and_key_up_without_real_input(self):
        captured: dict[str, object] = {}

        class FakeSendInput:
            argtypes = None
            restype = None

            def __call__(self, count, inputs, structure_size):
                captured["count"] = count
                captured["down_key"] = inputs[0].ki.wVk
                captured["down_flags"] = inputs[0].ki.dwFlags
                captured["up_key"] = inputs[1].ki.wVk
                captured["up_flags"] = inputs[1].ki.dwFlags
                captured["structure_size"] = structure_size
                return count

        class FakeUser32:
            SendInput = FakeSendInput()

        # Replacing WinDLL guarantees that Windows never receives these events.
        with patch.object(controls.ctypes, "WinDLL", return_value=FakeUser32()):
            with patch.object(controls.sys, "platform", "win32"):
                controls._send_windows_key(ControlBridge.VK_F1)

        self.assertEqual(captured["count"], 2)
        self.assertEqual(captured["down_key"], ControlBridge.VK_F1)
        self.assertEqual(captured["down_flags"], 0)
        self.assertEqual(captured["up_key"], ControlBridge.VK_F1)
        self.assertEqual(captured["up_flags"], 0x0002)
        self.assertGreater(captured["structure_size"], 0)


if __name__ == "__main__":
    unittest.main()
