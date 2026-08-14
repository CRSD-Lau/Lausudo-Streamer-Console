"""Read-only OBS WebSocket 5 monitor with Aitum Stream Suite status support."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import asdict, dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
from queue import Empty, Full, Queue
import threading
from typing import Any, Awaitable, Callable, Mapping, Protocol
import uuid

from websockets.asyncio.client import connect as websocket_connect

from .config import ObsSettings


LOGGER = logging.getLogger(__name__)


class ObsError(RuntimeError):
    pass


class ObsProtocolError(ObsError):
    pass


class ObsRequestError(ObsError):
    def __init__(self, request_type: str, code: int, comment: str = "") -> None:
        # Request comments are emitted by OBS and do not contain our auth data.
        super().__init__(f"OBS request {request_type} failed ({code}): {comment}".rstrip())
        self.request_type = request_type
        self.code = code


@dataclass(frozen=True, slots=True)
class ObsConnectionSettings:
    host: str = "127.0.0.1"
    port: int = 4455
    auth_required: bool = True
    password: str = field(default="", repr=False)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ObsStatus:
    connected: bool
    connection_state: str
    streaming: bool | None = None
    recording: bool | None = None
    main_scene: str = ""
    vertical_scene: str = ""
    mic_muted: bool | None = None
    mic_monitor_type: str = ""
    vertical_outputs: tuple[dict[str, Any], ...] = ()
    brb_state: str = "unknown"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def obs_websocket_config_path(app_data: str | Path | None = None) -> Path:
    if app_data is None:
        app_data = os.environ.get("APPDATA")
    base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
    return base / "obs-studio" / "plugin_config" / "obs-websocket" / "config.json"


def read_obs_connection_settings(
    path: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port_override: int = 0,
) -> ObsConnectionSettings:
    """Read OBS's own local server configuration without copying its secret."""

    target = Path(path) if path is not None else obs_websocket_config_path()
    try:
        with target.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ObsError("OBS WebSocket configuration is unavailable") from exc
    configured_port = int(data.get("server_port") or 4455)
    return ObsConnectionSettings(
        host=host,
        port=int(port_override or configured_port),
        auth_required=bool(data.get("auth_required", True)),
        password=str(data.get("server_password") or ""),
        enabled=bool(data.get("server_enabled", False)),
    )


