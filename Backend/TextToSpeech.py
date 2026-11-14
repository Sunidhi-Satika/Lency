"""Speech output with Windows voices only (instant, offline, no network).

LLM tokens -> sentence chunker -> synth workers -> ordered playback thread, so the first
sentence is audible while the rest of the answer is still being written.

Human delivery: each sentence is wrapped in SSML so pauses ("..."), questions, excitement and
reactions ("Aww", "Hmm") get natural pitch, pace and breathing room instead of a flat read.
Her speech never contains the user's name (several voices mispronounce it).

Voice:  chosen in the app (top-bar picker) or by saying "change voice to heera".
        Stored in Data/settings.json; falls back to .env WindowsVoice, then Zira.
Engines: 1. Windows OneCore voices via WinRT   2. fallback: classic SAPI voices via COM
"""
import re
import html
import queue
import random
import asyncio
import threading
import winsound
from concurrent.futures import ThreadPoolExecutor

from dotenv import dotenv_values

from Backend import State, Settings
from Backend.LLM import speakable

env_vars = dotenv_values(".env")
Username = env_vars.get("Username") or ""
_ENV_VOICE = (env_vars.get("WindowsVoice") or "zira").lower()
_FEMALE_HINTS = ("zira", "hazel", "heera", "susan", "aria", "jenny", "female")
_REGION = {"en-US": "US", "en-GB": "UK", "en-IN": "India", "en-AU": "Australia", "en-CA": "Canada"}


# ------------------------------------------------------------------ voice selection
def current_voice_key():
    return (Settings.get("voice") or _ENV_VOICE).lower()


_onecore = None      # None = not probed yet, [] = WinRT unavailable


def _load_onecore():
    global _onecore
    if _onecore is None:
        try:
            from winrt.windows.media.speechsynthesis import SpeechSynthesizer
            _onecore = list(SpeechSynthesizer.all_voices)
        except Exception as e:
            print(f"TTS: WinRT voices unavailable ({e}); using classic Windows voices")
            _onecore = []
    return _onecore


def list_voices():
    """-> [(key, label, is_female)], female voices first. key is what you pass to set_voice()."""
    out = []
    for v in _load_onecore():
        key = v.display_name.split()[-1].lower()
        out.append((key, f"{key.capitalize()} ({_REGION.get(v.language, v.language)})", int(v.gender) == 1))
    if not out:                                              # classic-SAPI fallback list
        try:
            import win32com.client
            for t in win32com.client.Dispatch("SAPI.SpVoice").GetVoices():
                d = t.GetDescription()
                key = d.split()[1].lower()
                out.append((key, key.capitalize(), any(h in d.lower() for h in _FEMALE_HINTS)))
        except Exception:
            pass
    out.sort(key=lambda x: (not x[2], x[1]))
    return out


def set_voice(key):
    key = (key or "").strip().lower()
    if any(k == key for k, _, _ in list_voices()):
        Settings.set("voice", key)
        return True
    return False


def _pick_onecore():
    voices, key = _load_onecore(), current_voice_key()
    for v in voices:
        if key in v.display_name.lower():
            return v
    for v in voices:
        if int(v.gender) == 1:
            return v
    return None


# ------------------------------------------------------------------ names + human delivery
def scrub_name(text):
    """Remove the user's name from speech and tidy the punctuation it leaves behind."""
    if not Username:
        return text
    t = re.sub(rf"\b{re.escape(Username)}(?:['’]s)?\b", "", text, flags=re.I)
    t = re.sub(r"\s+([,!.?;:])", r"\1", t)          # "Hey , you" -> "Hey, you"
    t = re.sub(r",\s*([!.?])", r"\1", t)            # "Thanks,!" -> "Thanks!"
    t = re.sub(r"^[,;:\s]+", "", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:1].upper() + t[1:] if t else t


_REACT = re.compile(r"^(?:aww+|ooh+|oh+|hmm+|hm+|wow|haha+|hehe+|well|yay|ah+|oops|okay|ok|so)\b[,!.]*", re.I)


def to_ssml(text, lang="en-US"):
    """Turn a sentence into SSML with human-ish pauses and intonation."""
    t = html.escape(text, quote=False)
    t = re.sub(r"(?:\.{3}|…)", '<break time="300ms"/>', t)                  # thinking pause
    t = re.sub(r"\s*[—–]\s*|\s-\s", '<break time="170ms"/>', t)             # quick aside
    t = re.sub(r",\s+", ', <break time="70ms"/>', t)                       # tiny breath at commas
    t = _REACT.sub(lambda m: m.group(0) + '<break time="130ms"/>', t)       # "Aww, ..." breathes
    end = text.rstrip()[-1:]
    if end == "!":
        rate, pitch = 28, 8          # excited: quicker, brighter
    elif end == "?":
        rate, pitch = 20, 7          # curious: rising
    elif "..." in text or "…" in text:
        rate, pitch = 10, -2          # thoughtful: a touch slower, softer
    else:
        rate, pitch = 22, 2          # relaxed chat pace
    rate += random.randint(-3, 3)    # never exactly the same twice, so it doesn't sound canned
    pitch += random.randint(-2, 2)
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">'
            f'<prosody rate="{rate:+d}%" pitch="{pitch:+d}%">{t}</prosody></speak>')


