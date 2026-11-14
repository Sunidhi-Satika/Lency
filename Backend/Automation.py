from AppOpener import close, open as appopen
import webbrowser
from pywhatkit import search, playonyt
from rich import print
import subprocess
import keyboard
import asyncio
import os
import time
import re
import math
from urllib.parse import urlparse
from Backend.LLM import complete, Username

SystemChatBot = [{"role": "system", "content": f"Hello, I am {Username}. You have to write content like letters, codes, applications, essays, notes, songs etc. Output only the requested content."}]

WebsiteBot = [{"role": "system", "content": f"Hello, I am {Username}. You have to tell me official website links of any website asked. Tell only the link not even a single extra word is allowed"}]

file_extensions = {
    "pdf": [".pdf"],
    "word": [".doc", ".docx"],
    "excel": [".xls", ".xlsx", ".csv"],
    "ppt": [".ppt", ".pptx"],
    "text": [".txt", ".md", ".rtf"],
    "video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"],
    "audio": [".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a"],
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
    "code": [".py", ".java", ".c", ".cpp", ".html", ".css", ".js", ".php", ".json", ".xml", ".sql", ".sh", ".bat"]
}

def GoogleSearch(Topic):
    search(Topic)
    return True

def Content(Topic):
    def OpenNotepad(File):
        default_text_editor = 'notepad.exe'
        subprocess.Popen([default_text_editor, File])
    
    def ContentWriterAI(prompt):
        # fixed: old code did messages[-5] (an int) and used a retired model
        return complete(SystemChatBot + [{"role": "user", "content": prompt}],
                        max_tokens=2048, temperature=0.7)

    Topic: str = Topic.replace("content ", "")
    ContentByAI = ContentWriterAI(Topic)

    safe = re.sub(r"[^a-z0-9]+", "_", Topic.lower()).strip("_")[:60] or "content"
    path = rf"Data/{safe}.txt"
    with open(path, "w", encoding="utf-8") as file:
        file.write(ContentByAI)

    OpenNotepad(path)
    return True

def YoutubeSearch(Topic):
    Url4Search = f"https://www.youtube.com/results?search_query={Topic}"
    webbrowser.open(Url4Search)
    return True

def PlayYoutube(query):
    playonyt(query)
    return True

_VAGUE = {"it", "this", "that", "them", "everything", "all", "something", "anything"}


def _site_matches(url, app):
    """Only trust a link when it is https and its host looks like the app asked for."""
    try:
        u = urlparse(url)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    words = [w for w in re.split(r"\W+", app.lower()) if len(w) >= 3]
    return u.scheme == "https" and "." in host and any(w in host for w in words)


def OpenApp(app):
    app = app.strip()
    if not app or app.lower() in _VAGUE:
        return False
    try:
        print(f"Debug: Trying to open {app}")
        appopen(app, match_closest=True, output=True, throw_error=True)
        return True
    except Exception as e:
        print(f"Debug: {e} - App not installed, Trying to open in web.")

    try:
        websitelink = complete(
            WebsiteBot + [{"role": "user", "content": f"What is the official website of {app}?"}],
            fast=True, max_tokens=60, temperature=0,
        ).strip().split()[0]
        print(f"debug: {websitelink}")
        if _site_matches(websitelink, app):
            webbrowser.open(websitelink)
            return True
        # the model's link is unverified: search for it instead of opening an invented domain
        search(f"{app} official website")
        return True
    except Exception as e:
        print(f"Debug: Error while looking up a website -> {e}")
        return False


def CloseApp(app):
    app = app.strip()
    if not app or app.lower() in _VAGUE:
        return False
    app = "edge" if app.lower() in ("msedge", "microsoft edge") else app
    try:
        close(app, match_closest=True, output=True, throw_error=True)
        return True
    except Exception:
        return False


def _default_search_dirs():
    # Personal folders only. Walking all of C:\ D:\ E:\ (old behaviour) pegged the
    # disk and CPU for minutes and even scanned venv/site-packages.
    home = os.path.expanduser("~")
    dirs = [os.path.join(home, d) for d in ("Desktop", "Documents", "Downloads", "Videos", "Music", "Pictures", "OneDrive")]
    return [d for d in dirs if os.path.isdir(d)]

_SKIP_DIRS = {"venv", ".venv", "node_modules", "site-packages", "__pycache__", ".git", "appdata", "windows", "program files", "program files (x86)"}

def SearchAndOpenFile(file_type, file_name, search_dirs=None, max_depth=6, time_limit=15):
    """Search personal folders for a file and open the first match (stops early)."""

    if file_type not in file_extensions:
        print(f"Debug: Unknown file type '{file_type}'.")
        return False

    exts = tuple(file_extensions[file_type])
    words = file_name.lower().split()
    deadline = time.time() + time_limit

    for base in (search_dirs or _default_search_dirs()):
        base_depth = base.rstrip("\\/").count(os.sep)
        for root, dirs, files in os.walk(base, topdown=True):
            if time.time() > deadline:
                print("Debug: File search timed out.")
                return False
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            if root.count(os.sep) - base_depth >= max_depth:
                dirs[:] = []
            for file in files:
                if file.lower().endswith(exts):
                    cleaned_name = re.sub(r"[_\-@.]", " ", file).lower()
                    if all(w in cleaned_name for w in words):
                        file_path = os.path.join(root, file)
                        print(f"Debug: Opening {file_path}")
                        os.startfile(file_path)
                        return True

    print(f"Debug: No {file_type} file found matching '{file_name}'.")
    return False

