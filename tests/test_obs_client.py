from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import tempfile
import unittest

from streamer_console.config import LoggingSettings, ObsSettings
from streamer_console.logging_setup import configure_logging
from streamer_console.obs_client import (
    ObsConnectionSettings,
    ObsRequestError,
    ObsWebSocketSession,
    calculate_obs_auth,
    collect_obs_status,
    read_obs_connection_settings,
)


class ObsConfigurationTests(unittest.TestCase):
    def test_reads_existing_obs_configuration_and_repr_redacts_password(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "server_enabled": True,
                        "server_port": 4455,
                        "auth_required": True,
                        "server_password": "do-not-print-me",
                    }
                ),
                encoding="utf-8",
            )

            result = read_obs_connection_settings(path)

        self.assertTrue(result.enabled)
        self.assertEqual(result.port, 4455)
        self.assertEqual(result.password, "do-not-print-me")
        self.assertNotIn("do-not-print-me", repr(result))

    def test_port_override_wins_without_modifying_obs_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"server_enabled": True, "server_port": 4455}),
                encoding="utf-8",
            )

            result = read_obs_connection_settings(path, port_override=4456)

        self.assertEqual(result.port, 4456)

    def test_calculates_obs_websocket_auth_value(self) -> None:
        result = calculate_obs_auth("password", "salt", "challenge")

        self.assertEqual(result, "zTM5ki6L2vVvBQiTG9ckH1Lh64AbnCf6XZ226UmnkIA=")

    def test_rotating_log_redacts_credentials_and_does_not_log_message_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = configure_logging(
                LoggingSettings(max_bytes=64 * 1024, backup_count=1), directory=directory
            )
            logger = logging.getLogger("streamer_console.test")
            logger.info(
                "password=hunter2 token:abc123 Authorization: Bearer bearer-secret connected"
            )
            root_logger = logging.getLogger("streamer_console")
            for handler in root_logger.handlers:
                handler.flush()
            contents = path.read_text(encoding="utf-8")
            for handler in list(root_logger.handlers):
                root_logger.removeHandler(handler)
                handler.close()

        self.assertIn("password=[REDACTED]", contents)
        self.assertIn("token:[REDACTED]", contents)
        self.assertNotIn("hunter2", contents)
        self.assertNotIn("abc123", contents)
        self.assertNotIn("bearer-secret", contents)


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.closed = False
        self._initial = [
            {
                "op": 0,
                "d": {
                    "rpcVersion": 1,
                    "authentication": {"salt": "salt", "challenge": "challenge"},
                },
            },
            {"op": 2, "d": {"negotiatedRpcVersion": 1}},
        ]

    async def recv(self) -> str:
        if self._initial:
            return json.dumps(self._initial.pop(0))
        request = self.sent[-1]
        request_data = request["d"]
        assert isinstance(request_data, dict)
        return json.dumps(
            {
                "op": 7,
                "d": {
                    "requestType": request_data["requestType"],
                    "requestId": request_data["requestId"],
                    "requestStatus": {"result": True, "code": 100},
                    "responseData": {"ok": True},
                },
            }
        )

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def close(self) -> None:
        self.closed = True


class ObsProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticates_and_sends_protocol_v5_request(self) -> None:
        socket = FakeSocket()

        async def connect_factory(*args: object, **kwargs: object) -> FakeSocket:
            return socket

        session = ObsWebSocketSession(
            ObsConnectionSettings(password="password"), connect_factory=connect_factory
        )

        await session.connect()
        result = await session.request("GetStreamStatus")
        await session.close()

        identify = socket.sent[0]
        identify_data = identify["d"]
        assert isinstance(identify_data, dict)
        self.assertEqual(identify["op"], 1)
        self.assertEqual(
            identify_data["authentication"],
            "zTM5ki6L2vVvBQiTG9ckH1Lh64AbnCf6XZ226UmnkIA=",
        )
        self.assertEqual(socket.sent[1]["op"], 6)
        self.assertEqual(result, {"ok": True})
        self.assertTrue(socket.closed)


class FakeStatusSession:
    def __init__(self, *, aitum_available: bool = True) -> None:
        self.aitum_available = aitum_available

    async def request(self, request_type: str, request_data=None):
        if request_type == "GetStreamStatus":
            return {"outputActive": True}
        if request_type == "GetRecordStatus":
            return {"outputActive": True}
        if request_type == "GetCurrentProgramScene":
            return {"currentProgramSceneName": "BRB - Main"}
        if request_type == "GetInputMute":
            return {"inputMuted": True}
        if request_type == "GetInputAudioMonitorType":
            return {"monitorType": "OBS_MONITORING_TYPE_NONE"}
        if request_type == "CallVendorRequest":
            if not self.aitum_available:
                raise ObsRequestError("CallVendorRequest", 204, "vendor unavailable")
            vendor_request = request_data["requestType"]
            if vendor_request == "current_scene":
                return {"responseData": {"success": True, "scene": "BRB - Vertical"}}
            if vendor_request == "get_outputs":
                return {
                    "responseData": {
                        "success": True,
                        "outputs": [
                            {"name": "Virtual Camera", "type": "virtualcam", "active": True}
                        ],
                    }
                }
        raise AssertionError(f"unexpected request {request_type}")


class ObsStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_collects_stream_record_audio_and_aitum_actual_state(self) -> None:
        status = await collect_obs_status(FakeStatusSession(), ObsSettings())  # type: ignore[arg-type]

        self.assertTrue(status.connected)
        self.assertTrue(status.streaming)
        self.assertTrue(status.recording)
        self.assertEqual(status.main_scene, "BRB - Main")
        self.assertEqual(status.vertical_scene, "BRB - Vertical")
        self.assertTrue(status.mic_muted)
        self.assertEqual(status.mic_monitor_type, "OBS_MONITORING_TYPE_NONE")
        self.assertEqual(status.brb_state, "brb")
        self.assertEqual(status.vertical_outputs[0]["active"], True)

    async def test_aitum_failure_preserves_main_obs_status(self) -> None:
        status = await collect_obs_status(
            FakeStatusSession(aitum_available=False), ObsSettings()  # type: ignore[arg-type]
        )

        self.assertTrue(status.connected)
        self.assertTrue(status.streaming)
        self.assertEqual(status.main_scene, "BRB - Main")
        self.assertEqual(status.vertical_scene, "")
        self.assertEqual(status.brb_state, "unknown")


if __name__ == "__main__":
    unittest.main()
