"""WhatsApp Web and Gmail by voice - she DRAFTS, you APPROVE, only then it is sent.

  "message Mom saying I'll be late"        -> types exactly that in Mom's WhatsApp chat, shows it, asks, sends on "yes"
  "message Raj asking if he's free today"  -> she writes the message (you see it first)
  "email Raj about the meeting tomorrow"   -> Gmail compose window filled in, she asks, presses Send on "yes"

Safety, in order:  nothing is ever sent without your "yes" | the real chat name is read from the page and shown to you
| on "yes" she re-checks that the same chat / the same draft is still on screen, else she does NOT send
| "no" (or asking something else) removes the draft.
It uses your own logged-in browser through Windows accessibility, so there is no password or API key anywhere.

Names -> people:  Data/contacts.json  {"mom": {"whatsapp": "Mummy", "email": "mom@gmail.com"}}   (optional;
unknown names are searched in WhatsApp as spoken, and she asks for an email address when she needs one).
"""
import difflib
import json
import os
import re
import time
from urllib.parse import quote

from Backend import State, Web
from Backend import Windows as W

CONTACTS = os.path.join("Data", "contacts.json")

# ------------------------------------------------------------------ understanding the sentence
_VERBATIM = {"saying", "says", "that", "say"}
_CONN = r"(?P<conn>saying|says|say|that|asking|ask|to ask|about|regarding|wishing|telling|to tell|to say)"
_WA = [
    re.compile(r"^(?:please )?(?:send|write|drop|shoot)?(?: an?| the)? ?(?:whats ?app |wa )?(?:message|msg)(?: to)? (?P<to>.+?)(?: on whats ?app)? " + _CONN + r"(?: that)? (?P<body>.+)$", re.I),
    re.compile(r"^(?:send|write|drop|shoot) (?P<to>.+?) (?:an? )?(?:whats ?app )?(?:message|msg|text) " + _CONN + r"(?: that)? (?P<body>.+)$", re.I),
    re.compile(r"^(?:whats ?app|msg) (?P<to>[\w' ]{1,30}?) " + _CONN + r"(?: that)? (?P<body>.+)$", re.I),
    re.compile(r"^text (?P<to>[\w']{1,20}) " + _CONN + r"(?: that)? (?P<body>.+)$", re.I),
    re.compile(r"^tell (?P<to>(?!me\b|the\b|us\b|everyone\b)[\w' ]{1,30}?) (?P<conn>that|to)(?: that)? (?P<body>.+)$", re.I),
]
_WA_NOBODY = re.compile(r"^(?:please )?(?:send )?(?:a )?(?:whats ?app |wa )?(?:message|msg)(?: to)? (?P<to>[\w']{1,20}(?: [\w']{1,20})?)$|^whats ?app (?P<to2>[\w']{1,20})$", re.I)
_MAIL = [
    re.compile(r"^(?:please )?(?:send|write|draft|compose|shoot)?(?: an?| the)? ?(?:e-?mail|mail)(?: to)? (?P<to>.+?) (?:with subject (?P<subj>.+?) )?" + _CONN + r"(?: that)? (?P<body>.+)$", re.I),
    re.compile(r"^(?:send|write|draft|compose|shoot) (?P<to>.+?) (?:an? )?(?:e-?mail|mail) " + _CONN + r"(?: that)? (?P<body>.+)$", re.I),
    re.compile(r"^(?:e-?mail|mail) (?P<to>.+?) " + _CONN + r"(?: that)? (?P<body>.+)$", re.I),
]
_SAVE = re.compile(r"^(?:save|set|add|store)(?: that)? (?P<who>[\w' ]+?)(?:'s| s) (?P<what>e-?mail|mail|whats ?app(?: name)?|chat name) (?:as|is|to) (?P<val>.+)$", re.I)
_OPEN_ONLY = re.compile(r"^(?:open|show)\b", re.I)

_INBOX = re.compile(r"^(?:(?:open|check|show|go to|read|see|view|look at)(?: me)?(?: all)?(?: my| the)? ?)?(?:e-?mails?|mail|inbox|gmail)(?: inbox)?$", re.I)
_BROWSERS = W.BROWSERS                                               # any browser the system knows


