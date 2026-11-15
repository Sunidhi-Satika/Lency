"""Notes (a plain Notepad-friendly file) and long-term memory (facts she keeps about you).

Data/notes.txt   one note per line:  [2026-11-14 18:05] buy milk      -> "take a note ..." / "read my notes"
Data/memory.txt  one fact per line:  my sister's birthday is 3 March  -> "remember that ..." / "forget ..."
Both are ordinary text files: "open my notes" / "open my memory" opens them in Notepad, so editing is just typing.
Facts are quietly added to every chat prompt, so she uses them naturally ("you said you're allergic to peanuts").
"""
import datetime
import os
import re
import subprocess

NOTES = os.path.join("Data", "notes.txt")
MEMORY = os.path.join("Data", "memory.txt")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f if ln.strip()]
    except OSError:
        return []


def _write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def _backup(path):
    """Never destroy: 'clear' moves the file aside as <name>.old.txt."""
    if os.path.exists(path):
        old = path.replace(".txt", ".old.txt")
        if os.path.exists(old):
            os.remove(old)
        os.replace(path, old)


def _open_in_notepad(path):
    if not os.path.exists(path):
        _write(path, [])
    subprocess.Popen(["notepad.exe", os.path.abspath(path)])


# ------------------------------------------------------------------ notes
def add_note(text):
    text = text.strip(" .")
    if not text:
        return "What should I write down?"
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    _write(NOTES, _read(NOTES) + [f"[{stamp}] {text}"])
    return "Noted... I wrote that down."


def _plain(line):
    return re.sub(r"^\[[^\]]*\]\s*", "", line)


def read_notes(n=5):
    notes = _read(NOTES)
    if not notes:
        return "You don't have any notes yet.", None
    latest = [_plain(x) for x in notes[-n:]]
    spoken = (f"You have {len(notes)} notes. The latest: " if len(notes) > 1 else "Your note says: ") \
        + ". ".join(latest[::-1][:3]) + "."
    full = "\n".join(notes[-12:])
    return spoken, (full if len(notes) > 3 else None)


def find_notes(word):
    hits = [x for x in _read(NOTES) if word.lower() in x.lower()]
    if not hits:
        return f"I couldn't find anything about {word} in your notes.", None
    return f"I found {len(hits)}: " + ". ".join(_plain(x) for x in hits[:3]) + ".", "\n".join(hits)


def delete_last_note():
    notes = _read(NOTES)
    if not notes:
        return "There are no notes to delete."
    gone = notes.pop()
    _write(NOTES, notes)
    return f"Deleted your last note: {_plain(gone)}."


def clear_notes():
    if not _read(NOTES):
        return "Your notes are already empty."
    _backup(NOTES)
    return "All notes cleared. I kept a backup called notes dot old, just in case."


def open_notes():
    _open_in_notepad(NOTES)
    return "Here are your notes."


# ------------------------------------------------------------------ long-term memory
def facts():
    return _read(MEMORY)


def remember(text):
    text = re.sub(r"\s+", " ", text).strip(" .")
    if len(text) < 3:
        return "What should I remember?"
    current = facts()
    if any(text.lower() == f.lower() for f in current):
        return "I already know that."
    _write(MEMORY, current + [text])
    return "Got it... I'll remember that."


def _score(fact, query):
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2 and w not in ("that", "the", "about", "and")]
    return sum(1 for w in words if w in fact.lower()), len(words)


def forget(query):
    current = facts()
    if not current:
        return "I'm not remembering anything yet."
    query = query.strip(" .")
    if query in ("", "that", "this", "the last one", "last one", "the last thing"):
        gone = current.pop()
        _write(MEMORY, current)
        return f"Okay, forgotten: {gone}."
    scored = sorted(((*_score(f, query), f) for f in current), reverse=True)
    top, total, best = scored[0]
    if top == 0 or (total > 1 and top < 1):
        return f"I don't remember anything about {query}."
    current.remove(best)
    _write(MEMORY, current)
    return f"Okay, I've forgotten that: {best}."


def forget_all():
    if not facts():
        return "There's nothing to forget."
    _backup(MEMORY)
    return "Done... I've forgotten everything. A backup is saved as memory dot old, if you change your mind."


def recall(about=""):
    items = facts()
    if about:
        items = [f for f in items if _score(f, about)[0] > 0]
    if not items:
        return ("I don't remember anything about that yet." if about else
                "I don't remember anything yet. Tell me to remember something."), None
    spoken = f"I remember {len(items)} thing{'s' if len(items) != 1 else ''}. " + ". ".join(items[:4]) + \
             ("... and more, I put the list in the chat." if len(items) > 4 else ".")
    return spoken, ("\n".join("- " + f for f in items) if len(items) > 1 else None)


def open_memory():
    _open_in_notepad(MEMORY)
    return "Here's my memory about you. Edit it however you like, one fact per line."


def facts_messages():
    """System message with what she knows about the user (empty list if nothing)."""
    items = facts()[-40:]
    if not items:
        return []
    return [{"role": "system", "content":
             "Things the user asked you to remember (use them naturally when relevant, never recite the list):\n"
             + "\n".join("- " + f for f in items)}]
