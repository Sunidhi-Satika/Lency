"""Thread-safe in-memory state shared by the GUI thread and the assistant thread.

This replaces the old "write a .data file, poll it every few ms" IPC: no disk I/O,
no polling races, and typed input has a proper queue.
"""
import queue
import time

import threading

_status = "Available..."
_cancel = threading.Event()   # set = "stop talking / abandon this answer"
_on_stop = None               # callback registered by the speech module (cuts audio instantly)
_STOP_WORDS = {"stop", "stop it", "stop talking", "shut up", "be quiet", "quiet", "enough", "cancel", "never mind"}
_mic = False
_busy = False                 # a request is being processed / answered right now

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


_hide_hook = None             # set by the GUI: hides/shows Lency's window (for screenshots, typing into other apps)


def set_hide_hook(fn):
    global _hide_hook
    _hide_hook = fn


def hide_window(on):
    """Make Lency's own window invisible (True) or visible again (False). Safe from any thread."""
    if _hide_hook:
        try:
            _hide_hook(bool(on))
        except Exception:
            pass


_pending = None               # a question waiting for yes / no (see Backend/Confirm.py)


_expired = []


def set_pending(prompt, on_yes, on_no=None, ttl=90, on_text=None, on_drop=None):
    """Ask before doing something risky. on_yes() runs only if the user agrees within ttl seconds.
    on_text(text): the question wants a free answer (e.g. 'what should I say?') instead of yes / no.
    on_drop(): tidy-up when the question is dropped (timeout, or the user asked something else)."""
    global _pending
    _pending = {"prompt": prompt, "yes": on_yes, "no": on_no, "until": time.time() + ttl,
                "on_text": on_text, "drop": on_drop}


def get_pending():
    global _pending
    if _pending and time.time() > _pending["until"]:
        _expired.append(_pending)
        _pending = None
    return _pending


def pop_expired():
    """Questions that timed out (for the worker thread to tidy up after)."""
    out = list(_expired)
    _expired.clear()
    return out


def clear_pending():
    global _pending
    _pending = None


def set_busy(on):
    global _busy
    _busy = bool(on)


def busy():
    return _busy


def submit_text(text):
    text = (text or "").strip()
    if text.lower().strip(" .!?") in _STOP_WORDS:     # handled instantly, even while she is busy
        if _pending and text.lower().strip(" .!?") in ("cancel", "never mind", "stop", "stop it"):
            clear_pending()                           # "cancel" while she is asking = a polite no
        request_stop()
        return
    if text:
        if _busy:                                       # talking over her: she stops and listens to the new thing
            request_stop()
        _typed.put(text)


def has_text():
    return not _typed.empty()


def wait_text(timeout=0.1):
    try:
        return _typed.get(timeout=timeout)
    except queue.Empty:
        return None
