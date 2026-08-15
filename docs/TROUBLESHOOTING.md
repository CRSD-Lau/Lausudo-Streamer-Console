# Troubleshooting

## Spotify shows Waiting for Spotify

Open the native Spotify app and start or pause any track once so Windows
publishes its media session. The console targets Spotify by application identity
and deliberately does not fall back to global media keys. This does not affect
the OBS Spotify source or its monitoring route.

## Twitch says authorization required after upgrading

Open INFO and connect Twitch again. Native EventSub chat adds the
`user:read:chat` permission, so Twitch requires a one-time approval refresh.
TikTok/Social Stream collection and OBS controls remain independent.

## Collector status is unclear

Open HEALTH. It distinguishes the loopback listener, native Twitch EventSub,
and the age of the most recent platform data. The recovery buttons open the
exact Twitch pop-out and TikTok LIVE pages without changing their settings.

## No chat from either platform

- Confirm Streamer Console shows its Social Stream listener as ready.
- Confirm Social Stream Ninja's POST destination is exactly `http://127.0.0.1:17840/ingest/socialstream`.
- Start the console before opening chat collection; local POST has no replay queue.
- Confirm only one Social Stream Ninja collector is using the session.

## Twitch works but TikTok does not

- TikTok must be live before a LIVE chat exists.
- Keep `https://www.tiktok.com/@lausudo/live` open and confirm the browser session is signed in if TikTok requires it.
- Check Social Stream Ninja's TikTok source mode and reconnect it once.
- Do not run duplicate TikTok connectors; this can trigger rate limits.
- CAPTCHA, region, account, and platform changes may require manual attention.

## Follow, subscription, gift, raid, or platform notices do not appear

- For Twitch follows and complete Twitch alert coverage, open **INFO** and finish the official Twitch Client ID/device-code authorization. Browser chat alone does not reliably expose new follows.
- For TikTok alerts, keep the live TikTok page and Social Stream Ninja collector active.
- Generic platform prompts, joins, likes, counters, and anonymous system cards are intentionally omitted even when collection is working.
- If the INFO panel says permissions changed, choose **CONNECT TWITCH** again and approve the current scopes.

## Twitch Stream Info cannot connect or update

- Confirm the Client ID belongs to a public Twitch application. Do not enter a client secret.
- Complete the device code in the browser before it expires.
- Title/category updates require the Twitch account that owns the channel.
- Category names use Twitch search; select the intended suggestion when names are similar.
- Removing `%LOCALAPPDATA%\NeilMitchell\StreamerConsole\twitch-auth.dat` disconnects only the console's Twitch API integration; it does not affect OBS or Twitch chat.

## Chat works but OBS is disconnected

- OBS must be running.
- OBS WebSocket must remain enabled on loopback port 4455.
- Do not put the OBS password in Streamer Console configuration. The app reads the existing local OBS configuration in memory.
- Chat remains independent while OBS reconnects.

## BRB button does nothing

- Confirm OBS and the AutoHotkey helper are running.
- Confirm the helper log exists under `%LOCALAPPDATA%\NeilMitchell\OBSPrivacyToggle`.
- Test the physical F1 key. The UI button sends that exact same key and does not own a second BRB state machine.

## Discord button does nothing

- Confirm Discord and the AutoHotkey helper are running.
- Discord's native Windows Toggle Mute shortcut is invoked inside Discord, then focus is restored.
- Discord may not display a useful mute state while disconnected from voice. The console intentionally does not guess.

## Window opens on the wrong display

- Move the window onto the 1080x1920 portrait display and close it normally;
  that display and geometry are remembered for the next launch.
- If the portrait monitor is disconnected, the app falls back to an available display instead of forcing an off-screen position.
- Reset the saved window geometry in the local configuration if the monitor arrangement changed substantially.

## Window cannot be resized or Windows 11 Snap Layouts do not appear

- Open Reader Settings and turn off **Borderless window**.
- Normal framed mode uses the native Windows resize edges and supports the Snap Layouts menu when the maximize button is hovered.
- Borderless mode intentionally removes the native frame, so native edge resizing, the maximize hover target, and Snap Layouts are unavailable in that mode.

## Close button is unavailable

- Confirm **Borderless window** is off, then restart Streamer Console after updating it.
- Normal framed mode explicitly enables Windows' native Close command; closing the window performs the normal bounded service shutdown and does not stop OBS, a stream, recording, or Virtual Camera.

## Opening from the taskbar creates a second icon

- Run `Install-StreamerConsoleShortcut.ps1` once to give the Start-menu and existing pinned shortcuts the same Windows application identity as the running console.
- Restart Streamer Console from the pinned icon. If Windows retained an older cached pin, unpin it once and pin **Streamer Console** again from the Start menu.

## Logs

Rotating diagnostic logs are under `%LOCALAPPDATA%\NeilMitchell\StreamerConsole`. Logs omit chat bodies and credentials.
