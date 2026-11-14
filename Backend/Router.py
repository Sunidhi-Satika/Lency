"""Zero-latency rule router.

Most requests are obvious ("open chrome", "volume up", "hi lency"). Sending those to an
LLM costs 1-3 seconds for nothing, so we recognise them locally and only fall back to the
LLM router (Backend/Model.py) for anything ambiguous or compound.

quick_route(text) -> list of task strings (same format the LLM router returns) or None.
"""
import re

from Backend import Calc, Weather

_FILLER = re.compile(
    r"^(?:(?:please|can you|could you|would you|hey+|hi+|hello+|yo|ok|okay|lency|"
    r"good (?:morning|afternoon|evening|night))(?:[ ,]+|$))+")
_BAD_TARGET = r"(?!(?:it|this|that|them|everything|all)$)"      # "close it" must not fuzzy-close a random app

_EXIT = re.compile(r"(?:bye|goodbye|bye bye|exit|quit|see you|see ya)(?: lency)?(?: for now| later)?")
_VOLUME = {
    "volume up": "volume up", "increase volume": "volume up", "increase the volume": "volume up",
    "turn up the volume": "volume up", "turn it up": "volume up", "louder": "volume up",
    "volume down": "volume down", "decrease volume": "volume down", "decrease the volume": "volume down",
    "turn down the volume": "volume down", "turn it down": "volume down", "quieter": "volume down",
    "mute": "mute", "unmute": "unmute",
}

_MEDIA = [
    (re.compile(r"^(?:pause|resume|unpause|continue|play/pause)(?: the)?(?: music| song| track| video| playback| media| it)?$"), "system media playpause"),
    (re.compile(r"^stop (?:the )?(?:music|song|track|video|playback|media)$"), "system media playpause"),
    (re.compile(r"^(?:next|skip|skip this|play next)(?: the| this)?(?: song| track| video)?$"), "system media next"),
    (re.compile(r"^(?:previous|go back|last|play previous|play the previous)(?: the)?(?: song| track| video)?$"), "system media previous"),
]
_VOICE_NAMES = r"(?:zira|hazel|heera|susan|david|george|mark|ravi)"

_RULES = [
    # voice switching: "change voice to heera", "switch to susan", "use hazel voice"
    (re.compile(r"^(?:change|switch|set|use)(?: your| the| my)? voice(?: to)? (\w+)$"), "voice {}"),
    (re.compile(rf"^(?:change|switch|set|use)(?: your| the)?(?: voice)?(?: to)? ({_VOICE_NAMES})(?: voice)?$"), "voice {}"),
    (re.compile(r"^(?:change|switch)(?: your)? voice$"), "voice list"),
    (re.compile(r"^(?:what|which) voices(?: do you have)?$"), "voice list"),
    (re.compile(r"^open (?!my |file )(?:the )?(?:app |application |website |site )?" + _BAD_TARGET + r"(.+)$"), "open {}"),
    (re.compile(r"^close (?:the )?(?:app |application |window )?" + _BAD_TARGET + r"(.+)$"), "close {}"),
    # volume with a number: "set volume to 40", "increase the volume by 20"
    (re.compile(r"^(?:set|change|put|make)(?: the| my)? volume (?:to|at) (\d{1,3})(?: ?%| percent)?$"), "system volume set {}"),
    (re.compile(r"^(?:increase|raise|turn up|up)(?: the)? volume(?: by (\d{1,3}))?(?: ?%| percent)?$"), "system volume up {}"),
    (re.compile(r"^(?:decrease|lower|reduce|turn down|down)(?: the)? volume(?: by (\d{1,3}))?(?: ?%| percent)?$"), "system volume down {}"),
    (re.compile(r"^play (?:me )?(?:the )?(?:song |music |video )?(.+?)(?: on youtube)?$"), "play {}"),
    (re.compile(r"^(?:google search|google) (.+)$"), "google search {}"),
    (re.compile(r"^search (?:for )?(.+?) on google$"), "google search {}"),
    (re.compile(r"^(?:youtube search|youtube) (.+)$"), "youtube search {}"),
    (re.compile(r"^search (?:for )?(.+?) on youtube$"), "youtube search {}"),
    (re.compile(r"^(?:generate|create|make|draw)(?: me)?(?: an?| some)?(?: image| picture| photo| drawing)(?: of)? (.+)$"),
     "generate image {}"),
]

