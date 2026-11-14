"""Reminders, alarms and timers that survive restarts.

Spoken or typed requests go through handle(text) -> one sentence for Lency to say.
Items live in Data/reminders.json, and main.py's loop calls pop_due() to find anything that has
come due while the app was running (or while it was closed: those are announced as "missed").

Time parsing is rule-based for the common cases ("in 20 minutes", "at 6:30 pm", "timer for 10
minutes") so it works instantly and offline; anything fancier ("every Monday at 9", "on the 25th
of June") is handed to the fast LLM, which returns a date we validate before saving.
"""
import re
import json
import uuid
import threading
import datetime as dt

from Backend.LLM import complete, MissingKey

FILE = r"Data/reminders.json"
_lock = threading.RLock()
last_fired = None            # most recent item that rang, so "snooze" knows what to postpone

_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
          "forty five": 45, "sixty": 60, "half a": 0.5, "half an": 0.5}
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_NUM = r"\d+(?:\.\d+)?|half an?|forty five|a|an|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty|sixty"
_REL = re.compile(rf"\b(?:in|after|for)\s+(?P<n>{_NUM})\s*(?P<u>seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b")
_CLOCK = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?(?=\W|$)")
_FANCY = re.compile(r"\b(?:every|each|daily|weekly|weekdays?|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                    r"next|january|february|march|april|may|june|july|august|september|october|november|december|"
                    r"\d{1,2}(?:st|nd|rd|th)|day after|tonight|tomorrow|noon|midnight|morning|evening|afternoon)\b")

_CANCEL = re.compile(r"\b(?:cancel|delete|remove|clear|stop|forget|turn off)\b.*\b(?:timers?|reminders?|alarms?)\b")
_LIST = re.compile(r"\b(?:what|which|list|show|read|any|do i have|how many)\b.*\b(?:timers?|reminders?|alarms?)\b|"
                   r"\bhow (?:long|much time)\b.*\b(?:timer|left)\b|\btime (?:is )?left\b")
_SNOOZE = re.compile(r"\bsnooze\b")


# ------------------------------------------------------------------ storage
def _load():
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError):
        return []


def _save(items):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def add(when, text="", kind="reminder", repeat="none", label="", length=""):
    item = {"id": uuid.uuid4().hex[:8], "when": when.timestamp(), "text": text, "kind": kind,
            "repeat": repeat or "none", "label": label, "length": length}
    with _lock:
        items = _load()
        items.append(item)
        _save(items)
    return item


def upcoming():
    with _lock:
        return sorted(_load(), key=lambda i: i["when"])


def _next_repeat(when, repeat, now):
    d = dt.datetime.fromtimestamp(when)
    step = {"daily": 1, "weekly": 7}.get(repeat, 1)
    while d <= now:
        d += dt.timedelta(days=step)
        if repeat == "weekdays":
            while d.weekday() >= 5:
                d += dt.timedelta(days=1)
    return d


def pop_due(now=None):
    """Items whose time has come. One-offs are removed, repeating ones are rescheduled.
    Each result carries 'late' = seconds past due, so missed ones can be announced as missed."""
    global last_fired
    now = now or dt.datetime.now()
    fired = []
    with _lock:
        items = _load()
        if not any(i["when"] <= now.timestamp() for i in items):
            return fired
        keep = []
        for i in items:
            if i["when"] <= now.timestamp():
                out = dict(i)
                out["late"] = now.timestamp() - i["when"]
                fired.append(out)
                if i.get("repeat", "none") != "none":
                    i["when"] = _next_repeat(i["when"], i["repeat"], now).timestamp()
                    keep.append(i)
            else:
                keep.append(i)
        _save(keep)
    if fired:
        last_fired = fired[-1]
    return fired


def cancel(kind=None, words=()):
    """Remove matching items; returns how many. No words -> everything of that kind."""
    with _lock:
        items = _load()
        gone = [i for i in items if (not kind or i["kind"] == kind)
                and (not words or any(w in (i["text"] + " " + i["label"]).lower() for w in words))]
        ids = {i["id"] for i in gone}
        _save([i for i in items if i["id"] not in ids])
    return len(gone)


