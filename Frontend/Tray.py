"""System-tray icon so Lency keeps running (and reminders keep ringing) when the window is closed,
plus an opt-in 'Start with Windows' switch."""
import os
import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction

from Backend import State

try:
    from Frontend import Theme as T
except ImportError:
    import Theme as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Lency"


# ------------------------------------------------------------------ start with Windows (HKCU, no admin)
def _launch_command():
    exe = sys.executable
    venv = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
    if os.path.exists(venv):
        exe = venv
    elif exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return f'"{exe}" "{os.path.join(ROOT, "main.py")}" --tray'


def autostart_enabled(winreg=None):
    try:
        winreg = winreg or __import__("winreg")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def set_autostart(on, winreg=None):
    winreg = winreg or __import__("winreg")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


# ------------------------------------------------------------------ the icon
class Tray(QSystemTrayIcon):
    def __init__(self, window, icon_path, name, on_quit):
        super().__init__(QIcon(icon_path), window)
        self.window = window
        self.setToolTip(f"{name} is running")

        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{ background: {T.BG_DARK}; color: {T.FG}; border: 1px solid {T.BORDER}; padding: 6px; }}
            QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
            QMenu::item:selected {{ background: {T.BG_LIGHT}; color: {T.BLUE}; }}
            QMenu::separator {{ height: 1px; background: {T.BORDER}; margin: 5px 8px; }}""")
        self.show_action = QAction(f"Open {name}", menu)
        self.show_action.triggered.connect(self.show_window)
        self.mic_action = QAction("Listening", menu, checkable=True)
        self.mic_action.triggered.connect(lambda on: State.set_mic(on))
        stop_action = QAction("Stop talking", menu)
        stop_action.triggered.connect(State.request_stop)
        self.auto_action = QAction("Start with Windows", menu, checkable=True)
        self.auto_action.triggered.connect(self._toggle_autostart)
        quit_action = QAction(f"Quit {name}", menu)
        quit_action.triggered.connect(on_quit)
        for a in (self.show_action, None, self.mic_action, stop_action, None, self.auto_action, None, quit_action):
            menu.addSeparator() if a is None else menu.addAction(a)
        menu.aboutToShow.connect(self._refresh_menu)
        self.setContextMenu(menu)
        self._menu = menu
        self.activated.connect(self._clicked)
        self.show()

    def _refresh_menu(self):
        self.mic_action.setChecked(State.mic_on())
        self.auto_action.setChecked(autostart_enabled())
        self.show_action.setText(("Hide " if self.window.isVisible() else "Open ") + self.window.windowTitle())

    def _toggle_autostart(self, on):
        try:
            set_autostart(on)
        except OSError as e:
            self.showMessage("Couldn't change startup", str(e), QSystemTrayIcon.Warning, 5000)

    def _clicked(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.window.isVisible() and self.window.isActiveWindow():
                self.window.hide()
            else:
                self.show_window()

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def toast(self, title, message, seconds=8):
        self.showMessage(title, message, QSystemTrayIcon.Information, seconds * 1000)