def _volume_endpoint():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


def System(command):
    """Volume control: exact levels and a real mute state through Windows' audio API.
    Falls back to media keys if the API is unavailable."""
    cmd = command.lower()
    if cmd.startswith("media"):
        key = {"media playpause": "play/pause media", "media next": "next track",
               "media previous": "previous track"}.get(cmd.strip())
        try:
            if key:
                keyboard.press_and_release(key)
                return True
        except Exception as e:
            print(f"Debug: media key failed: {e}")
        return False
    num = re.search(r"(\d{1,3})", cmd)
    n = min(100, int(num.group(1))) if num else None
    try:
        if "unmute" in cmd:
            action = "unmute"
        elif "mute" in cmd:
            action = "mute"
        elif re.search(r"\bset\b", cmd):
            action = "set"
        elif re.search(r"\b(up|increase|raise|louder)\b", cmd):
            action = "up"
        elif re.search(r"\b(down|decrease|lower|quieter|reduce)\b", cmd):
            action = "down"
        else:
            print(f"Debug: Unknown system command: '{command}'")
            return False
        if action == "set" and n is None:
            return False
    except Exception as e:
        print(f"Debug: Error parsing '{command}': {e}")
        return False

    try:
        ep = _volume_endpoint()
        level = ep.GetMasterVolumeLevelScalar()
        if action == "mute":
            ep.SetMute(1, None)
        elif action == "unmute":
            ep.SetMute(0, None)
        else:
            if action == "set":
                level = n / 100
            else:
                step = (n if n is not None else 10) / 100
                level += step if action == "up" else -step
            ep.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level)), None)
            if level > 0:
                ep.SetMute(0, None)
        print(f"Debug: volume {action} done")
        return True
    except Exception as e:
        print(f"Debug: pycaw unavailable ({e}); using media keys")

    try:                                              # fallback: each key press is about 2%
        key = {"up": "volume up", "down": "volume down", "mute": "volume mute", "unmute": "volume mute"}.get(action)
        if key is None:
            return False
        for _ in range(1 if action in ("mute", "unmute") else math.ceil((n if n is not None else 10) / 2)):
            keyboard.press_and_release(key)
            time.sleep(0.03)
        return True
    except Exception as e:
        print(f"Debug: Error executing '{command}': {e}")
        return False


async def TranslateAndExecute(commands: list[str]):

    funcs = []

    for command in commands:
        try:
            if command.startswith("open "):
                if "open it " in command:
                    pass
                if "open file " in command:
                    pass
                else:
                    fun = asyncio.to_thread(OpenApp, command.removeprefix("open "))
                    funcs.append(fun)
            elif command.startswith("general "):
                pass
            elif command.startswith("realtime "):
                pass
            elif command.startswith("close "):
                fun = asyncio.to_thread(CloseApp, command.removeprefix("close "))
                funcs.append(fun)
            elif command.startswith("play "):
                fun = asyncio.to_thread(PlayYoutube, command.removeprefix("play "))
                funcs.append(fun)
            elif command.startswith("content "):
                fun = asyncio.to_thread(Content, command.removeprefix("content "))
                funcs.append(fun)
            elif command.startswith("google search "):
                fun = asyncio.to_thread(GoogleSearch, command.removeprefix("google search "))
                funcs.append(fun)
            elif command.startswith("youtube search "):
                fun = asyncio.to_thread(YoutubeSearch, command.removeprefix("youtube search "))
                funcs.append(fun)
            elif command.startswith("system "):
                fun = asyncio.to_thread(System, command.removeprefix("system "))
                funcs.append(fun)
            elif command.startswith("SearchAndOpenFile "):
                # format is "<name words> <type>", type is the LAST word (old code split on the first word)
                parts = command.replace("SearchAndOpenFile ", "").rsplit(" ", 1)
                if len(parts) == 2:
                    file_name, file_type = parts
                    print(f"Debug: Searching for {file_type} file named '{file_name}'...")
                    fun = asyncio.to_thread(SearchAndOpenFile, file_type, file_name)
                    funcs.append(fun)
                else:
                    print(f"Debug: Invalid SearchAndOpenFile format -> {command}")
            else:
                print(f"No Function Found. For {command}")

        except Exception as e:
            print(f"Debug: Error processing command '{command}': {e}")

    results = await asyncio.gather(*funcs, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            print(f"Debug: Command execution error -> {result}")
            yield False
        else:
            yield result

async def Automation(commands: list[str]):
    """Run every task. Returns (succeeded, failed) counts so the caller can be honest about it."""
    ok = failed = 0
    async for result in TranslateAndExecute(commands):
        if result:
            ok += 1
        else:
            failed += 1
    return ok, failed