# ------------------------------------------------------------------ speaking times
def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def duration_phrase(seconds):
    seconds = int(round(seconds))
    if seconds < 90:
        return _plural(max(seconds, 1), "second")
    if seconds < 5400:
        return _plural(round(seconds / 60), "minute")
    if seconds < 172800:
        h, m = divmod(round(seconds / 60), 60)
        return _plural(h, "hour") + (f" {_plural(m, 'minute')}" if m else "")
    return _plural(round(seconds / 86400), "day")


def clock_phrase(d):
    return d.strftime("%I:%M %p").lstrip("0").replace(":00", "")


def when_phrase(d, now=None):
    now = now or dt.datetime.now()
    secs = (d - now).total_seconds()
    if secs < 5400:
        return "in " + duration_phrase(secs)
    days = (d.date() - now.date()).days
    if days == 0:
        return f"at {clock_phrase(d)}"
    day = "tomorrow" if days == 1 else f"on {d.strftime('%A')}" if days < 7 else f"on {d.strftime('%d %B')}"
    return f"at {clock_phrase(d)} {day}"


def _you(text):
    """'call my mom' -> 'call your mom' (she says it back to the user)."""
    for a, b in ((r"\bmy\b", "your"), (r"\bme\b", "you"), (r"\bI'm\b", "you're"), (r"\bI am\b", "you are"),
                 (r"\bI'll\b", "you'll"), (r"\bI\b", "you"), (r"\bmyself\b", "yourself"), (r"\bmine\b", "yours")):
        text = re.sub(a, b, text, flags=re.I)
    return text


# ------------------------------------------------------------------ parsing
def _kind(low):
    if re.search(r"\btimers?\b", low):
        return "timer"
    if re.search(r"\balarms?\b|\bwake me\b", low):
        return "alarm"
    return "reminder"


