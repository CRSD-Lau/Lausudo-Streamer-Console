# Changelog

All notable changes to Lausudo Streamer Console are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] — 2026-08-15

### Added

- One receipt-ordered Twitch and TikTok LIVE viewer feed with bounded retention.
- Meaningful follow, subscription, gift, raid, Bits, reward, and share alerts.
- Twitch Helix Stream Info, EventSub chat/alerts, viewer count, and stream markers.
- TikTok viewer, new-follow, and like activity counters from Social Stream Ninja.
- Read-only OBS WebSocket and Aitum vertical-canvas status.
- Shared F1 BRB/privacy and F2 Discord-mute controls.
- Windows Spotify media-session controls and metadata.
- Native portrait-window placement, resizing, Windows 11 Snap Layouts, application
  identity, taskbar icon, and shortcut installer.
- Aggregate-only stream session summaries and bounded rotating logs.

### Security

- Loopback-only Social Stream ingestion with request-size limits and JSON validation.
- DPAPI encryption for Twitch tokens.
- Credential redaction and no chat-body logging.
- Evidence-based BRB privacy status covering microphone monitoring and Spotify routing.

[1.0.0]: https://github.com/CRSD-Lau/Lausudo-Streamer-Console/releases/tag/v1.0.0
