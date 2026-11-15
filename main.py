import os
import sys

# Always run from the project folder so every relative path (.env, Data/) resolves,
# no matter where the app is launched from. Must happen before the other imports.
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

from Frontend.GUI import GraphicalUserInterface, QueryModifier, AnswerModifier
from Backend import State
from Backend.Model import FirstlayerDMM
from Backend.Automation import Automation
from Backend.RealTimeSearchEngine import RealTimeSearchEngine
from Backend.Chatbot import ChatBot
from Backend import Reminders, Weather, Calc, Memory, Control, Confirm, Web, Paths, Messaging
from Backend.TextToSpeech import TextToSpeech, LiveSpeaker, list_voices, set_voice
from dotenv import dotenv_values
from asyncio import run
import random
import subprocess
import threading
import traceback
import json
import psutil

IGscript_path = os.path.join(ROOT, "Backend", "ImageGeneration.py")
env_vars = dotenv_values(".env")
Username = env_vars.get("Username") or "You"
Assistantname = env_vars.get("Assistantname") or "Lency"
DefaultMessage = f'''{Username} : Hello {Assistantname}, How are you?
{Assistantname} : Hi {Username}! I'm doing great, and even better now that you're here. What shall we do today? '''
Functions = ["open", "close", "play", "system", "content", "google search", "youtube search", "SearchAndOpenFile"]

DoneLines = [
    "Done!",
    "All set... anything else?",
    "There you go.",
    "Sorted! What's next?",
    "On it... and done!",
    "Easy peasy. What else?",
]

FailLines = [
    "Hmm, I couldn't get that done. Could you check it?",
    "Sorry... that one didn't work.",
    "Oops, something went wrong with that.",
]
PartlyLines = [
    "I did some of it, but not everything went through.",
    "Part of that worked... the rest didn't, sorry.",
]

# spoken instantly while a web search runs, so she never goes quiet and then suddenly answers
SearchFillers = [
    "Hmm, let me check that.",
    "Ooh, good question... one sec.",
    "Let me look that up.",
    "Okay, give me a moment.",
]


# ---------------------------------------------------------------- startup: show history
def ReadChatLogJson():
    try:
        with open(r'Data/ChatLog.json', "r", encoding='utf-8') as file:
            return json.load(file)
    except (FileNotFoundError, ValueError):
        return []

def LoadHistoryToGUI():
    lines = []
    for entry in ReadChatLogJson():
        if entry.get("role") == "user":
            lines.append(f"{Username} : {entry['content']}")
        elif entry.get("role") == "assistant":
            lines.append(f"{Assistantname} : {entry['content']}")
    State.post(AnswerModifier("\n".join(lines)) if lines else DefaultMessage, kind="history")

def InitialExecution():
    os.makedirs("Data", exist_ok=True)
    if not os.path.exists(r"Data/ChatLog.json"):
        with open(r"Data/ChatLog.json", "w", encoding="utf-8") as f:
            f.write("[]")
    State.set_mic(False)
    State.set_status("Available...")
    LoadHistoryToGUI()

InitialExecution()


# ---------------------------------------------------------------- one request
_turn = {"said": [], "chat": False, "did": []}     # what happened during the current request (for memory)


def Say(text):
    """Speak and show a short fixed line."""
    _turn["said"].append(text)
    State.post(f"{Assistantname}: {text}")
    State.set_status("Answering...")
    TextToSpeech(text)


def ChangeVoice(arg):
    voices = [(k, label, female) for k, label, female in list_voices()]
    if arg == "list" or not arg:
        names = ", ".join(label.split(" (")[0] for _, label, female in voices if female)
        Say(f"I can sound like {names}... just say change voice to, and a name.")
    elif set_voice(arg):
        Say("Okay... how's this? I think I like it.")
    else:
        names = ", ".join(label.split(" (")[0] for _, label, female in voices if female)
        Say(f"Hmm, I don't have a voice called {arg}. Try {names}.")


