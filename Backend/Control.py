"""PC control by voice: brightness, screenshots, windows and browser tabs, system status, clipboard,
notes, long-term memory, typing / key presses into the app you were using.

match(text)  -> True if this sentence is one of these commands (cheap; used by the router)
handle(text) -> (spoken, full_text_or_None), or None if it isn't really a control request after all
"""
import datetime
import io
import os
import re
import subprocess
import time

import psutil

from Backend import Notes, State
from Backend import Windows as W

_FILLER = re.compile(r"^(?:(?:please|can you|could you|would you|will you|hey+|hi+|ok|okay|lency|just|go ahead and)(?:[ ,]+|$))+", re.I)
_VOICES = {"zira", "hazel", "heera", "susan", "david", "george", "mark", "ravi"}
_NO_WINDOW = 0x08000000


def _clean(text):
    t = re.sub(r"\s+", " ", text.strip())
    return _FILLER.sub("", t).strip(" .?!,;")           # case kept: names in notes must stay as spoken


# ============================================================================ command table
# (kind, regex) tried in order against the lower-cased, filler-free sentence.
_P = [
    # ---- typing / keys (matched on the ORIGINAL text so capitals survive; see _TYPE)
    ("press", r"^press (.+)$"),
    ("key", r"^(new line|next line|enter|select all|undo|redo|paste(?: it| that| here)?|cut(?: it| that)?|copy(?: this| it| selection| the selection)?|save(?: this| it| the file)?|go full ?screen|full ?screen|scroll (?:down|up)|page (?:down|up))$"),
    # ---- clipboard
    ("clip_copy_answer", r"^copy (?:that|your (?:last )?(?:answer|reply|response)|the (?:answer|reply|response)|what you (?:just )?said)$"),
    ("clip_read", r"^(?:read|show|tell me|what(?:'s| is) on|what(?:'s| is) in|what is there on)(?: me)?(?: what(?:'s| is) on)?(?: in)? (?:my |the )?clipboard$"),
    ("clip_read", r"^what (?:did|have) i (?:just )?cop(?:y|ied)$"),
    ("clip_ai", r"^(summari[sz]e|explain|translate|proofread|fix|rewrite|shorten|simplify|paraphrase)(?: the| my)?(?: text)?(?: (?:what |that )?i (?:just )?copied| (?:in |from |on )?(?:the |my )?clipboard| copied text)(.*)$"),
    ("clip_clear", r"^(?:clear|empty) (?:my |the )?clipboard$"),
    # ---- notes
    ("note_open", r"^(?:open|show|edit)(?: me)?(?: all)?(?: my| the)? notes(?: file| in notepad| in a file)?$"),
    ("note_read", r"^(?:read|tell|list|show)(?: me)?(?: back)?(?: all)?(?: my| the)? notes$|^what(?:'s| is| are)(?: in| on)? my notes$|^what did i (?:just )?note(?: down)?$"),
    ("note_find", r"^(?:find|search|look)(?: in| through| up)?(?: my)? notes (?:for|about) (.+)$|^search (?:for )?(.+) in (?:my )?notes$"),
    ("note_del", r"^(?:delete|remove|undo|scratch)(?: the| my)? last note$"),
    ("note_clear", r"^(?:clear|delete|erase|wipe)(?: all)?(?: of)?(?: my| the)? notes$"),
    ("note_add", r"^(?:take|make|add|write|jot|save|put|create)(?: down)?(?: a| an| this| that)? ?notes?(?: that| to myself| for me)?[:, ]+(.+)$"),
    ("note_add", r"^note (?:down|this|that)?[:, ]*(.+)$"),
    ("note_add", r"^add (.+) to (?:my |the )?notes$"),
    # ---- long-term memory
    ("mem_open", r"^(?:open|show|edit)(?: me)?(?: all)?(?: your| my| the)? memor(?:y|ies)(?: file)?$"),
    ("mem_recall", r"^what do you (?:remember|know) about me$|^what (?:have|did) i told you$|^what do you remember$|^what do you know about me$|^(?:show|list|tell me)(?: me)?(?: all)?(?: your| my)? memor(?:y|ies)$|^what(?:'s| is) in your memory$"),
    ("mem_recall_about", r"^what do you (?:remember|know) about (?:my |the )?(.+)$|^do you remember (?:my |the |what )?(.+)$"),
    ("mem_forget_all", r"^forget (?:everything|all(?: of it| about me)?|all memories|everything about me)$|^clear (?:your |my )?memor(?:y|ies)$|^wipe (?:your |my )?memor(?:y|ies)$"),
    ("mem_forget", r"^forget (?!it$|about it$)(?:about |that |what i said about )?(.+)$|^forget(?: that| this)?$"),
    ("mem_add", r"^(?:remember|don'?t forget|keep in mind|memori[sz]e)(?: that| this| about)?[:, ]+(.+)$"),
    # ---- brightness
    ("bright_set", r"^(?:(?:set|change|put|make|turn)(?: the| my)? ?)?(?:screen |display )?brightness (?:to|at) (\d{1,3})(?: ?%| percent)?$|^(?:screen |display )?brightness (\d{1,3})(?: ?%| percent)?$"),
    ("bright_rel", r"^(increase|raise|turn up|up|decrease|lower|reduce|turn down|down|dim|boost)(?: the| my)?(?: screen| display)? ?brightness(?: by (\d{1,3}))?(?: ?%| percent)?(?: a (?:bit|little|lot))?$"),
    ("bright_rel", r"^(?:make )?(?:the |my )?(?:screen|display|it) (brighter|dimmer|darker)(?: by (\d{1,3}))?(?: a (?:bit|little|lot))?$|^(brighter|dimmer|darker)$"),
    ("bright_rel", r"^(dim) (?:the |my )?(?:screen|display)$"),
    ("bright_ext", r"^(?:max(?:imum)?|full|min(?:imum)?|lowest|highest) brightness$|^(?:brightness|screen) (?:to )?(?:max(?:imum)?|full|min(?:imum)?|lowest|highest)$"),
    ("bright_get", r"^(?:what(?:'s| is)(?: the| my)?|how bright is(?: the| my)?|check(?: the| my)?)(?: current)?(?: screen| display)? brightness(?: level)?(?: now)?$"),
    # ---- screenshot
    ("shot_snip", r"^(?:snip|screen ?clip|clip the screen|(?:take|grab|make)(?: me)?(?: a| an)? (?:screen ?shot|snip|screen ?clip)(?: of| for)?(?: a| an)? (?:part|area|region|selection|portion|section)(?: of (?:the|my) screen)?|(?:select|choose|pick)(?: an?)? (?:area|region) (?:to|for) (?:screen ?shot|capture))$"),
    ("shot_window", r"^(?:take|grab|capture|get|make)(?: me)?(?: a| the)? (?:screen ?shot|screen capture|picture|photo) of (?:this|the|that|current|active) (?:window|app|page|tab)$|^screen ?shot (?:of )?(?:this|the|that|current|active) (?:window|app|page|tab)$"),
    ("shot_full", r"^(?:take|grab|capture|get|make|do)(?: me)?(?: a| the| my)? ?(?:screen ?shot|screen capture|screen grab|snapshot)(?: of (?:my |the )?(?:whole |full |entire )?(?:screen|display|desktop))?(?: in (\d{1,2}) seconds?)?(?: please)?$|^screen ?shot(?: in (\d{1,2}) seconds?)?$|^capture (?:my |the )?(?:whole |entire )?screen$"),
    # ---- browser tabs
    ("tab_next", r"^(?:go to |switch to |jump to |show )?(?:the )?next tab$"),
    ("tab_prev", r"^(?:go to |switch to |jump to |show )?(?:the )?(?:previous|prev|last used|back) tab$|^go back a tab$"),
    ("tab_new", r"^(?:open |make |create )?(?:a )?new tab$|^open (?:another|a) tab$|^new (?:browser )?window$"),
    ("tab_close", r"^close (?:this|the current|current|that) tab$|^close tab$"),
    ("tab_reopen", r"^(?:reopen|restore|bring back|undo close)(?: the)?(?: last| previous)?(?: closed)? tab$|^reopen closed tab$"),
    ("tab_num", r"^(?:go|switch|jump) to tab (?:number )?(\d{1,2})$|^tab (?:number )?(\d{1,2})$|^(?:go|switch|jump) to the (first|last) tab$"),
    ("tab_list", r"^(?:what|which) tabs (?:are|do i have|have i got)(?: open)?(?: in (?:my )?browser)?$|^list (?:my |all |the )?(?:open )?tabs$|^how many tabs(?: (?:are|do i have))?(?: open)?$"),
    ("tab_named", r"^(?:go|switch|jump|move) to (?:the )?(.+?) tab$|^(?:find|focus|show me|bring up|pull up) (?:the )?(.+?) tab$"),
    ("tab_reload", r"^(?:reload|refresh)(?: this| the)?(?: page| tab)?$"),
    # ---- windows
    ("win_min_all", r"^(?:minimi[sz]e|hide) (?:all|everything|all windows|all apps|every window)$|^show (?:the |my )?desktop$|^clear (?:the |my )?(?:screen|desktop)$"),
    ("win_min", r"^minimi[sz]e(?: this| the| that| current)?(?: window| app)?$"),
    ("win_max", r"^(?:maximi[sz]e|enlarge|make (?:this|it) (?:bigger|full size))(?: this| the| that| current)?(?: window| app)?$"),
    ("win_restore", r"^restore(?: this| the| that| current)?(?: window| app)?$|^(?:un-?maximi[sz]e|make (?:this|it) smaller)(?: this| the| that)?(?: window| app)?$"),
    ("win_snap", r"^(?:snap|move|put|dock)(?: this| the| that| current)?(?: window| app)?(?: to)?(?: the)? (left|right)(?: half| side)?(?: of the screen)?$|^(?:left|right) half$"),
    ("win_list", r"^(?:what|which) (?:windows|apps|programs) (?:are|do i have|have i got)(?: open| running)?$|^list (?:my |all |the )?(?:open )?(?:windows|apps)$"),
    ("win_switch", r"^(?:switch|alt tab|change|jump)(?: back)? to (?:the )?(.+?)(?: window| app)?$|^(?:focus|bring up|bring forward|pull up) (?:the )?(.+?)(?: window| app)?$"),
    # ---- system status
    ("st_battery", r"\b(?:battery|charging|plugged in|on charge)\b"),
    ("st_cpu", r"^(?:how busy is (?:my |the )?(?:pc|cpu|computer|laptop|processor)|what(?:'s| is) (?:my |the )?cpu(?: usage| load)?|cpu (?:usage|load)|how much cpu|check (?:my |the )?cpu)$"),
    ("st_ram", r"^(?:what(?:'s| is) (?:my |the )?(?:ram|memory)(?: usage)?|(?:ram|memory) usage|how much (?:ram|memory)(?: (?:is|am i|do i have))?(?: (?:used|free|left|using|available))?|check (?:my |the )?(?:ram|memory))$"),
    ("st_disk", r"^(?:how much )?(?:disk|storage|drive|hard disk|space)(?: space)?(?: (?:is )?(?:left|free|available|do i have))?$|^how much (?:disk|storage|drive|hard disk)? ?space (?:is |do i have |have i got )?(?:left|free|available)?(?: on (?:my )?(?:pc|laptop|disk|drive))?$|^check (?:my |the )?(?:disk|storage)(?: space)?$"),
    ("st_top", r"^what(?:'s| is) (?:using|eating|hogging|taking|slowing)(?: up| down)?(?: my| the)? ?(cpu|memory|ram|pc|computer|laptop)?(?: down)?$|^why is (?:my |the )?(?:pc|computer|laptop) (?:so )?(?:slow|lagging|hanging)$"),
    ("st_uptime", r"^(?:how long (?:has|have) (?:my |this |the )?(?:pc|computer|laptop|system) been (?:on|running|up)|uptime|when did (?:my |this )?(?:pc|computer|laptop) start)$"),
    ("st_net", r"^(?:am i|are we) (?:online|connected)(?: to the internet)?$|^is (?:the |my )?(?:internet|wifi|wi-fi|net) (?:working|on|up|connected)$|^check (?:my |the )?(?:internet|connection)$"),
    ("st_wifi", r"^(?:which|what) (?:wifi|wi-fi|network)(?: am i (?:on|connected to|using))?$|^(?:wifi|wi-fi) name$|^what(?:'s| is) (?:my |the )?(?:wifi|wi-fi|network)(?: name)?$"),
    ("st_all", r"^(?:system|pc|computer|laptop) (?:status|health|stats|report)$|^how(?:'s| is) (?:my |the )?(?:pc|computer|laptop|system)(?: doing)?$|^(?:status|health) report$"),
]
_COMPILED = [(k, re.compile(rx, re.I)) for k, rx in _P]
_TYPE = re.compile(r"^(?:please |can you |could you |hey |lency |ok |okay )*(?:type|dictate)(?: out)?(?: in)?(?: the following| this| for me)?[:, ]+(.+)$", re.I | re.S)


