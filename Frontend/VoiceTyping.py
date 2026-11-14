"""Hands-free voice input using Windows' built-in Voice Typing (Win+H).

No Chrome, no Selenium, no third-party recogniser. When the mic is on we:
  1. focus the text box and press Win+H for you,
  2. watch the text box; once you stop talking for ~1.6 s the text is submitted,
  3. press Win+H again to close dictation while Lency answers (so she can't hear herself),
  4. re-arm automatically when she has finished speaking.

Requires Windows 10/11 with  Settings > Privacy > Speech > "Online speech recognition"  turned on.
"""
import ctypes
import time

from PyQt5.QtCore import QTimer

from Backend import State

_VK_LWIN = 0x5B
_VK_H = 0x48
_KEYUP = 0x0002


def press_win_h():
    """Send the Win+H shortcut (toggles Windows Voice Typing)."""
    u = ctypes.windll.user32
    u.keybd_event(_VK_LWIN, 0, 0, 0)
    u.keybd_event(_VK_H, 0, 0, 0)
    u.keybd_event(_VK_H, 0, _KEYUP, 0)
    u.keybd_event(_VK_LWIN, 0, _KEYUP, 0)


class VoiceTyper:
    SILENCE_SUBMIT = 2.0    # seconds without new text before we send what you said
    REARM_DELAY = 1.0       # seconds of idle before re-opening dictation after an answer
    FOCUS_GRACE = 2.0       # seconds the window may lose focus before dictation is shut off

    def __init__(self, window, get_edit, press=press_win_h):
        self.window = window
        self.get_edit = get_edit        # -> the QLineEdit on the visible page
        self._press = press
        self.active = False             # is Windows voice typing believed to be open?
        self._last_text = ""
        self._last_change = 0.0
        self._idle_since = None
        self._unfocused_since = None
        self._timer = QTimer(window)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self.tick)
        self._timer.start()

    needs_focus = True      # the Win+H popup types into whatever is focused, so it needs our window in front

    def _before_tick(self):
        """Hook for subclasses."""

    # -- open / close dictation ------------------------------------------------------------
    def _start(self):
        edit = self.get_edit()
        if self.needs_focus:
            self.window.activateWindow()
            self.window.raise_()
        edit.clear()
        edit.setFocus()
        self._last_text = ""
        self._last_change = time.time()
        self.active = True
        QTimer.singleShot(200, self._press)     # let focus settle first

    def _stop(self, clear=False):
        if self.active:
            self._press()
            self.active = False
        if clear:
            self.get_edit().clear()
        self._idle_since = None
        self._unfocused_since = None

    def shutdown(self):
        self._stop(clear=True)

    # -- state machine, called every 100 ms ---------------------------------------------------
    def tick(self):
        self._before_tick()
        now = time.time()
        want = State.mic_on()
        idle = State.get_status().startswith("Available")
        focused = (not self.needs_focus) or self.window.isActiveWindow()

        if self.active:
            if not want:
                return self._stop(clear=True)
            if not idle:                         # she is thinking/answering: close dictation
                return self._stop(clear=False)
            if focused:
                self._unfocused_since = None
            else:                                # never let dictation type into another app
                self._unfocused_since = self._unfocused_since or now
                if now - self._unfocused_since > self.FOCUS_GRACE:
                    return self._stop(clear=True)
            edit = self.get_edit()
            text = edit.text()
            if text != self._last_text:
                self._last_text = text
                self._last_change = now
            elif text.strip() and now - self._last_change >= self.SILENCE_SUBMIT:
                edit.clear()
                State.set_status("Thinking...")
                State.submit_text(text)
                self._stop()
            return

        # not active: (re)arm when she's idle and our window is in front
        if want and idle and focused:
            self._idle_since = self._idle_since or now
            if now - self._idle_since >= self.REARM_DELAY:
                self._start()
        else:
            self._idle_since = None


# =============================================================================================
# Popup-free dictation: the same Windows speech engine, called directly (no Win+H window).
# =============================================================================================
class _Recognizer:
    """Windows.Media.SpeechRecognition dictation on a private asyncio thread."""

    def __init__(self):
        import asyncio
        import threading
        self._asyncio = asyncio
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self._rec = None
        self.final = []
        self.hyp = ""
        self.error = None
        self.ended = False
        self.running = False

    def text(self):
        return " ".join(self.final + ([self.hyp] if self.hyp else [])).strip()

    def _run(self, coro):
        return self._asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def _ensure(self):
        if self._rec is not None:
            return
        from winrt.windows.media.speechrecognition import (
            SpeechRecognizer, SpeechRecognitionScenario, SpeechRecognitionTopicConstraint)
        rec = SpeechRecognizer()
        rec.constraints.append(SpeechRecognitionTopicConstraint(SpeechRecognitionScenario.DICTATION, "dictation"))
        await rec.compile_constraints_async()
        rec.add_hypothesis_generated(lambda s, a: setattr(self, "hyp", a.hypothesis.text))

        def got(s, a):
            if a.result.text:
                self.final.append(a.result.text)
            self.hyp = ""
        sess = rec.continuous_recognition_session
        sess.add_result_generated(got)
        sess.add_completed(lambda s, a: setattr(self, "ended", True))
        self._rec = rec

    async def _start(self):
        try:
            await self._ensure()
            self.final, self.hyp, self.ended = [], "", False
            await self._rec.continuous_recognition_session.start_async()
            self.running = True
        except Exception as e:
            self.error = str(e)

    async def _stop(self):
        try:
            if self.running:
                self.running = False
                await self._rec.continuous_recognition_session.stop_async()
        except Exception:
            pass

    def start(self):
        self._run(self._start())

    def stop(self):
        self._run(self._stop())


class DictationTyper(VoiceTyper):
    """Same behaviour as VoiceTyper, but speech goes straight to Windows' recogniser, so no
    voice-typing popup appears. If Windows refuses (Online speech recognition switched off),
    it quietly falls back to the Win+H method."""

    def __init__(self, window, get_edit):
        self._rec = _Recognizer()
        self._mode = "api"
        self._open = False
        super().__init__(window, get_edit, press=self._toggle)

    @property
    def needs_focus(self):
        return self._mode != "api"      # direct recogniser only fills Lency's own box: works while you use other apps

    def _toggle(self):
        self._open = not self._open
        if self._mode == "api":
            self._rec.start() if self._open else self._rec.stop()
        else:
            press_win_h()

    def _before_tick(self):
        if not self.active:
            return
        if self._mode == "api":
            if self._rec.error:
                print(f"Voice: direct dictation unavailable ({self._rec.error}); falling back to Win+H.\n"
                      "       For popup-free voice turn on Settings > Privacy > Speech > Online speech recognition.")
                self._mode = "win"
                self._rec.error = None
                State.post("Lency: Voice popup mode is on. For a popup-free mic, turn on Online speech recognition "
                           "in Windows Settings > Privacy > Speech.")
                if self._open:
                    press_win_h()
                return
            if self._rec.ended and self._open:                 # Windows ends sessions after long silence
                self._rec.ended = False
                self._rec.start()
            edit = self.get_edit()
            text = self._rec.text()
            if text and edit.text() != text:
                edit.setText(text)
