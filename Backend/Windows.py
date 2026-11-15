"""Low-level Windows helpers: find windows, focus them, type into them, read browser tabs.

Lency's own window floats on top of everything, so "this window" always means the window
UNDER her (the one you were using before you talked to her), never Lency herself.
"""
import ctypes
import os
import time
from ctypes import wintypes

import psutil
import win32api
import win32con
import win32gui
import win32process

_u32 = ctypes.windll.user32
_dwm = ctypes.windll.dwmapi

BROWSERS = {"chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe", "vivaldi.exe", "arc.exe"}
_SHELL_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "Windows.UI.Core.CoreWindow",
                  "XamlExplorerHostIslandWindow"}


def _cloaked(hwnd):
    c = ctypes.c_int(0)
    try:
        _dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(c), 4)      # DWMWA_CLOAKED
    except Exception:
        return False
    return c.value != 0


def exe_of(hwnd):
    try:
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        return psutil.Process(pid).name().lower()
    except Exception:
        return ""


def top_windows(include_minimized=False):
    """Real application windows, front to back: [(hwnd, title, exe)], never Lency's own."""
    me = os.getpid()
    found = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd).strip()
        if not title or win32gui.GetClassName(hwnd) in _SHELL_CLASSES or _cloaked(hwnd):
            return True
        if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
            return True
        if win32process.GetWindowThreadProcessId(hwnd)[1] == me:
            return True
        if not include_minimized and win32gui.IsIconic(hwnd):
            return True
        found.append((hwnd, title, exe_of(hwnd)))
        return True

    win32gui.EnumWindows(cb, None)
    return found


def target_window():
    """The window you were working in before talking to Lency (None if there isn't one)."""
    wins = top_windows()
    return wins[0] if wins else None


def focus(hwnd):
    """Bring a window to the front (restoring it if minimised)."""
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        fg = win32gui.GetForegroundWindow()
        me_t = win32api.GetCurrentThreadId()
        fg_t = win32process.GetWindowThreadProcessId(fg)[0] if fg else me_t
        if fg_t != me_t:
            _u32.AttachThreadInput(me_t, fg_t, True)
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        finally:
            if fg_t != me_t:
                _u32.AttachThreadInput(me_t, fg_t, False)
    except Exception:
        return False
    time.sleep(0.25)
    return win32gui.GetForegroundWindow() == hwnd


def find_window(query):
    """Best window for a spoken name ('chrome', 'visual studio', 'whatsapp'); None if nothing fits."""
    q = query.lower().strip()
    if not q:
        return None
    wins = top_windows(include_minimized=True)
    for hwnd, title, exe in wins:                                  # exact-ish: app name
        if q == exe.replace(".exe", "") or q in exe.replace(".exe", ""):
            return hwnd, title, exe
    for hwnd, title, exe in wins:
        if q in title.lower():
            return hwnd, title, exe
    words = [w for w in q.split() if len(w) > 2]
    for hwnd, title, exe in wins:
        if words and all(w in title.lower() or w in exe for w in words):
            return hwnd, title, exe
    return None


def minimize_all():
    n = 0
    for hwnd, _t, _e in top_windows():
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        n += 1
    return n


def window_rect(hwnd):
    """Visible bounds (without the invisible resize border)."""
    r = wintypes.RECT()
    if _dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:   # DWMWA_EXTENDED_FRAME_BOUNDS
        return win32gui.GetWindowRect(hwnd)
    return r.left, r.top, r.right, r.bottom


# ------------------------------------------------------------------ typing
class _KI(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MI(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("ki", _KI), ("mi", _MI)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


_UNICODE, _KEYUP = 0x0004, 0x0002


def _send(units):
    arr = (_INPUT * len(units))(*units)
    _u32.SendInput(len(units), arr, ctypes.sizeof(_INPUT))


def _key(vk=0, scan=0, flags=0):
    return _INPUT(1, _U(ki=_KI(vk, scan, flags, 0, 0)))


def type_text(text, delay=0.004):
    """Type any text (any language, emoji) into whatever has focus, as real key presses."""
    for ch in text.replace("\r\n", "\n"):
        if ch == "\n":
            _send([_key(0x0D), _key(0x0D, 0, _KEYUP)])
        elif ch == "\t":
            _send([_key(0x09), _key(0x09, 0, _KEYUP)])
        else:
            data = ch.encode("utf-16-le")
            for i in range(0, len(data), 2):
                unit = int.from_bytes(data[i:i + 2], "little")
                _send([_key(0, unit, _UNICODE), _key(0, unit, _UNICODE | _KEYUP)])
        time.sleep(delay)


def press(combo):
    """'ctrl+t', 'enter', 'windows+left' ..."""
    import keyboard
    keyboard.send(combo)


# ------------------------------------------------------------------ browser tabs (UI Automation)
def browser_tabs():
    """[(hwnd, tab_title, control)] for every tab of every open browser window."""
    import uiautomation as auto
    out = []
    for hwnd, _title, exe in top_windows(include_minimized=True):
        if exe not in BROWSERS:
            continue
        try:
            root = auto.ControlFromHandle(hwnd)
            for ctl, _depth in auto.WalkControl(root, includeTop=False, maxDepth=9):
                if ctl.ControlTypeName == "TabItemControl" and ctl.Name:
                    out.append((hwnd, ctl.Name, ctl))
        except Exception:
            continue
    return out


def select_tab(hwnd, ctl):
    focus(hwnd)
    try:
        ctl.GetSelectionItemPattern().Select()
        return True
    except Exception:
        pass
    try:
        ctl.GetInvokePattern().Invoke()
        return True
    except Exception:
        pass
    try:
        ctl.Click(simulateMove=False)
        return True
    except Exception:
        return False


def com_thread():
    """Context manager so UI Automation works on a background thread."""
    import uiautomation as auto
    return auto.UIAutomationInitializerInThread()


def last_browser():
    for hwnd, title, exe in top_windows():
        if exe in BROWSERS:
            return hwnd, title, exe
    return None
