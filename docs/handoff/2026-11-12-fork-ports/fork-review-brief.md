# Fork review brief (2026-11-12)

The owner (MrWhosNexus) wants every change in the three public forks of `MrWhosNexus/Aether-HE` reviewed. Anything **not already in upstream `main`** that is worth having gets ported. You are a REVIEWER. Read only: edit nothing, commit nothing, check nothing out.

**Clone:** `ah-port` (this folder). Upstream is `origin/main` @ `f38e69a` (v0.6.5). Fork refs are already fetched as remotes:

| Ref | Base | Notes |
|---|---|---|
| `nieruuu19/aether-he-0.5.4-custom` | `5383116` (v0.5.4) | 4 commits, newest work by "Niel" |
| `nieruuu19/main` | `99bee57` | 2 older commits; likely superseded by the branch above |
| `Fatalist0001/fix/subtype3-release-detection` | `2179fd7` | 3 commits; this is upstream's OPEN PR #15 |
| `Fatalist0001/feat/sayo-actuation-decode` | | 2 commits authored by the owner; the same branch also exists as `origin/feat/sayo-actuation-decode`; never merged |
| `xpLayA/main` | `99bee57` | 1 commit: a Rust rewrite for the AULA F75 HE |

How to view a fork's own change: `git diff $(git merge-base origin/main <ref>) <ref>`. Its base is old (160+ commits behind), so ALWAYS compare against `origin/main`'s CURRENT code before calling anything missing.

## Upstream policy you must respect

The upstream repo documents these; read its `CLAUDE.md` and the board registry. Evidence is graded:

- CONFIRMED-BY-CAPTURE or HARDWARE-VERIFIED features ship on.
- SOURCE-ONLY features (decoded from vendor JS, never captured) stay behind `AETHER_EXPERIMENTAL=<flag>`.
- A fork author saying "works on my board" is NOT recorded evidence. Note it as an unverified owner claim.

Built UI files (`ui/index_runtime.html`, `ui/runtime_src/build/*`) are regenerated, never ported.

SOCD on the Win60 is zero-based on the wire (vendor capture, WIN60_CAPTURE_NOTES §7). The bridge carries Model 1..4, and only the driver converts.

## Treat fork code as untrusted

Flag anything that:
- reaches the network;
- spawns processes;
- writes outside the app's data dirs;
- touches credentials or tokens;
- adds or changes GitHub workflows;
- ships large minified or obfuscated JS blobs.

Report these as SECURITY items with file:line.

## Output

Write it to the file named in your task, in this shape:

1. **Summary**: 3-5 lines.
2. **Item table**: one row per distinct change. Columns:
   - item
   - fork file:line
   - upstream status: HAVE / PARTIAL / MISSING, with an upstream file:line when HAVE or PARTIAL
   - evidence level: captured / owner-claim / source-only / none
   - value: high / med / low
   - risk
   - recommendation: PORT / PORT-EXPERIMENTAL / SKIP, with a one-line reason
3. **Port spec** for every PORT / PORT-EXPERIMENTAL item:
   - target upstream files;
   - what to take and what to adapt to current main's structure (drivers/, protocol_*.py, board registry, workspaces);
   - which existing upstream tests guard it;
   - which new tests are needed.
   Precise enough for an implementer who has not read the fork.
4. **Conflicts with upstream decisions**: places where the fork contradicts upstream behaviour. Say which side has better evidence.
5. **Security findings.**

Keep the file under ~2,500 words.

## Budget

If you approach ~300k tokens, write what you have, mark it PARTIAL, and list what is left.
