"""Official Twitch channel-info and EventSub integration.

OAuth uses Twitch's Device Code Grant so this public desktop application never
needs a client secret. Refresh/access tokens are encrypted with Windows DPAPI
and are never written to the ordinary JSON configuration or logs.
"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import queue
import threading
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import TwitchSettings, app_data_dir


LOGGER = logging.getLogger("streamer_console.twitch")

TWITCH_SCOPES = (
    "channel:manage:broadcast",
    "user:read:chat",
    "moderator:read:followers",
    "channel:read:subscriptions",
    "bits:read",
    "channel:read:redemptions",
)


class TwitchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TwitchUpdate:
    kind: str
    payload: Mapping[str, Any]


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class TwitchTokenStore:
    """Small DPAPI-protected token store scoped to the current Windows user."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else app_data_dir() / "twitch-auth.dat"

    @staticmethod
    def _blob(data: bytes) -> tuple[_DataBlob, Any]:
        buffer = ctypes.create_string_buffer(data)
        blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        return blob, buffer

    def _protect(self, data: bytes) -> bytes:
        if os.name != "nt":
            raise TwitchError("Secure Twitch token storage requires Windows")
        source, keepalive = self._blob(data)
        output = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        ok = crypt32.CryptProtectData(
            ctypes.byref(source), "Streamer Console Twitch", None, None, None, 0,
            ctypes.byref(output),
        )
        del keepalive
        if not ok:
            raise TwitchError("Windows could not encrypt the Twitch authorization")
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            kernel32.LocalFree(output.pbData)

    def _unprotect(self, data: bytes) -> bytes:
        if os.name != "nt":
            raise TwitchError("Secure Twitch token storage requires Windows")
        source, keepalive = self._blob(data)
        output = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
        )
        del keepalive
        if not ok:
            raise TwitchError("Windows could not decrypt the Twitch authorization")
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            kernel32.LocalFree(output.pbData)

    def load(self) -> dict[str, Any] | None:
        try:
            raw = self._unprotect(self.path.read_bytes())
            value = json.loads(raw.decode("utf-8"))
        except (FileNotFoundError, OSError, ValueError, UnicodeError, TwitchError):
            return None
        return dict(value) if isinstance(value, Mapping) else None

    def save(self, token: Mapping[str, Any]) -> None:
        allowed = {
            key: token[key]
            for key in ("access_token", "refresh_token", "expires_in", "scope", "token_type")
            if key in token
        }
        protected = self._protect(json.dumps(allowed).encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(protected)
        os.replace(temporary, self.path)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class TwitchApiClient:
    """Minimal stdlib Twitch OAuth/Helix client with no secret-bearing logs."""

    def __init__(self, *, timeout: float = 12.0, opener: Any = urlopen) -> None:
        self.timeout = timeout
        self._opener = opener

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        data: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        body: bytes | None = None
        request_headers = dict(headers or {})
        if data is not None:
            body = urlencode({key: str(value) for key, value in data.items()}).encode()
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("message", "")
            except Exception:
                detail = ""
            raise TwitchError(f"Twitch request failed ({exc.code}){': ' + detail if detail else ''}") from None
        except (URLError, OSError, TimeoutError) as exc:
            raise TwitchError(f"Twitch is unreachable ({type(exc).__name__})") from None
        if not raw:
            return {}
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise TwitchError("Twitch returned an unreadable response") from None
        return dict(decoded) if isinstance(decoded, Mapping) else {}

    @staticmethod
    def auth_headers(client_id: str, access_token: str) -> dict[str, str]:
        return {"Client-Id": client_id, "Authorization": f"Bearer {access_token}"}

    def begin_device_authorization(self, client_id: str) -> dict[str, Any]:
        return self._request(
            "https://id.twitch.tv/oauth2/device",
            method="POST",
            data={"client_id": client_id, "scopes": " ".join(TWITCH_SCOPES)},
        )

    def poll_device_authorization(self, client_id: str, device_code: str) -> dict[str, Any]:
        return self._request(
            "https://id.twitch.tv/oauth2/token",
            method="POST",
            data={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )

    def refresh_token(self, client_id: str, refresh_token: str) -> dict[str, Any]:
        return self._request(
            "https://id.twitch.tv/oauth2/token",
            method="POST",
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

    def validate(self, access_token: str) -> dict[str, Any]:
        return self._request(
            "https://id.twitch.tv/oauth2/validate",
            headers={"Authorization": f"OAuth {access_token}"},
        )

    def channel_info(self, client_id: str, access_token: str, broadcaster_id: str) -> dict[str, Any]:
        result = self._request(
            "https://api.twitch.tv/helix/channels?" + urlencode({"broadcaster_id": broadcaster_id}),
            headers=self.auth_headers(client_id, access_token),
        )
        rows = result.get("data", [])
        return dict(rows[0]) if isinstance(rows, list) and rows else {}

    def stream_status(
        self, client_id: str, access_token: str, broadcaster_id: str
    ) -> dict[str, Any]:
        """Return the broadcaster's current live state and viewer count."""

        result = self._request(
            "https://api.twitch.tv/helix/streams?"
            + urlencode({"user_id": broadcaster_id}),
            headers=self.auth_headers(client_id, access_token),
        )
        rows = result.get("data", [])
        if not isinstance(rows, list) or not rows:
            return {"live": False, "viewers": 0}
        row = rows[0] if isinstance(rows[0], Mapping) else {}
        try:
            viewers = max(0, int(row.get("viewer_count", 0) or 0))
        except (TypeError, ValueError):
            viewers = 0
        return {"live": True, "viewers": viewers}

    def categories(self, client_id: str, access_token: str, query: str) -> list[dict[str, Any]]:
        result = self._request(
            "https://api.twitch.tv/helix/search/categories?" + urlencode({"query": query, "first": 10}),
            headers=self.auth_headers(client_id, access_token),
        )
        rows = result.get("data", [])
        return [dict(row) for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []

    def update_channel(
        self,
        client_id: str,
        access_token: str,
        broadcaster_id: str,
        *,
        title: str,
        game_id: str | None,
    ) -> None:
        body: dict[str, Any] = {"title": title}
        if game_id:
            body["game_id"] = game_id
        self._request(
            "https://api.twitch.tv/helix/channels?" + urlencode({"broadcaster_id": broadcaster_id}),
            method="PATCH",
            json_body=body,
            headers=self.auth_headers(client_id, access_token),
        )

    def create_stream_marker(
        self,
        client_id: str,
        access_token: str,
        broadcaster_id: str,
        description: str,
    ) -> dict[str, Any]:
        result = self._request(
            "https://api.twitch.tv/helix/streams/markers",
            method="POST",
            json_body={"user_id": broadcaster_id, "description": description[:140]},
            headers=self.auth_headers(client_id, access_token),
        )
        rows = result.get("data", [])
        return dict(rows[0]) if isinstance(rows, list) and rows else {}

    def create_eventsub(
        self,
        client_id: str,
        access_token: str,
        event_type: str,
        version: str,
        condition: Mapping[str, str],
        session_id: str,
    ) -> None:
        self._request(
            "https://api.twitch.tv/helix/eventsub/subscriptions",
            method="POST",
            json_body={
                "type": event_type,
                "version": version,
                "condition": dict(condition),
                "transport": {"method": "websocket", "session_id": session_id},
            },
            headers=self.auth_headers(client_id, access_token),
        )


class TwitchService:
    """Background Twitch API command worker plus independent EventSub monitor."""

    METRICS_POLL_SECONDS = 15.0

    def __init__(
        self,
        settings: TwitchSettings,
        *,
        api: TwitchApiClient | None = None,
        token_store: TwitchTokenStore | None = None,
        event_sink: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> None:
        self.settings = settings
        self.api = api or TwitchApiClient()
        self.token_store = token_store or TwitchTokenStore()
        self.event_sink = event_sink
        self._commands: queue.Queue[tuple[str, tuple[Any, ...]]] = queue.Queue(maxsize=50)
        self._updates: queue.Queue[TwitchUpdate] = queue.Queue(maxsize=500)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._event_thread: threading.Thread | None = None
        self._token_lock = threading.RLock()
        self._token: dict[str, Any] | None = None
        self._identity: dict[str, Any] | None = None
        self._subscribed_event_types: set[str] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="TwitchApi", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 4.0) -> None:
        self._stop.set()
        try:
            self._commands.put_nowait(("stop", ()))
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout)
        if self._event_thread:
            self._event_thread.join(timeout)

    def drain(self, max_items: int = 100) -> list[TwitchUpdate]:
        items: list[TwitchUpdate] = []
        for _ in range(max(0, max_items)):
            try:
                items.append(self._updates.get_nowait())
            except queue.Empty:
                break
        return items

    def connect(self, client_id: str) -> None:
        self._enqueue("connect", client_id.strip())

    def refresh_info(self) -> None:
        self._enqueue("refresh")

    def search_categories(self, query: str) -> None:
        self._enqueue("categories", query.strip())

    def update_info(self, title: str, category: str) -> None:
        self._enqueue("update", title.strip(), category.strip())

    def create_marker(self, description: str = "Raid moment") -> None:
        self._enqueue("marker", description.strip() or "Raid moment")

    def _enqueue(self, name: str, *values: Any) -> None:
        try:
            self._commands.put_nowait((name, values))
        except queue.Full:
            self._emit("error", message="Twitch command queue is busy")

    def _emit(self, kind: str, **payload: Any) -> None:
        update = TwitchUpdate(kind, payload)
        try:
            self._updates.put_nowait(update)
        except queue.Full:
            try:
                self._updates.get_nowait()
                self._updates.put_nowait(update)
            except queue.Empty:
                pass

    def _run(self) -> None:
        if self.settings.client_id:
            try:
                self._restore_authorization()
            except TwitchError:
                LOGGER.warning("Stored Twitch authorization could not be restored")
                self._emit("status", connected=False, state="authorization_required")
        else:
            self._emit("status", connected=False, state="needs_client_id")
        next_metrics_at = time.monotonic() + self.METRICS_POLL_SECONDS
        while not self._stop.is_set():
            try:
                name, args = self._commands.get(timeout=0.5)
            except queue.Empty:
                name = ""
                args = ()
            if name:
                if name == "stop":
                    break
                try:
                    if name == "connect":
                        self._authorize(str(args[0]))
                    elif name == "refresh":
                        self._load_channel_info()
                    elif name == "categories":
                        self._search_categories(str(args[0]))
                    elif name == "update":
                        self._update_channel(str(args[0]), str(args[1]))
                    elif name == "marker":
                        self._create_marker(str(args[0]))
                except TwitchError as exc:
                    LOGGER.warning("Twitch operation failed operation=%s", name)
                    self._emit("error", message=str(exc))
            now = time.monotonic()
            if now >= next_metrics_at and self._has_credentials():
                try:
                    self._load_stream_metrics()
                except TwitchError:
                    LOGGER.warning("Twitch viewer count refresh failed")
                    self._emit("metrics", twitch_viewers=None, twitch_live=None)
                next_metrics_at = now + self.METRICS_POLL_SECONDS

    def _restore_authorization(self) -> None:
        token = self.token_store.load()
        if not token or not token.get("access_token"):
            self._emit("status", connected=False, state="authorization_required")
            return
        try:
            identity = self.api.validate(str(token["access_token"]))
        except TwitchError:
            refresh = str(token.get("refresh_token", ""))
            if not refresh:
                self._emit("status", connected=False, state="authorization_required")
                return
            token = self.api.refresh_token(self.settings.client_id, refresh)
            self.token_store.save(token)
            identity = self.api.validate(str(token["access_token"]))
        self._set_authorized(token, identity)

    def _authorize(self, client_id: str) -> None:
        if not client_id:
            raise TwitchError("Enter the Twitch application Client ID first")
        self.settings.client_id = client_id
        device = self.api.begin_device_authorization(client_id)
        code = str(device.get("device_code", ""))
        verification_url = str(device.get("verification_uri", "https://www.twitch.tv/activate"))
        user_code = str(device.get("user_code", ""))
        if not code or not user_code:
            raise TwitchError("Twitch did not provide an authorization code")
        interval = max(1, int(device.get("interval", 5) or 5))
        deadline = time.monotonic() + max(60, int(device.get("expires_in", 900) or 900))
        self._emit("device_code", verification_url=verification_url, user_code=user_code)
        self._emit("status", connected=False, state="waiting_for_authorization")
        while not self._stop.is_set() and time.monotonic() < deadline:
            if self._stop.wait(interval):
                return
            try:
                token = self.api.poll_device_authorization(client_id, code)
            except TwitchError as exc:
                message = str(exc).casefold()
                if "authorization_pending" in message:
                    continue
                if "slow_down" in message:
                    interval += 2
                    continue
                raise
            if token.get("access_token"):
                self.token_store.save(token)
                identity = self.api.validate(str(token["access_token"]))
                self._set_authorized(token, identity)
                return
        if not self._stop.is_set():
            raise TwitchError("Twitch authorization code expired; choose Connect again")

    def _set_authorized(self, token: Mapping[str, Any], identity: Mapping[str, Any]) -> None:
        granted = {str(scope) for scope in identity.get("scopes", token.get("scope", ())) or ()}
        if not set(TWITCH_SCOPES).issubset(granted):
            raise TwitchError(
                "Twitch permissions changed; connect again to approve native chat, alerts and Stream Info"
            )
        with self._token_lock:
            self._token = dict(token)
            self._identity = dict(identity)
        self._emit(
            "status",
            connected=True,
            state="connected",
            account=str(identity.get("login", "")),
        )
        self._load_channel_info()
        try:
            self._load_stream_metrics()
        except TwitchError:
            # Viewer telemetry is optional and must never invalidate an
            # otherwise healthy channel-info/EventSub authorization.
            LOGGER.warning("Initial Twitch viewer count unavailable")
            self._emit("metrics", twitch_viewers=None, twitch_live=None)
        self._start_eventsub()

    def _has_credentials(self) -> bool:
        with self._token_lock:
            return bool(
                self.settings.client_id
                and (self._token or {}).get("access_token")
                and (self._identity or {}).get("user_id")
            )

    def _credentials(self) -> tuple[str, str, str]:
        with self._token_lock:
            token = dict(self._token or {})
            identity = dict(self._identity or {})
        access_token = str(token.get("access_token", ""))
        broadcaster_id = str(identity.get("user_id", ""))
        if not self.settings.client_id or not access_token or not broadcaster_id:
            raise TwitchError("Connect Twitch before using Stream Info")
        return self.settings.client_id, access_token, broadcaster_id

    def _load_channel_info(self) -> None:
        client_id, access_token, broadcaster_id = self._credentials()
        info = self.api.channel_info(client_id, access_token, broadcaster_id)
        self._emit(
            "channel_info",
            title=str(info.get("title", "")),
            category=str(info.get("game_name", "")),
            category_id=str(info.get("game_id", "")),
        )

    def _load_stream_metrics(self) -> None:
        client_id, access_token, broadcaster_id = self._credentials()
        status = self.api.stream_status(client_id, access_token, broadcaster_id)
        self._emit(
            "metrics",
            twitch_viewers=max(0, int(status.get("viewers", 0) or 0)),
            twitch_live=bool(status.get("live", False)),
        )

    def _search_categories(self, query: str) -> None:
        if len(query) < 2:
            self._emit("categories", values=[])
            return
        client_id, access_token, _ = self._credentials()
        rows = self.api.categories(client_id, access_token, query)
        self._emit("categories", values=[{"id": row.get("id", ""), "name": row.get("name", "")} for row in rows])

    def _update_channel(self, title: str, category: str) -> None:
        if not title:
            raise TwitchError("Stream title cannot be empty")
        client_id, access_token, broadcaster_id = self._credentials()
        game_id: str | None = None
        if category:
            rows = self.api.categories(client_id, access_token, category)
            exact = next(
                (row for row in rows if str(row.get("name", "")).casefold() == category.casefold()),
                rows[0] if rows else None,
            )
            if not exact:
                raise TwitchError("Twitch could not find that category")
            game_id = str(exact.get("id", "")) or None
        self.api.update_channel(
            client_id, access_token, broadcaster_id, title=title, game_id=game_id
        )
        self._emit("updated", message="Twitch stream info updated")
        self._load_channel_info()

    def _create_marker(self, description: str) -> None:
        client_id, access_token, broadcaster_id = self._credentials()
        marker = self.api.create_stream_marker(
            client_id, access_token, broadcaster_id, description[:140]
        )
        self._emit(
            "marker",
            success=True,
            message="Moment marked on Twitch",
            marker_id=str(marker.get("id", "")),
            position_seconds=marker.get("position_seconds"),
            description=description[:140],
        )

    def _start_eventsub(self) -> None:
        if self._event_thread and self._event_thread.is_alive():
            return
        self._event_thread = threading.Thread(
            target=self._eventsub_loop, name="TwitchEventSub", daemon=True
        )
        self._event_thread.start()

    def _eventsub_loop(self) -> None:
        try:
            from websockets.sync.client import connect
        except ImportError:
            self._emit("eventsub_status", connected=False, state="unavailable")
            return
        delay = 1.0
        endpoint = "wss://eventsub.wss.twitch.tv/ws"
        migrated_session = False
        while not self._stop.is_set():
            try:
                with connect(
                    endpoint,
                    open_timeout=12,
                    close_timeout=2,
                ) as socket:
                    self._emit("eventsub_status", connected=False, state="connecting")
                    while not self._stop.is_set():
                        raw = socket.recv(timeout=15)
                        message = json.loads(raw)
                        metadata = message.get("metadata", {})
                        payload = message.get("payload", {})
                        message_type = metadata.get("message_type", "")
                        if message_type == "session_welcome":
                            session_id = str(payload.get("session", {}).get("id", ""))
                            if not migrated_session:
                                self._subscribed_event_types = self._subscribe(session_id)
                            event_types = set(self._subscribed_event_types)
                            self._emit(
                                "eventsub_status",
                                connected=True,
                                state="connected" if event_types else "partial",
                                event_types=sorted(event_types),
                            )
                            endpoint = "wss://eventsub.wss.twitch.tv/ws"
                            migrated_session = False
                            delay = 1.0
                        elif message_type == "notification":
                            event = self._event_payload(message)
                            if event:
                                if self.event_sink is not None:
                                    self.event_sink(event)
                                else:
                                    self._emit("event", message=event)
                        elif message_type == "session_reconnect":
                            reconnect_url = str(payload.get("session", {}).get("reconnect_url", ""))
                            if reconnect_url:
                                endpoint = reconnect_url
                                migrated_session = True
                            break
            except Exception as exc:
                if not self._stop.is_set():
                    LOGGER.warning("Twitch EventSub reconnecting type=%s", type(exc).__name__)
                    self._emit("eventsub_status", connected=False, state="reconnecting")
                    self._stop.wait(delay)
                    delay = min(delay * 2, 30.0)

    def _subscribe(self, session_id: str) -> set[str]:
        client_id, access_token, broadcaster_id = self._credentials()
        subscriptions = (
            (
                "channel.chat.message",
                "1",
                {"broadcaster_user_id": broadcaster_id, "user_id": broadcaster_id},
            ),
            ("channel.follow", "2", {"broadcaster_user_id": broadcaster_id, "moderator_user_id": broadcaster_id}),
            ("channel.subscribe", "1", {"broadcaster_user_id": broadcaster_id}),
            ("channel.subscription.message", "1", {"broadcaster_user_id": broadcaster_id}),
            ("channel.subscription.gift", "1", {"broadcaster_user_id": broadcaster_id}),
            ("channel.cheer", "1", {"broadcaster_user_id": broadcaster_id}),
            ("channel.raid", "1", {"to_broadcaster_user_id": broadcaster_id}),
            ("channel.channel_points_custom_reward_redemption.add", "1", {"broadcaster_user_id": broadcaster_id}),
        )
        successes: set[str] = set()
        for event_type, version, condition in subscriptions:
            try:
                self.api.create_eventsub(
                    client_id, access_token, event_type, version, condition, session_id
                )
                normalized = {
                    "channel.chat.message": "chat",
                    "channel.follow": "follow",
                    "channel.subscribe": "subscription",
                    "channel.subscription.message": "resub",
                    "channel.subscription.gift": "gift",
                    "channel.cheer": "bits",
                    "channel.raid": "raid",
                    "channel.channel_points_custom_reward_redemption.add": "reward",
                }[event_type]
                successes.add(normalized)
            except TwitchError:
                LOGGER.warning("Twitch EventSub subscription unavailable type=%s", event_type)
        return successes

    @staticmethod
    def _event_payload(message: Mapping[str, Any]) -> dict[str, Any] | None:
        metadata = message.get("metadata", {})
        payload = message.get("payload", {})
        subscription = payload.get("subscription", {})
        event = payload.get("event", {})
        if not isinstance(event, Mapping):
            return None
        source_type = str(subscription.get("type", ""))
        if source_type == "channel.chat.message":
            username = str(event.get("chatter_user_name") or "").strip()
            chat = event.get("message", {})
            text = str(chat.get("text", "")) if isinstance(chat, Mapping) else ""
            if not username or not text.strip():
                return None
            return {
                "type": "twitch",
                "chatname": username,
                "chatmessage": text,
                "event": "",
                "id": "eventsub:" + str(metadata.get("message_id", "")),
            }
        event_type = {
            "channel.follow": "follow",
            "channel.subscribe": "subscription",
            "channel.subscription.message": "resub",
            "channel.subscription.gift": "gift",
            "channel.cheer": "bits",
            "channel.raid": "raid",
            "channel.channel_points_custom_reward_redemption.add": "reward",
        }.get(source_type)
        if not event_type:
            return None
        username = str(
            event.get("user_name")
            or event.get("from_broadcaster_user_name")
            or ("Anonymous" if event.get("is_anonymous") else "")
        )
        if not username:
            return None
        amount = ""
        text = ""
        if event_type == "resub":
            text = str((event.get("message") or {}).get("text", ""))
        elif event_type == "gift":
            amount = f"{event.get('total', 1)} gifted sub(s)"
        elif event_type == "bits":
            amount = f"{event.get('bits', 0)} Bits"
            text = str(event.get("message", ""))
        elif event_type == "raid":
            amount = f"{event.get('viewers', 0)} viewers"
        elif event_type == "reward":
            reward = event.get("reward", {})
            text = str(reward.get("title", "Channel reward redeemed")) if isinstance(reward, Mapping) else "Channel reward redeemed"
        return {
            "type": "twitch",
            "chatname": username,
            "chatmessage": text,
            "event": event_type,
            "amount": amount,
            "id": "eventsub:" + str(metadata.get("message_id", "")),
        }
