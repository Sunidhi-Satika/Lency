"""Web helpers that use your DEFAULT browser: search, open the Nth result, and play the YouTube video you named
(not just the first hit).

open_url(url)    opens a link in your default browser and brings it to the front
search(query)    opens a web search and remembers the results so "open the third result" works
play(query)      finds the best-matching video on YouTube and opens it; if unsure, shows the results page
handle(command)  "play X" | "search X" | "result N"  ->  (spoken, None)
"""
import difflib
import json
import re
import threading
import time
import webbrowser
from urllib.parse import quote_plus

import requests

_ORD = {"first": 1, "1st": 1, "one": 1, "second": 2, "2nd": 2, "two": 2, "third": 3, "3rd": 3, "three": 3,
        "fourth": 4, "4th": 4, "four": 4, "fifth": 5, "5th": 5, "five": 5, "sixth": 6, "6th": 6, "seventh": 7,
        "eighth": 8, "ninth": 9, "tenth": 10, "last": -1}

_state = {"kind": None, "results": [], "thread": None, "query": ""}      # what "the third result" refers to

_SITES = {
    "gmail": "https://mail.google.com", "google mail": "https://mail.google.com", "mail": "https://mail.google.com",
    "email": "https://mail.google.com", "google drive": "https://drive.google.com", "drive": "https://drive.google.com",
    "google docs": "https://docs.google.com", "google sheets": "https://sheets.google.com",
    "google slides": "https://slides.google.com", "google calendar": "https://calendar.google.com",
    "google maps": "https://maps.google.com", "maps": "https://maps.google.com", "google photos": "https://photos.google.com",
    "youtube": "https://www.youtube.com", "youtube music": "https://music.youtube.com", "github": "https://github.com",
    "linkedin": "https://www.linkedin.com", "instagram": "https://www.instagram.com", "facebook": "https://www.facebook.com",
    "twitter": "https://x.com", "x": "https://x.com", "reddit": "https://www.reddit.com", "netflix": "https://www.netflix.com",
    "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "stack overflow": "https://stackoverflow.com",
    "whatsapp web": "https://web.whatsapp.com", "web whatsapp": "https://web.whatsapp.com",
    "amazon": "https://www.amazon.com", "wikipedia": "https://www.wikipedia.org",
    "outlook": "https://outlook.live.com", "google": "https://www.google.com", "spotify web": "https://open.spotify.com",
}


def known_site(name):
    """URL for well-known websites that are not apps (so 'open google drive' never launches a random app by fuzzy luck)."""
    return _SITES.get(re.sub(r"\s+", " ", name.lower().strip()))


def default_browser_exe():
    """The .exe of the browser Windows uses for https links (e.g. 'chrome.exe'), or None if unknown."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice")
        prog = winreg.QueryValueEx(key, "ProgId")[0].lower()
    except OSError:
        return None
    for needle, exe in (("brave", "brave.exe"), ("chrome", "chrome.exe"), ("msedge", "msedge.exe"), ("edge", "msedge.exe"),
                        ("firefox", "firefox.exe"), ("opera", "opera.exe"), ("vivaldi", "vivaldi.exe")):
        if needle in prog:
            return exe
    return None


def _front(exe):
    time.sleep(1.2)
    try:
        from Backend import Windows as W
        for hwnd, _title, e in W.top_windows():
            if e == exe:
                W.focus(hwnd)
                return
    except Exception:
        pass


def open_url(url):
    """Open a link in the default browser and bring that browser to the front."""
    webbrowser.open(url, new=2)
    exe = default_browser_exe()
    if exe:
        threading.Thread(target=_front, args=(exe,), daemon=True).start()
    return True


# ------------------------------------------------------------------ web search
def _fetch_results(query, out):
    try:
        from ddgs import DDGS
        for backend in ("duckduckgo", "auto"):
            try:
                rows = DDGS(timeout=6).text(query, max_results=10, backend=backend)
            except Exception:
                rows = []
            if rows:
                out.extend({"title": r.get("title", ""), "url": r.get("href", "")} for r in rows if r.get("href"))
                return
    except Exception:
        pass


def search(query):
    query = query.strip()
    if not query:
        return "What should I search for?"
    open_url("https://duckduckgo.com/?q=" + quote_plus(query))
    results = []
    t = threading.Thread(target=_fetch_results, args=(query, results), daemon=True)
    t.start()
    _state.update(kind="web", results=results, thread=t, query=query)
    return f"Searching for {query}."


# ------------------------------------------------------------------ YouTube
_JUNK = {"cover", "reaction", "reacts", "remix", "karaoke", "slowed", "reverb", "8d", "status", "shorts", "instrumental",
         "tutorial", "lesson", "trailer", "teaser", "mashup", "live", "nightcore", "sped", "edit", "dance", "hour", "hours", "loop", "extended", "lofi", "bass", "boosted"}


def _find_all(obj, key, out):
    if isinstance(obj, dict):
        if key in obj:
            out.append(obj[key])
        for v in obj.values():
            _find_all(v, key, out)
    elif isinstance(obj, list):
        for v in obj:
            _find_all(v, key, out)


def youtube_results(query, limit=10):
    """[{id, title, channel, length}] straight from YouTube's search page (no API key)."""
    r = requests.get("https://www.youtube.com/results", params={"search_query": query}, timeout=8,
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                              "Accept-Language": "en-US,en;q=0.9"}, cookies={"CONSENT": "YES+1"})
    r.raise_for_status()
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});</script>", r.text, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    vids = []
    _find_all(data, "videoRenderer", vids)
    out = []
    for v in vids:
        try:
            out.append({"id": v["videoId"],
                        "title": "".join(x.get("text", "") for x in v["title"]["runs"]),
                        "channel": "".join(x.get("text", "") for x in v.get("ownerText", {}).get("runs", [])),
                        "length": v.get("lengthText", {}).get("simpleText", "live")})
        except KeyError:
            continue
        if len(out) >= limit:
            break
    return out


