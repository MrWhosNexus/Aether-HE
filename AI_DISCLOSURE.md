# AI disclosure

Aether HE is built with substantial help from AI tools. This page says how,
so you can judge the software with that in mind.

## How AI is used to build Aether

- **Code, tests and documentation.** Much of the application code, its test
  suite and its documentation was drafted by AI coding assistants (primarily
  Anthropic's Claude, through Claude Code), working under the maintainer's
  direction. Commits written this way carry a `Co-Authored-By:` line naming the
  model.
- **Protocol research.** AI assistants help analyse USB captures and other
  interoperability research material (see [NOTICE.md](NOTICE.md)) and draft the
  notes and packet builders that come out of it.
- **Reviews.** AI reviewers are used, alongside the maintainer, to look for
  bugs and security problems before changes ship.
- **Board-draft bot.** When a maintainer explicitly approves it (the
  `bot-draft` label), a GitHub Actions workflow sends a public board-submission
  issue to an AI model (MiniMax) to draft a registry entry and layout. Those
  drafts are labelled *AI-drafted, experimental, unverified*, commit data files
  only, and are never merged automatically.

## What humans are responsible for

A human maintainer decides what is built, directs and reviews the work, tests
releases on real hardware before publishing them, and makes every release. Support for a keyboard is only marked
*supported* after it has been tested on the physical keyboard; everything else
is labelled *bring-up*, *experimental* or *planned*, and claims in the code and
registry carry a provenance tag (`HARDWARE-VERIFIED`, `CONFIRMED-BY-CAPTURE`,
`SOURCE-ONLY`).

## What AI does **not** do

- **No AI runs inside the app.** Aether contains no AI model and calls no AI
  service. Nothing you do in the app, and none of your data, is sent to an AI
  provider. (Typing statistics and actuation suggestions are plain arithmetic
  done on your computer.)
- AI tools are not given your settings, statistics or any user's data. Public
  issue content is processed by the board-draft bot only as described above.

## Limits

AI-generated code and text can be wrong in ways that look convincing. The test
suite, the review process and hardware testing reduce that risk; they do not
remove it. This is part of why Aether comes with **no warranty** (GPL-3.0,
sections 15-16; see [NOTICE.md](NOTICE.md)). Please report anything that looks
wrong.

In some jurisdictions, purely AI-generated material may not be protected by
copyright. The project is licensed under GPL-3.0 to the full extent that
copyright applies to it.

## Contributors

You may use AI tools for contributions. If you do, say so in your pull request,
review the result yourself, and make sure you have the right to submit it under
GPL-3.0 (your DCO sign-off certifies this; see
[CONTRIBUTING.md](CONTRIBUTING.md)). Do not paste vendor code into an AI tool
and submit what comes out.