def _find(text):
    """-> (kind, groups) or None."""
    m = _TYPE.match(text.strip())
    if m:
        return "type", (m.group(1).strip(),)
    t = _clean(text)
    if not t:
        return None
    tl = t.lower()
    for kind, rx in _COMPILED:
        m = rx.search(t) if kind == "st_battery" else rx.match(t)
        if not m:
            continue
        if kind in ("win_switch", "tab_named"):
            name = next((g for g in m.groups() if g), "").strip().lower()
            if (not name or name in _VOICES or name in ("it", "this", "that", "sleep", "bed", "work", "school", "home",
                                                        "dark mode", "light mode", "full screen", "fullscreen")
                    or kind == "tab_named" and name in ("next", "previous", "new", "this", "the", "that", "first", "last")):
                continue
        if kind == "st_battery":
            if not re.search(r"\b(?:how|what|is|check|status|level|much|percent|left|remaining)\b", tl)                     or re.search(r"\b(?:phone|mobile|car|earbuds?|airpods?|watch|remote|camera|tv)\b", tl):
                continue
        if kind == "mem_forget" and len(tl.split()) > 12:
            continue
        return kind, tuple(m.groups())
    return None


def match(text):
    try:
        return _find(text) is not None
    except Exception:
        return False


# ============================================================================ small helpers
def _ps(cmd, timeout=10):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True,
                       text=True, timeout=timeout, creationflags=_NO_WINDOW)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def _spoken_list(items, limit=6):
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    shown = items[:limit]
    return ", ".join(shown[:-1]) + " and " + shown[-1] + (f", plus {len(items) - limit} more" if len(items) > limit else "")


