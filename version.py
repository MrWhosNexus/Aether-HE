"""Single source of truth for the app version + update feed.

Bump __version__ here for a release, then push a matching tag `vX.Y.Z`
(the GitHub Actions release workflow builds the Windows installer and the
Linux Flatpak bundle and publishes them as release assets). The in-app
updater (updater.py) compares this against the latest GitHub release.

Keep installer.iss (#define MyAppVersion) and the Flatpak metainfo
<release> in step with this when you bump — they're cosmetic, but tidy.
"""
__version__ = "0.1.4"

# owner/repo that releases are published under.
GITHUB_REPO = "MrWhosNexus/aether-linux-app"
