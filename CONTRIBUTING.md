# Contributing to Aether HE

Aether is community-driven. The goal is one secure, local, open tool for many
keyboards, built from what owners learn about their own boards. You don't need
to code to help: sending your board's data is a big contribution.

## Ways to help

1. **Submit your keyboard.** Open the
   [Add-a-keyboard form](https://github.com/MrWhosNexus/Aether-HE/issues/new?template=add-a-board.yml)
   or use *Settings → Submit a board* in the app. Photos, USB IDs, the vendor
   software you use and short captures are enough to start. The maintainer
   builds support from there. See [docs/SUBMIT_A_BOARD.md](docs/SUBMIT_A_BOARD.md).
2. **Go deep on your board.** Capture lighting, actuation, macros or any
   feature your stock software has, decode it, and contribute packet builders,
   layouts, notes and tests. Features the stock app lacks are welcome too.
3. **Test bring-up builds** on hardware you own and report what works, using
   [docs/HARDWARE_TEST_CHECKLIST.md](docs/HARDWARE_TEST_CHECKLIST.md).
4. **Fix bugs and improve the app.**

## License and sign-off (required)

Aether is licensed under **GPL-3.0-or-later** ([LICENSE](LICENSE)). By
contributing, you agree your contribution is licensed under the same terms.

Every commit must be signed off under the
[Developer Certificate of Origin 1.1](https://developercertificate.org/):
add `Signed-off-by: Your Name <you@example.com>` with `git commit -s`. The
sign-off certifies that you wrote the change or otherwise have the right to
submit it under GPL-3.0.

## Rules that protect the project and its users

**Legal**

- **No vendor code or files.** Do not commit any manufacturer's software,
  driver or web-app code (minified or deobfuscated), string tables, config
  files, firmware images, firmware updaters or SDKs. Describe what you learned
  **in your own words and your own code**. Keep vendor reference material on
  your machine (`research/` is git-ignored for this).
- **Only your own hardware and captures**, or ones the owner shared publicly
  for this purpose. Never bypass encryption, DRM or other protection measures.
- **No manufacturer logos or artwork.** Product names are fine for saying what
  hardware is supported.
- Custom-firmware work belongs in its own project. Aether does not flash or
  distribute firmware.

**Security** (enforced by CI; see
[docs/security/2026-11-04-submissions-plan.md](docs/security/2026-11-04-submissions-plan.md))

- Protocol and driver code (`protocol*.py`, `drivers/`) only builds packets and
  talks to the device object it is given: no network, no starting programs, no
  native code, no file access, no `eval`/`exec`, no dynamic attribute tricks.
  `tools/scan_contrib.py` checks this on every pull request.
- Don't commit built files (`ui/index_runtime.html`, `ui/runtime_src/build/`,
  `dist/`): CI and the maintainer build them from source.
- New drivers come with tests that use fake devices, never a real keyboard.
- Dependency, installer, updater and CI changes need the owner's review
  ([.github/CODEOWNERS](.github/CODEOWNERS)).
- Testers only get builds from this project's CI, never from a fork.

**Privacy**

- Never store or send what a user types: key order, text or per-keystroke
  times. Aggregated counts only (see [PRIVACY.md](PRIVACY.md)).
- No telemetry, analytics or new network calls without discussion.

**AI tools** are allowed: say so in the pull request and review the result
yourself ([AI_DISCLOSURE.md](AI_DISCLOSURE.md)).

## Getting set up

See the *Install* sections of the [README](README.md). Run the tests with:

```bash
python -m pytest -q -p no:cacheprovider tests/
```

and, if you changed UI source, rebuild with
`python ui/runtime_src/build_runtime.py`.

Be kind and constructive in issues and reviews.