def _pretty_app(exe, title):
    name = exe.replace(".exe", "").replace("msedge", "Edge").replace("claude", "Claude")
    return name.capitalize() if name.islower() else name


# ============================================================================ brightness
def _get_brightness():
    code, out, _err = _ps("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness")
    return int(out.split()[0]) if code == 0 and out.split() else None


def _set_brightness(pct):
    pct = max(5, min(100, int(pct)))
    code, _out, _err = _ps("Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                           f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness={pct}}}")
    return pct if code == 0 else None


_NO_BRIGHT = "I can only change a laptop's built-in screen brightness, and this display doesn't allow it."


def _brightness(kind, g):
    cur = _get_brightness()
    if cur is None:
        return _NO_BRIGHT
    if kind == "bright_get":
        return f"Brightness is at {cur} percent."
    if kind == "bright_set":
        target = int(next(x for x in g if x))
    elif kind == "bright_ext":
        target = 100 if re.search(r"max|full|high", g_text[0]) else 5
    else:
        word = next((x for x in g if x and not x.isdigit()), "up").lower()
        amount = next((int(x) for x in g if x and x.isdigit()), 15)
        target = cur - amount if word in ("decrease", "lower", "reduce", "turn down", "down", "dim", "dimmer", "darker") else cur + amount
    done = _set_brightness(target)
    return f"Brightness is now {done} percent." if done is not None else _NO_BRIGHT


