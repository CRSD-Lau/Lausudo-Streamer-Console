# Social Stream Ninja setup

Use only the official Social Stream Ninja project and extension:

- Website: <https://socialstream.ninja/>
- Source: <https://github.com/steveseguin/social_stream>
- Official Chrome extension: <https://chromewebstore.google.com/detail/social-stream-ninja/cppibjhfemifednoimlblfcmjgfhfjeg>

## Preferred local transport

1. Start Streamer Console.
2. Open the Social Stream Ninja extension settings.
3. Enable **Send all to POST server**.
4. Set the destination to `http://127.0.0.1:17840/ingest/socialstream`.
5. Use one Social Stream Ninja collector instance only. Do not run the extension and standalone app with the same session at the same time.

## Twitch

For ordinary chat, keep the official Twitch chat or pop-out chat open with Social Stream Ninja enabled. Social Stream Ninja's native Twitch WebSocket/EventSub option can expose richer follow/sub/raid events when separately authenticated.

## TikTok LIVE

Open `https://www.tiktok.com/@lausudo/live` while the channel is live and enable Social Stream Ninja for that page. TikTok collection cannot be fully verified while the channel is offline. Region, login, CAPTCHA, rate limiting, and TikTok changes can affect availability.

Keep the chat page open and visible enough that Chromium does not discard or throttle it. Do not start a second TikTok collector, because duplicate collectors can cause duplicate messages or rate limits.

## Status meaning

With the loopback POST transport, the console can prove that its listener is ready and that messages have recently arrived from a platform. It cannot prove that an idle platform is authenticated merely because a browser tab is open. The UI therefore uses conservative states such as **Waiting for chat** until actual platform data arrives, **Receiving** after a message, and **No recent data** after 30 seconds of silence. Social Stream Ninja/browser owns upstream reconnection.