def calculate_obs_auth(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(
        hashlib.sha256((password + salt).encode("utf-8")).digest()
    ).decode("ascii")
    return base64.b64encode(
        hashlib.sha256((secret + challenge).encode("utf-8")).digest()
    ).decode("ascii")


class _WebSocketLike(Protocol):
    async def recv(self) -> str | bytes: ...
    async def send(self, message: str) -> None: ...
    async def close(self) -> None: ...


ConnectFactory = Callable[..., Awaitable[_WebSocketLike]]


class ObsWebSocketSession:
    def __init__(
        self,
        connection: ObsConnectionSettings,
        *,
        connect_factory: ConnectFactory = websocket_connect,
    ) -> None:
        self.connection = connection
        self._connect_factory = connect_factory
        self._socket: _WebSocketLike | None = None
        self._request_lock = asyncio.Lock()

    async def connect(self) -> None:
        if not self.connection.enabled:
            raise ObsError("OBS WebSocket server is disabled")
        uri = f"ws://{self.connection.host}:{self.connection.port}"
        socket = await self._connect_factory(
            uri, open_timeout=5, close_timeout=2, max_size=2 * 1024 * 1024
        )
        self._socket = socket
        hello = await self._receive_json()
        if hello.get("op") != 0:
            raise ObsProtocolError("OBS did not send a Hello message")
        hello_data = hello.get("d") if isinstance(hello.get("d"), Mapping) else {}
        auth_data = hello_data.get("authentication")
        identify: dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}
        if isinstance(auth_data, Mapping):
            if not self.connection.password:
                raise ObsError("OBS WebSocket authentication is required")
            identify["authentication"] = calculate_obs_auth(
                self.connection.password,
                str(auth_data.get("salt", "")),
                str(auth_data.get("challenge", "")),
            )
        await socket.send(json.dumps({"op": 1, "d": identify}, separators=(",", ":")))
        identified = await self._receive_json()
        if identified.get("op") != 2:
            raise ObsProtocolError("OBS WebSocket authentication failed")

    async def _receive_json(self) -> Mapping[str, Any]:
        if self._socket is None:
            raise ObsError("OBS WebSocket is not connected")
        raw = await self._socket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            message = json.loads(raw)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ObsProtocolError("OBS sent invalid JSON") from exc
        if not isinstance(message, Mapping):
            raise ObsProtocolError("OBS sent an invalid message envelope")
        return message

    async def request(
        self, request_type: str, request_data: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        if self._socket is None:
            raise ObsError("OBS WebSocket is not connected")
        async with self._request_lock:
            request_id = uuid.uuid4().hex
            payload = {
                "op": 6,
                "d": {
                    "requestType": request_type,
                    "requestId": request_id,
                    "requestData": dict(request_data or {}),
                },
            }
            await self._socket.send(json.dumps(payload, separators=(",", ":")))
            while True:
                response = await self._receive_json()
                if response.get("op") != 7:
                    continue
                data = response.get("d")
                if not isinstance(data, Mapping) or data.get("requestId") != request_id:
                    continue
                request_status = data.get("requestStatus")
                if not isinstance(request_status, Mapping):
                    raise ObsProtocolError("OBS response omitted request status")
                if not request_status.get("result"):
                    raise ObsRequestError(
                        request_type,
                        int(request_status.get("code") or 0),
                        str(request_status.get("comment") or ""),
                    )
                response_data = data.get("responseData")
                return response_data if isinstance(response_data, Mapping) else {}

    async def close(self) -> None:
        socket, self._socket = self._socket, None
        if socket is not None:
            await socket.close()


async def _call_aitum(
    session: ObsWebSocketSession,
    settings: ObsSettings,
    request_type: str,
    request_data: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    outer = await session.request(
        "CallVendorRequest",
        {
            "vendorName": settings.aitum_vendor_name,
            "requestType": request_type,
            "requestData": dict(request_data or {}),
        },
    )
    response = outer.get("responseData")
    if not isinstance(response, Mapping):
        return {}
    if response.get("success") is False:
        raise ObsRequestError(f"Aitum/{request_type}", 0, str(response.get("error") or ""))
    return response


def _brb_state(main_scene: str, vertical_scene: str, settings: ObsSettings) -> str:
    if not main_scene or not vertical_scene:
        return "unknown"
    main_brb = main_scene == settings.brb_main_scene
    vertical_brb = vertical_scene == settings.brb_vertical_scene
    if main_brb and vertical_brb:
        return "brb"
    if not main_brb and not vertical_brb:
        return "live"
    return "mixed"


async def collect_obs_status(
    session: ObsWebSocketSession, settings: ObsSettings
) -> ObsStatus:
    stream = await session.request("GetStreamStatus")
    record = await session.request("GetRecordStatus")
    main_scene = await session.request("GetCurrentProgramScene")
    mic_mute = await session.request("GetInputMute", {"inputName": settings.mic_input})
    mic_monitor = await session.request(
        "GetInputAudioMonitorType", {"inputName": settings.mic_input}
    )

    vertical_scene_name = ""
    vertical_outputs: tuple[dict[str, Any], ...] = ()
    try:
        vertical_scene = await _call_aitum(
            session,
            settings,
            "current_scene",
            {"canvas": settings.aitum_vertical_canvas},
        )
        vertical_scene_name = str(vertical_scene.get("scene") or "")
        output_result = await _call_aitum(session, settings, "get_outputs")
        outputs = output_result.get("outputs")
        if isinstance(outputs, list):
            vertical_outputs = tuple(
                {
                    "name": str(item.get("name") or ""),
                    "type": str(item.get("type") or ""),
                    "active": bool(item.get("active")),
                }
                for item in outputs
                if isinstance(item, Mapping)
            )
    except ObsRequestError as exc:
        # OBS state remains useful when Aitum isn't installed or is reloading.
        LOGGER.warning("Aitum status unavailable code=%d", exc.code)

    current_scene = str(main_scene.get("currentProgramSceneName") or "")
    return ObsStatus(
        connected=True,
        connection_state="connected",
        streaming=bool(stream.get("outputActive")),
        recording=bool(record.get("outputActive")),
        main_scene=current_scene,
        vertical_scene=vertical_scene_name,
        mic_muted=bool(mic_mute.get("inputMuted")),
        mic_monitor_type=str(mic_monitor.get("monitorType") or ""),
        vertical_outputs=vertical_outputs,
        brb_state=_brb_state(current_scene, vertical_scene_name, settings),
    )


class ObsMonitor:
    """Background OBS status monitor with bounded Qt-safe status delivery."""

    def __init__(
        self,
        settings: ObsSettings | None = None,
        *,
        websocket_config: str | Path | None = None,
        queue_size: int = 16,
        session_factory: Callable[[ObsConnectionSettings], ObsWebSocketSession] = ObsWebSocketSession,
    ) -> None:
        self.settings = settings or ObsSettings()
        self.websocket_config = Path(websocket_config) if websocket_config else None
        self._session_factory = session_factory
        self._queue: Queue[ObsStatus] = Queue(maxsize=max(1, int(queue_size)))
        self._latest = ObsStatus(False, "disconnected")
        self._latest_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def latest_status(self) -> ObsStatus:
        with self._latest_lock:
            return self._latest

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _publish(self, status: ObsStatus) -> None:
        with self._latest_lock:
            self._latest = status
        try:
            self._queue.put_nowait(status)
            return
        except Full:
            pass
        try:
            self._queue.get_nowait()
        except Empty:
            pass
        try:
            self._queue.put_nowait(status)
        except Full:
            pass

    def drain(self, max_items: int = 16) -> list[ObsStatus]:
        statuses: list[ObsStatus] = []
        for _ in range(max(0, int(max_items))):
            try:
                statuses.append(self._queue.get_nowait())
            except Empty:
                break
        return statuses

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_main, name="obs-status-monitor", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))
        self._publish(ObsStatus(False, "disconnected"))

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._monitor_loop())
        except Exception as exc:  # last-resort boundary; no secret-bearing repr
            LOGGER.error("OBS monitor stopped unexpectedly type=%s", type(exc).__name__)
            self._publish(ObsStatus(False, "disconnected", detail="Monitor stopped"))

    async def _monitor_loop(self) -> None:
        delay = self.settings.reconnect_initial_seconds
        while not self._stop_event.is_set():
            self._publish(ObsStatus(False, "reconnecting"))
            session: ObsWebSocketSession | None = None
            try:
                connection = read_obs_connection_settings(
                    self.websocket_config,
                    host=self.settings.host,
                    port_override=self.settings.port,
                )
                session = self._session_factory(connection)
                await session.connect()
                LOGGER.info("OBS connected")
                delay = self.settings.reconnect_initial_seconds
                while not self._stop_event.is_set():
                    status = await collect_obs_status(session, self.settings)
                    self._publish(status)
                    await self._interruptible_wait(self.settings.poll_interval_seconds)
            except (ObsError, OSError, asyncio.TimeoutError, ConnectionError) as exc:
                LOGGER.warning("OBS unavailable type=%s; reconnect scheduled", type(exc).__name__)
                self._publish(
                    ObsStatus(False, "reconnecting", detail="OBS unavailable; retrying")
                )
            except Exception as exc:
                # websockets uses several library-specific connection exceptions;
                # report only the type so URI/path data cannot leak into logs.
                LOGGER.warning("OBS connection lost type=%s; reconnect scheduled", type(exc).__name__)
                self._publish(
                    ObsStatus(False, "reconnecting", detail="OBS connection lost; retrying")
                )
            finally:
                if session is not None:
                    try:
                        await session.close()
                    except Exception:
                        pass
            if not self._stop_event.is_set():
                await self._interruptible_wait(delay)
                delay = min(delay * 2.0, self.settings.reconnect_max_seconds)
        self._publish(ObsStatus(False, "disconnected"))

    async def _interruptible_wait(self, seconds: float) -> None:
        deadline = asyncio.get_running_loop().time() + max(0.0, seconds)
        while not self._stop_event.is_set():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.1, remaining))


# Backward-friendly name for integration code drafted before the final class name.
ObsClient = ObsMonitor