# ============================================================================ screenshots
def _shots_dir():
    d = os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots")
    os.makedirs(d, exist_ok=True)
    return d


def _clipboard_image(img):
    import win32clipboard
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    data = buf.getvalue()[14:]                      # DIB = BMP without its 14-byte file header
    for _ in range(10):
        try:
            win32clipboard.OpenClipboard()
            break
        except Exception:
            time.sleep(0.05)
    else:
        return False
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()
    return True


def _screenshot(kind, g):
    if kind == "shot_snip":
        State.hide_window(True)
        time.sleep(0.3)
        W.press("windows+shift+s")
        threading_restore(8)
        return "Drag over the part you want... it goes straight to your clipboard."
    from PIL import ImageGrab
    delay = int(next((x for x in g if x and x.isdigit()), 0))
    target = W.target_window() if kind == "shot_window" else None
    if kind == "shot_window" and not target:
        return "I couldn't find a window to capture."
    if delay:
        time.sleep(min(delay, 30))
    State.hide_window(True)                         # Lency floats on top: hide her so she isn't in the picture
    try:
        time.sleep(0.35)
        if target:
            W.focus(target[0])
            box = W.window_rect(target[0])
            img = ImageGrab.grab(bbox=box, all_screens=True)
        else:
            img = ImageGrab.grab(all_screens=True)
    finally:
        State.hide_window(False)
    name = datetime.datetime.now().strftime("Lency screenshot %Y-%m-%d %H-%M-%S.png")
    path = os.path.join(_shots_dir(), name)
    img.save(path)
    on_clip = _clipboard_image(img)
    what = "that window" if target else "your screen"
    return (f"Got {what}... saved in your Screenshots folder" + (" and copied, so you can paste it anywhere." if on_clip else "."))