_CHITCHAT = re.compile(
    r"^(?:hi+|hello+|hey+|yo|sup|thanks?(?: you)?|thx|ok(?:ay)?|cool|nice|great|wow|lol|"
    r"good (?:morning|afternoon|evening|night)|how are you|how'?s it going|what'?s up|"
    r"i love you|you are .{1,20}|who are you|what is your name|what'?s your name|tell me a joke|"
    r"i am (?:sad|bored|tired|happy|hungry)|i'?m (?:sad|bored|tired|happy|hungry)|how was your day|"
    r"i missed you|miss you)\b.{0,50}$"
)

_REALTIME = re.compile(
    r"\b(?:weather|temperature in|news|headlines?|latest|scores?|stock price|share price|price of|"
    r"trending|exchange rate|who won|breaking|right now|today'?s|tonight|tomorrow'?s)\b"
)
# words that might mean "do something" or "needs live data": only these queries need the LLM router
_TRIGGERS = re.compile(
    r"\b(?:open|close|launch|start|play|search|google|youtube|generate|image|picture|photo|draw|volume|mute|"
    r"unmute|remind|reminder|write|code|email|letter|essay|song|bye|exit|quit|who is|who's|who was|tell me about|"
    r"news|weather|score|price|latest|find|file|current|president|minister|ceo)\b"
)
_WEATHER = re.compile(r"\b(?:weather|forecast|umbrella|will it (?:rain|snow)|is it (?:raining|snowing|hot|cold|sunny)|"
                      r"how (?:hot|cold|warm) is it|temperature(?: in| outside| today| now)?)\b")
_DATE_TIME_Q =re.compile(r"\b(?:what'?s|what is|tell me) (?:the )?(?:time|date|day|month|year)\b")


def _norm(text):
    return re.sub(r"\s+", " ", text.lower().strip()).strip(" .?!,;")


def _route_part(part):
    p = _FILLER.sub("", part.strip()).strip(" .?!,;")
    if not p:
        return None
    if _EXIT.fullmatch(p):
        return "exit"
    if p in _VOLUME:
        return "system " + _VOLUME[p]
    for rx, task in _MEDIA:
        if rx.match(p):
            return task
    city = Weather.parse_city_command(p)
    if city:
        return "city " + city
    for rx, template in _RULES:
        m = rx.match(p)
        if m:
            return template.format((m.group(1) or "").strip() if m.groups() else "")
    return None


def quick_route(text):
    q = _norm(text)
    if not q:
        return None

    # commands, possibly several: "open chrome and close notepad". Every part must be understood,
    # otherwise return None and let the LLM handle it (e.g. "play rock and roll").
    if re.search(r"\b(?:remind(?:er|ers)?|timers?|alarms?|snooze|wake me(?: up)?|time (?:is )?left)\b", q)             and not re.match(r"(?:please |hey |lency |can you |could you )*(?:play|open|close|google|youtube|search) ", q):
        return ["reminder " + text.strip()]
    parts = [x for x in re.split(r"\s*(?:,|\band\b|\bthen\b)\s*", q) if x.strip()]
    # a part that is only a greeting ("good morning, open spotify") is skipped, not a reason to give up
    parts = [x for x in parts if _FILLER.sub("", x.strip()).strip(" .?!,;")]
    routed = [_route_part(x) for x in parts]
    if routed and all(routed):
        return routed

    if Calc.parse(text):                                   # exact maths / conversions never go to the LLM
        return ["calc " + text.strip()]
    if _WEATHER.search(q):
        return ["weather " + text.strip()]
    if _DATE_TIME_Q.search(q):
        return ["general " + text.strip()]
    if len(q.split()) <= 12 and _CHITCHAT.match(q):
        return ["general " + text.strip()]
    if _REALTIME.search(q):
        return ["realtime " + text.strip()]
    if not _TRIGGERS.search(q):
        # no command word, no live-data word: it's plain conversation, skip the LLM router entirely
        return ["general " + text.strip()]
    return None


if __name__ == "__main__":
    for t in ["Open chrome.", "open chrome and close notepad", "Volume up.", "hi lency", "play rock and roll",
              "What is the weather in Delhi?", "Bye lency.", "generate an image of a fox", "explain black holes",
              "what's the time"]:
        print(f"{t!r:40} -> {quick_route(t)}")