def Alert(item):
    """A reminder, timer or alarm has come due: chime, show it, notify, and say it."""
    text = Reminders.alert_text(item)
    State.post(f"{Assistantname}: {text}")
    State.notify(f"{Assistantname}: " + ("Timer" if item["kind"] == "timer" else "Alarm" if item["kind"] == "alarm"
                                       else "Reminder"), text)
    try:
        import winsound
        for _ in range(3 if item["kind"] == "alarm" else 1):
            winsound.Beep(880, 140)
            winsound.Beep(1175, 220)
    except Exception:
        pass
    Say(text)


def Reply(generate, query, filler=None):
    """Run an answer generator with live speech: audio starts with the first sentence."""
    _turn["chat"] = True                    # the chat module writes its own memory entry
    speaker = LiveSpeaker()
    if filler:
        speaker.say_now(random.choice(filler))
        State.set_status("Searching...")
    answer = generate(query, speaker)
    State.post(f"{Assistantname}: {answer}")
    State.set_status("Answering...")
    if not speaker.fed_any:           # e.g. an error message that was never streamed
        speaker.feed(answer)
    speaker.finish()                  # returns once she has finished speaking

def MainExecution(text):
    """One request, then record it in the shared memory (chat answers record themselves)."""
    _turn.update(said=[], chat=False, did=[])
    Query = QueryModifier(text)
    try:
        _MainExecution(text)
    finally:
        if not _turn["chat"]:
            try:
                Memory.remember(Query, did="; ".join(_turn["did"]), said=" ".join(_turn["said"]))
            except Exception:
                pass


