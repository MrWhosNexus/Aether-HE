# In-App Board Submission — Design (sub-project A)

**Date:** 2026-07-05
**Status:** Approved (design), pending spec review → implementation plan
**Relationship:** Part 1 of 2. **A** = in-app "Submit your board" (this doc). **B** =
owner-side MiniMax automation that turns a submission into a review-ready PR (separate
spec). The **submission JSON file is the contract** between A and B.

## Goal

Let a user with an unsupported keyboard submit it **from inside AetherHE** — the app
detects the device, captures what it safely can, and hands off a structured submission —
so the (separate) owner-side MiniMax automation can draft board support for human review.

## Locked decisions (from brainstorm)

1. **Transport = GitHub issue as the queue.** The app captures data, writes a submission
   file, and opens a PRE-FILLED add-a-board GitHub issue in the browser; the user submits
   under their own GitHub account and attaches the file. B watches new issues. No server
   to host, no secrets in the app.
2. **Capture = guided traffic + size template.** Identity + HID descriptor + guided INPUT
   report capture + a size template pick (60/65/75/TKL).
3. **Output side = auto input + optional pcap.** The app auto-captures identity +
   descriptor + INPUT reports + size (zero extra tools). For OUTPUT/lighting commands
   (which a userspace HID app cannot read — they're what the vendor app writes), the app
   shows a short OPTIONAL guide to record a USBPcap file the user attaches. B drafts
   input-parsing + layout + registry always; lighting protocol only if a pcap is attached,
   else flags it for human RE.

## Key-security constraint (non-negotiable)

- **Never inject the MiniMax key into the frontend or the app bundle.** The React UI
  (`ui/runtime_src/**`, compiled into `index_runtime.html`), the Python client, and the
  PyInstaller bundle carry **no key**. A tech-savvy user inspecting network traffic or
  reverse-engineering the app must find nothing to extract — because there is nothing:
  **A makes zero MiniMax calls.**
- The key exists **only in B** (owner-side automation), read from a local env var /
  gitignored config on the maintainer's machine, never committed, never shipped.
- The A→B handoff is **public GitHub issues** — a one-way, key-free channel. A never
  calls MiniMax directly, so there is no client-side request that could carry, cache, or
  leak the key.
- The submission file MUST contain no secrets — only device/board data the user consents
  to share (it lands on a public issue).

## Technical reality that shapes capture (why §3 above)

Via `hidapi` the app can read **INPUT** reports (what the board sends: keypresses,
travel/actuation telemetry) but cannot observe **OUTPUT** reports (lighting/config writes
the vendor app sends) — those require USB bus sniffing (USBPcap/Wireshark). So in-app
auto-capture covers identity + descriptor + input; output/lighting is an optional attached
pcap.

## Flow & entry points

Entry points:
- Setup-wizard board-selection step: "My board isn't listed → **Submit it**".
- Settings → "**Submit a board**".
- Auto-offer when an unknown HE-like HID device is detected (not the supported Aula).

Steps (dedicated modal/wizard, reuses the glass/widget styling):
1. **Detect** — `list_hid_devices()`; user picks their board (auto-highlight the unknown
   non-Aula device). Capture VID/PID, manufacturer/product strings, usage_page, HID
   descriptor, interface list.
2. **Metadata** — brand & exact model, switch type, form factor, size (60/65/75/TKL).
3. **Consent + guided input capture** — a consent line ("record HID input from <device>")
   then guided prompts ("press every key once", "press a few keys slowly for travel").
   `open_capture → read_capture (stream) → stop_capture` records raw input reports with
   millisecond timestamps; UI shows keys-seen / report count progress.
4. **(Optional) lighting** — a collapsible guide to record a USBPcap capture; user picks
   the `.pcapng` path to reference (path noted in the submission; the file is attached by
   the user on the GitHub issue).
5. **Submit** — `save_submission(json)` writes the file to disk (returns path); the app
   opens the pre-filled add-a-board issue URL (brand/model/switch/form/VID:PID filled from
   captured data) with clear "attach the saved file" instructions.

## Submission file — the A↔B contract

Path: `%LOCALAPPDATA%\AetherHE\submissions\board-<slug>-<timestamp>.json`.

```json
{
  "schema": "aether-board-submission/1",
  "submitted_at": "2026-07-05T16:40:00Z",
  "app_version": "0.2.0",
  "device": {
    "vid": "0x2E3C", "pid": "0xC365",
    "manufacturer": "…", "product": "…",
    "usage_page": "0xFF1B",
    "hid_descriptor_b64": "…",
    "interfaces": [ { "interface_number": 2, "usage_page": "0xFF1B", "usage": 1 } ]
  },
  "meta": {
    "brand": "…", "model": "…",
    "switch_type": "Hall-effect|Mechanical|…",
    "form_factor": "…", "size": "60|65|75|tkl"
  },
  "size_template": "generic-60",
  "input_capture": {
    "duration_ms": 12000,
    "report_len": 64,
    "reports": [ { "t": 12, "hex": "01a2…" } ],
    "keys_seen": 61
  },
  "output_pcap": { "attached": false, "filename": null },
  "notes": "user free text"
}
```

A JSON Schema for `aether-board-submission/1` is committed under `tools/` so both A
(validate before save) and B (validate on ingest) share one definition.

## New backend surface (adds backend — outside the "frozen" UI goal; a deliberate, scoped exception)

New `Api` methods in `app_web.py`, all UI-triggered:
- `list_hid_devices()` → `[{vid,pid,manufacturer,product,usage_page,interface_number}]`
  from `hid.enumerate()`.
- `open_capture(vid, pid, interface_number)` → opens that device **read-only**; returns ok.
- `read_capture()` → returns buffered raw input reports since last call (hex + t).
- `stop_capture()` → closes the capture device.
- `save_submission(obj)` → validates against the schema, writes the file, returns the path.
- `open_url(url)` → opens the pre-filled issue in the default browser (reuse existing
  reveal/updater URL-open if present).

**Safety:** capture is **read-only** — the app never sends output reports to an unknown
device, so it cannot misconfigure a board it lacks a verified protocol for. Capture opens
a separate handle and never touches the connected/known Aula session.

## Safety, consent, non-goals

- Consent screen before any capture; capture is read-only; user can cancel anytime.
- **Non-goals (v1):** no in-app key-by-key layout builder (size-template only); no auto-
  writing of protocol; no marking a board "supported" (that's B's human-verify gate).
  Submitted boards surface as "submitted — pending review".
- The app never uploads anything itself — the user submits via their own GitHub account
  (transparent, no client secrets, no abuse surface for the project).

## Testing

- Schema-validate the submission JSON (valid + rejects malformed).
- Dry-run: run the capture flow against the **known Aula board**, produce a submission
  file, and assert it validates + contains input reports + descriptor + metadata.
- Confirm the pre-filled issue URL opens with metadata populated.
- Confirm `open_capture` is read-only (no writes issued) and does not disturb an active
  connected session.

## Decomposition note

B (owner-side MiniMax automation) is a separate spec: it watches new add-a-board issues,
pulls the attached submission file, runs MiniMax (owner-side key) to draft the
`board_registry` entry + `ui/layouts/*.json` (refined from the size template) + a
best-effort input-protocol adapter (+ lighting only if a pcap is attached), and opens a
PR that a human verifies on hardware before merge. A does not depend on B to be built or
shipped — a submission is useful to a human reviewer even before B exists.