def threading_restore(seconds):
    import threading
    threading.Timer(seconds, lambda: State.hide_window(False)).start()


# ============================================================================ windows and tabs
def _need_target():
    t = W.target_window()
    return t


def _window(kind, g):
    import win32con
    import win32gui
    if kind == "win_min_all":
        n = W.minimize_all()
        return "Everything's tucked away." if n else "There's nothing open to minimise."
    if kind == "win_list":
        names = []
        for _h, title, exe in W.top_windows():
            nm = _pretty_app(exe, title)
            if nm not in names:
                names.append(nm)
        return ("You have " + _spoken_list(names) + " open.") if names else "I don't see any open windows."
    if kind == "win_switch":
        name = next((x for x in g if x), "").strip()
        hit = W.find_window(name)
        if not hit:
            if g_text[0].lower().startswith(("switch", "focus", "alt tab", "jump", "change")):
                return f"I couldn't find a window for {name}."
            return None
        W.focus(hit[0])
        return f"Switched to {_pretty_app(hit[2], hit[1])}."
    t = _need_target()
    if not t:
        return "I don't see a window to do that to."
    hwnd = t[0]
    if kind == "win_min":
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        return "Minimised."
    if kind == "win_max":
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        return "Maximised."
    if kind == "win_restore":
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        return "Restored."
    if kind == "win_snap":
        side = next((x for x in g if x), "left").lower()
        W.focus(hwnd)
        W.press(f"windows+{side}")
        return f"Snapped to the {side}."
    return None


def _browser_focus():
    """Front the browser window (the one you were using, else any open browser). None if no browser is open."""
    t = W.target_window()
    if t and t[2] in W.BROWSERS:
        return t
    b = W.last_browser() or next((w for w in W.top_windows(True) if w[2] in W.BROWSERS), None)
    if b:
        W.focus(b[0])
    return b


def _tabs(kind, g):
    if kind in ("tab_list", "tab_named"):
        with W.com_thread():
            tabs = W.browser_tabs()
            if not tabs:
                return "I can't see any open browser tabs."
            if kind == "tab_list":
                titles = [t[1][:40] for t in tabs]
                full = "\n".join(f"{i + 1}. {t[1]}" for i, t in enumerate(tabs))
                return (f"You have {len(tabs)} tab{'s' if len(tabs) != 1 else ''} open. " +
                        (_spoken_list(titles, 4) + "." if len(tabs) <= 6 else "Some of them: " + _spoken_list(titles, 4) + ".")), full
            name = next((x for x in g if x), "").lower()
            words = [w for w in re.findall(r"\w+", name) if len(w) > 1]
            best = [t for t in tabs if name in t[1].lower()] or [t for t in tabs if words and all(w in t[1].lower() for w in words)]
            if not best:
                return f"I couldn't find a tab about {name}."
            ok = W.select_tab(best[0][0], best[0][2])
            return f"Switched to your {name} tab." if ok else f"I found the {name} tab but couldn't switch to it."
    if not _browser_focus():
        return "I don't see a browser open."
    keys = {"tab_next": "ctrl+tab", "tab_prev": "ctrl+shift+tab", "tab_new": "ctrl+t", "tab_close": "ctrl+w",
            "tab_reopen": "ctrl+shift+t", "tab_reload": "f5"}
    if kind == "tab_num":
        n = next((x for x in g if x), "1")
        n = 9 if n == "last" else 1 if n == "first" else int(n)
        W.press(f"ctrl+{min(n, 9)}")
        return f"Tab {n}." if n != 9 else "Last tab."
    W.press(keys[kind])
    return {"tab_next": "Next tab.", "tab_prev": "Previous tab.", "tab_new": "New tab.", "tab_close": "Closed it.",
            "tab_reopen": "Brought it back.", "tab_reload": "Refreshing."}[kind]


