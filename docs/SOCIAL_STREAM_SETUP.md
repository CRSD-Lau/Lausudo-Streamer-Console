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

For ordinary chat, keep the official Twitch chat or pop-out chat open with Social Stream Ninja enabled. Social Stream Ninja may collect richer follow, subscription, raid, bits, or other event payloads when separately authenticated, but Streamer Console deliberately discards them and displays only genuine viewer chat.

## TikTok LIVE

Open `https://www.tiktok.com/@lausudo/live` while the channel is live and enable Social Stream Ninja for that page. TikTok collection cannot be fully verified while the channel is offline. Region, login, CAPTCHA, rate limiting, and TikTok changes can affect availability.

Keep the chat page open and visible enough that Chromium does not discard or throttle it. Do not start a second TikTok collector, because duplicate collectors can cause duplicate messages or rate limits.

## Status meaning

With the loopback POST transport, the console can prove that its listener is ready and that messages have recently arrived from a platform. It cannot prove that an idle platform is authenticated merely because a browser tab is open. The UI therefore uses conservative states such as **Waiting for chat** until actual platform data arrives, **Receiving** after a message, and **No recent data** after 30 seconds of silence. Social Stream Ninja/browser owns upstream reconnection.

## What enters the feed

The console accepts only Twitch or TikTok viewer-chat records containing both a username and message text. It structurally drops events, platform and system notices, counters, placeholders, and unknown-platform records before they reach the visible or retained chat model. This includes standalone follows, subscriptions, gifts, raids, bits notices, and similar Social Stream Ninja event payloads. Genuine viewer messages remain visible when they carry subscriber, cheer, donation, or badge metadata but are not source-marked as events. Bot, command, duplicate, and repeated-spam filtering remains optional and applies only to otherwise valid viewer chat.
