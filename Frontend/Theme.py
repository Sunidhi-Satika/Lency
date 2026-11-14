"""Single source of truth for Lency's look: the Atom One Dark palette.

Backgrounds are deliberately soft greys (not black) so contrast stays easy on the eyes.
"""

BG        = "#282c34"   # main window
BG_DARK   = "#21252b"   # top bar, panels
BG_LIGHT  = "#2c313c"   # hover / selected
BORDER    = "#3b4048"
GUTTER    = "#4b5263"
COMMENT   = "#5c6370"   # muted text
FG        = "#abb2bf"   # normal text / icons
FG_BRIGHT = "#d7dae0"

RED     = "#e06c75"
GREEN   = "#98c379"
YELLOW  = "#e5c07b"
BLUE    = "#61afef"
MAGENTA = "#c678dd"
CYAN    = "#56b6c2"
ORANGE  = "#d19a66"


def rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# Fonts (all ship with Windows 11): an editorial serif for her words, a clean variable sans for the UI
DISPLAY = "Sitka Display"
UI = "Segoe UI Variable Text"
UI_DISPLAY = "Segoe UI Variable Display"
