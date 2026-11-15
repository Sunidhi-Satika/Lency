"""The permission gate: anything risky (sending, deleting, wiping) is PREPARED first, then she asks.

    State.set_pending("Send this to Mom?", on_yes=do_send)      # the action to run if you agree
    ... you answer "yes" / "send it" (spoken, typed, or the Yes button) -> on_yes() runs
    ... you answer "no" / "cancel"                                       -> nothing happens
    ... you ask something else, or 90 s pass                             -> the question is dropped, nothing happens

resolve(text) is called at the start of every request; it returns the spoken result, or None if there was
no question waiting (or your message was something else).
"""
import re

from Backend import State

_YES = re.compile(r"^(?:yes|yeah|yep|yup|sure|ok|okay|alright|go ahead|do it|send it|send|confirm|confirmed|please do|"
                  r"yes please|proceed|go on|absolutely|correct|approve|approved|delete it|clear it|go for it)\b")
_NO = re.compile(r"^(?:no|nope|nah|cancel|don'?t|do not|stop|never ?mind|discard|abort|not now|leave it|dont send|"
                 r"hold on|wait)\b")


def _norm(text):
    return re.sub(r"[^a-z' ]+", " ", text.lower()).strip()


def is_yes(text):
    t = _norm(text)
    return bool(_YES.match(t)) and len(t.split()) <= 6


def is_no(text):
    t = _norm(text)
    return bool(_NO.match(t)) and len(t.split()) <= 6


def resolve(text):
    """-> None (nothing was pending / treat the text as a new request) or (spoken, full_or_None)."""
    p = State.get_pending()
    if not p:
        return None
    if p.get("on_text"):                         # "what should I say?" - any answer except no/cancel is the answer
        State.clear_pending()
        if is_no(text):
            return "Okay, never mind.", None
        res = p["on_text"](text)
        return res if isinstance(res, tuple) else (res or "Done.", None)
    if is_yes(text):
        State.clear_pending()
        res = p["yes"]()
        return res if isinstance(res, tuple) else (res or "Done.", None)
    if is_no(text):
        State.clear_pending()
        res = p["no"]() if p.get("no") else "Okay, I won't."
        return res if isinstance(res, tuple) else (res, None)
    State.clear_pending()                       # something else entirely: the question is dropped
    if p.get("drop"):
        p["drop"]()
    return None


def tidy_expired():
    """Called from the worker thread when idle: undo what a timed-out question had prepared (e.g. a typed draft)."""
    for p in State.pop_expired():
        if p.get("drop"):
            try:
                p["drop"]()
            except Exception:
                pass
