# Development

## Technology

- Python 3.11 and 3.13
- PySide6 / Qt Widgets
- `websockets` for OBS and Twitch EventSub
- pywinrt for Windows media-session access
- standard-library HTTP server for loopback Social Stream ingestion

The project deliberately avoids Electron, a bundled browser, a database, and a
maintainer-operated backend.

## Set up

```powershell
git clone https://github.com/CRSD-Lau/Lausudo-Streamer-Console.git
Set-Location -LiteralPath '.\Lausudo-Streamer-Console'
py -3.13 -m pip install -r .\requirements.txt
```

## Tests

```powershell
py -3.13 -m unittest discover -s tests -v
py -3.11 -m unittest discover -s tests -v
git diff --check
```

The test suite forces Qt's off-screen platform and injects process, input,
network, OBS, Twitch, and Windows-media boundaries. Tests must never send real
keys, post production messages, access browser profiles, or require OBS.

## Preview assets

```powershell
py -3.13 .\tools\render_previews.py
```

The generator renders the real Qt window off-screen with synthetic chat, alerts,
counts, scenes, and media metadata. It produces:

- `docs/images/streamer-console-preview.png` — README portrait screenshot;
- `docs/images/social-preview.png` — 1280x640 GitHub social card.

No desktop capture or production connection is used. Review generated text and
dimensions before publishing.

## Module map

| Module | Responsibility |
| --- | --- |
| `app.py` | Qt lifecycle, service coordination, timers, persistence, shutdown. |
| `ui.py` | Portrait widgets, dialogs, feed rendering, controls, Windows frame behavior. |
| `normalizer.py` | Safe text conversion, viewer-chat/event allowlist, filters, sequencing. |
| `ingest.py` | Loopback-only Social Stream HTTP receiver and bounded queue. |
| `twitch.py` | Device authorization, Windows Credential Manager token store with legacy DPAPI compatibility, Helix, EventSub chat/alerts. |
| `obs_client.py` | Read-only OBS WebSocket and Aitum status. |
| `spotify.py` | Spotify-only Windows media-session discovery and controls. |
| `controls.py` | Guarded F1/F2 Win32 key emission. |
| `session.py` | Aggregate-only stream-session totals and markers. |
| `telemetry.py` | TikTok viewer/follow/like telemetry extraction. |
| `config.py` | Typed, bounded, atomic local configuration. |

## Engineering rules

- Keep all queues, caches, logs, and retained models bounded.
- Serialize receipt-order assignment and enqueueing as one critical section.
- Keep one service failure from stopping unrelated services.
- Derive UI state from authoritative integrations; do not fabricate it.
- Keep OBS access read-only and controls delegated to the canonical F1/F2 helper.
- Treat logs, fixtures, screenshots, and errors as potential credential-exposure
  surfaces.
- Document security-relevant changes in `SECURITY.md` or architecture docs.

## Releases

1. Update versions in `pyproject.toml` and `streamer_console/__init__.py`.
2. Update `CHANGELOG.md`.
3. Run the full suite on both supported Python versions.
4. Regenerate and inspect preview assets when UI changes.
5. Run a full-history secret scan and inspect the exact tracked tree.
6. Tag the verified commit and publish release notes derived from the changelog.
