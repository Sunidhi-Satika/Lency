"""Lency's short-term memory: ONE shared conversation log for every kind of request.

Before, only chatty answers were remembered; "play X", weather, reminders... left no trace, so
"open that song" or "I asked for ..." had nothing to refer to. Now:
  remember(user, what_she_did)  records any request (task or chat) in Data/ChatLog.json
  resolve(query)                rewrites a follow-up ("open that song on youtube") into a stand-alone
                                request, using the last few turns, BEFORE the router sees it.
The rewrite only runs when the sentence looks like a follow-up, so ordinary commands stay instant.
"""
import re

from Backend import LLM
from Backend import Chatbot

# words that point back at something said or done earlier
_FOLLOW = re.compile(
    r"\b(that|it|this|those|these|them|him|her|there|same|again|previous|last one|the (?:song|video|one|app|file|"
    r"first|second|other)|instead|one more|another|i (?:asked|meant|said|wanted)|not that|no[, ]|wrong|"
    r"also|too|and (?:what|how)|what about|how about)\b", re.I)

_PROMPT = """You turn the LAST user message into a complete, stand-alone request for a voice assistant, using the conversation.
- Replace vague words (it, that song, there, the same one, again) with the real thing from the conversation.
- A correction ('I asked for X', 'no, I meant X', 'not that, X') becomes a fresh request for X, repeating the earlier action.
- Lines like (I just did: play Ratina on youtube) are actions the assistant already carried out; their words tell you what 'that' refers to.
- Keep the user's own spelling of names; do not answer the message; do not invent anything.
- If it is already complete on its own, return it unchanged.
Examples:
Conversation: User: play Shape of You on youtube / Assistant: (I just did: play Shape of You on youtube) Done!
Last: open that song in youtube  ->  Play Shape of You on youtube.
Conversation: same
Last: I asked for Perfect by Ed Sheeran  ->  Play Perfect by Ed Sheeran on youtube.
Conversation: same
Last: play it again  ->  Play Shape of You on youtube.
Conversation: User: what's the weather in Pune / Assistant: Right now in Pune it's 28 degrees.
Last: and tomorrow?  ->  What is the weather in Pune tomorrow?
Output ONLY the final message on one line."""


def looks_like_followup(text):
    t = text.strip()
    return bool(t) and (bool(_FOLLOW.search(t)) or len(t.split()) <= 3)


def recent(n=6):
    return Chatbot._read_log()[-n:]


def remember(user_text, did="", said=""):
    """Add one request (and what she did / said) to the shared log."""
    note = ""
    if did:
        note = f"(I just did: {did}) "
    reply = (note + (said or "")).strip()
    if not reply:
        return
    log = Chatbot._read_log()
    log.append({"role": "user", "content": str(user_text)})
    log.append({"role": "assistant", "content": reply})
    Chatbot._write_log(log)


def resolve(query):
    """Stand-alone version of a follow-up message; the original on any doubt or error."""
    if not looks_like_followup(query):
        return query
    history = recent(6)
    if not history:
        return query
    lines = "\n".join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history)
    try:
        out = LLM.complete(
            [{"role": "system", "content": _PROMPT},
             {"role": "user", "content": f"Conversation so far:\n{lines}\n\nLAST user message: {query}"}],
            fast=True, max_tokens=80, temperature=0)
    except Exception:
        return query
    out = (out or "").strip().strip('"').strip("'").splitlines()[0:1]
    out = out[0].strip() if out else ""
    if not out or len(out) > 3 * len(query) + 60 or out.lower().startswith(("user:", "assistant:")):
        return query
    return out