def _strip_request(text):
    t = text
    t = re.sub(r"^(?:reminder\s+)", "", t, flags=re.I)
    t = re.sub(r"\b(?:please|can you|could you|would you|set (?:a|an|the)?|create (?:a|an)?|make (?:a|an)?|add (?:a|an)?|"
               r"remind me|reminder|timer|alarm|wake me up|wake me|hey lency|lency|for me)\b", " ", t, flags=re.I)
    t = re.sub(r"^\W*(?:to|that|about|of)\b", "", t.strip(), flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:-")
    t = re.sub(r"\b(?:to|that|about|for|at|in|on)$", "", t).strip(" ,.;:-")
    return re.sub(r"^(?:to|that|about)\b\s*", "", t, flags=re.I).strip()


def _rule_parse(text, now):
    """-> (datetime, remaining_text) for simple relative / clock times, else None."""
    low = text.lower()
    if _FANCY.search(low) and not _REL.search(low):
        return None
    m = _REL.search(low)
    if m and not (_FANCY.search(low) and re.search(r"\b(?:every|each|daily|weekly|weekdays?)\b", low)):
        n = m.group("n")
        n = float(n) if n[0].isdigit() else _WORDS.get(n, 1)
        mult = _UNIT[m.group("u")[0]]
        secs = n * mult
        return now + dt.timedelta(seconds=secs), (text[:m.start()] + " " + text[m.end():]), secs
    m = _CLOCK.search(low)
    if m and not re.search(r"\b(?:every|each|daily|weekly|weekdays?)\b", low):
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").replace(".", "")
        if h > 24 or mi > 59:
            return None
        if ap.startswith("p") and h < 12:
            h += 12
        elif ap.startswith("a") and h == 12:
            h = 0
        base = now.replace(hour=h % 24, minute=mi, second=0, microsecond=0)
        if not ap and h <= 12:                               # "at 6": the next 6 o'clock, morning or evening
            alts = [base, base + dt.timedelta(hours=12)]
            base = next((a for a in alts if a > now), alts[0] + dt.timedelta(days=1))
        elif base <= now:
            base += dt.timedelta(days=1)
        return base, (text[:m.start()] + " " + text[m.end():]), (base - now).total_seconds()
    return None


def _llm_parse(text, now):
    """Fancier phrases. Returns (datetime, remaining_text, repeat, kind) or None."""
    prompt = (f"Today is {now.strftime('%A %Y-%m-%d %H:%M')} (24 hour clock).\n"
              "Extract the reminder from the request. Reply with ONLY compact JSON: "
              '{"when":"YYYY-MM-DD HH:MM","text":"what to remind about, no time words","repeat":"none|daily|weekly|weekdays","kind":"reminder|alarm|timer"}. '
              "For recurring requests give the FIRST upcoming occurrence in the future. If no time is given use 09:00.\n"
              f"Request: {text}")
    try:
        raw = complete([{"role": "user", "content": prompt}], fast=True, temperature=0, max_tokens=150)
        m = re.search(r"\{.*\}", raw, flags=re.S)
        data = json.loads(m.group(0))
        when = dt.datetime.strptime(data["when"][:16], "%Y-%m-%d %H:%M")
        repeat = data.get("repeat", "none")
        return when, data.get("text", ""), repeat if repeat in ("none", "daily", "weekly", "weekdays") else "none", \
            data.get("kind", "reminder")
    except MissingKey:
        raise
    except Exception as e:
        print(f"Reminder parse (LLM) failed: {e}")
        return None


# ------------------------------------------------------------------ the one entry point
def handle(text):
    """Understand a reminder/timer/alarm request and return what Lency should say."""
    text = text.strip()
    if text.lower().startswith("reminder "):
        text = text[9:].strip()
    low = text.lower()
    now = dt.datetime.now().replace(microsecond=0)

    if _SNOOZE.search(low):
        return _snooze(low, now)
    if _CANCEL.search(low):
        return _cancel_request(low)
    if _LIST.search(low) and not re.search(r"\bremind me\b", low):
        return _list_phrase(now, "timer" if "timer" in low else "alarm" if "alarm" in low else None)

    parsed = _rule_parse(text, now)
    if not parsed and not re.search(r"\d|noon|midnight|tonight|tomorrow|morning|evening|afternoon|every|daily|weekly|"
                                    r"next|week|day|hour|minute", low):
        return "Sure... when? Say it with a time, like, remind me to stretch at six pm."
    repeat, kind = "none", _kind(low)
    if parsed:
        when, rest, secs = parsed
        length = duration_phrase(secs) if kind == "timer" else ""
    else:
        got = _llm_parse(text, now)
        if not got:
            return "I couldn't work out when. Try something like, remind me at six pm to call mom."
        when, rest, repeat, k = got
        kind = kind if kind != "reminder" else (k if k in ("reminder", "alarm", "timer") else "reminder")
        length = ""
        rest = rest or text
        if rest == text:                                     # the model gave nothing useful back
            rest = _strip_request(text)
    if when <= now:
        return "That time has already passed. When should I set it for?"

    label = ""
    body = _strip_request(rest)
    if kind == "timer":
        m = re.search(r"(\w+)\s+timer\b", low)
        label = m.group(1) if m and m.group(1) not in ("a", "an", "the", "set", "my", "new", "for", "this", "that", "another")             and not m.group(1).isdigit() else ""
        body = ""
    if kind == "reminder" and not body:
        return "Sure... what should I remind you about?"
    item = add(when, _you(body) if kind != "timer" else "", kind, repeat, label, length)

    return _confirmation(item, when, now, repeat)


def _confirmation(item, when, now, repeat):
    kind, text = item["kind"], item["text"]
    wp = when_phrase(when, now)
    every = {"daily": " every day", "weekly": " every week", "weekdays": " every weekday"}.get(repeat, "")
    if kind == "timer":
        nm = f"{item['label']} " if item["label"] else ""
        length = (item["length"] or duration_phrase((when - now).total_seconds())).replace("minutes", "minute")             .replace("seconds", "second").replace("hours", "hour").replace("days", "day")
        return f"Okay, {length} {nm}timer, starting now."
    if kind == "alarm":
        return f"Alarm set for {wp.removeprefix('at ')}{every}."
    link = "that" if text.lower().startswith("you ") else "to"
    return f"Okay, I'll remind you {link} {text} {wp}{every}.".replace("  ", " ")


def _list_phrase(now, kind=None):
    items = [i for i in upcoming() if not kind or i["kind"] == kind]
    if not items:
        return f"You've got no {kind + 's' if kind else 'reminders or timers'} set at the moment."
    parts = []
    for i in items[:5]:
        d = dt.datetime.fromtimestamp(i["when"])
        if i["kind"] == "timer":
            ln = (i["length"] or "countdown").replace("minutes", "minute").replace("seconds", "second").replace("hours", "hour")
            parts.append(f"a {ln} {i['label'] + ' ' if i['label'] else ''}timer with {duration_phrase((d - now).total_seconds())} left")
        elif i["kind"] == "alarm":
            parts.append(f"an alarm {when_phrase(d, now)}")
        else:
            link = "that" if i["text"].lower().startswith("you ") else "to"
            parts.append(f"a reminder {link} {i['text']} {when_phrase(d, now)}")
    more = f", plus {len(items) - 5} more" if len(items) > 5 else ""
    body = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + ", and " + parts[-1]
    return "You have " + body + more + "."


def _cancel_request(low):
    kind = "timer" if "timer" in low else "alarm" if "alarm" in low else "reminder" if "remind" in low else None
    if re.search(r"\b(?:all|every|everything)\b", low):
        n = cancel(kind)
        return f"Done, I cleared {n} of them." if n else "There's nothing to clear."
    words = [w for w in re.findall(r"[a-z]{4,}", low)
             if w not in ("cancel", "delete", "remove", "clear", "stop", "forget", "turn", "timer", "timers", "reminder",
                          "reminders", "alarm", "alarms", "please", "about", "that", "this", "with")]
    items = [i for i in upcoming() if not kind or i["kind"] == kind]
    if words:
        items = [i for i in items if any(w in (i["text"] + " " + i["label"]).lower() for w in words)]
    if not items:
        return "I couldn't find one like that."
    cancel_id = items[0]["id"]
    with _lock:
        _save([i for i in _load() if i["id"] != cancel_id])
    return "Okay, cancelled it."


def _snooze(low, now):
    m = re.search(rf"({_NUM})\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)", low)
    secs = 600
    if m:
        n = m.group(1)
        secs = (float(n) if n[0].isdigit() else _WORDS.get(n, 1)) * _UNIT[m.group(2)[0]]
    if not last_fired:
        return "There's nothing to snooze right now."
    add(now + dt.timedelta(seconds=secs), last_fired["text"], last_fired["kind"], "none", last_fired["label"], last_fired["length"])
    return f"Okay, I'll nudge you again in {duration_phrase(secs)}."


def alert_text(item):
    """What she says (and shows) when an item comes due."""
    late = item.get("late", 0)
    when = dt.datetime.fromtimestamp(item["when"])
    if item["kind"] == "timer":
        nm = f"{item['label']} " if item["label"] else ""
        ln = item["length"].replace("minutes", "minute").replace("seconds", "second").replace("hours", "hour")
        return f"Your {ln} {nm}timer is done!".replace("  ", " ")
    if item["kind"] == "alarm":
        return "Rise and shine... it's " + clock_phrase(when) + "!" if late < 300 else \
            f"I missed your {clock_phrase(when)} alarm while I was off."
    if late > 300:
        return f"Sorry, I was off earlier. At {clock_phrase(when)} I was meant to remind you {item['text']}."
    return f"Hey, quick reminder... {item['text']}."


if __name__ == "__main__":
    for t in ["remind me to call my mom in 20 minutes", "set a timer for 10 minutes", "wake me at 6:30 am",
              "what reminders do I have", "cancel all timers"]:
        print(t, "->", handle(t))
