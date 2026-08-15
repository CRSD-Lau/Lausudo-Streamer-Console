# Support

Start with [Troubleshooting](docs/TROUBLESHOOTING.md) and the collector **HEALTH**
panel. Most integration problems can be isolated to Twitch authorization,
Social Stream Ninja/TikTok browser capture, OBS WebSocket, or the external F1/F2
helper.

For a reproducible application bug, open a GitHub issue with:

- Windows, Python, OBS, Aitum, and Streamer Console versions;
- the failing feature and expected behavior;
- sanitized steps to reproduce;
- relevant log lines with credentials and viewer data removed;
- whether the issue reproduces in `--simulate` mode.

Do not attach runtime configuration, browser data, OBS configuration, tokens,
cookies, stream keys, DPAPI token files, or production viewer chat. Report
security or privacy issues privately under [SECURITY.md](SECURITY.md).

Upstream service outages, TikTok login/CAPTCHA behavior, and unsupported changes
inside Twitch, TikTok, OBS, Aitum, Social Stream Ninja, Discord, Spotify, or
Windows may require resolution by the relevant upstream project.
