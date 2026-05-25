"""AETHER HE palette — translated from the Win60 Controller design handoff
(esports/cyberpunk dark). CustomTkinter can't do gradients/glow/blur, so these
are flat approximations of the design's tokens."""

BG0       = "#07080d"   # app background
BG1       = "#0b0d15"
BG2       = "#0f1220"   # card surface
BG3       = "#161a29"
SURFACE   = "#12141d"   # ~ white/0.025 over bg
SURFACE2  = "#171a24"
BORDER    = "#232838"   # subtle line

ACCENT      = "#9d4edd"  # hyper violet
ACCENT_SOFT = "#b377e8"
ACCENT_FG   = "#1a0833"  # text on accent
ACCENT_DIM  = "#221432"  # accent @ ~0.18 over bg (active pill bg)
ACCENT_GLOW = "#3a1f55"

CYAN   = "#00f5ff"
TEXT   = "#e6e8f0"
S300   = "#cbd5e1"
S400   = "#94a3b8"
S500   = "#64748b"

EMERALD = "#34d399"
ROSE    = "#fb7185"
AMBER   = "#ffaa1f"
BLUE    = "#3b82f6"


def blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    r = [round(a[i] + (b[i] - a[i]) * max(0.0, min(1.0, t))) for i in range(3)]
    return "#%02x%02x%02x" % tuple(r)
