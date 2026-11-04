# Privacy

**Short version:** Aether runs on your computer, keeps its data on your
computer, and sends nothing about you or your typing to anyone. There is no
account, no analytics, no telemetry, no ads and no AI service in the app.

This page lists everything Aether stores and every time it uses the network.
If the code ever does something this page doesn't describe, that is a bug:
please report it (see [SECURITY.md](SECURITY.md)).

## What Aether stores, and where

Everything lives in one folder:
Windows `%LOCALAPPDATA%\AetherHE`, Linux `~/.config/AetherHE`
(Flatpak: inside the app's sandbox).

| What | File | Contents |
|---|---|---|
| Settings and profiles | `settings.json` | Your lighting, actuation, SOCD, macros names, game-to-profile mapping, overlay and app preferences. |
| Key statistics | `stats/YYYY-MM-DD.json` | **Counts per key per day only**: presses, bottom-outs, a depth histogram, shallow/barely-actuated counts, summed time-to-peak. If you map games, the same counts are also kept per detected game. **Never** the order of keys, any text, or when a key was pressed. Kept 90 days, then deleted automatically. |
| Games list cache | `games/detectable.json` | Discord's public list of game executables (see below). |
| Board submissions you create | `submissions/` | Only when you use *Settings → Submit a board* (see below). |
| Log | `aether.log` (rotated) | Errors and connection events. No keystrokes, no game names. |
| Web view data | `webview/` | The app window's own browser profile (no browsing happens in it). |

Key statistics can be switched off and cleared at any time in *Settings*.
Deleting the folder removes everything Aether has stored.

### Things Aether processes but never stores

- **Live key travel** from the keyboard: used for the Travel Test, lighting
  effects and the counts above, then discarded.
- **Running programs**: game detection (Windows) compares the names of running
  programs with the games list, on your computer only. Only the matched game's
  name is used, to pick a profile and to label statistics; the list of your
  programs is never stored or sent.
- **System load** (CPU, RAM, GPU) for the status-on-keys bars.
- **Audio** for the Music effect: what your PC is playing is analysed in memory,
  a few milliseconds at a time, and never recorded.

## When Aether uses the network

| When | Where | What is sent |
|---|---|---|
| Checking for updates (on launch if you allow it, or *Check for updates*) | `api.github.com` | A standard request for the latest release of this project. |
| Installing an update | `github.com` release downloads | A file download, verified against GitHub's published SHA-256 before it runs. |
| Game detection, at most weekly | `discord.com` (public list of detectable games) | A standard request for that public list. Nothing about you or your games. |

Like any web request, these reveal your IP address to the server (GitHub or
Discord), under that company's own privacy policy. Aether adds no identifiers,
cookies or tracking.

The app's interface itself loads nothing from the internet. The optional local
service (`service/`) listens on `127.0.0.1` only and is not reachable from
other computers.

## Submitting a board

*Settings → Submit a board* is the only feature that prepares data meant to be
shared, and only you can share it:

1. Aether records, for the few seconds you choose, the **raw reports your
   keyboard sends**, plus the board's USB identity (vendor/product ID, product
   name, interface list) and the details you type in.
2. Because it records **which keys you press and when**, do not type passwords
   or anything private while capturing. The app warns you on that screen.
3. The file is saved in `submissions/`, and Aether opens a pre-filled GitHub
   issue in your browser. **You** decide whether to attach the file and post it.
   Issues on GitHub are **public**.

Captures and photos posted to the project's issues may be used to add support
for that board, and parts of them (as decoded packets) may appear in this
repository's tests and notes.

## Children

Aether is a hardware utility and does not knowingly collect data from anyone.

## Changes

Changes to this page are made in the public repository, so its history shows
every revision.
