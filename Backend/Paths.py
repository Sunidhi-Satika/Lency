"""Spoken paths -> real folders and files.

"open D drive, then projects, then report"      -> D:\\projects\\report...
"open the lency folder in D drive"              -> inside-out order is understood too
"open downloads"  /  "open my desktop"          -> built-in places
Each spoken piece is fuzzy-matched against what is REALLY in that folder (speech-to-text spells names badly),
so "my project files" can still land on a folder called "My_Project-Files".
Your own shortcuts go in Data/places.json:  {"projects": "D:\\Work\\Projects", "school": "D:\\School"}
"""
import difflib
import json
import os
import re

import subprocess
import time

PLACES_FILE = os.path.join("Data", "places.json")
_HOME = os.path.expanduser("~")
_BUILTIN = {"desktop": "Desktop", "documents": "Documents", "downloads": "Downloads", "pictures": "Pictures",
            "videos": "Videos", "music": "Music", "home": "", "user folder": ""}
_FILL = {"the", "my", "folder", "folders", "directory", "file", "path", "drive", "called", "named",
         "explorer", "file explorer", "please", "then", "and", "into", "slash", "backslash", "forward slash", "inside",
         "within", "under", "on", "in", "of", "to", "open", "show", "go", "take", "me", "navigate", "launch"}
_VERBS = re.compile(r"^(?:open|show|go to|take me to|navigate to|launch|bring up|find)\s+", re.I)
_INSIDE = re.compile(r"\s+(?:in|inside|within|under|of|from)\s+(?:the\s+)?", re.I)
_FORWARD = re.compile(r"\s*(?:,|\bthen\b|\band then\b|\bslash\b|\bbackslash\b|\binto\b|->|>|/|\\)\s*", re.I)


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _places():
    out = {}
    for k, sub in _BUILTIN.items():
        cands = [os.path.join(_HOME, sub), os.path.join(_HOME, "OneDrive", sub)] if sub else [_HOME]
        out[k] = next((c for c in cands if os.path.isdir(c)), cands[0])
    try:
        with open(PLACES_FILE, encoding="utf-8") as f:
            out.update({k.lower(): v for k, v in json.load(f).items()})
    except (OSError, ValueError):
        pass
    return out


def is_place(name):
    """True for 'downloads', 'desktop' and the shortcuts in Data/places.json."""
    return name.lower().strip() in _places()


def _drives():
    import string as _s
    return [f"{d}:\\" for d in _s.ascii_uppercase if os.path.exists(f"{d}:\\")]


def _score(spoken, name):
    a, b = _norm(spoken), _norm(name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 3 and (a in b or b in a) and min(len(a), len(b)) / max(len(a), len(b)) > 0.35:
        return 0.93
    return difflib.SequenceMatcher(None, a, b).ratio()


def _best_child(folder, spoken, want_dir):
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return None, 0.0
    best, bs = None, 0.0
    for e in entries:
        if e.name.startswith("$") or e.name.lower() in ("system volume information",):
            continue
        is_dir = e.is_dir()
        if want_dir and not is_dir:
            continue
        s = _score(spoken, os.path.splitext(e.name)[0] if not is_dir else e.name)
        s = max(s, _score(spoken, e.name))
        if is_dir and not want_dir:
            s -= 0.02                                                 # last piece: prefer a file of the same name
        if s > bs:
            best, bs = e.path, s
    return (best, bs) if bs >= 0.6 else (None, bs)


def _find_start(first):
    """Where does the first spoken piece live? A saved place, then the top of each drive, then your home folders."""
    key = first.lower().strip()
    pl = _places()
    if key in pl and os.path.exists(pl[key]):
        return pl[key], True
    roots = _drives() + [os.path.join(_HOME, d) for d in ("Desktop", "Documents", "Downloads")] + [_HOME]
    best, bs = None, 0.0
    for r in roots:
        p, s = _best_child(r, first, True)
        if p and s > bs:
            best, bs = p, s
    return best, False


def parse(text):
    """-> (drive_letter or None, [pieces in top-down order]) from a spoken request."""
    t = _VERBS.sub("", text.strip().strip(" .?!"))
    # explicit Windows path typed or dictated: D:\\projects\\x
    m = re.match(r"^([a-zA-Z]):[\\/](.*)$", t)
    if m:
        return m.group(1).upper(), [p for p in re.split(r"[\\/]", m.group(2)) if p]
    drive = None
    m = re.search(r"\b(?:([a-z])\s+drive|drive\s+([a-z])|([a-z]):)\b", t, re.I)
    if m:
        drive = next(g for g in m.groups() if g).upper()
        t = (t[:m.start()] + " | " + t[m.end():]).strip()
    # which direction? "X in Y in D drive" is inside-out; "D drive then Y then X" is top-down
    has_forward = bool(_FORWARD.search(t))
    parts_in = [p for p in _INSIDE.split(t)] if not has_forward else None
    if parts_in is not None and len(parts_in) > 1:
        pieces = [x for x in parts_in]
        # a leading drive marker splits as '' | ...: handle both positions
        pieces = [x.strip(" |") for x in pieces if x.strip(" |")]
        pieces = list(reversed(pieces))
    else:
        pieces = [x.strip(" |") for x in _FORWARD.split(t) if x.strip(" |")]
    cleaned = []
    for p in pieces:
        words = [w for w in p.split() if w.lower() not in _FILL]
        w2 = " ".join(words).strip()
        w2 = re.sub(r"\s+dot\s+", ".", w2, flags=re.I)
        if w2:
            cleaned.append(w2)
    return drive, cleaned


def resolve(text):
    """-> (path, error). path is an existing folder/file, or None with a spoken error."""
    drive, pieces = parse(text)
    if not drive and not pieces:
        return None, "Which folder or file?"
    deadline = time.time() + 6
    if drive:
        cur = f"{drive}:\\"
        if not os.path.exists(cur):
            return None, f"I can't find a {drive} drive."
    else:
        cur, was_alias = _find_start(pieces[0])
        if not cur:
            return None, f"I couldn't find a folder called {pieces[0]}."
        pieces = pieces[1:]
    for i, piece in enumerate(pieces):
        if time.time() > deadline:
            return None, "That path took too long to search."
        last = i == len(pieces) - 1
        nxt, _s = _best_child(cur, piece, want_dir=not last)
        if not nxt:
            return None, f"I couldn't find {piece} in {os.path.basename(cur.rstrip(chr(92))) or cur}."
        cur = nxt
    return cur, None


def handle(text):
    path, err = resolve(text)
    if err:
        return err, None
    name = os.path.basename(path.rstrip("\\")) or path
    if os.path.isdir(path):
        subprocess.Popen(["explorer", os.path.normpath(path)])
        return f"Opened the {name} folder.", None
    os.startfile(path)
    return f"Opening {name}.", None
