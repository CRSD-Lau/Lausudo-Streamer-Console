from __future__ import annotations

import unittest

from streamer_console.config import TwitchSettings
from streamer_console.twitch import TWITCH_SCOPES, TwitchService


class MemoryTokenStore:
    def __init__(self, value=None) -> None:
        self.value = value

    def load(self):
        return self.value

    def save(self, value):
        self.value = dict(value)


class FakeApi:
    def __init__(self) -> None:
        self.updated = None

    def validate(self, token):
        return {"user_id": "42", "login": "lausudo", "scopes": list(TWITCH_SCOPES)}

    def channel_info(self, client_id, token, broadcaster_id):
        return {"title": "ICC tonight", "game_name": "World of Warcraft", "game_id": "18122"}

    def categories(self, client_id, token, query):
        return [{"id": "18122", "name": "World of Warcraft"}]

    def update_channel(self, client_id, token, broadcaster_id, *, title, game_id):
        self.updated = (title, game_id)


class TwitchEventTests(unittest.TestCase):
    def test_eventsub_notifications_map_to_meaningful_feed_records(self) -> None:
        cases = (
            ("channel.follow", {"user_name": "Follower"}, "follow"),
            ("channel.subscribe", {"user_name": "Subscriber"}, "subscription"),
            ("channel.subscription.message", {"user_name": "Resubber", "message": {"text": "12 months"}}, "resub"),
            ("channel.subscription.gift", {"user_name": "Gifter", "total": 5}, "gift"),
            ("channel.cheer", {"user_name": "Cheerer", "bits": 100}, "bits"),
            ("channel.raid", {"from_broadcaster_user_name": "Raider", "viewers": 25}, "raid"),
            ("channel.channel_points_custom_reward_redemption.add", {"user_name": "Redeemer", "reward": {"title": "Hydrate"}}, "reward"),
        )
        for source_type, event, expected in cases:
            with self.subTest(source_type=source_type):
                result = TwitchService._event_payload(
                    {
                        "metadata": {"message_id": source_type},
                        "payload": {"subscription": {"type": source_type}, "event": event},
                    }
                )
                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(result["event"], expected)
                self.assertEqual(result["type"], "twitch")
                self.assertTrue(result["chatname"])

    def test_stream_info_refresh_and_update_use_authorized_channel(self) -> None:
        api = FakeApi()
        token = {"access_token": "secret", "refresh_token": "refresh", "scope": list(TWITCH_SCOPES)}
        service = TwitchService(
            TwitchSettings(client_id="client"), api=api, token_store=MemoryTokenStore(token)
        )
        service._start_eventsub = lambda: None
        service._set_authorized(token, api.validate("secret"))
        updates = service.drain()
        channel = next(update for update in updates if update.kind == "channel_info")
        self.assertEqual(channel.payload["title"], "ICC tonight")

        service._update_channel("New title", "World of Warcraft")
        self.assertEqual(api.updated, ("New title", "18122"))


if __name__ == "__main__":
    unittest.main()
