# Security policy

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Report it privately through GitHub:
[**Report a vulnerability**](https://github.com/MrWhosNexus/Aether-HE/security/advisories/new).
If that link is not available, open an issue that says only "security contact
request" (no details) and the maintainer will reach out.

Include what you found, how to reproduce it, and which version you used. You
will get an acknowledgement as soon as possible; fixes ship in a new release,
and reporters are credited unless they prefer not to be.

## Supported versions

Only the **latest release** receives security fixes. The app updates itself on
launch (if you allow it) and verifies every update's SHA-256 against the
GitHub release before running it.

## In scope

- The desktop app and its updater, the local service (`service/`), the
  installer, and the repository's GitHub Actions workflows.
- Anything that lets a web page, a board submission, a contribution or another
  local program make Aether run code, write to a keyboard, read files, or send
  data off the computer.
- Any way Aether could record or leak what a user types (see
  [PRIVACY.md](PRIVACY.md)).

## How Aether is protected

- **Updates** are downloaded only from this repository's GitHub releases and
  checked against GitHub's published SHA-256; the app ignores any download
  link or checksum supplied by its own UI.
- **The app window** runs only the interface bundled with the app (no remote
  scripts, styles or fonts), and UI source may not use raw-HTML rendering
  (enforced in CI), so board names and layouts from submissions are always
  shown as plain text.
- **Board submissions and contributed code are never run** by automation. CI
  only parses contributed protocol and driver code
  ([tools/scan_contrib.py](tools/scan_contrib.py)), which rejects network,
  process, native, file and dynamic-code access. The AI board-draft bot runs
  only when a maintainer approves an issue, is bound to the issue text that
  was approved, and commits data files only.
- **Release, updater, installer and CI files** require the owner's review
  ([.github/CODEOWNERS](.github/CODEOWNERS)).
- The local service binds to `127.0.0.1` only.

Static checks are a filter in front of human review, not a sandbox. Treat
builds from forks as untrusted, and install Aether only from this repository's
releases.