def _clean(text):
    t = re.sub(r"\s+", " ", text.strip()).strip(" .!?,")
    return re.sub(r"^(?:(?:can|could|would|will) you |please |hey |lency |ok |okay )+", "", t, flags=re.I)


def parse(text):
    t = _clean(text)
    if not t:
        return None
    m = _INBOX.match(t)
    if m and (len(t.split()) <= 6):                               # "open my inbox", "check my email"
        return {"kind": "inbox"}
    if _OPEN_ONLY.match(t):
        return None
    m = _SAVE.match(t)
    if m:
        return {"kind": "save", "who": m.group("who"), "what": m.group("what").lower(), "val": m.group("val").strip(" .")}
    for rx in _MAIL:
        m = rx.match(t)
        if m:
            d = m.groupdict()
            return {"kind": "mail", "to": d["to"].strip(), "conn": d["conn"].lower(), "body": d["body"].strip(),
                    "subject": (d.get("subj") or "").strip()}
    for rx in _WA:
        m = rx.match(t)
        if m:
            d = m.groupdict()
            return {"kind": "wa", "to": d["to"].strip(), "conn": d["conn"].lower(), "body": d["body"].strip()}
    m = _WA_NOBODY.match(t)
    if m:
        return {"kind": "wa", "to": (m.group("to") or m.group("to2")).strip(), "conn": "", "body": ""}
    return None


def match(text):
    try:
        return parse(text) is not None
    except Exception:
        return False


