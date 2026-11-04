# Legal notice

Aether HE
Copyright (C) 2026 MrWhosNexus and the Aether HE contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See [LICENSE](LICENSE).

This program is distributed in the hope that it will be useful, but **WITHOUT
ANY WARRANTY**; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License, sections 15
(Disclaimer of Warranty) and 16 (Limitation of Liability), which apply in full.

## No affiliation, trademarks

Aether HE is an independent, community project. It is **not made, endorsed,
sponsored or supported by** Aula, SparkPlay, SayoDevice, Sonix, or any keyboard
manufacturer, nor by Microsoft, Discord, NVIDIA or GitHub.

"Aula", "WIN 60 HE", "WIN 68 HE", "MINI 60 HE PRO" and other product names are
trademarks of their respective owners. They are used here only to say which
hardware Aether works with (nominative use). No logo, artwork or branding of any
manufacturer is used or distributed.

## Interoperability, and what this repository does not contain

Aether talks to keyboards over standard USB HID. Support for each board comes
from **interoperability research**: observing the USB traffic between a
keyboard its owner bought and the manufacturer's own software, and studying how
that software behaves, so that the keyboard can be used with independent,
open software. Laws in many places expressly protect this kind of research done
for interoperability (for example 17 U.S.C. 1201(f) in the United States and
Article 6 of Directive 2009/24/EC in the European Union).

What is published here is **our own description** of the protocols (notes,
packet builders, tests) and USB captures recorded by the owners of the
hardware. This repository **does not publish**:

- any manufacturer's software, driver or web-app code (minified, deobfuscated or
  otherwise), string tables or configuration files;
- any firmware image, firmware updater or SDK;
- anything obtained by bypassing encryption, DRM or a technical protection
  measure.

Vendor reference material a maintainer studies for interoperability stays on
that maintainer's machine (the git-ignored `research/` folder) and is never
committed. Contributions must follow the same rule (see
[CONTRIBUTING.md](CONTRIBUTING.md)). If you believe something in this
repository infringes your rights, open an issue or contact the maintainer
through GitHub and it will be reviewed and, where appropriate, removed promptly.

## Use at your own risk

Aether writes settings to your keyboard's memory: lighting, key actuation,
Rapid Trigger, SOCD, key remaps, macros and calibration. Any such write can go
wrong, and a board that is new to Aether ("bring-up" or "experimental" in the
support table) has **not** been verified on real hardware. By using Aether you
accept that:

- your keyboard's settings may be changed, reset or need to be restored with the
  manufacturer's software;
- calibration, firmware-level features and anything marked experimental may
  leave a board in a state that needs recalibration or a factory reset;
- **the maintainers and contributors are not liable** for damage to hardware,
  loss of data, lost warranty, or any other loss (GPL-3.0 sections 15-16).

Aether never flashes firmware. Projects or forks that modify keyboard firmware
do so entirely at their own and their users' risk.

## Games, competitions and anti-cheat

Features such as **SOCD** (including "last input wins" / Snap Tap behaviour),
Rapid Trigger, macros, key remaps and the virtual gamepad are **prohibited or
restricted in some games, leagues and tournaments**. It is your responsibility
to check and follow the rules of the games and competitions you take part in.
The maintainers are not responsible for bans, penalties or lost accounts.

## Privacy

Aether runs locally and does not collect telemetry. See [PRIVACY.md](PRIVACY.md).

## AI assistance

Large parts of this project were written with AI assistance. See
[AI_DISCLOSURE.md](AI_DISCLOSURE.md).

## Third-party software

Aether bundles open-source components under their own licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
