from __future__ import annotations

from datetime import datetime, timezone
import unittest

from streamer_console.config import FilterSettings
from streamer_console.normalizer import (
    MessageNormalizer,
    html_to_plain_text,
    normalize_social_stream_message,
)


class PlainTextTests(unittest.TestCase):
    def test_converts_markup_and_emote_alt_text_without_urls(self) -> None:
        value = (
            "Hello <strong>raid</strong><br>"
            '<img src="https://secret.invalid/emote.png" alt="Kappa"> &amp; gg'
        )

        result = html_to_plain_text(value)

        self.assertEqual(result, "Hello raid\nKappa & gg")
        self.assertNotIn("secret.invalid", result)

    def test_ignores_script_and_style_contents(self) -> None:
        result = html_to_plain_text(
            "safe<script>steal()</script><style>.hidden{}</style><div>message</div>"
        )

        self.assertEqual(result, "safe\nmessage")

    def test_truncates_pathological_messages(self) -> None:
        result = html_to_plain_text("x" * 50, max_length=12)

        self.assertEqual(result, "x" * 11 + "…")


class MessageNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.received_at = datetime(2026, 8, 14, 21, 5, 6, 123000, timezone.utc)

    def test_normalizes_twitch_message_and_assigns_receipt_metadata(self) -> None:
        normalizer = MessageNormalizer()

        first = normalizer.normalize(
            {"type": "twitch", "chatname": "PizzaGuy", "chatmessage": "nice pull"},
            received_at=self.received_at,
        )
        second = normalizer.normalize(
            {"type": "tiktok-live", "chatname": "Sarah", "chatmessage": "hi"},
            received_at=self.received_at,
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 2)
        self.assertEqual(first.received_at, "2026-08-14T21:05:06.123Z")
        self.assertEqual(first.platform, "TWITCH")
        self.assertEqual(second.platform, "TIKTOK")
        self.assertEqual(first.username, "PizzaGuy")
        self.assertEqual(first.text, "nice pull")

    def test_unwraps_webhook_envelope_and_highlights_case_insensitively(self) -> None:
        message = normalize_social_stream_message(
            {
                "data": {
                    "type": "tiktok",
                    "chatname": "Viewer",
                    "chatmessage": "Hey @LAUSUDO what addon is that?",
                }
            },
            received_at=self.received_at,
        )

        self.assertIsNotNone(message)
        assert message is not None
        self.assertTrue(message.highlight)
        self.assertEqual(message.text, "Hey @LAUSUDO what addon is that?")

    def test_unwraps_stringified_social_stream_overlay_payload(self) -> None:
        message = normalize_social_stream_message(
            {
                "dataReceived": {
                    "overlayNinja": {
                        "value": '{"type":"twitch","chatname":"A","chatmessage":"hello"}'
                    }
                }
            },
            received_at=self.received_at,
        )

        self.assertIsNotNone(message)
        assert message is not None
        self.assertEqual(message.platform, "TWITCH")
        self.assertEqual(message.text, "hello")

    def test_marks_supported_events_inline(self) -> None:
        message = normalize_social_stream_message(
            {
                "type": "twitch",
                "chatname": "Supporter",
                "chatmessage": "For the pizza fund",
                "hasDonation": "$5.00",
            },
            received_at=self.received_at,
        )

        self.assertIsNotNone(message)
        assert message is not None
        self.assertEqual(message.kind, "event")
        self.assertEqual(message.event_type, "donation")
        self.assertEqual(message.amount, "$5.00")

    def test_creates_readable_text_for_event_without_chat_body(self) -> None:
        message = normalize_social_stream_message(
            {"type": "tiktok", "chatname": "GiftUser", "gift": {"count": 3}},
            received_at=self.received_at,
        )

        self.assertIsNotNone(message)
        assert message is not None
        self.assertEqual(message.kind, "event")
        self.assertEqual(message.text, "Gift: 3")

    def test_rejects_empty_payload_and_exact_retransmitted_source_id(self) -> None:
        normalizer = MessageNormalizer()

        empty = normalizer.normalize({"type": "twitch", "chatname": "Nobody"})
        first = normalizer.normalize(
            {"type": "twitch", "id": "abc", "chatname": "A", "chatmessage": "one"}
        )
        duplicate = normalizer.normalize(
            {"type": "twitch", "id": "abc", "chatname": "A", "chatmessage": "one"}
        )

        self.assertIsNone(empty)
        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)

    def test_conservative_defaults_do_not_hide_commands_or_repeated_text(self) -> None:
        normalizer = MessageNormalizer()

        command = normalizer.normalize(
            {"type": "twitch", "chatname": "A", "chatmessage": "!gear"}
        )
        repeated = normalizer.normalize(
            {"type": "twitch", "chatname": "A", "chatmessage": "!gear"}
        )

        self.assertIsNotNone(command)
        self.assertIsNotNone(repeated)

    def test_optional_filters_hide_bots_commands_and_duplicates(self) -> None:
        filters = FilterSettings(
            hide_bots=True,
            bot_names=["NightBot"],
            hide_commands=True,
            hide_duplicates=True,
        )
        normalizer = MessageNormalizer(filters=filters)

        bot = normalizer.normalize(
            {"type": "twitch", "chatname": "NightBot", "chatmessage": "hello"}
        )
        command = normalizer.normalize(
            {"type": "twitch", "chatname": "Viewer", "chatmessage": "!gear"}
        )
        first = normalizer.normalize(
            {"type": "twitch", "chatname": "Viewer", "chatmessage": "same"}
        )
        duplicate = normalizer.normalize(
            {"type": "twitch", "chatname": "Viewer", "chatmessage": "same"}
        )

        self.assertIsNone(bot)
        self.assertIsNone(command)
        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)

    def test_retention_is_bounded_to_newest_messages(self) -> None:
        normalizer = MessageNormalizer(max_messages=2)
        for number in range(3):
            normalizer.normalize(
                {
                    "type": "twitch",
                    "chatname": "Viewer",
                    "chatmessage": f"message {number}",
                }
            )

        snapshot = normalizer.snapshot()

        self.assertEqual([item.sequence for item in snapshot], [2, 3])
        self.assertEqual([item.text for item in snapshot], ["message 1", "message 2"])

    def test_filter_caches_remain_hard_bounded_under_hostile_message_rate(self) -> None:
        filters = FilterSettings(
            hide_duplicates=True,
            hide_repeated_spam=True,
            repeated_spam_threshold=3,
            repeated_spam_window_seconds=600.0,
        )
        normalizer = MessageNormalizer(
            filters=filters, max_messages=100, monotonic=lambda: 1.0
        )

        for number in range(2_000):
            normalizer.normalize(
                {
                    "type": "twitch",
                    "id": f"id-{number}",
                    "chatname": f"viewer-{number}",
                    "chatmessage": f"unique-{number}",
                }
            )
        sizes = normalizer.diagnostic_cache_sizes()

        self.assertEqual(sizes["limit"], 512)
        self.assertLessEqual(sizes["source_ids"], sizes["limit"])
        self.assertLessEqual(sizes["recent_text"], sizes["limit"])
        self.assertLessEqual(sizes["repeat_keys"], sizes["limit"])
        self.assertLessEqual(
            sizes["repeat_timestamps"], sizes["repeat_keys"] * 3
        )

        repeated_only = MessageNormalizer(
            filters=FilterSettings(
                hide_repeated_spam=True,
                repeated_spam_threshold=3,
                repeated_spam_window_seconds=600.0,
            ),
            max_messages=100,
            monotonic=lambda: 1.0,
        )
        for _ in range(10_000):
            repeated_only.normalize(
                {"type": "tiktok", "chatname": "spammer", "chatmessage": "same"}
            )

        repeated_sizes = repeated_only.diagnostic_cache_sizes()
        self.assertEqual(repeated_sizes["repeat_keys"], 1)
        self.assertEqual(repeated_sizes["repeat_timestamps"], 3)


if __name__ == "__main__":
    unittest.main()