def _MainExecution(text):
    State.clear_cancel()
    TaskExecution = False
    ok = failed = 0
    ImageExecution = False
    ImageGenerationQuery = ""

    Query = QueryModifier(text)
    State.post(f"{Username}: {Query}")
    State.set_status("Thinking...")
    answered = Confirm.resolve(Query)         # was she waiting for a yes / no? ("send it", "no")
    if answered is not None:
        spoken, full = answered
        if full:
            State.post(f"{Assistantname}: {full}")
        Say(spoken)
        return
    Query = Memory.resolve(Query)           # "open that song" -> "play <the song> on youtube"
    Decision = FirstlayerDMM(Query)
    _turn["did"] = [d for d in Decision if not d.startswith(("general", "realtime", "exit", "control", "web ", "path ", "msg "))]

    for q in Decision:                       # "change voice to heera"
        if q.startswith("voice"):
            ChangeVoice(q[5:].strip())
            return

    if any(i.startswith("reminder") for i in Decision):      # reminders, timers, alarms, snooze, cancel, list
        for i in [i for i in Decision if i.startswith("reminder")]:
            Say(Reminders.handle(i))
        Decision = [i for i in Decision if not i.startswith("reminder")]
        if not Decision:
            return

    for i in [i for i in Decision if i.startswith("msg ")]:                # drafts WhatsApp / email, then asks
        State.set_status("Writing...")
        result = Messaging.handle(i[4:])
        if result is None:
            Reply(ChatBot, QueryModifier(i[4:].strip()))
            return
        spoken, full = result
        if full:
            State.post(f"{Assistantname}: {full}")
        Say(spoken)
    Decision = [i for i in Decision if not i.startswith("msg ")]
    if not Decision:
        return

    for i in [i for i in Decision if i.startswith(("web ", "path "))]:      # web search, YouTube video finder, spoken paths
        State.set_status("Working...")
        result = Web.handle(i[4:]) if i.startswith("web ") else Paths.handle(i[5:])
        spoken, full = result if result else ("Hmm, I couldn't do that one.", None)
        Say(spoken)
    Decision = [i for i in Decision if not i.startswith(("web ", "path "))]
    if not Decision:
        return

    for i in [i for i in Decision if i.startswith("control")]:        # PC control, notes, memory, typing...
        State.set_status("Working...")
        result = Control.handle(i[7:].strip())
        if result is None:                                             # not a real control request: just chat
            Reply(ChatBot, QueryModifier(i[7:].strip()))
            return
        spoken, full = result
        if full:
            State.post(f"{Assistantname}: {full}")
        Say(spoken)
    Decision = [i for i in Decision if not i.startswith("control")]
    if not Decision:
        return

    for i in [i for i in Decision if i.startswith(("weather", "city", "calc"))]:   # local, instant, no LLM
        if i.startswith("city"):
            Say(Weather.set_home_city(i[4:].strip()))
        elif i.startswith("weather"):
            Say(Weather.answer(i[7:].strip()))
        else:
            answer = Calc.answer(i[4:].strip())
            if answer:
                Say(answer)
            else:                                   # not a calculation after all: let her chat about it
                Reply(ChatBot, QueryModifier(i[4:].strip()))
    Decision = [i for i in Decision if not i.startswith(("weather", "city", "calc"))]
    if not Decision:
        return

    R = any(i.startswith("realtime") for i in Decision)

    Mearged_query = " and ".join(
        [" ".join(i.split()[1:]) for i in Decision if i.startswith("general") or i.startswith("realtime")]
    )

    for queries in Decision:
        if queries.startswith("generate image"):
            ImageGenerationQuery = queries[len("generate image"):].strip() or "art"
            ImageExecution = True

    for queries in Decision:
        if not TaskExecution and any(queries.startswith(func) for func in Functions):
            ok, failed = run(Automation(list(Decision)))
            TaskExecution = True

    if ImageExecution:
        try:
            State.set_status("Creating...")
            done = subprocess.run([sys.executable, IGscript_path, ImageGenerationQuery],
                                  capture_output=True, text=True, errors="replace", cwd=ROOT)
            if done.stdout:
                print(f"ImageGeneration.py Output:\n{done.stdout}")
            if done.stderr:
                print(f"ImageGeneration.py Error:\n{done.stderr}")
            if done.returncode == 0:
                ok += 1
            else:
                failed += 1
        except Exception as e:
            print(f"Error starting ImageGeneration.py: {e}")
            failed += 1

    if R:
        State.set_status("Searching...")
        Reply(RealTimeSearchEngine, QueryModifier(Mearged_query), filler=SearchFillers)
        return

    for Queries in Decision:
        if Queries.startswith("general"):
            State.set_status("Thinking...")
            Reply(ChatBot, QueryModifier(Queries.replace("general", "", 1)))
            return

        elif Queries.startswith("exit"):
            Reply(ChatBot, QueryModifier("Okay, Bye!"))
            cleanup()
            os._exit(0)

    # only tasks (open/close/play/...) were requested: short spoken confirmation
    if TaskExecution or ImageExecution:
        if failed and ok:
            Say(random.choice(PartlyLines))
        elif failed:
            Say(random.choice(FailLines))
        else:
            Say(random.choice(DoneLines))


def cleanup():
    """Stop only what THIS app started (subprocesses). The very first version terminated
    every python/chrome/msedge process on the PC."""
    print("Cleaning up background processes...")
    try:
        for child in psutil.Process(os.getpid()).children(recursive=True):
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except psutil.Error:
        pass


def FirstThread():
    """Waits for text (typed, or dictated by Windows Voice Typing into the box) and answers it."""
    while True:
        try:
            text = State.wait_text(timeout=0.1)
            if text:
                State.set_busy(True)
                try:
                    MainExecution(text)
                finally:
                    State.set_busy(False)
            else:
                Confirm.tidy_expired()                 # a question nobody answered: undo its draft
                for item in Reminders.pop_due():       # runs only between requests, never over her speech
                    Alert(item)
            if not State.has_text():
                State.set_status("Available...")
        except Exception:
            traceback.print_exc()
            State.set_status("Oops, try again...")
            threading.Event().wait(1)
            State.set_status("Available...")


if __name__ == "__main__":
    threading.Thread(target=FirstThread, daemon=True).start()
    try:
        GraphicalUserInterface(start_hidden="--tray" in sys.argv)
    finally:
        cleanup()
