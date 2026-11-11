#!/usr/bin/env python3
"""Fail a release whose tag is not `v<version.__version__>`.

The built apps report version.__version__; the updater compares THAT with the
release tag. If the two differ (tag pushed before the bump, or the bump
forgotten) every published asset is wrong:
  - macOS: the updater's staged-bundle check refuses the zip (its
    CFBundleShortVersionString is not the release tag), so no Mac can ever
    install the update;
  - Windows/Linux: the installed app still reports the old version and offers
    the same "update" again on every launch.
So the check runs once, before anything is built or published.

usage: check_release_tag.py [TAG]     (TAG, else $RELEASE_TAG)
An empty tag is a build-only run (manual dispatch without a tag): nothing is
published, so there is nothing to compare. Exit 0 = fine, 1 = mismatch.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def check(tag, version):
    """(ok, message)."""
    tag = (tag or "").strip()
    if not tag:
        return True, f"build-only run (no release tag); version.py is {version}"
    want = f"v{version}"
    if tag != want:
        return False, (f"release tag {tag!r} does not match version.py "
                       f"({version}): expected {want!r}. Bump __version__ in "
                       "version.py (or fix the tag) before releasing.")
    return True, f"release tag {tag} matches version.py"


def main(argv):
    import version
    tag = argv[1] if len(argv) > 1 else os.environ.get("RELEASE_TAG", "")
    ok, msg = check(tag, version.__version__)
    # ::error:: makes the reason the headline of a failed GitHub Actions run.
    print(msg if ok else f"::error::{msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
