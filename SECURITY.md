# Security policy

## Supported versions

Security fixes are applied to the latest commit on `main` and the latest tagged
release. Older snapshots are not maintained separately.

## Report a vulnerability privately

Do not open a public issue for a suspected vulnerability, leaked credential, or
privacy exposure. Use GitHub's **Report a vulnerability** flow in the Security
tab of this repository. Include:

- the affected version or commit;
- the component and expected trust boundary;
- minimal reproduction steps;
- realistic impact;
- whether any credential or private stream data may have been exposed.

If private vulnerability reporting is unavailable, contact the repository owner
through the profile contact method and include only a high-level description
until a private channel is established. Never send real tokens, cookies, stream
keys, passwords, or viewer data in an issue.

## Security boundaries

- The Social Stream HTTP listener must remain loopback-only.
- OBS WebSocket access is read-only in this application. Its password is read
  from OBS's configuration in memory and must never be persisted or logged.
- Twitch OAuth uses a public-client Device Code flow. A client secret is neither
  needed nor accepted.
- Twitch tokens must remain DPAPI-encrypted at rest and absent from logs.
- Global key emission is restricted to F1 and F2 after the expected target/helper
  processes are detected.
- Chat, request headers, cookies, stream keys, and authentication payloads must
  never enter logs, session summaries, screenshots, fixtures, or commits.
- External URLs must use HTTPS; local integrations must bind to loopback.

## Publishing checklist

Before every public release:

1. Run the full unit suite on supported Python versions.
2. Run a full-history secret scanner and inspect all findings.
3. Inspect the exact tracked file list and generated preview images.
4. Confirm examples contain placeholders only.
5. Verify dependency changes and update `THIRD_PARTY_NOTICES.md` when needed.
6. Confirm no runtime files from `%LOCALAPPDATA%`, OBS, browsers, Discord, or
   TikTok LIVE Studio are tracked.

## Out of scope

Reports about upstream Twitch, TikTok, OBS, Aitum, Social Stream Ninja, Discord,
Spotify, Qt, or Windows vulnerabilities should be sent to the relevant upstream
project unless this application creates the vulnerable behavior.
