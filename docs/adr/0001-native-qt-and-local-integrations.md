# ADR-0001 — Native Qt and local-first integrations

**Date**: 2026-08-15
**Status**: Accepted

## Context

The console runs beside World of Warcraft, OBS, local recording, TikTok LIVE
Studio, Voicemeeter, Discord, and Spotify. It must remain readable on a portrait
monitor without adding a large browser/Electron process or making a cloud service
responsible for stream controls and private chat data.

The production setup already has authoritative components: OBS/Aitum owns output
state, Social Stream Ninja handles TikTok browser collection, Twitch exposes
official APIs, Windows exposes Spotify media sessions, and an existing F1/F2
helper owns BRB/privacy and Discord mute.

## Decision

Use Python with PySide6/Qt Widgets for the native desktop UI. Keep each integration
behind a small bounded worker and communicate with the UI through queues/signals.
Bind Social Stream ingestion to loopback, read OBS status without modifying it,
use Twitch's public-client Device Code flow, store Twitch tokens with Windows
Credential Manager while retaining legacy DPAPI compatibility, and
delegate stream controls to the existing F1/F2 automation.

Do not bundle a browser, Electron runtime, database, maintainer backend, or second
BRB state machine. Treat unobservable states as unknown instead of inferring them
from a previous click.

## Consequences

- CPU, RAM, and rendering overhead remain low and predictable.
- Chat and account data stay on the streaming PC except for normal platform API
  traffic.
- One integration can fail without stopping unrelated UI features.
- TikTok collection remains best effort because it depends on the browser LIVE
  page and Social Stream Ninja.
- BRB and Discord buttons require the external canonical helper.
- The project is Windows-specific because it relies on Windows Credential Manager,
  legacy DPAPI compatibility, native taskbar
  identity, Win32 input, and Windows media sessions.
