from __future__ import annotations

import unittest

from streamer_console.models import ChatListModel, ChatPreferences, FilterSettings


class ChatOnlyModelTests(unittest.TestCase):
    def test_preserves_true_chat_and_rejects_event_and_system_records(self) -> None:
        model = ChatListModel(
            preferences=ChatPreferences(
                filters=FilterSettings(show_system_messages=True),
            )
        )

        added = model.append_messages(
            [
                {
                    "platform": "twitch",
                    "username": "System",
                    "text": "great pull",
                    "kind": "chat",
                    "metadata": {"hasDonation": "100 bits"},
                },
                {
                    "platform": "tiktok",
                    "username": "Subscriber",
                    "text": "hello",
                    "kind": "chat",
                    "metadata": {"membership": "SUBSCRIBER"},
                },
                {
                    "platform": "tiktok",
                    "username": "System",
                    "text": "Some people are previewing your LIVE.",
                    "kind": "event",
                    "event_type": "event",
                },
                {
                    "platform": "system",
                    "username": "Collector",
                    "text": "collector ready",
                    "kind": "chat",
                },
                {
                    "platform": "twitch",
                    "username": "Raider",
                    "text": "Raid: 12 viewers joined",
                    "kind": "system",
                },
                {
                    "platform": "tiktok",
                    "username": "",
                    "text": "platform notice mislabeled as chat",
                    "kind": "chat",
                },
                {
                    "platform": "twitch",
                    "text": "missing viewer identity",
                    "kind": "chat",
                },
            ]
        )

        self.assertEqual(added, 2)
        self.assertEqual(
            [
                (message.platform.value, message.username, message.kind.value)
                for message in model.messages
            ],
            [
                ("twitch", "System", "chat"),
                ("tiktok", "Subscriber", "chat"),
            ],
        )

    def test_show_system_preference_cannot_bypass_chat_only_boundary(self) -> None:
        model = ChatListModel(
            preferences=ChatPreferences(
                filters=FilterSettings(show_system_messages=True),
            )
        )

        self.assertFalse(
            model.append_message(
                {
                    "platform": "tiktok",
                    "username": "System",
                    "text": "· 1",
                    "kind": "event",
                    "event_type": "event",
                }
            )
        )
        self.assertEqual(model.rowCount(), 0)

    def test_blank_source_username_is_not_relabelled_as_a_viewer(self) -> None:
        model = ChatListModel()

        self.assertFalse(
            model.append_message(
                {
                    "platform": "tiktok",
                    "username": "",
                    "text": "Some people are previewing your LIVE.",
                    "kind": "chat",
                }
            )
        )
        self.assertEqual(model.rowCount(), 0)


if __name__ == "__main__":
    unittest.main()
