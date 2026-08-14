from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest

from streamer_console.config import AppConfig, ConfigStore, IngestSettings
from streamer_console.ingest import BoundedMessageQueue, SocialStreamIngestServer
from streamer_console.normalizer import MessageNormalizer, NormalizedMessage


def post(
    host: str,
    port: int,
    path: str,
    payload: object,
    *,
    content_type: str = "application/json",
) -> tuple[int, dict[str, object]]:
    body = json.dumps(payload).encode("utf-8")
    connection = HTTPConnection(host, port, timeout=3)
    connection.request(
        "POST",
        path,
        body=body,
        headers={"Content-Type": content_type, "Content-Length": str(len(body))},
    )
    response = connection.getresponse()
    data = json.loads(response.read().decode("utf-8"))
    status = response.status
    connection.close()
    return status, data


class IngestServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = SocialStreamIngestServer(
            MessageNormalizer(),
            IngestSettings(port=0, max_body_bytes=512, queue_size=10),
        )
        self.host, self.port = self.server.start()

    def tearDown(self) -> None:
        self.server.stop()

    def test_post_normalizes_and_queues_message_for_gui_thread(self) -> None:
        status, response = post(
            self.host,
            self.port,
            "/ingest/socialstream",
            {
                "type": "twitch",
                "chatname": "PizzaGuy",
                "chatmessage": "nice <b>pull</b>",
            },
        )

        messages = self.server.drain()
        self.assertEqual(status, 200)
        self.assertEqual(response, {"accepted": 1, "ignored": 0})
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].text, "nice pull")

    def test_batch_continues_when_one_item_is_invalid(self) -> None:
        status, response = post(
            self.host,
            self.port,
            "/ingest/socialstream",
            {
                "messages": [
                    {"type": "twitch", "chatname": "A", "chatmessage": "one"},
                    "not-an-object",
                    {"type": "tiktok", "chatname": "B", "chatmessage": "two"},
                ]
            },
        )

        messages = self.server.drain()
        self.assertEqual(status, 200)
        self.assertEqual(response, {"accepted": 2, "ignored": 1})
        self.assertEqual([message.sequence for message in messages], [1, 2])

    def test_rejects_wrong_path_without_processing_body(self) -> None:
        status, response = post(
            self.host,
            self.port,
            "/wrong",
            {"type": "twitch", "chatname": "A", "chatmessage": "private"},
        )

        self.assertEqual(status, 404)
        self.assertEqual(response, {"error": "not_found"})
        self.assertEqual(self.server.drain(), [])

    def test_rejects_oversized_body_before_reading_it(self) -> None:
        connection = HTTPConnection(self.host, self.port, timeout=3)
        body = b"{" + b"x" * 600 + b"}"
        connection.request(
            "POST",
            "/ingest/socialstream",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        response_body = json.loads(response.read().decode("utf-8"))
        connection.close()

        self.assertEqual(response.status, 413)
        self.assertEqual(response_body, {"error": "body_too_large"})
        self.assertEqual(self.server.drain(), [])

    def test_rejects_non_json_content_type(self) -> None:
        status, response = post(
            self.host,
            self.port,
            "/ingest/socialstream",
            {"chatmessage": "message"},
            content_type="application/octet-stream",
        )

        self.assertEqual(status, 415)
        self.assertEqual(response, {"error": "json_required"})

    def test_start_and_stop_are_idempotent(self) -> None:
        first = self.server.address

        second = self.server.start()
        self.server.stop()
        self.server.stop()

        self.assertEqual(first, second)
        self.assertFalse(self.server.is_running)

    def test_non_loopback_bind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            SocialStreamIngestServer(settings=IngestSettings(host="0.0.0.0"))

    def test_concurrent_handlers_enqueue_in_the_same_total_order_as_sequence(self) -> None:
        class BlockingFirstQueue(BoundedMessageQueue):
            def __init__(self) -> None:
                super().__init__(maxsize=10)
                self.first_put_started = threading.Event()
                self.release_first_put = threading.Event()

            def put(self, message: NormalizedMessage) -> None:
                if message.sequence == 1:
                    self.first_put_started.set()
                    self.release_first_put.wait(timeout=3)
                super().put(message)

        blocking_queue = BlockingFirstQueue()
        self.server.messages = blocking_queue
        completed: dict[str, tuple[int, dict[str, object]]] = {}
        errors: list[BaseException] = []
        second_done = threading.Event()

        def submit(label: str, text: str, done: threading.Event | None = None) -> None:
            try:
                completed[label] = post(
                    self.host,
                    self.port,
                    "/ingest/socialstream",
                    {"type": "twitch", "chatname": label, "chatmessage": text},
                )
            except BaseException as exc:  # captured for assertion on the test thread
                errors.append(exc)
            finally:
                if done is not None:
                    done.set()

        first = threading.Thread(target=submit, args=("first", "one"), daemon=True)
        second = threading.Thread(
            target=submit, args=("second", "two", second_done), daemon=True
        )
        first.start()
        self.assertTrue(blocking_queue.first_put_started.wait(timeout=2))
        second.start()
        try:
            # The second handler must wait because sequence 1 has normalized but
            # has not yet entered the delivery queue.
            self.assertFalse(second_done.wait(timeout=0.25))
        finally:
            blocking_queue.release_first_put.set()
        first.join(timeout=3)
        second.join(timeout=3)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(completed["first"][0], 200)
        self.assertEqual(completed["second"][0], 200)
        messages = self.server.drain()
        self.assertEqual([message.sequence for message in messages], [1, 2])
        self.assertEqual([message.text for message in messages], ["one", "two"])


class BoundedQueueTests(unittest.TestCase):
    @staticmethod
    def message(sequence: int) -> NormalizedMessage:
        return NormalizedMessage(
            sequence=sequence,
            received_at="2026-08-14T00:00:00.000Z",
            platform="TWITCH",
            username="Viewer",
            text=str(sequence),
        )

    def test_full_queue_keeps_newest_records(self) -> None:
        queue = BoundedMessageQueue(maxsize=2)

        queue.put(self.message(1))
        queue.put(self.message(2))
        queue.put(self.message(3))

        self.assertEqual([item.sequence for item in queue.drain()], [2, 3])


class ConfigStoreTests(unittest.TestCase):
    def test_round_trip_preserves_unicode_and_nested_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "config.json"
            store = ConfigStore(path)
            config = AppConfig()
            config.window.monitor_name = "Portrait – 左"
            config.chat.font_size = 34
            config.chat.filters.hide_commands = True

            store.save(config)
            loaded = store.load()

        self.assertEqual(loaded.window.monitor_name, "Portrait – 左")
        self.assertEqual(loaded.chat.font_size, 34)
        self.assertTrue(loaded.chat.filters.hide_commands)

    def test_invalid_json_falls_back_to_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("not json", encoding="utf-8")

            loaded = ConfigStore(path).load()

        self.assertEqual(loaded.window.width, 1080)
        self.assertEqual(loaded.window.height, 1920)
        self.assertEqual(loaded.chat.max_messages, 750)

    def test_malformed_known_key_types_fall_back_while_valid_siblings_survive(self) -> None:
        malformed = {
            "version": {"bad": True},
            "window": {
                "width": {"bad": True},
                "height": "999999",
                "x": "not-a-number",
                "monitor_name": "Portrait Display",
                "always_on_top": "yes",
            },
            "chat": {
                "font_size": None,
                "message_spacing": [],
                "max_messages": "25",
                "highlight_terms": "not-a-list",
                "filters": {
                    "hide_commands": "yes",
                    "bot_names": {"bad": True},
                    "repeated_spam_threshold": [],
                    "repeated_spam_window_seconds": "NaN",
                },
            },
            "ingest": {
                "host": ["0.0.0.0"],
                "port": "17845",
                "path": {"bad": True},
                "queue_size": "infinite",
            },
            "obs": {
                "poll_interval_seconds": "NaN",
                "reconnect_initial_seconds": "2.5",
                "reconnect_max_seconds": {"bad": True},
                "mic_input": "Mic/Aux",
            },
            "logging": {"level": 7, "max_bytes": [], "backup_count": None},
            "start_with_windows": [True],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(malformed), encoding="utf-8")

            loaded = ConfigStore(path).load()

        self.assertEqual(loaded.version, 1)
        self.assertEqual(loaded.window.width, 1080)
        self.assertEqual(loaded.window.height, 7680)
        self.assertIsNone(loaded.window.x)
        self.assertEqual(loaded.window.monitor_name, "Portrait Display")
        self.assertTrue(loaded.window.always_on_top)
        self.assertEqual(loaded.chat.font_size, 28)
        self.assertEqual(loaded.chat.message_spacing, 18)
        self.assertEqual(loaded.chat.max_messages, 100)
        self.assertEqual(loaded.chat.highlight_terms, ["Lausudo", "@Lausudo"])
        self.assertTrue(loaded.chat.filters.hide_commands)
        self.assertEqual(loaded.chat.filters.bot_names, [])
        self.assertEqual(loaded.chat.filters.repeated_spam_threshold, 3)
        self.assertEqual(loaded.chat.filters.repeated_spam_window_seconds, 20.0)
        self.assertEqual(loaded.ingest.host, "127.0.0.1")
        self.assertEqual(loaded.ingest.port, 17845)
        self.assertEqual(loaded.ingest.path, "/ingest/socialstream")
        self.assertEqual(loaded.ingest.queue_size, 1000)
        self.assertEqual(loaded.obs.poll_interval_seconds, 1.5)
        self.assertEqual(loaded.obs.reconnect_initial_seconds, 2.5)
        self.assertEqual(loaded.obs.reconnect_max_seconds, 20.0)
        self.assertEqual(loaded.obs.mic_input, "Mic/Aux")
        self.assertEqual(loaded.logging.level, "INFO")
        self.assertEqual(loaded.logging.max_bytes, 1_048_576)
        self.assertEqual(loaded.logging.backup_count, 3)
        self.assertFalse(loaded.start_with_windows)


if __name__ == "__main__":
    unittest.main()