# ============================================================================ typing and keys
_KEYWORDS = {"enter": "enter", "return": "enter", "tab": "tab", "escape": "esc", "esc": "esc", "backspace": "backspace",
             "delete": "delete", "space": "space", "spacebar": "space", "up": "up", "down": "down", "left": "left",
             "right": "right", "home": "home", "end": "end", "page up": "page up", "page down": "page down",
             "control": "ctrl", "ctrl": "ctrl", "alt": "alt", "shift": "shift", "windows": "windows", "win": "windows",
             "plus": "plus", "minus": "-", "print screen": "print screen"}
_KEYPHRASES = {"new line": "enter", "next line": "enter", "enter": "enter", "select all": "ctrl+a", "undo": "ctrl+z",
               "redo": "ctrl+y", "paste": "ctrl+v", "paste it": "ctrl+v", "paste that": "ctrl+v", "paste here": "ctrl+v",
               "cut": "ctrl+x", "cut it": "ctrl+x", "cut that": "ctrl+x", "copy": "ctrl+c", "copy this": "ctrl+c",
               "copy it": "ctrl+c", "copy selection": "ctrl+c", "copy the selection": "ctrl+c", "save": "ctrl+s",
               "save this": "ctrl+s", "save it": "ctrl+s", "save the file": "ctrl+s", "go fullscreen": "f11",
               "go full screen": "f11", "fullscreen": "f11", "full screen": "f11", "scroll down": "page down",
               "scroll up": "page up", "page down": "page down", "page up": "page up"}
_DONE = {"enter": "Done.", "ctrl+a": "Selected everything.", "ctrl+z": "Undone.", "ctrl+y": "Redone.",
         "ctrl+v": "Pasted.", "ctrl+x": "Cut.", "ctrl+c": "Copied.", "ctrl+s": "Saved.", "f11": "Done.",
         "page down": "Scrolling.", "page up": "Scrolling."}


def _keys_from_words(words):
    parts = []
    for tok in re.split(r"\s*(?:\+|\band\b| then )\s*", words.strip().lower()):
        tok = tok.strip()
        if tok in _KEYWORDS:
            parts.append(_KEYWORDS[tok])
        elif re.fullmatch(r"[a-z0-9]", tok):
            parts.append(tok)
        elif re.fullmatch(r"f\d{1,2}", tok):
            parts.append(tok)
        else:
            # "control c" without a plus
            sub = tok.split()
            if len(sub) >= 2 and all(s in _KEYWORDS or re.fullmatch(r"[a-z0-9]", s) for s in sub):
                parts.extend(_KEYWORDS.get(s, s) for s in sub)
            else:
                return None
    return "+".join(parts) if parts else None


def _to_target():
    """Focus the window you were using. Returns it, or None."""
    t = W.target_window()
    if not t:
        return None
    State.hide_window(False)
    W.focus(t[0])
    time.sleep(0.15)
    return t


def _typing(kind, g, original):
    if kind == "type":
        text = g[0]
        if not _to_target():
            return "I don't see an app to type into. Click where you want the text first."
        W.type_text(text)
        return "Typed it."
    if kind == "press":
        combo = _keys_from_words(g[0])
        if not combo:
            return None
        if not _to_target():
            return "I don't see an app to press that in."
        W.press(combo)
        return "Done."
    combo = _KEYPHRASES.get((g[0] if g and g[0] else "").lower())
    if combo is None:
        return None
    if not _to_target():
        return "I don't see an app to do that in."
    W.press(combo)
    return _DONE.get(combo, "Done.")


# ============================================================================ system status
def _bytes(n):
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}".replace(".0 ", " ")
        n /= 1024


def _fmt_dur(seconds):
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    bits = []
    if d:
        bits.append(f"{d} day{'s' if d != 1 else ''}")
    if h:
        bits.append(f"{h} hour{'s' if h != 1 else ''}")
    if m and not d:
        bits.append(f"{m} minute{'s' if m != 1 else ''}")
    return " and ".join(bits) or "less than a minute"


