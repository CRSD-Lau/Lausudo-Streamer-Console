from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from streamer_console.normalizer import NormalizedMessage
from streamer_console.session import SessionTracker


class SessionTrackerTests(unittest.TestCase):
    def test_tracks_aggregates_markers_and_never_writes_chat_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tracker = SessionTracker(directory)
            tracker.record_message(
                NormalizedMessage(1, "2026-08-15T00:00:00Z", "TWITCH", "Neil", "private test text")
            )
            tracker.record_message(
                NormalizedMessage(2, "2026-08-15T00:00:01Z", "TIKTOK", "Follower", "followed", kind="event", event_type="follow")
            )
            tracker.record_metrics(
                {"twitch_viewers": 42, "tiktok_viewers": 125, "tiktok_likes": 900, "tiktok_follows": 7}
            )
            tracker.add_marker("Professor Putricide kill")
            target = tracker.save(end=True)
            raw = target.read_text(encoding="utf-8")
            payload = json.loads(raw)

        self.assertNotIn("private test text", raw)
        self.assertEqual(payload["twitch_messages"], 1)
        self.assertEqual(payload["tiktok_messages"], 1)
        self.assertEqual(payload["alerts"]["follow"], 1)
        self.assertEqual(payload["peak_tiktok_viewers"], 125)
        self.assertEqual(payload["markers"][0]["description"], "Professor Putricide kill")


if __name__ == "__main__":
    unittest.main()
