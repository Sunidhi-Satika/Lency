"""Thread-safe in-memory state shared by the GUI thread and the assistant thread.

This replaces the old "write a .data file, poll it every few ms" IPC: no disk I/O,
no polling races, and typed input has a proper queue.
"""
import queue

import threading

_status = "Available..."
_cancel = threading.Event()   # set = "stop talking / abandon this answer"
_on_stop = None               # callback registered by the speech module (cuts audio instantly)
_STOP_WORDS = {"stop", "stop it", "stop talking", "shut up", "be quiet", "quiet", "enough", "cancel", "never mind"}
_mic = False

messages = queue.Queue()   # (kind, text) lines for the GUI. kind: "live" | "history"
_typed = queue.Queue()     # text the user typed instead of speaking


def set_status(text):
    global _status
    _status = text


def get_status():
    return _status


def set_mic(on):
    global _mic
    _mic = bool(on)


def mic_on():
    return _mic


def post(text, kind="live"):
    messages.put((kind, text))


def drain():
    out = []
    while True:
        try:
            out.append(messages.get_nowait())
        except queue.Empty:
            return out


_notes = queue.Queue()     # (title, message) desktop notifications for the tray icon


def notify(title, message):
    _notes.put((title, message))


def drain_notes():
    out = []
    while True:
        try:
            out.append(_notes.get_nowait())
        except queue.Empty:
            return out


def cancelled():
    return _cancel.is_set()


def clear_cancel():
    _cancel.clear()


def set_stop_hook(fn):
    global _on_stop
    _on_stop = fn


def request_stop():
    """Stop speaking and abandon the current answer. Safe to call from any thread."""
    _cancel.set()
    if _on_stop:
        try:
            _on_stop()
        except Exception:
            pass


def submit_text(text):
    text = (text or "").strip()
    if text.lower().strip(" .!?") in _STOP_WORDS:     # handled instantly, even while she is busy
        request_stop()
        return
    if text:
        _typed.put(text)


def has_text():
    return not _typed.empty()


def wait_text(timeout=0.1):
    try:
        return _typed.get(timeout=timeout)
    except queue.Empty:
        return None
