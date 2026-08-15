# Contributing

Thank you for improving Lausudo Streamer Console. Keep changes focused, low
overhead, privacy-preserving, and compatible with the existing stream stack.

## Development setup

```powershell
git clone https://github.com/CRSD-Lau/Lausudo-Streamer-Console.git
Set-Location -LiteralPath '.\Lausudo-Streamer-Console'
py -3.13 -m pip install -r .\requirements.txt
py -3.13 -m unittest discover -s tests -v
```

Python 3.11 and 3.13 are supported. UI tests use `QT_QPA_PLATFORM=offscreen` and
must not send global keys, interact with production services, or require a live
stream.

## Pull requests

1. Create a focused branch from `main`.
2. Add or update tests for behavior changes.
3. Update the README, changelog, and relevant docs when public behavior changes.
4. Run the full test suite and `git diff --check`.
5. Inspect the staged file list and run a secret scan before pushing.
6. Explain the user impact, security/privacy impact, and validation in the PR.

## Security and privacy rules

Never commit:

- OAuth tokens, cookies, stream keys, passwords, client secrets, or OBS credentials;
- `%LOCALAPPDATA%` runtime files, logs, browser profiles, or DPAPI blobs;
- production viewer chat, screenshots, account identifiers, or private window content;
- real webhook payloads unless fully synthetic and reviewed.

Use placeholders in fixtures. Security issues must follow [SECURITY.md](SECURITY.md)
instead of a public issue.

## Design constraints

- Keep network and service failures isolated.
- Keep retention and queues bounded.
- Do not add Electron or a browser runtime without a demonstrated need.
- Do not duplicate BRB/privacy logic inside the UI.
- Do not claim states that cannot be read through a supported interface.
- Preserve native Windows accessibility and Snap Layout behavior.
- Explain non-obvious trust-boundary decisions in code and architecture docs.

## Legal

No general license is granted by this repository. Before submitting a
contribution, ensure you have the right to provide it and that it contains no
third-party material that cannot be distributed here.
