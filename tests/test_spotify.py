from __future__ import annotations

from datetime import timedelta
import time
import unittest

from streamer_console.spotify import SpotifyService


class Properties:
    title = "The Frozen Throne"
    artist = "Raid Mix"


class Playback:
    playback_status = 4


class Timeline:
    position = timedelta(seconds=30)
    end_time = timedelta(minutes=4)


class Session:
    source_app_user_model_id = "Spotify.exe"

    def __init__(self) -> None:
        self.commands: list[str] = []

    async def try_get_media_properties_async(self):
        return Properties()

    def get_playback_info(self):
        return Playback()

    def get_timeline_properties(self):
        return Timeline()

    async def try_toggle_play_pause_async(self):
        self.commands.append("toggle")

    async def try_skip_next_async(self):
        self.commands.append("next")

    async def try_skip_previous_async(self):
        self.commands.append("previous")


class Manager:
    def __init__(self, session) -> None:
        self.session = session

    def get_sessions(self):
        return [self.session]


class SpotifyServiceTests(unittest.TestCase):
    def test_targets_spotify_session_and_exposes_clean_metadata(self) -> None:
        session = Session()
        service = SpotifyService(lambda: Manager(session))
        service.POLL_SECONDS = 0.01
        service.start()
        deadline = time.monotonic() + 1
        updates = []
        while time.monotonic() < deadline and not updates:
            updates = service.drain()
            time.sleep(0.01)
        service.play_pause()
        service.next()
        service.previous()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and len(session.commands) < 3:
            time.sleep(0.01)
        service.stop()

        self.assertTrue(updates)
        payload = updates[-1].payload
        self.assertEqual(payload["title"], "The Frozen Throne")
        self.assertEqual(payload["artist"], "Raid Mix")
        self.assertTrue(payload["playing"])
        self.assertEqual(session.commands, ["toggle", "next", "previous"])


if __name__ == "__main__":
    unittest.main()
