from __future__ import annotations

import unittest

from streamer_console.telemetry import extract_tiktok_telemetry


class TikTokTelemetryTests(unittest.TestCase):
    def test_viewer_updates_accept_numeric_and_compact_counts(self) -> None:
        numeric = extract_tiktok_telemetry(
            {"type": "tiktok", "event": "viewer_update", "meta": 128}
        )
        compact = extract_tiktok_telemetry(
            {"type": "tiktok", "event": "viewer_update", "meta": "1.2K"}
        )
        self.assertEqual((numeric.kind, numeric.value), ("tiktok_viewers", 128))
        self.assertEqual((compact.kind, compact.value), ("tiktok_viewers", 1200))

    def test_follow_requires_a_viewer_identity(self) -> None:
        follow = extract_tiktok_telemetry(
            {"type": "tiktok", "event": "followed", "chatname": "Sarah"}
        )
        notice = extract_tiktok_telemetry(
            {"type": "tiktok", "event": "followed", "chatname": ""}
        )
        self.assertEqual((follow.kind, follow.value), ("tiktok_follow", 1))
        self.assertIsNone(notice)

    def test_like_uses_explicit_or_text_count_and_otherwise_one(self) -> None:
        explicit = extract_tiktok_telemetry(
            {"type": "tiktok", "event": "liked", "repeatCount": 4}
        )
        text = extract_tiktok_telemetry(
            {"type": "tiktok", "event": "liked", "chatmessage": "sent likes × 12"}
        )
        ordinary = extract_tiktok_telemetry(
            {"type": "tiktok", "event": "liked", "chatname": "John"}
        )
        self.assertEqual(explicit.value, 4)
        self.assertEqual(text.value, 12)
        self.assertEqual(ordinary.value, 1)

    def test_regular_chat_and_other_platforms_are_not_telemetry(self) -> None:
        self.assertIsNone(
            extract_tiktok_telemetry(
                {"type": "tiktok", "event": False, "chatname": "A", "chatmessage": "hi"}
            )
        )
        self.assertIsNone(
            extract_tiktok_telemetry(
                {"type": "twitch", "event": "follow", "chatname": "A"}
            )
        )


if __name__ == "__main__":
    unittest.main()
