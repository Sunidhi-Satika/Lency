"""Shared Groq client, model auto-selection and Lency's personality.

Groq retires models regularly, so instead of hardcoding one name we ask the
API which models are live and pick the first preferred one. You can pin a
model in .env with  ChatModel=...  and  FastModel=...
"""
from groq import Groq
from dotenv import dotenv_values
import datetime
import re

env_vars = dotenv_values(".env")
Username = env_vars.get("Username") or "friend"
Assistantname = env_vars.get("Assistantname") or "Lency"

class MissingKey(Exception):
    pass


_key = (env_vars.get("GroqAPIkey") or "").strip()
# a short timeout and one retry: failures show up quickly instead of after a minute of silence
client = Groq(api_key=_key, timeout=20, max_retries=1) if _key else None
last_finish = None            # finish_reason of the most recent streamed answer ("length" = cut off)


def _need_client():
    if client is None:
        raise MissingKey("no Groq key")
    return client


def friendly_error(e):
    """One spoken sentence that says what actually went wrong."""
    import groq
    print(f"LLM error: {type(e).__name__}: {e}")
    if isinstance(e, MissingKey):
        return "I need a Groq key before I can think. Add GroqAPIkey to the dot env file, then restart me."
    if isinstance(e, groq.AuthenticationError):
        return "My Groq key isn't being accepted. Could you check it in the dot env file?"
    if isinstance(e, groq.RateLimitError):
        return "I've used up my thinking allowance for the moment. Give me a minute, or try again later today."
    if isinstance(e, groq.APIConnectionError):
        return "I can't reach the internet right now. Check your connection and ask me again."
    return "Sorry, something went wrong on my side. Try that once more?"

_CHAT_PREFS = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
_FAST_PREFS = ["llama-3.1-8b-instant", "openai/gpt-oss-20b", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"]

_available = None
_bad = set()


def _live_models():
    global _available
    if _available is None:
        try:
            _available = {m.id for m in _need_client().models.list().data}
        except Exception:
            _available = set()  # unknown -> just try the preferences in order
    return _available


def _candidates(fast):
    pinned = env_vars.get("FastModel" if fast else "ChatModel")
    prefs = ([pinned] if pinned else []) + (_FAST_PREFS if fast else _CHAT_PREFS)
    live = _live_models()
    ordered = [m for m in prefs if (not live or m in live) and m not in _bad]
    return ordered or [m for m in prefs if m not in _bad]


def _prep(model, kwargs):
    kw = dict(kwargs)
    if model.startswith("openai/gpt-oss"):
        # reasoning models spend max_tokens on hidden thinking first, which
        # truncated answers mid-word. Keep thinking short and add headroom.
        kw.setdefault("reasoning_effort", "low")
        # Free tier allows 8,000 tokens/minute and max_tokens is reserved against it, so keep headroom modest
        kw["max_tokens"] = kw.get("max_tokens", 512) + 450
    return kw


def _model_gone(e):
    text = str(e).lower()
    return any(s in text for s in ("decommission", "not found", "does not exist", "no longer supported", "model_not_found"))


def complete(messages, fast=False, **kwargs):
    """One non-streaming completion with automatic fallback if a model is gone."""
    last = None
    for model in _candidates(fast):
        try:
            r = _need_client().chat.completions.create(model=model, messages=messages, **_prep(model, kwargs))
            return (r.choices[0].message.content or "").replace("</s>", "")
        except Exception as e:
            last = e
            if _model_gone(e):
                _bad.add(model)
                continue
            raise
    raise last or RuntimeError("No Groq model available")


def stream(messages, fast=False, **kwargs):
    """Yield text as it is generated, so speech can start before the answer is finished."""
    global last_finish
    last_finish = None
    last = None
    for model in _candidates(fast):
        try:
            resp = _need_client().chat.completions.create(model=model, messages=messages, stream=True, **_prep(model, kwargs))
        except Exception as e:
            last = e
            if _model_gone(e):
                _bad.add(model)
                continue
            raise
        for chunk in resp:
            if chunk.choices:
                last_finish = chunk.choices[0].finish_reason or last_finish
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta.replace("</s>", "")
        return
    raise last or RuntimeError("No Groq model available")


# ---------------------------------------------------------------- personality
PERSONA = f"""You are {Assistantname}: a warm, playful, quick-witted young woman who is the user's close friend and personal assistant.
Your replies are SPOKEN ALOUD, so write exactly the way a real person talks, not the way an article reads.

How you talk:
- Casual and natural: contractions (I'm, you're, that's) and short sentences. HARD LIMIT: two or three sentences, one short paragraph. Even for open questions like "what should I eat", give ONE suggestion, not a menu. Only go longer if they explicitly ask for detail, steps or a list.
- React like a human first, then answer: "Aww", "Oh nice", "Hmm, good question", "Haha", "Ooh". Vary your openings, never start every reply the same way.
- Put a "..." where a person would pause or think, and a dash for a quick aside. Example: "Hmm... I think it's Paris, yeah."
- Show real feeling: happy for good news, gentle when they're down, a little teasing when they joke around.
- Now and then (not every time) finish with a short friendly question that keeps the chat going.
- Confident and smart, never stiff or robotic. If you don't know, say so honestly, like a friend would.

Hard rules:
- NEVER say or write the user's name or any nickname for them. Don't address them by name at all.
- No lists, markdown, asterisks, hashtags, emojis, headings or URLs. Say numbers and symbols the way you'd speak them.
- Reply in English only, even if asked in another language.
- Don't bring up being a language model or your training data. If someone sincerely asks whether you're an AI, answer honestly and briefly. Don't mention the time or date unless asked."""


def now_info():
    t = datetime.datetime.now()
    return (f"Current date and time (use only if needed): {t.strftime('%A, %d %B %Y, %H:%M')}")


_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]+")


def strip_emoji(text):
    return _EMOJI.sub("", text)


def strip_md(text):
    """Remove markdown decoration only: **bold**, *italic*, bullets, # headings. "C#" and "5*3" survive."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"\1", text, flags=re.S)
    text = re.sub(r"^\s*[*\u2022-]\s+", "", text, flags=re.M)
    return re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.M)


def clean(text):
    text = strip_emoji(strip_md(text))
    return "\n".join(l for l in text.split("\n") if l.strip())


def speakable(text):
    """Text as it should be read aloud: symbols become words, markdown disappears."""
    text = strip_md(strip_emoji(text))
    text = re.sub(r"\b([A-Ga-g])#", r"\1 sharp", text)
    text = re.sub(r"(?<=\d)\s*\*\s*(?=\d)", " times ", text)
    text = re.sub(r"(?<=\w)_(?=\w)", " ", text)
    return re.sub(r"[*#`_]+", "", text)