def _battery_text():
    b = psutil.sensors_battery()
    if b is None:
        return "I can't find a battery, so this looks like a desktop."
    pct = round(b.percent)
    if b.power_plugged:
        return f"Battery is at {pct} percent and charging." if pct < 100 else "Battery is full and plugged in."
    left = ""
    if b.secsleft not in (psutil.POWER_TIME_UNKNOWN, psutil.POWER_TIME_UNLIMITED) and 0 < b.secsleft < 48 * 3600:
        left = f", about {_fmt_dur(b.secsleft)} left"
    return f"Battery is at {pct} percent, not charging{left}."


def _cpu_text():
    return f"CPU is at {psutil.cpu_percent(interval=0.6):.0f} percent."


def _ram_text():
    v = psutil.virtual_memory()
    return f"You're using {v.percent:.0f} percent of your memory, {_bytes(v.available)} free."


def _disk_text():
    out = []
    for p in psutil.disk_partitions(all=False):
        if "cdrom" in p.opts or not p.fstype:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        out.append(f"Drive {p.device.rstrip(chr(92)).rstrip(':')} has {_bytes(u.free)} free of {_bytes(u.total)}")
    return (_spoken_list(out, 4) + ".") if out else "I couldn't read the disks."


def _top_text(what):
    procs = list(psutil.process_iter(["name"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(0.8)
    use = {}
    for p in procs:
        try:
            name = (p.info["name"] or "?").replace(".exe", "")
            if name in ("System Idle Process", "Idle", "System", "Registry", "Memory Compression"):
                continue
            cpu = p.cpu_percent(None) / max(1, psutil.cpu_count())
            mem = p.memory_info().rss
        except psutil.Error:
            continue
        a = use.setdefault(name, [0.0, 0])
        a[0] += cpu
        a[1] += mem
    by_mem = (what or "") in ("memory", "ram")
    top = sorted(use.items(), key=lambda kv: kv[1][1 if by_mem else 0], reverse=True)[:3]
    if by_mem:
        return "The biggest memory users are " + _spoken_list([f"{n} with {_bytes(v[1])}" for n, v in top]) + "."
    return "The busiest right now: " + _spoken_list([f"{n} at {v[0]:.0f} percent" for n, v in top]) + "."


def _net_text():
    import socket
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        return "Yes, you're online."
    except OSError:
        return "No, I can't reach the internet right now."


def _wifi_text():
    try:
        r = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=6,
                           creationflags=_NO_WINDOW)
        m = re.search(r"^\s*SSID\s*:\s*(.+)$", r.stdout, re.M)
        return f"You're on {m.group(1).strip()}." if m else "You're not connected to Wi-Fi right now."
    except Exception:
        return "I couldn't check the Wi-Fi."


def _status(kind, g, original):
    if kind == "st_battery":
        return _battery_text()
    if kind == "st_cpu":
        return _cpu_text()
    if kind == "st_ram":
        return _ram_text()
    if kind == "st_disk":
        return _disk_text()
    if kind == "st_top":
        return _top_text(next((x for x in g if x), ""))
    if kind == "st_uptime":
        return f"Your PC has been on for {_fmt_dur(time.time() - psutil.boot_time())}."
    if kind == "st_net":
        return _net_text()
    if kind == "st_wifi":
        return _wifi_text()
    parts = [_battery_text(), _cpu_text(), _ram_text(), _disk_text()]
    return " ".join(parts)


# ============================================================================ clipboard
def clipboard_text():
    """('text', str) / ('image', None) / ('empty', None)"""
    import win32clipboard
    for _ in range(10):
        try:
            win32clipboard.OpenClipboard()
            break
        except Exception:
            time.sleep(0.05)
    else:
        return "empty", None
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            return ("text", text) if text and text.strip() else ("empty", None)
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB):
            return "image", None
    finally:
        win32clipboard.CloseClipboard()
    return "empty", None


def set_clipboard(text):
    import win32clipboard
    for _ in range(10):
        try:
            win32clipboard.OpenClipboard()
            break
        except Exception:
            time.sleep(0.05)
    else:
        return False
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()
    return True


def _last_answer():
    from Backend import Chatbot
    for m in reversed(Chatbot._read_log()):
        if m.get("role") == "assistant":
            return re.sub(r"^\(I just did:[^)]*\)\s*", "", m["content"]).strip()
    return ""


def _clipboard(kind, g):
    if kind == "clip_clear":
        set_clipboard("")
        return "Clipboard cleared."
    if kind == "clip_copy_answer":
        text = _last_answer()
        if not text:
            return "I haven't said anything to copy yet."
        return "Copied what I just said." if set_clipboard(text) else "I couldn't reach the clipboard."
    state, text = clipboard_text()
    if state == "empty":
        return "Your clipboard is empty."
    if state == "image":
        return "There's an image on your clipboard, but I can only read text."
    if kind == "clip_read":
        flat = re.sub(r"\s+", " ", text).strip()
        if len(flat) <= 220:
            return f"It says: {flat}"
        return "It's a long one. I'll read the start: " + flat[:200].rsplit(" ", 1)[0] + "... the rest is in the chat.", text
    verb = g[0].lower()
    extra = (g[1] or "").strip(" .,")
    from Backend.LLM import complete, clean
    instruction = {
        "summarise": "Summarise this text in two or three short spoken sentences.",
        "summarize": "Summarise this text in two or three short spoken sentences.",
        "explain": "Explain what this text means in two or three short spoken sentences.",
        "translate": f"Translate this text{(' ' + extra) if extra else ' into English'}. Output only the translation.",
        "proofread": "Fix spelling and grammar. Output only the corrected text.",
        "fix": "Fix spelling and grammar. Output only the corrected text.",
        "rewrite": f"Rewrite this text{(' ' + extra) if extra else ' more clearly'}. Output only the rewritten text.",
        "shorten": "Make this text shorter. Output only the shortened text.",
        "simplify": "Rewrite this in simpler words. Output only the result.",
        "paraphrase": "Paraphrase this text. Output only the result.",
    }[verb]
    try:
        out = clean(complete([{"role": "system", "content": instruction + " No markdown, no preface."},
                              {"role": "user", "content": text[:6000]}], temperature=0.4, max_tokens=700))
    except Exception:
        return "I couldn't reach my brain for that. Check your connection and ask again."
    if verb in ("summarise", "summarize", "explain"):
        return out
    set_clipboard(out)
    short = out if len(out) <= 200 else out[:190].rsplit(" ", 1)[0] + "..."
    return f"Done, and it's on your clipboard. {short}", out


# ============================================================================ entry point
g_text = [""]


def handle(text):
    """Run one control command. -> (spoken, full_or_None) or None when it isn't one after all."""
    found = _find(text)
    if not found:
        return None
    kind, g = found
    g_text[0] = _clean(text).lower()
    try:
        if kind.startswith("bright"):
            res = _brightness(kind, g)
        elif kind.startswith("shot"):
            res = _screenshot(kind, g)
        elif kind.startswith("win"):
            res = _window(kind, g)
        elif kind.startswith("tab"):
            res = _tabs(kind, g)
        elif kind in ("type", "press", "key"):
            res = _typing(kind, g, text)
        elif kind.startswith("st_"):
            res = _status(kind, g, text)
        elif kind.startswith("clip"):
            res = _clipboard(kind, g)
        elif kind == "note_add":
            res = Notes.add_note(next(x for x in g if x))
        elif kind == "note_read":
            res = Notes.read_notes()
        elif kind == "note_find":
            res = Notes.find_notes(next(x for x in g if x))
        elif kind == "note_del":
            res = Notes.delete_last_note()
        elif kind == "note_clear":
            State.set_pending("Clear all your notes?", Notes.clear_notes)
            res = "Clear all your notes? Say yes to confirm, or no."
        elif kind == "note_open":
            res = Notes.open_notes()
        elif kind == "mem_add":
            if g[0].lower().startswith("to "):
                res = "If you want a reminder, say, remind me to, then what and when. I keep facts about you when you say remember that."
            else:
                res = Notes.remember(g[0])
        elif kind == "mem_forget":
            res = Notes.forget(g[0] or "")
        elif kind == "mem_forget_all":
            State.set_pending("Forget everything I know about you?", Notes.forget_all)
            res = "Forget everything I remember about you? Say yes to confirm, or no."
        elif kind == "mem_recall":
            res = Notes.recall()
        elif kind == "mem_recall_about":
            res = Notes.recall(next((x for x in g if x), ""))
        elif kind == "mem_open":
            res = Notes.open_memory()
        else:
            res = None
    except Exception as e:
        print(f"Control error ({kind}): {e!r}")
        return "Sorry, that one didn't work.", None
    if res is None:
        return None
    return res if isinstance(res, tuple) else (res, None)