# ------------------------------------------------------------------ contacts
def _load():
    try:
        with open(CONTACTS, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs("Data", exist_ok=True)
    with open(CONTACTS, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def contact(name):
    return _load().get(name.lower().strip(), {})


def _title(name):
    return " ".join(w.capitalize() for w in name.split())


def _email_from_speech(text):
    """'raj at gmail dot com' / 'raj@gmail.com' -> raj@gmail.com (None if it isn't an address)."""
    t = text.lower().strip(" .")
    t = re.sub(r"\s+at the rate(?: of)?\s+|\s+at\s+(?=\S+\s+dot\s+)", "@", t)
    t = re.sub(r"\s+dot\s+", ".", t)
    t = re.sub(r"\s*@\s*", "@", t).replace(" ", "")
    return t if re.fullmatch(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", t) else None


def _save_contact(d):
    who, what, val = d["who"].lower().strip(), d["what"], d["val"]
    data = _load()
    entry = data.setdefault(who, {})
    if what in ("email", "e-mail", "mail"):
        addr = _email_from_speech(val)
        if not addr:
            return "That doesn't look like an email address. Say it like, raj at gmail dot com."
        entry["email"] = addr
        msg = f"Saved {_title(who)}'s email."
    else:
        entry["whatsapp"] = val
        msg = f"Okay, when you say {_title(who)} I'll look for {val} in WhatsApp."
    _save(data)
    return msg


# ------------------------------------------------------------------ drafting
def _llm(system, user, **kw):
    from Backend.LLM import complete, clean
    return clean(complete([{"role": "system", "content": system}, {"role": "user", "content": user}], **kw)).strip()


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def _draft_wa(to, conn, body):
    if conn in _VERBATIM:
        return _cap(body)                                  # her words, untouched
    try:
        from Backend.LLM import Username
        out = _llm(f"Write the WhatsApp message {Username} will send to {to}. They want to: {conn} {body}. "
                   "Casual, natural, one or two short sentences, written in first person as the sender. "
                   "No quotes, no preface, no emojis unless it clearly fits. Output only the message.",
                   f"{conn} {body}", temperature=0.6, max_tokens=120)
        return out.strip('"') or _cap(body)
    except Exception:
        return _cap(body)


def _draft_mail(to_name, conn, body, subject):
    from Backend.LLM import Username
    try:
        raw = _llm(f"Write a short, polite email from {Username} to {to_name}. The topic or message: {conn} {body}. "
                   f"Reply ONLY with JSON: {{\"subject\": \"...\", \"body\": \"...\"}}. Body: a greeting using the "
                   f"recipient's first name, two to four short sentences, a friendly sign-off, then the name {Username}. "
                   "Plain text, use \\n for line breaks.", f"{conn} {body}", temperature=0.5, max_tokens=400)
        j = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        return (subject or j.get("subject") or _cap(body)[:60]).strip(), j.get("body", "").replace("\\n", "\n").strip()
    except Exception:
        first = to_name.split()[0].capitalize()
        return (subject or _cap(body)[:60]), f"Hi {first},\n\n{_cap(body)}\n\nThanks,\n{Username}"


# ------------------------------------------------------------------ page helpers (UI Automation)
_cur = {"hwnd": None}                 # the browser window whose tab was last brought forward


def _walk(root, pred, min_depth=10):
    import uiautomation as auto
    for ctl, depth in auto.WalkControl(root, includeTop=False, maxDepth=40):
        if depth > min_depth and pred(ctl):
            return ctl
    return None


def _root():
    import uiautomation as auto
    hwnd = _cur["hwnd"]
    if not hwnd:
        hit = next((w for w in W.top_windows() if w[2] in _BROWSERS), None)
        hwnd = hit[0] if hit else None
    return (hwnd, auto.ControlFromHandle(hwnd)) if hwnd else (None, None)


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _value(ctl):
    try:
        return ctl.GetValuePattern().Value
    except Exception:
        return ""


def _show_tab(word, exact_start=False, exes=None, must_contain=None):
    """Bring the browser tab whose title matches to the front (only in the given browsers). -> True/False"""
    for hwnd, title, ctl in W.browser_tabs():
        if exes and W.exe_of(hwnd) not in exes:
            continue
        t = title.lower()
        if not (t.startswith(word.lower()) if exact_start else word.lower() in t):
            continue
        if must_contain and must_contain.lower() not in t:
            continue
        if W.select_tab(hwnd, ctl):
            _cur["hwnd"] = hwnd
            return True
    return False


def _wait(fn, seconds, every=1.0):
    end = time.time() + seconds
    while time.time() < end:
        r = fn()
        if r:
            return r
        time.sleep(every)
    return None


# ------------------------------------------------------------------ WhatsApp (WhatsApp Web in your default browser)
def _wa_ready():
    """Front the WhatsApp tab (opening it if needed). -> (root, error_text)"""
    if not _show_tab("whatsapp", exes=_BROWSERS):
        Web.open_url("https://web.whatsapp.com")
        _wait(lambda: _show_tab("whatsapp", exes=_BROWSERS), 20, 1.0)

    def ready():
        _h, root = _root()
        if root is None:
            return None
        return root if _search_box(root) else None

    root = _wait(ready, 40, 1.5)
    if root:
        return root, None
    return None, "WhatsApp Web isn't ready. Check that it's logged in in your browser, then ask me again."


def _search_box(root):
    """WhatsApp's chat-search box. Its accessible name comes and goes, so: by name if present, else the page's other edit field."""
    import uiautomation as auto
    nameless = None
    for ctl, depth in auto.WalkControl(root, includeTop=False, maxDepth=40):
        if depth > 10 and ctl.ControlTypeName == "EditControl":
            n = (ctl.Name or "").lower()
            if "search" in n:
                return ctl
            if not n.startswith("type a message") and nameless is None and not n.startswith("address"):
                nameless = ctl
    return nameless


def _compose_box(root, chat_name=None):
    def pred(c):
        n = c.Name or ""
        return c.ControlTypeName == "EditControl" and n.lower().startswith("type a message") and \
            (chat_name is None or n == "Type a message to " + chat_name)
    return _walk(root, pred)


def _wa_clear(chat_name):
    try:
        with W.com_thread():
            if not _show_tab("whatsapp", exes=_BROWSERS):
                return
            _h, root = _root()
            box = _compose_box(root, chat_name)
            if box:
                box.SetFocus()
                box.SendKeys("{Ctrl}a{Delete}", waitTime=0.1)
    except Exception:
        pass


def _wa_send(chat_name, text):
    try:
        with W.com_thread():
            if not _show_tab("whatsapp", exes=_BROWSERS):
                return "I couldn't find the WhatsApp tab any more, so I didn't send anything."
            time.sleep(0.4)
            _h, root = _root()
            box = _compose_box(root, chat_name)
            if not box:
                return "The chat changed, so I didn't send anything."
            if _norm(text[:25]) not in _norm(_value(box)):
                return "The draft isn't in the box any more, so I didn't send anything."
            btn = _walk(root, lambda c: c.ControlTypeName == "ButtonControl" and (c.Name or "") == "Send")
            if not btn:
                return "I couldn't find WhatsApp's send button. Nothing was sent."
            btn.GetInvokePattern().Invoke()
            time.sleep(1.3)
            left = _norm(_value(_compose_box(root, chat_name)))
            return f"Sent to {chat_name}." if _norm(text[:25]) not in left else \
                "I pressed send, but I can't confirm it went. Please check WhatsApp."
    except Exception as e:
        print(f"WhatsApp send error: {e!r}")
        return "Something went wrong, so I'm not sure it was sent. Please check WhatsApp."


def _whatsapp(d):
    spoken_name = d["to"]
    entry = contact(spoken_name)
    search_name = entry.get("whatsapp") or _title(spoken_name)

    if not d["body"]:
        def got_text(t):
            return _whatsapp({"to": spoken_name, "conn": "saying", "body": t.strip()})
        State.set_pending(f"What should I say to {_title(spoken_name)}?", on_yes=lambda: "", on_text=got_text)
        return f"What should I say to {_title(spoken_name)}?", None

    text = _draft_wa(spoken_name, d["conn"], d["body"])
    try:
        with W.com_thread():
            root, err = _wa_ready()
            if err:
                return err, None
            search = _search_box(root)
            search.SetFocus()
            time.sleep(0.3)
            W.press("ctrl+a")
            W.type_text(search_name)
            time.sleep(1.7)
            W.press("enter")
            time.sleep(1.8)
            box = _compose_box(root)
            if not box:
                W.press("esc")
                return f"I couldn't find a WhatsApp chat for {_title(spoken_name)}.", None
            chat_name = (box.Name or "")[len("Type a message to "):].strip() or search_name
            box.SetFocus()
            time.sleep(0.2)
            lines = text.split("\n")
            for i, line in enumerate(lines):
                W.type_text(line)
                if i < len(lines) - 1:
                    W.press("shift+enter")
            time.sleep(0.6)
            if _norm(text[:25]) not in _norm(_value(box)):
                box.SendKeys("{Ctrl}a{Delete}", waitTime=0.1)
                return "I couldn't type into the chat properly, so I stopped. Nothing was sent.", None
    except Exception as e:
        print(f"WhatsApp draft error: {e!r}")
        return "WhatsApp wouldn't cooperate, so I stopped. Nothing was sent.", None

    mismatch = difflib.SequenceMatcher(None, _norm(search_name), _norm(chat_name)).ratio() < 0.55 and \
        _norm(search_name) not in _norm(chat_name)
    warn = f" (careful, you said {_title(spoken_name)})" if mismatch else ""
    State.set_pending(f"Send to {chat_name}?{warn}", on_yes=lambda: _wa_send(chat_name, text),
                      on_no=lambda: (_wa_clear(chat_name), "Okay, I cleared the draft.")[1],
                      on_drop=lambda: _wa_clear(chat_name))
    spoken = f"Here's what I typed for {chat_name}: {text}. Shall I send it?"
    return spoken, f"WhatsApp draft for {chat_name}:\n{text}"


# ------------------------------------------------------------------ Gmail (in your default browser, signed in to Gmail)
def _mail_url(tail):
    return "https://mail.google.com/mail/?" + tail


def _mail_select():
    """Front the Gmail compose tab. -> root or None"""
    if not _show_tab("compose mail", exact_start=True, exes=_BROWSERS):
        return None
    time.sleep(0.5)
    return _root()[1]


def _mail_discard():
    try:
        with W.com_thread():
            root = _mail_select()
            if root is None:
                return
            btn = _walk(root, lambda c: c.ControlTypeName == "ButtonControl" and (c.Name or "").startswith("Discard draft"))
            if btn:
                btn.GetInvokePattern().Invoke()
                time.sleep(1.2)
                if _show_tab("compose mail", exact_start=True, exes=_BROWSERS):
                    W.press("ctrl+w")
    except Exception:
        pass


def _mail_send(subject):
    try:
        with W.com_thread():
            root = _mail_select()
            if root is None:
                return "I couldn't find the email draft any more, so I didn't send anything."
            sub = _walk(root, lambda c: c.ControlTypeName == "EditControl" and (c.Name or "") == "Subject")
            if not sub or _norm(subject[:20]) not in _norm(_value(sub)):
                return "The email on screen isn't the one I wrote, so I didn't send it."
            btn = _walk(root, lambda c: c.ControlTypeName == "ButtonControl" and (c.Name or "").startswith("Send")
                        and "options" not in (c.Name or "").lower())
            if not btn:
                return "I couldn't find Gmail's send button. Nothing was sent."
            btn.GetInvokePattern().Invoke()
            time.sleep(2.5)
            still = any(t[1].startswith("Compose Mail") for t in W.browser_tabs())
            return "Email sent." if not still else "I pressed send, but the draft is still open. Please check Gmail."
    except Exception as e:
        print(f"Gmail send error: {e!r}")
        return "Something went wrong, so I'm not sure it was sent. Please check Gmail."


def _inbox(d):
    Web.open_url(_mail_url("tab=rm&ogbl#inbox"))
    return "Opening your inbox.", None


def _email(d):
    to = d["to"]
    entry = contact(to)
    addr = entry.get("email") or _email_from_speech(to)
    if not addr:
        def got_addr(t):
            a = _email_from_speech(t)
            if not a:
                return "I couldn't read that as an email address. Ask me again and say it like raj at gmail dot com."
            data = _load()
            data.setdefault(to.lower().strip(), {})["email"] = a
            _save(data)
            return _email({**d, "to": to})
        State.set_pending(f"What's {_title(to)}'s email address?", on_yes=lambda: "", on_text=got_addr)
        return f"What's {_title(to)}'s email address? Say it like raj at gmail dot com. I'll remember it.", None

    to_name = _title(to) if "@" not in to else to.split("@")[0]
    subject, body = _draft_mail(to_name, d["conn"], d["body"], d.get("subject", ""))
    Web.open_url(_mail_url(f"view=cm&fs=1&to={quote(addr)}&su={quote(subject)}&body={quote(body)}"))
    try:
        with W.com_thread():
            def composed():
                root = _mail_select()
                if root is None:
                    return None
                sub = _walk(root, lambda c: c.ControlTypeName == "EditControl" and (c.Name or "") == "Subject")
                return root if sub and _norm(subject[:20]) in _norm(_value(sub)) else None
            if not _wait(composed, 40, 1.5):
                return "Gmail didn't open the draft. Check that you're signed in to Gmail in your browser. Nothing was sent.", None
    except Exception as e:
        print(f"Gmail draft error: {e!r}")
        return "Gmail wouldn't cooperate, so I stopped. Nothing was sent.", None

    State.set_pending(f"Send this email to {addr}?", on_yes=lambda: _mail_send(subject),
                      on_no=lambda: (_mail_discard(), "Okay, I discarded the draft.")[1], on_drop=_mail_discard)
    return (f"I wrote an email to {to_name} with the subject {subject}. It's open in Gmail and in the chat. Shall I send it?",
            f"Email to {addr}\nSubject: {subject}\n\n{body}")


# ------------------------------------------------------------------ entry point
def handle(text):
    d = parse(text)
    if not d:
        return None
    if "to" in d:
        d["to"] = re.sub(r"^(?:my|the)\s+", "", d["to"], flags=re.I)             # "email my boss" -> boss
    if d["kind"] == "save":
        return _save_contact(d), None
    if d["kind"] == "inbox":
        return _inbox(d)
    if d["kind"] == "mail":
        return _email(d)
    return _whatsapp(d)
