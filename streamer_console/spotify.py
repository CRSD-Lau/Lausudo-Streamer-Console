"""Low-overhead Spotify controls through the local Windows media session."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from queue import Empty, Full, Queue
import threading
from typing import Any, Callable, Mapping


LOGGER = logging.getLogger("streamer_console.spotify")


@dataclass(frozen=True, slots=True)
class SpotifyUpdate:
    kind: str
    payload: Mapping[str, Any]


class SpotifyService:
    """Poll and control only the Spotify GSMTC session; never send global keys."""

    POLL_SECONDS = 1.0

    def __init__(self, manager_factory: Callable[[], Any] | None = None) -> None:
        self._manager_factory = manager_factory
        self._updates: Queue[SpotifyUpdate] = Queue(maxsize=32)
        self._commands: Queue[str] = Queue(maxsize=16)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._thread_main, name="SpotifyMedia", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def drain(self, max_items: int = 16) -> list[SpotifyUpdate]:
        result: list[SpotifyUpdate] = []
        for _ in range(max(0, max_items)):
            try:
                result.append(self._updates.get_nowait())
            except Empty:
                break
        return result

    def play_pause(self) -> None:
        self._command("play_pause")

    def next(self) -> None:
        self._command("next")

    def previous(self) -> None:
        self._command("previous")

    def _command(self, value: str) -> None:
        try:
            self._commands.put_nowait(value)
        except Full:
            self._emit("error", message="Spotify controls are busy")

    def _emit(self, kind: str, **payload: Any) -> None:
        update = SpotifyUpdate(kind, payload)
        try:
            self._updates.put_nowait(update)
        except Full:
            try:
                self._updates.get_nowait()
                self._updates.put_nowait(update)
            except (Empty, Full):
                pass

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            LOGGER.warning("Spotify media service unavailable type=%s", type(exc).__name__)
            self._emit("status", available=False, state="unavailable", detail="WINDOWS MEDIA API UNAVAILABLE")

    async def _manager(self) -> Any:
        if self._manager_factory is not None:
            value = self._manager_factory()
            return await value if hasattr(value, "__await__") else value
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

        return await GlobalSystemMediaTransportControlsSessionManager.request_async()

    @staticmethod
    def _spotify_session(manager: Any) -> Any | None:
        for session in manager.get_sessions():
            identity = str(getattr(session, "source_app_user_model_id", ""))
            if "spotify" in identity.casefold():
                return session
        return None

    async def _run(self) -> None:
        manager = await self._manager()
        last_snapshot: tuple[Any, ...] | None = None
        while not self._stop.is_set():
            session = self._spotify_session(manager)
            if session is None:
                snapshot = (False, "", "", False, 0, 0)
                if snapshot != last_snapshot:
                    self._emit("status", available=False, state="not_running", title="", artist="")
                    last_snapshot = snapshot
            else:
                while True:
                    try:
                        command = self._commands.get_nowait()
                    except Empty:
                        break
                    action = {
                        "play_pause": session.try_toggle_play_pause_async,
                        "next": session.try_skip_next_async,
                        "previous": session.try_skip_previous_async,
                    }[command]
                    await action()
                properties = await session.try_get_media_properties_async()
                playback = session.get_playback_info()
                timeline = session.get_timeline_properties()
                playback_status = getattr(playback, "playback_status", None)
                try:
                    playing = int(playback_status) == 4
                except (TypeError, ValueError):
                    playing = "playing" in str(playback_status).casefold()
                position = getattr(timeline, "position", None)
                end_time = getattr(timeline, "end_time", None)
                position_ms = int(position.total_seconds() * 1000) if hasattr(position, "total_seconds") else 0
                duration_ms = int(end_time.total_seconds() * 1000) if hasattr(end_time, "total_seconds") else 0
                snapshot = (
                    True,
                    str(getattr(properties, "title", "")),
                    str(getattr(properties, "artist", "")),
                    playing,
                    position_ms,
                    duration_ms,
                )
                if snapshot != last_snapshot:
                    self._emit(
                        "status",
                        available=True,
                        state="playing" if playing else "paused",
                        title=snapshot[1],
                        artist=snapshot[2],
                        playing=playing,
                        position_ms=position_ms,
                        duration_ms=duration_ms,
                    )
                    last_snapshot = snapshot
            await asyncio.sleep(self.POLL_SECONDS)