# ------------------------------------------------------------------ engine 1: WinRT (OneCore)
async def _wav_bytes(text, voice, styled=True):
    from winrt.windows.media.speechsynthesis import SpeechSynthesizer
    from winrt.windows.storage.streams import DataReader
    synth = SpeechSynthesizer()
    synth.voice = voice
    stream = None
    if styled:
        try:
            stream = await synth.synthesize_ssml_to_stream_async(to_ssml(text, voice.language))
        except Exception as e:
            print(f"TTS: SSML failed ({e}); plain delivery")
    if stream is None:
        stream = await synth.synthesize_text_to_stream_async(text)
    reader = DataReader(stream.get_input_stream_at(0))
    await reader.load_async(stream.size)
    buf = bytearray(stream.size)
    reader.read_bytes(buf)
    return bytes(buf)


# ------------------------------------------------------------------ engine 2: classic SAPI
_sapi_local = threading.local()


def _sapi_speak(text):
    import pythoncom
    import win32com.client
    if getattr(_sapi_local, "key", None) != current_voice_key():
        pythoncom.CoInitialize()
        v = win32com.client.Dispatch("SAPI.SpVoice")
        try:
            tokens, key = list(v.GetVoices()), current_voice_key()
            pick = next((t for t in tokens if key in t.GetDescription().lower()), None) \
                or next((t for t in tokens if any(h in t.GetDescription().lower() for h in _FEMALE_HINTS)), None)
            if pick is not None:
                v.Voice = pick
        except Exception:
            pass
        v.Volume = 100
        _sapi_local.voice, _sapi_local.key = v, current_voice_key()
    _sapi_local.voice.Speak(text)


# ------------------------------------------------------------------ synthesis + playback
def _synth(text):
    """-> ("wav", bytes) or ("sapi", text). Never raises."""
    voice = _pick_onecore()
    if voice is not None:
        try:
            return ("wav", asyncio.run(_wav_bytes(text, voice)))
        except Exception as e:
            print(f"TTS: WinRT synth failed ({e}); falling back to SAPI")
    return ("sapi", text)


def clean_for_speech(text):
    text = speakable(text)                               # emoji/markdown out, "C#" -> "C sharp", "5*3" -> "5 times 3"
    text = re.sub(r"\s+", " ", text).strip()
    return scrub_name(text)


class SpeechStream:
    """Queue sentences with speak(); they are synthesised ahead and played in order."""

    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=2)
        self._futs = queue.Queue()
        self._thread = None

    def speak(self, text):
        text = clean_for_speech(text)
        if not text or State.cancelled():
            return
        if self._thread is None:
            State.set_status("Answering...")
            self._thread = threading.Thread(target=self._player, daemon=True)
            self._thread.start()
        self._futs.put(self._pool.submit(_synth, text))

    def _player(self):
        while True:
            fut = self._futs.get()
            if fut is None:
                return
            try:
                kind, value = fut.result()
                if State.cancelled():
                    continue                                         # stopped: drain without playing
                if kind == "wav":
                    winsound.PlaySound(value, winsound.SND_MEMORY)     # blocks until it has played
                else:
                    _sapi_speak(value)
            except Exception as e:
                print(f"TTS playback error: {e}")

    def finish(self):
        """Block until everything queued has been spoken."""
        if self._thread is not None:
            self._futs.put(None)
            self._thread.join()
        self._pool.shutdown(wait=False)


def stop_speaking():
    """Cut the audio that is playing right now (queued sentences are skipped by State.cancelled())."""
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


State.set_stop_hook(stop_speaking)


# ------------------------------------------------------------------ text -> sentences
class LiveSpeaker:
    """Feed it raw LLM deltas. It cuts sentences, starts speaking the first one immediately,
    and keeps the rule: long answers are read for ~4 sentences, then 'the rest is on screen'."""

    MAX_UNITS = 4
    MIN_CHARS = 30      # merge tiny sentences ("Sure." "Okay.") into the next one

    def __init__(self):
        self.stream = SpeechStream()
        self._buf = ""
        self._pending = ""
        self._units = 0
        self._overflow = []
        self._chars = 0
        self.fed_any = False

    def say_now(self, text):
        """Speak a short filler line immediately (e.g. 'Let me look that up...')."""
        self.stream.speak(text)

    def feed(self, delta):
        if not delta or State.cancelled():
            return
        self.fed_any = True
        self._chars += len(delta)
        self._buf += delta
        while True:
            m = re.search(r"[.!?]+[\"')\]]*\s", self._buf)
            if not m:
                break
            self._take(self._buf[:m.end()].strip())
            self._buf = self._buf[m.end():]

    def _take(self, sentence, final=False):
        self._pending = f"{self._pending} {sentence}".strip()
        if len(self._pending) >= self.MIN_CHARS or final:
            unit, self._pending = self._pending, ""
            if unit:
                self._say(unit)

    def _say(self, unit):
        if self._units < self.MAX_UNITS:
            self._units += 1
            self.stream.speak(unit)
        else:
            self._overflow.append(unit)

    def finish(self):
        if self._buf.strip():
            self._take(self._buf.strip(), final=True)
            self._buf = ""
        elif self._pending:
            self._take("", final=True)
        if self._overflow:
            if self._chars >= 250:
                self.stream.speak(random.choice(_REDIRECTS))
            else:
                self.stream.speak(" ".join(self._overflow))
        self.stream.finish()


_REDIRECTS = [
    "I've put the rest on the chat screen for you.",
    "The rest of it's on the chat screen... have a look when you can.",
    "There's a bit more on the chat screen, take a peek.",
    "I'll let you read the rest on the chat screen.",
    "Check the chat screen for the full answer.",
]


def TextToSpeech(Text):
    """Speak a complete string (used for short fixed lines)."""
    State.clear_cancel()
    sp = LiveSpeaker()
    sp.feed(str(Text))
    sp.finish()


if __name__ == "__main__":
    while True:
        TextToSpeech(input("Enter the text: "))