def _norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()


def _window_ratio(qj, tj):
    """Best fuzzy match of the spoken words (joined) anywhere in the title: 'ratinamo' ~ 'rathinamo'."""
    if not qj or not tj:
        return 0.0
    n = len(qj)
    best = 0.0
    for i in range(0, max(1, len(tj) - n + 3)):
        best = max(best, difflib.SequenceMatcher(None, qj, tj[i:i + n + 2]).ratio())
    return best


def _score(query, v, rank=0, total=10):
    q, t = _norm(query), _norm(v["title"] + " " + v["channel"])
    if not q:
        return 0.0
    words = sum(1 for w in q if w in t) / len(q)                      # how many of the spoken words the video has
    fuzzy = _window_ratio("".join(q), "".join(_norm(v["title"])))     # tolerates speech-to-text spellings
    hit = max(words, fuzzy * 0.95 if fuzzy > 0.86 and len("".join(q)) >= 6 else 0.0)
    seq = difflib.SequenceMatcher(None, " ".join(q), " ".join(_norm(v["title"]))).ratio()
    title_words = _norm(v["title"])
    junk = sum(1 for w in _JUNK if w in title_words and w not in q)
    official = 0.07 if re.search(r"official|vevo|records|t-series|sony|zee|saregama|music", v["channel"], re.I) else 0.0
    official += 0.10 if "official" in title_words else 0.0
    official -= 0.06 if "lyrics" in title_words and "lyrics" not in q and "lyric" not in q else 0.0
    prior = 0.18 * (1 - rank / max(1, total))                         # YouTube's own order already favours the popular official upload
    return 0.65 * hit + 0.35 * seq - 0.15 * junk + official + prior


def play(query):
    """Open the video that best matches what was said; otherwise the results page."""
    query = re.sub(r"\s+on youtube$", "", query.strip(), flags=re.I)
    if not query:
        return "What should I play?"
    try:
        vids = youtube_results(query)
    except Exception:
        vids = []
    if not vids:
        open_url("https://www.youtube.com/results?search_query=" + quote_plus(query))
        return f"I couldn't read the YouTube results, so I opened the search for {query}."
    scored = sorted(((_score(query, v, i, len(vids)), v) for i, v in enumerate(vids)), key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    _state.update(kind="youtube", results=[{"title": v["title"], "url": "https://www.youtube.com/watch?v=" + v["id"]}
                                           for v in vids], thread=None, query=query)
    if best_score < 0.5:
        open_url("https://www.youtube.com/results?search_query=" + quote_plus(query))
        return f"I wasn't sure which one you meant, so I opened the YouTube results for {query}."
    open_url("https://www.youtube.com/watch?v=" + best["id"])
    ch = f" by {best['channel']}" if best["channel"] else ""
    return f"Playing {best['title']}{ch}."


# ------------------------------------------------------------------ "open the third result"
def _ordinal(word):
    word = word.lower().strip()
    return int(word) if word.isdigit() else _ORD.get(word)


def open_result(spec):
    n = _ordinal(spec)
    if n is None:
        return "Which result? Say first, second, third..."
    t = _state["thread"]
    if t is not None:
        t.join(timeout=7)
    res = _state["results"]
    if not res:
        return "I don't have any results to pick from. Ask me to search for something first."
    if n == -1:
        n = len(res)
    if not 1 <= n <= len(res):
        return f"I only have {len(res)} results."
    item = res[n - 1]
    open_url(item["url"])
    title = (item["title"] or "").strip()
    return f"Opening result {n}" + (f": {title[:80]}." if title else ".")


def handle(command):
    """'play X' | 'search X' | 'result N' -> (spoken, None)"""
    command = command.strip()
    verb, _, rest = command.partition(" ")
    verb = verb.lower()
    if verb == "play":
        return play(rest), None
    if verb == "search":
        return search(rest), None
    if verb == "result":
        return open_result(rest), None
    return None
