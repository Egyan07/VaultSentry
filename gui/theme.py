# =============================================================================
#   gui/theme.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#   Dark blue theme matching PhantomEye palette
# =============================================================================

# Background layers
BG_DARK    = "#0d1b2a"   # main window background
BG_CARD    = "#1a2d42"   # card / panel background
BG_PANEL   = "#112233"   # sidebar / header
BG_HOVER   = "#1e3a5f"   # button hover

# Accent
ACCENT     = "#2a7fff"   # blue accent
ACCENT_DIM = "#1a5fcc"   # darker accent

# Status colours
OK_COLOR       = "#00c97a"   # green
WARNING_COLOR  = "#f5a623"   # amber
CRITICAL_COLOR = "#ff4444"   # red
INFO_COLOR     = "#5bc0de"   # teal/info

# Text
TEXT_PRIMARY   = "#e8f0fe"
TEXT_SECONDARY = "#8faac7"
TEXT_MUTED     = "#4a6080"

# Fonts
FONT_TITLE  = ("Consolas", 18, "bold")
FONT_H1     = ("Consolas", 13, "bold")
FONT_H2     = ("Consolas", 11, "bold")
FONT_BODY   = ("Consolas", 10)
FONT_SMALL  = ("Consolas", 9)
FONT_MONO   = ("Consolas", 9)

# Severity colours map
SEVERITY_COLORS = {
    "CRITICAL": CRITICAL_COLOR,
    "WARNING":  WARNING_COLOR,
    "OK":       OK_COLOR,
    "INFO":     INFO_COLOR,
    "NEW FILE": INFO_COLOR,
}
