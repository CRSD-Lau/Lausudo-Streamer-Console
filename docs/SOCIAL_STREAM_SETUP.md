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
6. Enable **Show viewer count per source** for the TikTok current-viewer figure.
7. Enable **Show TikTok likes in main chat/events** for the running like figure.
   The console consumes these as telemetry and does not show the raw records in
   chat.

## Twitch

F3 opens the official Twitch pop-out with Social Stream Ninja as a fallback.
Use the console's **INFO** control and one-time official Twitch authorization for
native chat, follows, subscriptions, resubs, gifted subscriptions, raids, Bits,
reward redemptions, and title/category editing. Native EventSub is primary; the
console suppresses Social Stream browser copies while EventSub chat is healthy
and accepts the browser fallback if it disconnects.

## TikTok LIVE

F3 opens `https://www.tiktok.com/@lausudo/live` in Chrome's Default profile.
Keep Social Stream Ninja enabled for that page while the channel is live. TikTok
collection cannot be fully verified while the channel is offline. Region,
login, CAPTCHA, rate limiting, and TikTok changes can affect availability.

Keep the chat page open and visible enough that Chromium does not discard or throttle it. Do not start a second TikTok collector, because duplicate collectors can cause duplicate messages or rate limits.

The TikTok viewer number is the latest value exposed by the LIVE page. **New
follows** counts named follow events received since Streamer Console launched.
**Likes** counts like activity records captured this stream; TikTok may batch
or deduplicate DOM events, so it is a useful running activity indicator rather
than an authoritative account-level total. Twitch viewers come from Twitch's
official API and refresh approximately every 15 seconds.

## Status meaning

With the loopback POST transport, the console can prove that its listener is ready and that messages have recently arrived from a platform. It cannot prove that an idle platform is authenticated merely because a browser tab is open. The UI therefore uses conservative states such as **Waiting for chat** until actual platform data arrives, **Receiving** after a message, and **No recent data** after 30 seconds of silence. Social Stream Ninja/browser owns upstream reconnection.

## What enters the feed

The console accepts Twitch/TikTok viewer chat plus named meaningful alerts: follows, subscriptions/resubs, gifted subscriptions, raids, Bits, TikTok gifts/shares, and reward redemptions where the source exposes them. It structurally drops generic system events, preview prompts, joins, likes, viewer counters, placeholders, anonymous notices, and unknown platforms. Bot, command, duplicate, and repeated-spam filtering remains optional and applies to otherwise valid viewer chat.
