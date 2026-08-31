from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from streamer_console.config import TwitchSettings
from streamer_console.twitch import TWITCH_SCOPES, TwitchError, TwitchService, TwitchTokenStore


class MemoryTokenStore:
    def __init__(self, value=None) -> None:
        self.value = value

    def load(self):
        return self.value

    def save(self, value):
        self.value = dict(value)


class MemoryCredentialStore:
    def __init__(self, value: bytes | None = None) -> None:
        self.value = value
        self.cleared = False

    def load(self):
        return self.value

    def save(self, value):
        self.value = bytes(value)

    def clear(self):
        self.value = None
        self.cleared = True


class UnavailableCredentialStore(MemoryCredentialStore):
    def save(self, value):
        raise TwitchError("Credential Manager unavailable")


class TestableLegacyTokenStore(TwitchTokenStore):
    def _protect(self, data: bytes) -> bytes:
        return b"legacy:" + data

    def _unprotect(self, data: bytes) -> bytes:
        if not data.startswith(b"legacy:"):
            raise TwitchError("invalid legacy payload")
        return data.removeprefix(b"legacy:")


class FakeApi:
    def __init__(self) -> None:
        self.updated = None
        self.marker = None

    def validate(self, token):
        return {"user_id": "42", "login": "lausudo", "scopes": list(TWITCH_SCOPES)}

    def channel_info(self, client_id, token, broadcaster_id):
        return {"title": "ICC tonight", "game_name": "World of Warcraft", "game_id": "18122"}

    def stream_status(self, client_id, token, broadcaster_id):
        return {"live": True, "viewers": 46}

    def categories(self, client_id, token, query):
        return [{"id": "18122", "name": "World of Warcraft"}]

    def update_channel(self, client_id, token, broadcaster_id, *, title, game_id):
        self.updated = (title, game_id)

    def create_stream_marker(self, client_id, token, broadcaster_id, description):
        self.marker = (broadcaster_id, description)
        return {"id": "marker-1", "position_seconds": 123}


class TwitchEventTests(unittest.TestCase):
    def test_token_store_prefers_windows_credential_manager_without_plaintext_file(self) -> None:
        token = {
            "access_token": "access",
            "refresh_token": "refresh",
            "scope": list(TWITCH_SCOPES),
            "ignored": "not-persisted",
        }
        credentials = MemoryCredentialStore()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "twitch-auth.dat"
            store = TwitchTokenStore(path, credential_store=credentials)

            store.save(token)

            self.assertFalse(path.exists())
            self.assertIsNotNone(credentials.value)
            assert credentials.value is not None
            self.assertNotIn(b"ignored", credentials.value)
            loaded = store.load()
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded["refresh_token"], "refresh")

    def test_token_store_keeps_legacy_dpapi_file_as_secure_fallback(self) -> None:
        credentials = UnavailableCredentialStore()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "twitch-auth.dat"
            store = TestableLegacyTokenStore(path, credential_store=credentials)

            store.save({"access_token": "access", "refresh_token": "refresh"})

            self.assertTrue(path.read_bytes().startswith(b"legacy:"))
            loaded = store.load()
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded["access_token"], "access")

    def test_token_store_clear_removes_both_secure_backends(self) -> None:
        credentials = MemoryCredentialStore(json.dumps({"access_token": "x"}).encode())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "twitch-auth.dat"
            path.write_bytes(b"legacy")
            store = TwitchTokenStore(path, credential_store=credentials)

            store.clear()

            self.assertTrue(credentials.cleared)
            self.assertFalse(path.exists())

    def test_native_chat_event_maps_to_normalized_collector_shape(self) -> None:
        result = TwitchService._event_payload(
            {
                "metadata": {"message_id": "chat-1"},
                "payload": {
                    "subscription": {"type": "channel.chat.message"},
                    "event": {
                        "chatter_user_name": "PizzaGuy",
                        "message": {"text": "clean pull"},
                    },
                },
            }
        )
        self.assertEqual(result["event"], "")
        self.assertEqual(result["chatname"], "PizzaGuy")
        self.assertEqual(result["chatmessage"], "clean pull")
        self.assertTrue(result["id"].startswith("eventsub:"))

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
        metrics = next(update for update in updates if update.kind == "metrics")
        self.assertEqual(metrics.payload["twitch_viewers"], 46)
        self.assertTrue(metrics.payload["twitch_live"])

        service._update_channel("New title", "World of Warcraft")
        self.assertEqual(api.updated, ("New title", "18122"))

        service._create_marker("Professor Putricide kill")
        self.assertEqual(api.marker, ("42", "Professor Putricide kill"))
        marker = next(update for update in service.drain() if update.kind == "marker")
        self.assertTrue(marker.payload["success"])


if __name__ == "__main__":
    unittest.main()
