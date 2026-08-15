"""Bounded, aggregate-only stream session tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping

from .config import app_data_dir


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SessionStats:
    started_at: str
    ended_at: str = ""
    twitch_messages: int = 0
    tiktok_messages: int = 0
    alerts: dict[str, int] = field(default_factory=dict)
    peak_twitch_viewers: int = 0
    peak_tiktok_viewers: int = 0
    tiktok_likes: int = 0
    tiktok_follows: int = 0
    markers: list[dict[str, Any]] = field(default_factory=list)


class SessionTracker:
    """Tracks useful totals without retaining viewer chat content."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory else app_data_dir() / "sessions"
        self._lock = threading.RLock()
        self._stats = SessionStats(started_at=_utc_now().isoformat())

    def reset(self) -> None:
        with self._lock:
            self._stats = SessionStats(started_at=_utc_now().isoformat())

    def record_message(self, message: Any) -> None:
        platform = str(getattr(message, "platform", "")).casefold()
        kind = str(getattr(message, "kind", "chat")).casefold()
        event_type = str(getattr(message, "event_type", "")).casefold()
        with self._lock:
            if "twitch" in platform:
                self._stats.twitch_messages += 1
            elif "tiktok" in platform:
                self._stats.tiktok_messages += 1
            if "event" in kind and event_type:
                self._stats.alerts[event_type] = self._stats.alerts.get(event_type, 0) + 1

    def record_metrics(self, metrics: Mapping[str, Any]) -> None:
        def integer(key: str) -> int:
            try:
                return max(0, int(metrics.get(key, 0) or 0))
            except (TypeError, ValueError):
                return 0

        with self._lock:
            self._stats.peak_twitch_viewers = max(
                self._stats.peak_twitch_viewers, integer("twitch_viewers")
            )
            self._stats.peak_tiktok_viewers = max(
                self._stats.peak_tiktok_viewers, integer("tiktok_viewers")
            )
            self._stats.tiktok_likes = integer("tiktok_likes")
            self._stats.tiktok_follows = integer("tiktok_follows")

    def add_marker(self, description: str, *, twitch_synced: bool = False) -> None:
        with self._lock:
            if len(self._stats.markers) >= 200:
                self._stats.markers.pop(0)
            self._stats.markers.append(
                {
                    "at": _utc_now().isoformat(),
                    "description": (description.strip() or "Raid moment")[:140],
                    "twitch_synced": bool(twitch_synced),
                }
            )

    def mark_latest_synced(self) -> None:
        with self._lock:
            if self._stats.markers:
                self._stats.markers[-1]["twitch_synced"] = True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            payload = asdict(self._stats)
        start = datetime.fromisoformat(payload["started_at"])
        end = datetime.fromisoformat(payload["ended_at"]) if payload["ended_at"] else _utc_now()
        payload["duration_seconds"] = max(0, int((end - start).total_seconds()))
        return payload

    def save(self, *, end: bool = False) -> Path:
        with self._lock:
            if end and not self._stats.ended_at:
                self._stats.ended_at = _utc_now().isoformat()
            payload = asdict(self._stats)
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = payload["started_at"].replace(":", "-").replace("+", "_")
        target = self.directory / f"session-{stamp}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, target)
        return target

