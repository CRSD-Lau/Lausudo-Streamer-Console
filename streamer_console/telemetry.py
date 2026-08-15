"""Small, bounded audience telemetry extracted from Social Stream records.

Telemetry is deliberately separate from the normalized chat model. TikTok
viewer and like events can therefore drive counters without re-introducing
noisy platform notices into the conversation feed.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class TelemetryUpdate:
    kind: str
    value: int
    source_id: str = ""


_FALSE_LIKE = {"", "0", "false", "none", "null", "off", "no"}
_COMPACT_NUMBER = re.compile(r"^\s*([\d,.]+)\s*([kmb])?\s*$", re.IGNORECASE)
_LIKE_COUNT = re.compile(
    r"(?:[x×]\s*(\d[\d,]*)|(\d[\d,]*)\s+likes?\b)", re.IGNORECASE
)


def extract_tiktok_telemetry(payload: Mapping[str, Any]) -> TelemetryUpdate | None:
    """Return a supported TikTok metric update from a raw SSN payload."""

    platform = str(payload.get("type", payload.get("platform", "")) or "").strip().casefold()
    if platform not in {"tiktok", "tik tok", "tt", "tiktok live"}:
        return None
    event = _event_name(payload)
    source_id = str(
        payload.get("id", payload.get("message_id", payload.get("event_id", "")))
        or ""
    ).strip()
    if event in {"viewer_update", "viewer_updates", "viewers", "viewer"}:
        value = _viewer_value(payload.get("meta"))
        return (
            TelemetryUpdate("tiktok_viewers", value, source_id)
            if value is not None
            else None
        )
    if event in {"follow", "followed", "new_follower"}:
        # A source ID or named viewer is required so generic system text cannot
        # inflate the session tally.
        identity = str(
            payload.get("userid", payload.get("chatname", payload.get("username", "")))
            or ""
        ).strip()
        return TelemetryUpdate("tiktok_follow", 1, source_id) if identity else None
    if event in {"like", "liked"}:
        return TelemetryUpdate("tiktok_like", _like_increment(payload), source_id)
    return None


def _event_name(payload: Mapping[str, Any]) -> str:
    for key in ("event", "eventType", "event_type"):
        raw = payload.get(key)
        if isinstance(raw, str):
            value = raw.strip().casefold()
            if value not in _FALSE_LIKE:
                return value
    return ""


def _viewer_value(meta: Any) -> int | None:
    if isinstance(meta, Mapping):
        for key in ("tiktok", "viewers", "viewer_count", "viewerCount", "count"):
            if key in meta:
                return _parse_count(meta[key])
        return None
    return _parse_count(meta)


def _parse_count(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    match = _COMPACT_NUMBER.match(str(value).replace(" ", ""))
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(
        (match.group(2) or "").casefold(), 1
    )
    return max(0, int(number * multiplier))


def _like_increment(payload: Mapping[str, Any]) -> int:
    # Prefer an explicit delta when a collector supplies one. TikTok's standard
    # DOM event usually has no count, in which case one captured like event is
    # one increment.
    for source in (payload, payload.get("meta")):
        if not isinstance(source, Mapping):
            continue
        for key in ("delta", "increment", "repeat_count", "repeatCount"):
            parsed = _parse_count(source.get(key))
            if parsed is not None and parsed > 0:
                return parsed
    text = str(payload.get("chatmessage", payload.get("message", "")) or "")
    match = _LIKE_COUNT.search(text)
    if match:
        return max(1, int((match.group(1) or match.group(2)).replace(",", "")))
    return 1
